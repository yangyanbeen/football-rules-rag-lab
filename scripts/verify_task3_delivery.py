"""Check task 3 reproducibility and reject corrupted derived-data fixtures.

All fault injection takes place under .tmp/task3-verification. The original
corpus, account database, application indexes and model configuration are read
only. This is dataset acceptance, not retrieval or answer-quality evaluation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import build_rag_dataset as builder

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / ".tmp/task3-verification"
NAMES = ("rag_chunks_zh.jsonl", "rag_chunks_parallel.jsonl")


def run(script, *arguments):
    command = [sys.executable, str(ROOT / "scripts" / script), *map(str, arguments)]
    result = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True)
    return {"command": [".venv/Scripts/python.exe", "scripts/" + script, *map(str, arguments)], "exit_code": result.returncode, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (ROOT / 'reports/task3_delivery_verification.json').exists():
        raise ValueError('Refusing to overwrite historical reports; use verify_task3_isolated.py --report <new JSON>')
    assert LAB.resolve().is_relative_to((ROOT / ".tmp").resolve())
    LAB.mkdir(parents=True, exist_ok=True)
    checks, executions = [], []
    def check(name, passed, details=None):
        checks.append({"check": name, "passed": bool(passed), "details": details})

    canonical_paths = [ROOT / "data/processed" / name for name in NAMES] + [ROOT / "data/manifests/rag_dataset_manifest.json"]
    before = {path.relative_to(ROOT).as_posix(): hash_file(path) for path in canonical_paths}
    result = run("validate_rag_dataset.py")
    executions.append(result)
    check("canonical_dataset_independent_validation", result["exit_code"] == 0)
    result = run("build_rag_dataset.py")
    executions.append(result)
    check("canonical_rebuild_is_byte_identical_including_manifest", result["exit_code"] == 0 and all(hash_file(ROOT / path) == checksum for path, checksum in before.items()), before)

    fresh = LAB / "fresh"
    result = run("build_rag_dataset.py", "--output-dir", fresh.relative_to(ROOT).as_posix())
    executions.append(result)
    equal = all((fresh / name).is_file() and (fresh / name).read_bytes() == (ROOT / "data/processed" / name).read_bytes() for name in NAMES)
    check("fresh_directory_rebuild_preserves_both_JSONL_bytes", result["exit_code"] == 0 and equal)
    result = run("validate_rag_dataset.py", "--data-dir", fresh.relative_to(ROOT).as_posix(), "--report", (fresh / "validation.json").relative_to(ROOT).as_posix())
    executions.append(result)
    check("fresh_directory_passes_independent_validation", result["exit_code"] == 0)

    read_rows = builder.read_rows
    baseline_zh, baseline_parallel, _ = builder.prepare()
    try:
        def reversed_parallel(path):
            data = read_rows(path)
            return list(reversed(data)) if path.name == "parallel_zh_en.jsonl" else data
        builder.read_rows = reversed_parallel
        reversed_zh, reversed_pairs, _ = builder.prepare()
        check("in_memory_reversed_English_input_is_joined_by_ID_not_zip_order", baseline_zh == reversed_zh and baseline_parallel == reversed_pairs)
    finally:
        builder.read_rows = read_rows

    result = run("build_rag_dataset.py", "--output-dir", "data/processed/wikipedia_zh_2026-11-10", "--overwrite")
    executions.append(result)
    check("frozen_input_directory_cannot_be_used_as_output_even_with_overwrite", result["exit_code"] != 0 and all(hash_file(ROOT / path) == checksum for path, checksum in before.items()))

    zh = [json.loads(line) for line in (ROOT / "data/processed" / NAMES[0]).read_text(encoding="utf-8").splitlines()]
    parallel = [json.loads(line) for line in (ROOT / "data/processed" / NAMES[1]).read_text(encoding="utf-8").splitlines()]
    manifest = json.loads(canonical_paths[-1].read_text(encoding="utf-8"))
    cases = []
    mutations = (
        "duplicate_id", "missing_record", "changed_source_id", "forged_source_URL",
        "invalid_source_lines", "invented_parent", "overstated_revision_verification",
        "overstated_expert_review", "removed_review_notes", "rewritten_Chinese",
        "rewritten_English", "truncated_table", "table_mislabeled_as_paragraph",
        "boolean_source_line_numbers", "missing_required_field", "forged_provenance",
    )
    for name in mutations:
        folder = LAB / name
        assert folder.resolve().is_relative_to(LAB.resolve())
        folder.mkdir(parents=True, exist_ok=True)
        left, right = copy.deepcopy(zh), copy.deepcopy(parallel)
        if name == "duplicate_id":
            for items in (left, right):
                items[1]["id"] = items[0]["id"]
                items[1]["chunk_id"] = items[0]["chunk_id"]
        elif name == "missing_record":
            left.pop()
            right.pop()
        elif name == "changed_source_id":
            left[0]["source_id"] = right[0]["source_id"] = "wiki-16"
        elif name == "forged_source_URL":
            left[0]["source_url"] = right[0]["source_url"] = "https://invalid.example/unsupported"
        elif name == "invalid_source_lines":
            left[0]["source_lines"] = right[0]["source_lines"] = [-1, 0]
        elif name == "invented_parent":
            left[0]["parent_id"] = right[0]["parent_id"] = "invented-root"
        elif name == "overstated_revision_verification":
            left[0]["source_revision_verified"] = right[0]["source_revision_verified"] = True
            left[0]["source_revision_timestamp"] = right[0]["source_revision_timestamp"] = "2026-11-10T00:00:00Z"
        elif name == "overstated_expert_review":
            left[0]["expert_reviewed"] = right[0]["expert_reviewed"] = True
        elif name == "removed_review_notes":
            for items in (left, right):
                next(row for row in items if row["needs_rule_review"])["review_notes"] = []
        elif name == "rewritten_Chinese":
            left[0]["content_zh"] = right[0]["content_zh"] = "Changed content without authorization."
        elif name == "rewritten_English":
            right[0]["content_en"] += " Unsupported extra sentence."
        elif name == "truncated_table":
            for items in (left, right):
                row = next(row for row in items if row["id"] == "L14-04")
                row["content_zh"] = "\n".join(line for line in row["content_zh"].split("\n") if "守门员将球扑出底线" not in line)
        elif name == "table_mislabeled_as_paragraph":
            for items in (left, right):
                next(row for row in items if row["id"] == "L14-04")["chunk_type"] = "paragraph"
        elif name == "boolean_source_line_numbers":
            left[0]["source_lines"] = right[0]["source_lines"] = [True, True]
        elif name == "missing_required_field":
            del left[0]["source_url"]
            del right[0]["source_url"]
        elif name == "forged_provenance":
            left[0]["provenance"]["chinese_input"] = right[0]["provenance"]["chinese_input"] = "invented.jsonl"

        # Re-sign altered rows and files so semantic/source validation, rather
        # than an obvious stale checksum alone, must reject the corruption.
        contents = []
        for filename, items in zip(NAMES, (left, right)):
            for row in items:
                row["content_zh_sha256"] = builder.sha(row["content_zh"].encode("utf-8"))
                if "content_en" in row:
                    row["content_en_sha256"] = builder.sha(row["content_en"].encode("utf-8"))
                row["record_sha256"] = builder.row_hash(row)
            data = b"".join(builder.canonical(row) + b"\n" for row in items)
            (folder / filename).write_bytes(data)
            contents.append(data)
        altered = copy.deepcopy(manifest)
        altered["outputs"] = [{"path": (folder / filename).relative_to(ROOT).as_posix(), "size_bytes": len(data), "sha256": builder.sha(data), "records": len(items)} for filename, data, items in zip(NAMES, contents, (left, right))]
        altered["dataset_content_id"] = builder.sha(b"\0".join(contents))
        (folder / "rag_dataset_manifest.json").write_text(json.dumps(altered, ensure_ascii=False, indent=2), encoding="utf-8")
        outcome_path = folder / "validation.json"
        outcome = run("validate_rag_dataset.py", "--data-dir", folder.relative_to(ROOT).as_posix(), "--report", outcome_path.relative_to(ROOT).as_posix())
        detail = json.loads(outcome_path.read_text(encoding="utf-8"))
        rejected = outcome["exit_code"] == 1 and detail["status"] == "FAIL"
        cases.append({"case": name, "passed": rejected, "expected_exit_code": 1, "actual_exit_code": outcome["exit_code"], "failed_validation_checks": [item for item in detail["checks"] if not item["passed"]], "command": outcome["command"]})
        print(f"Negative case: {name}: {'REJECTED' if rejected else 'UNEXPECTED PASS'}", flush=True)
    check("all_16_corrupt_derived_datasets_rejected_after_rehashing", len(cases) == 16 and all(case["passed"] for case in cases))
    result = run("validate_rag_dataset.py")
    executions.append(result)
    check("canonical_data_and_frozen_inputs_still_pass_after_fault_injection", result["exit_code"] == 0 and all(hash_file(ROOT / path) == checksum for path, checksum in before.items()))
    report = {"task": 3, "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"), "criteria": "Original task 3 unchanged", "checks": checks, "positive_checks_passed": sum(item["passed"] for item in checks), "positive_checks_total": len(checks), "negative_cases_rejected": sum(case["passed"] for case in cases), "negative_cases_total": len(cases), "negative_cases": cases, "executions": executions, "status": "PASS" if all(item["passed"] for item in checks) else "FAIL"}
    path = ROOT / "reports/task3_delivery_verification.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Task 3 delivery: {report['status']}; checks {report['positive_checks_passed']}/{len(checks)}; corrupt cases rejected {report['negative_cases_rejected']}/{len(cases)}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
