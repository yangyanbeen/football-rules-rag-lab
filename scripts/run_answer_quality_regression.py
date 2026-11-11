"""Run explicitly identified development regressions, not a locked benchmark."""

import argparse
import json
from pathlib import Path

from kotaemon_runtime_env import configure_local_runtime

configure_local_runtime()

from football_evidence import ROOT, get_engine, paragraphs, validate_selection


def structural_checks(engine, result):
    errors = []
    for cite in result["citations"]:
        row = engine.by_id.get(cite["chunk_id"])
        if row is None:
            errors.append("unknown cited chunk")
            continue
        for key in ("source_url", "source_lines", "source_revision_id", "needs_rule_review"):
            if cite[key] != row["metadata"][key]:
                errors.append(f"incorrect citation field: {key}")
        known = {p["id"]: p["text"] for p in paragraphs(row)}
        if any(known.get(pid) != quote for pid, quote in zip(cite["paragraph_ids"], cite["quotes"])):
            errors.append("quote differs from complete source paragraph")
        if any(pid not in result.get("offered_paragraphs", {}) for pid in cite["paragraph_ids"]):
            errors.append("citation was not offered to model")
    if result["status"] == "answered" and not result["citations"]:
        errors.append("answered without evidence")
    if result["status"] == "refused" and result["citations"]:
        errors.append("refusal contains asserted citations")
    if result.get("input_token_count_cl100k", 0) > engine.config["input_token_budget"]:
        errors.append("input budget exceeded")
    if result.get("error"):
        errors.append(result["error"])
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="data/quality_regression/development_cases.jsonl")
    parser.add_argument("--output", default="reports/answer-quality-fix-2026-11-11.json")
    parser.add_argument("--original-three", action="store_true")
    args = parser.parse_args()
    engine = get_engine()
    if args.original_three:
        source = json.loads((ROOT / "reports/task2-ui-evidence-2026-11-11.json").read_text(encoding="utf-8"))
        labelled = {case["id"]: case for case in [json.loads(s) for s in (ROOT / args.cases).read_text(encoding="utf-8").splitlines() if s.strip()]}
        cases = [labelled[q["question_id"]] for q in source["qa"]]
    else:
        cases = [json.loads(s) for s in (ROOT / args.cases).read_text(encoding="utf-8").splitlines() if s.strip()]
    results = []
    for case in cases:
        result = engine.answer(case["question"])
        errors = structural_checks(engine, result)
        citations = {c["chunk_id"] for c in result["citations"]}
        if result["status"] != case["expected_status"]:
            errors.append("unexpected answer/refusal")
        for group in case.get("required_chunk_groups", []):
            if not citations.intersection(group):
                errors.append("missing supporting unit group: " + ",".join(group))
        for chunk_id in case.get("forbidden_chunks", []):
            if chunk_id in citations:
                errors.append("unsupported citation: " + chunk_id)
        result["case"] = case
        result["automated_errors"] = errors
        result["automated_passed"] = not errors
        results.append(result)
        print(case["id"], result["status"], sorted(citations), "PASS" if not errors else errors, flush=True)
        # Save each complete result so an interrupted run retains real evidence.
        output = ROOT / args.output
        output.write_text(json.dumps({"scope": "development regressions, not a locked test set or expert judgement", "results": results, "passed": sum(r["automated_passed"] for r in results), "total": len(cases)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if all(r["automated_passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
