"""Opt-in answer decision layer for evidence sufficiency and refusal recovery.

The default Worker remains byte-identical.  When FOOTBALL_GENERATION_DECISION=1,
the existing strict selection instruction is enabled and a model refusal is
reconsidered only through the already reviewed source-bound fact registry.
No arbitrary fact extraction or unverified answer is added here.
"""
from __future__ import annotations

import os

from answer_eval_engine import selection_prompt


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
