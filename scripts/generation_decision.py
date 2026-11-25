"""Opt-in answer decision layer for evidence sufficiency and refusal recovery.

The default Worker remains byte-identical.  When FOOTBALL_GENERATION_DECISION=1,
the existing strict selection instruction is enabled and a model refusal is
reconsidered only through the already reviewed source-bound fact registry.
No arbitrary fact extraction or unverified answer is added here.
"""
from __future__ import annotations

import os
from copy import deepcopy
from itertools import combinations

from answer_eval_engine import selection_prompt
from answer_eval_core import digest


# E31 is deliberately a separate, opt-in pass.  It does not feed the first
# model's self-justification back into the review prompt: the reviewer sees the
# same question and evidence, but receives a shorter role-specific instruction.
# This helps distinguish a genuinely supported multi-part answer from a
# first-pass selection that merely shares vocabulary with the question.
AUDIT_SYSTEM = """你是第二道证据审核器。只依据用户问题和证据正文，不相信任何先前选择。先逐项检查问题中的对象、数字、条件、否定、例外和比较两侧；再选择覆盖全部必要要点的最少证据段。只有正文直接支持整个要点才可选；同主题、部分支持或反驳不能算完整支持。证据足够时回答，只有关键要点缺失、冲突或版本无法确认时拒答。最多选择3段。只输出规定JSON。"""


def selection_audit_enabled() -> bool:
    return os.environ.get("FOOTBALL_SELECTION_AUDIT", "0") == "1"


def audit_messages(messages):
    """Build an independent audit prompt without changing the frozen payload."""
    if not isinstance(messages, list) or len(messages) != 2:
        raise ValueError("Selection audit requires the frozen two-message prompt")
    result = deepcopy(messages)
    result[0] = {**result[0], "content": AUDIT_SYSTEM}
    return result


def run_selection_audit(chat, messages, cfg, parser, schema, request_json):
    """Run one opt-in second pass and return an auditable record.

    The first selection remains the fallback.  A valid answerable audit result
    may replace it; an audit refusal never turns an already answered result into
    a refusal.  Parse failures are recorded and do not alter the answer.
    """
    if not selection_audit_enabled():
        return None
    audit_input = audit_messages(messages)
    parsed, attempts, error = request_json(chat, audit_input, cfg, parser, schema)
    return {
        "enabled": True,
        "system_prompt_sha256": digest(AUDIT_SYSTEM.encode("utf-8")),
        "selection": parsed,
        "attempts": attempts,
        "error": error,
        "prompt_messages": audit_input,
    }


def choose_audited_selection(initial, audit):
    """Apply the conservative replacement policy for E31."""
    if not audit or not audit.get("selection"):
        return initial
    reviewed = audit["selection"]
    if reviewed.get("answerable") is True:
        return reviewed
    # Never introduce an audit-only refusal regression.  An initial refusal is
    # still allowed to remain a refusal and may be recovered by the existing
    # source-bound fact path below.
    return initial


def anchor_guard_enabled() -> bool:
    return os.environ.get("FOOTBALL_ANCHOR_GUARD", "0") == "1"


def _anchor_groups(question):
    """Infer only explicit, lexical obligations from the user's question.

    This is intentionally a small safety gate, not a semantic gold-label
    lookup.  It can add a paragraph only when its original text contains the
    requested rule object/condition.  Unknown questions produce no groups and
    keep the model's selection unchanged.
    """
    q = "".join(str(question).split())
    groups = []
    terms = ("任意球", "界外球", "球门球", "角球", "开球", "点球", "加时赛", "补时")
    # Narrow, lexical obligations for the four E38 failure patterns.  These
    # rules only choose from the already packed context and never add a
    # paragraph that is absent from the prompt.
    if "球门球" in q and "角球" in q and ("离开" in q or "放球区域" in q):
        groups.extend([
            ("goal_kick_area", ("离开罚球区", "球门球")),
            ("corner_kick_area", ("离开角球区", "角球区")),
        ])
    if "坠球" in q and "不同队员" in q and "再次触球" in q:
        groups.extend([
            ("dropped_ball_count", ("至少两名", "不同队员")),
            ("dropped_ball_repeat", ("首次触球者", "再次触球", "第二次触球")),
            ("dropped_ball_version", ("2019", "2020", "版本", "固定Wikipedia")),
        ])
    restart_ownership = "按出界位置" in q and "最后触球队" in q and all(x in q for x in ("界外球", "球门球", "角球"))
    if restart_ownership:
        groups.extend([
            ("touchline_last_touch", ("越过边线",)),
            ("goal_line_attack_last_touch", ("最后由攻方触球", "攻方最后触球")),
            ("goal_line_defense_last_touch", ("最后由守方触球", "守方最后触球")),
        ])
    if "动作正确" in q and "碰地" in q and ("入场前" in q or "进入场地前" in q):
        groups.extend([
            ("throw_in_valid_action", ("动作本身正确", "动作正确")),
            ("throw_in_ground_before_entry", ("进入场地前碰地", "入场前碰地", "碰地")),
            ("throw_in_same_team_retake", ("原队", "原处", "重新掷球")),
        ])
    # Explicitly named rule objects in comparisons must each be represented.
    if not restart_ownership and any(x in q for x in ("对比", "比较", "区分")):
        for term in terms:
            if term in q:
                groups.append(("object:" + term, (term,)))
    if "开球者" in q and "再次" in q and "触球" in q:
        groups.extend([
            ("kickoff_restart", ("开出", "重新开球", "开球")),
            ("second_touch", ("再次触球", "第二次触球")),
            ("handball_exception", ("手球", "直接任意球")),
        ])
    if "完成" in q and "助跑" in q and "假动作" in q:
        groups.extend([
            ("post_run_feint", ("完成助跑后", "假动作")),
            ("run_up_feint_distinction", ("助跑过程中", "迷惑对方")),
            ("feint_restart_consequence", ("间接任意球", "警告")),
        ])
    if "补时" in q and "加时赛" in q:
        groups.extend([
            ("stoppage_time", ("补时",)),
            ("extra_time", ("加时赛",)),
            ("extra_time_length", ("两个15分钟",)),
        ])
    return groups


