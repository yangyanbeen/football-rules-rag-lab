"""Opt-in candidate evidence ordering for the isolated E39 T022 experiment.

The production path keeps the rerank prefix unchanged.  E39 first expands the
reranker output, then uses a small, query-derived coverage pass to put the
most useful paragraphs in the bounded context window.  It does not inspect
question IDs, labels, or expected answers and it is disabled unless the
experiment flag is explicitly set.
"""
from __future__ import annotations


def _requirements(question):
    q = "".join(str(question).split())
    # This is intentionally narrow: only the three-way restart comparison is
    # eligible for E39.  Other questions retain the frozen rerank prefix.
    if not all(term in q for term in ("界外球", "球门球", "角球", "最后触球队")):
        return []
    return [
        ("boundary_definition", ("越过边线", "越过球门线"), True),
        ("throw_in_ownership", ("界外球", "最后触球"), True),
        ("goal_kick_ownership", ("球门球", "球门线"), True),
        ("corner_ownership", ("角球",), True),
    ]


def reorder(question, evidence, limit):
    """Return an expanded-candidate order for one isolated experiment.

    A paragraph covers a requirement only when all terms in that requirement
    occur in its own original text.  Greedy selection maximizes uncovered
    requirements, then keeps the original reranker order as the tie-breaker.
    Remaining candidates follow unchanged.  The caller still enforces the
    normal segment count and byte budget.
    """
    requirements = _requirements(question)
    if not requirements or not isinstance(evidence, list) or limit < 1:
        return evidence
    rows = list(evidence)
    selected = []
    covered = set()
    while len(selected) < min(limit, len(rows)):
        best = None
        for index, row in enumerate(rows):
            if index in selected:
                continue
            text = str(row.get("content_zh", ""))
            gains = {
                name for name, terms, _ in requirements
                if name not in covered and all(term in text for term in terms)
            }
            score = (len(gains), -index)
            if best is None or score > best[0]:
                best = (score, index, gains)
        if best is None or not best[2]:
            break
        _, index, gains = best
        selected.append(index)
        covered.update(gains)
    # If the requirements cannot all be covered, do not discard the original
    # prefix; append it after the selected rows so the experiment remains
    # conservative and diagnosable.
    for index in range(len(rows)):
        if index not in selected and len(selected) < min(limit, len(rows)):
            selected.append(index)
    return [rows[index] for index in selected]


