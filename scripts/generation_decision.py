"""Opt-in answer decision layer for evidence sufficiency and refusal recovery.

The default Worker remains byte-identical.  When FOOTBALL_GENERATION_DECISION=1,
the existing strict selection instruction is enabled and a model refusal is
reconsidered only through the already reviewed source-bound fact registry.
No arbitrary fact extraction or unverified answer is added here.
"""
from __future__ import annotations

import os
from copy import deepcopy

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