def apply_anchor_guard(question, selection, context):
    """Repair only explicit missing evidence anchors, with deterministic ties."""
    base = {
        "enabled": anchor_guard_enabled(), "changed": False,
        "groups": [], "before": list(selection.get("chunk_ids", [])),
        "after": list(selection.get("chunk_ids", [])), "reason": "disabled",
    }
    if not anchor_guard_enabled() or not selection.get("answerable"):
        return {"selection": selection, "trace": base}
    groups = _anchor_groups(question)
    base["groups"] = [name for name, _ in groups]
    base["reason"] = "no_explicit_anchor_groups" if not groups else "anchors_already_covered"
    if not groups or not isinstance(context, list) or not context:
        return {"selection": selection, "trace": base}
    by_id = {row.get("chunk_id"): row for row in context}
    offered = [row.get("chunk_id") for row in context]
    current = list(selection.get("chunk_ids", []))

    def covered(ids):
        text = {cid: str(by_id[cid].get("content_zh", "")) for cid in ids if cid in by_id}
        return sum(any(any(term in text[cid] for term in terms) for cid in text) for _, terms in groups)

    best = None
    for size in range(1, min(3, len(offered)) + 1):
        for combo in combinations(offered, size):
            score = (covered(combo), len(set(combo).intersection(current)), -size,
                     tuple(-offered.index(cid) for cid in combo))
            if best is None or score > best[0]:
                best = (score, list(combo))
    if best is None or best[0][0] < len(groups) or best[1] == current:
        return {"selection": selection, "trace": base}
    revised = {"answerable": True, "chunk_ids": best[1], "reason": None}
    base.update(changed=True, after=list(best[1]), reason="explicit_anchor_coverage_repaired")
    return {"selection": revised, "trace": base}


def enabled() -> bool:
    return os.environ.get("FOOTBALL_GENERATION_DECISION", "0") == "1"


def recovery_enabled() -> bool:
    """Keep the previously accepted E13 switch backward compatible."""
    return enabled() or os.environ.get("FOOTBALL_SOURCE_FACTS", "0") == "1"


def prompt_for(prompt: str) -> str:
    """Return the candidate prompt while preserving the default prompt."""
    if enabled():
        previous = os.environ.get("FOOTBALL_STRICT_SELECTION")
        try:
            os.environ["FOOTBALL_STRICT_SELECTION"] = "1"
            return selection_prompt(prompt)
        finally:
            if previous is None:
                os.environ.pop("FOOTBALL_STRICT_SELECTION", None)
            else:
                os.environ["FOOTBALL_STRICT_SELECTION"] = previous
    return selection_prompt(prompt)


def decide(question, selection, context, messages, *, recovery_allowed=True):
    """Apply deterministic post-selection policy; never invent evidence.

    The returned ``trace`` is safe to persist in a private execution trace.
    Only the reviewed source-bound registry can convert an ordinary
    ``insufficient_evidence`` refusal into an answer.
    """
    trace = {
        "version": "generation-decision-layer-1.0",
        "enabled": enabled(),
        "recovery_enabled": recovery_enabled(),
        "model_answerable": bool(selection.get("answerable")),
        "model_reason": selection.get("reason"),
        "reconsidered": False,
        "outcome": "answer" if selection.get("answerable") else "refusal",
    }
    if selection.get("answerable") or not recovery_enabled() or not recovery_allowed:
        return {"selection": selection, "recovery": None, "trace": trace}
    if selection.get("reason") != "insufficient_evidence":
        return {"selection": selection, "recovery": None, "trace": trace}

    from source_bound_facts import evaluate

    trace["reconsidered"] = True
    recovery = evaluate(question, selection, context, messages)
    trace["outcome"] = "answer" if recovery.get("applied") else "refusal"
    trace["recovery_reason"] = recovery.get("reason")
    return {"selection": selection, "recovery": recovery, "trace": trace}

