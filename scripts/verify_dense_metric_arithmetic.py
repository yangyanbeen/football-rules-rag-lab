"""Reproduce retrieval metric arithmetic using synthetic IDs, without model or data access.

Recall@K remains the original plan's any-labelled-support-hit proportion over
answerable questions. all_gold_coverage@5 is a separate diagnostic. The function
under test is imported unchanged; stricter run-input validation belongs to the
real evaluation runner rather than this arithmetic-only regression.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import hashlib
from pathlib import Path

from retrieval_metrics import compute_metrics


ROOT = Path(__file__).resolve().parents[1]


def question(qid, gold, answerable=True):
    return {"question_id": qid, "expected_chunk_ids": gold, "answerable": answerable}


def prediction(qid, ids):
    return {"question_id": qid, "results": [
        {"chunk_id": chunk_id, "rank": rank}
        for rank, chunk_id in enumerate(ids, 1)
    ]}


def ranked_with_hit(qid, gold, rank, size=11):
    ids = [f"{qid}-N{i}" for i in range(1, size + 1)]
    ids[rank - 1] = gold
    return prediction(qid, ids)


def run_checks():
    checks = []

    def equal(name, actual, expected):
        passed = (math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
                  if type(expected) is float else actual == expected)
        checks.append({"name": name, "passed": bool(passed),
                       "actual": actual, "expected": expected})

    def rejects(name, questions, predictions):
        try:
            compute_metrics(questions, predictions)
        except ValueError as exc:
            checks.append({"name": name, "passed": True,
                           "expected": "ValueError", "actual": str(exc)})
        except Exception as exc:
            checks.append({"name": name, "passed": False,
                           "expected": "ValueError", "actual": type(exc).__name__})
        else:
            checks.append({"name": name, "passed": False,
                           "expected": "ValueError", "actual": "accepted"})

    # All IDs and labels below are invented; no on-disk evaluation input is read.
    questions = [question("A", ["A-G"]), question("B", ["B-G"]),
                 question("C", ["C-G"]), question("D", ["D-G"]),
                 question("M", ["M-G1", "M-G2"]), question("U", [], False)]
    predictions = [ranked_with_hit("A", "A-G", 5),
                   ranked_with_hit("B", "B-G", 6),
                   ranked_with_hit("C", "C-G", 10),
                   ranked_with_hit("D", "D-G", 11),
                   prediction("M", ["M-G1", "M-N2", "M-N3", "M-N4", "M-N5"]),
                   prediction("U", ["U-N1", "U-N2"])]
    result = compute_metrics(questions, predictions)
    rows = {row["question_id"]: row for row in result["per_question"]}
    equal("question_count", result["questions"], 6)
    equal("answerable_denominator_excludes_U", result["answerable_denominator"], 5)
    equal("unanswerable_count", result["unanswerable_excluded"], 1)
    equal("U_is_not_included", rows["U"]["retrieval_metric_included"], False)
    equal("U_has_no_numeric_recall", "Recall@5" in rows["U"], False)
    for qid, expected5, expected10, expected_mrr, first in (
        ("A", 1.0, 1.0, 1.0 / 5, 5),
        ("B", 0.0, 1.0, 1.0 / 6, 6),
        ("C", 0.0, 1.0, 1.0 / 10, 10),
        ("D", 0.0, 0.0, 0.0, None),
        ("M", 1.0, 1.0, 1.0, 1),
    ):
        equal(f"{qid}_Recall_at_5", rows[qid]["Recall@5"], expected5)
        equal(f"{qid}_Recall_at_10", rows[qid]["Recall@10"], expected10)
        equal(f"{qid}_MRR_at_10", rows[qid]["MRR@10"], expected_mrr)
        equal(f"{qid}_first_relevant_rank_within_10",
              rows[qid]["first_relevant_rank_within_10"], first)
    equal("M_any_hit_recall_is_one", rows["M"]["Recall@5"], 1.0)
    equal("M_separate_all_gold_coverage_is_half", rows["M"]["all_gold_coverage@5"], 0.5)
    equal("aggregate_Recall_at_5_is_2_over_5", result["metrics"]["Recall@5"], 2.0 / 5)
    equal("aggregate_Recall_at_10_is_4_over_5", result["metrics"]["Recall@10"], 4.0 / 5)
    equal("aggregate_MRR_at_10", result["metrics"]["MRR@10"],
          (1.0 / 5 + 1.0 / 6 + 1.0 / 10 + 0.0 + 1.0) / 5)
    equal("aggregate_separate_all_gold_coverage_at_5", result["metrics"]["all_gold_coverage@5"], 0.3)
    equal("nDCG_not_fabricated_without_graded_labels", result["nDCG@10"], None)

    empty = compute_metrics([question("E", ["E-G"])], [prediction("E", [])])
    for metric in ("Recall@5", "Recall@10", "MRR@10", "all_gold_coverage@5"):
        equal("empty_prediction_" + metric, empty["metrics"][metric], 0.0)
    multi = compute_metrics([question("M", ["M-G1", "M-G2"])],
                            [prediction("M", ["M-G1", "N2", "N3", "N4", "M-G2"])])
    equal("two_gold_hits_do_not_double_any_hit_recall", multi["metrics"]["Recall@5"], 1.0)
    equal("two_gold_hits_complete_separate_coverage", multi["metrics"]["all_gold_coverage@5"], 1.0)
    equal("second_gold_hit_does_not_inflate_MRR", multi["metrics"]["MRR@10"], 1.0)
    reverse = compute_metrics(list(reversed(questions)), list(reversed(predictions)))
    equal("input_order_does_not_change_aggregates", reverse["metrics"], result["metrics"])

    rejects("missing_prediction_rejected", questions, predictions[:-1])
    rejects("duplicate_prediction_rejected", questions, predictions + [deepcopy(predictions[0])])
    rejects("unexpected_prediction_rejected", questions, predictions + [prediction("X", [])])
    rejects("duplicate_question_rejected", questions + [deepcopy(questions[0])], predictions)
    bad = deepcopy(predictions)
    bad[0]["results"][1]["chunk_id"] = bad[0]["results"][0]["chunk_id"]
    rejects("duplicate_chunk_rejected", questions, bad)
    for name, ranks in (("rank_starts_at_zero", [0, 1]),
                        ("rank_gap", [1, 3]), ("rank_duplicate", [1, 1]),
                        ("rank_reversed", [2, 1])):
        rejects(name + "_rejected", [question("A", ["A-G"])],
                [{"question_id": "A", "results": [
                    {"chunk_id": f"A-{i}", "rank": rank}
                    for i, rank in enumerate(ranks)]}])
    rejects("answerable_without_gold_rejected", [question("A", [])], [prediction("A", [])])
    rejects("unanswerable_with_gold_rejected", [question("U", ["U-G"], False)],
            [prediction("U", [])])
    rejects("non_boolean_answerability_rejected", [question("A", ["A-G"], 1)],
            [prediction("A", [])])
    rejects("all_unanswerable_denominator_rejected", [question("U", [], False)],
            [prediction("U", [])])
    rejects("empty_dataset_denominator_rejected", [], [])

    # These observations describe current arithmetic-helper limits. They are not
    # passing bad-data gates and must be rejected by the real runner's schema.
    observations = []
    for name, sample_questions, sample_predictions in (
        ("boolean_rank_compares_equal_to_integer_one",
         [question("T", ["T-G"])],
         [{"question_id": "T", "results": [{"chunk_id": "T-G", "rank": True}]}]),
        ("string_gold_container_is_interpreted_as_characters",
         [question("T", "G")], [prediction("T", ["G"])]),
        ("non_string_identifiers_are_accepted",
         [question(7, [8])], [prediction(7, [8])]),
    ):
        try:
            compute_metrics(sample_questions, sample_predictions)
        except (ValueError, TypeError, KeyError):
            accepted = False
        else:
            accepted = True
        observations.append({"name": name, "arithmetic_helper_accepts": accepted,
                             "required_outer_validation": "Reject invalid schema before metric arithmetic"})
    return {"status": "PASS" if all(item["passed"] for item in checks) else "FAIL",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "kind": "synthetic_metric_arithmetic_and_rejection_regression",
            "model_requests": 0, "actual_evaluation_questions_read": False,
            "actual_labels_or_document_text_read": False,
            "definitions": result["definitions"],
            "checks_passed": sum(item["passed"] for item in checks),
            "checks_total": len(checks), "checks": checks,
            "schema_observations": observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True,
                        help="New JSON report under reports/ or .tmp/; existing files are refused")
    args = parser.parse_args()
    report_path = Path(args.report)
    report_path = (ROOT / report_path).resolve() if not report_path.is_absolute() else report_path.resolve()
    if report_path.suffix.lower() != ".json" or not any(
            report_path.is_relative_to(ROOT / parent) for parent in ("reports", ".tmp")):
        parser.error("Report must be a new .json file inside this repository's reports/ or .tmp/")
    if report_path.exists():
        parser.error("Refusing to overwrite an existing report")
    result = run_checks()
    result['source_sha256'] = {name: hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest()
                              for name in ('verify_dense_metric_arithmetic.py','retrieval_metrics.py')}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": result["status"], "checks_passed": result["checks_passed"],
                      "checks_total": result["checks_total"],
                      "report": report_path.relative_to(ROOT).as_posix()}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
