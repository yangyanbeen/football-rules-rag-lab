"""Independently validate task 3's derived records against frozen original input.

This module deliberately does not import the builder's transformation or type
classifier. Recomputing a derived record hash cannot bypass source comparisons.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data/processed/wikipedia_zh_2026-11-10"
SOURCES = ROOT / "data/processed/wikipedia_2026-11-10/sources.json"
BASELINE = ROOT / "data/manifests/task1_task2_baseline_lock.json"
COMMON_FIELDS = {
    "schema_version", "dataset_version", "id", "chunk_id", "parent_id", "chunk_type", "title_zh", "content_zh",
    "source_title", "source_language", "source_revision_timestamp", "source_revision_verified",
    "source_acquisition_method", "source_acquired_date", "source_page_raw_sha256", "source_page_clean_sha256",
    "source_raw_files", "translation_status", "content_zh_sha256", "provenance", "record_sha256",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def rows(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if any(not line.strip() for line in lines):
        raise ValueError(f"Blank JSONL record: {path.name}")
    result = [json.loads(line) for line in lines]
    if not all(isinstance(item, dict) for item in result):
        raise ValueError(f"JSONL rows must be objects: {path.name}")
    return result


def expected_type(text: str) -> str:
    lines = text.splitlines()
    for position, line in enumerate(lines):
        stripped = line.strip()
        if position == 0 or "|" not in stripped:
            continue
        parts = stripped.strip("|").split("|")
        if len(parts) < 2 or len(lines[position - 1].strip().strip("|").split("|")) != len(parts):
            continue
        if all(re.fullmatch(r"\s*:?-{3,}:?\s*", part) is not None for part in parts):
            return "table"
    if "|" in text or "```" in text or "~~~" in text or re.search(r"<\/?[A-Za-z][^>]*>", text):
        return "unknown"
    return "paragraph" if text.strip() else "unknown"


def checked_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Validation paths must stay inside the project")
    return path


def inspect_dataset(data_dir: Path) -> dict:
    checks = []
    def check(name, errors):
        checks.append({"check": name, "passed": not errors, "errors": errors})

    lock = load(BASELINE)
    fixed_errors = []
    for item in lock["files"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha(path.read_bytes()) != item["sha256"]:
            fixed_errors.append(item["path"])
    check("original_technical_task_and_Corpus_B0_files_unchanged", fixed_errors)
    prefix_errors = []
    for item in lock["append_only_files"]:
        content = (ROOT / item["path"]).read_bytes()[:item["original_size_bytes"]]
        if sha(content) != item["original_prefix_sha256"]:
            prefix_errors.append(item["path"])
    check("existing_report_prefixes_preserved", prefix_errors)

    original_zh = rows(CORPUS / "chunks_zh.jsonl")
    original_parallel = rows(CORPUS / "parallel_zh_en.jsonl")
    original_ids = [r["id"] for r in original_zh]
    original_by_id = {r["id"]: r for r in original_zh}
    parallel_by_id = {r["id"]: r for r in original_parallel}
    sources = load(SOURCES)
    source_by_id = {r["source_id"]: r for r in sources}
    check("frozen_inputs_have_99_unique_aligned_IDs_and_18_sources", [] if len(original_zh) == len(original_parallel) == len(original_by_id) == len(parallel_by_id) == 99 and set(original_by_id) == set(parallel_by_id) and len(sources) == len(source_by_id) == 18 else ["Original input count/ID mismatch"])

    paths = [data_dir / "rag_chunks_zh.jsonl", data_dir / "rag_chunks_parallel.jsonl"]
    output_rows = [rows(path) for path in paths]
    zh, parallel = output_rows
    id_errors = []
    for path, items in zip(paths, output_rows):
        ids = [item.get("id") for item in items]
        if len(ids) != 99 or len(set(ids)) != 99 or ids != original_ids:
            id_errors.append(f"{path.name}: count, uniqueness or deterministic input order changed")
    check("both_outputs_preserve_all_99_original_IDs_in_order", id_errors)

    errors = {key: [] for key in ("required_fields_and_types", "stable_chunk_and_source_IDs", "Chinese_and_English_content_match_input_by_ID", "all_original_metadata_preserved", "source_URL_lines_and_version", "license_attribution_and_acquisition", "translation_review_status_and_notes", "hashes_match_actual_text_and_records", "parent_IDs_and_structure_types", "provenance_paths")}
    for file_index, items in enumerate(output_rows):
        for item in items:
            identifier = item.get("id")
            label = f"{paths[file_index].name}:{identifier}"
            def issue(category, message):
                errors[category].append(label + ": " + message)
            if identifier not in original_by_id:
                issue("stable_chunk_and_source_IDs", "unknown original ID")
                continue
            original = original_by_id[identifier]
            paired = parallel_by_id[identifier]
            meta = original["metadata"]
            source = source_by_id[meta["source_id"]]
            required = COMMON_FIELDS | set(meta)
            if file_index:
                required |= {"content_en", "content_en_sha256"}
            if set(item) != required:
                issue("required_fields_and_types", f"missing={sorted(required-set(item))}, extra={sorted(set(item)-required)}")
            nonempty_strings = required - {"parent_id", "source_revision_timestamp", "source_revision_verified", "official_translation", "expert_reviewed", "needs_rule_review", "law_number", "section_path", "source_lines", "review_notes", "source_raw_files", "provenance"}
            if any(not isinstance(item.get(key), str) or not item[key].strip() for key in nonempty_strings):
                issue("required_fields_and_types", "required nonempty string is missing or has wrong type")
            for key in ("source_revision_verified", "official_translation", "expert_reviewed", "needs_rule_review"):
                if type(item.get(key)) is not bool:
                    issue("required_fields_and_types", f"{key} must be boolean")
            if type(item.get("law_number")) is not int or not 1 <= item["law_number"] <= 17:
                issue("required_fields_and_types", "law_number must be integer 1..17")
            for key, allow_empty in (("section_path", False), ("review_notes", True), ("source_raw_files", False)):
                values = item.get(key)
                if not isinstance(values, list) or (not allow_empty and not values) or (isinstance(values, list) and any(not isinstance(value, str) or not value.strip() for value in values)):
                    issue("required_fields_and_types", f"invalid {key} array")
            if item.get("schema_version") != "1.0.0" or item.get("dataset_version") != "corpus-b0-rag-adapter-1.0.0":
                issue("required_fields_and_types", "unexpected schema/data version")
            if item.get("chunk_id") != identifier or item.get("source_id") != meta["source_id"]:
                issue("stable_chunk_and_source_IDs", "changed chunk_id or source_id")
            if item.get("content_zh") != paired["text_zh"] or item.get("title_zh") != paired["title_zh"] or original["text"].split("\n\n", 1)[1] != paired["text_zh"]:
                issue("Chinese_and_English_content_match_input_by_ID", "Chinese body/title differs from original")
            if file_index and item.get("content_en") != paired["text_en"]:
                issue("Chinese_and_English_content_match_input_by_ID", "English excerpt differs from original")
            for key, value in meta.items():
                if type(item.get(key)) is not type(value) or item.get(key) != value:
                    issue("all_original_metadata_preserved", f"changed original metadata: {key}")
            line_range = item.get("source_lines")
            if not isinstance(line_range, list) or len(line_range) != 2 or any(type(value) is not int for value in line_range) or not 0 < line_range[0] <= line_range[1]:
                issue("source_URL_lines_and_version", "invalid source_lines")
            elif not any(line_range[0] <= line <= line_range[1] for line in source["included_source_lines"]):
                issue("source_URL_lines_and_version", "source range has no included snapshot lines")
            expected_source = {"source_url": source["url"], "source_title": source["title"], "source_language": source["language"], "source_revision_id": source["revision_id"], "source_revision_status": source["revision_status"], "source_revision_verified": False, "source_revision_timestamp": None, "source_page_raw_sha256": source["raw_sha256"], "source_page_clean_sha256": source["text_sha256"]}
            for key, value in expected_source.items():
                if type(item.get(key)) is not type(value) or item.get(key) != value:
                    issue("source_URL_lines_and_version", f"source mismatch or overstated verification: {key}")
            expected_license = {"license": source["license"], "license_url": source["license_url"], "contributors_url": source["contributors_url"], "source_attribution": source["attribution"], "source_acquisition_method": source["acquisition_method"], "source_acquired_date": source["acquired_date"], "source_raw_files": source["raw_files"]}
            for key, value in expected_license.items():
                if item.get(key) != value:
                    issue("license_attribution_and_acquisition", f"source mismatch: {key}")
            if any(not (ROOT / path).is_file() for path in source["raw_files"]):
                issue("license_attribution_and_acquisition", "missing original raw snapshot")
            if item.get("translation_status") != "ai_translated_unreviewed" or item.get("official_translation") is not False or item.get("expert_reviewed") is not False:
                issue("translation_review_status_and_notes", "translation falsely upgraded")
            if item.get("needs_rule_review") is True and not item.get("review_notes"):
                issue("translation_review_status_and_notes", "review flag without original notes")
            for key, hash_key in (("content_zh", "content_zh_sha256"), ("content_en", "content_en_sha256")):
                if key == "content_en" and not file_index:
                    continue
                if not isinstance(item.get(key), str) or sha(item[key].encode("utf-8")) != item.get(hash_key):
                    issue("hashes_match_actual_text_and_records", f"bad {hash_key}")
            if item.get("content_zh_sha256") != meta["translated_body_sha256"] or (file_index and item.get("content_en_sha256") != meta["source_text_sha256"]):
                issue("hashes_match_actual_text_and_records", "hash aliases differ from original excerpt hashes")
            if item.get("record_sha256") != sha(canonical({k: v for k, v in item.items() if k != "record_sha256"})):
                issue("hashes_match_actual_text_and_records", "bad record hash")
            for key in ("record_sha256", "content_zh_sha256", "source_text_sha256", "translated_body_sha256", "source_page_raw_sha256", "source_page_clean_sha256"):
                if not isinstance(item.get(key), str) or re.fullmatch(r"[0-9a-f]{64}", item[key]) is None:
                    issue("hashes_match_actual_text_and_records", f"invalid SHA-256 format: {key}")
            if item.get("parent_id") is not None or item.get("chunk_type") != expected_type(paired["text_zh"]):
                issue("parent_IDs_and_structure_types", "invented parent or incorrect structure type")
            expected_provenance = {"chinese_input": (CORPUS / "chunks_zh.jsonl").relative_to(ROOT).as_posix(), "parallel_input": (CORPUS / "parallel_zh_en.jsonl").relative_to(ROOT).as_posix(), "source_manifest": SOURCES.relative_to(ROOT).as_posix()}
            if item.get("provenance") != expected_provenance:
                issue("provenance_paths", "incorrect input references")
    for name, details in errors.items():
        check(name, details)
    left_by_id = {row.get("id"): row for row in zh}
    right_by_id = {row.get("id"): row for row in parallel}
    shared_errors = []
    for identifier in set(left_by_id) & set(right_by_id):
        left = {key: value for key, value in left_by_id[identifier].items() if key != "record_sha256"}
        right = {key: value for key, value in right_by_id[identifier].items() if key not in ("record_sha256", "content_en", "content_en_sha256")}
        if left != right:
            shared_errors.append(identifier)
    check("Chinese_and_parallel_shared_fields_match_by_ID", shared_errors)

    manifest_path = ROOT / "data/manifests/rag_dataset_manifest.json" if data_dir == ROOT / "data/processed" else data_dir / "rag_dataset_manifest.json"
    manifest = load(manifest_path)
    manifest_errors = []
    expected_inputs = {item["path"] for item in lock["files"]} | {SOURCES.relative_to(ROOT).as_posix(), "data/manifests/sources.csv", BASELINE.relative_to(ROOT).as_posix()}
    if {item["path"] for item in manifest["inputs"]} != expected_inputs:
        manifest_errors.append("input hash coverage differs from declared frozen inputs")
    entries = manifest["inputs"] + manifest["outputs"] + manifest["implementation"] + [manifest["schema_document"]]
    for entry in entries:
        path = checked_path(entry["path"])
        if not path.is_file() or path.stat().st_size != entry["size_bytes"] or sha(path.read_bytes()) != entry["sha256"]:
            manifest_errors.append("file checksum/size mismatch: " + entry["path"])
    if [item["path"] for item in manifest["outputs"]] != [path.relative_to(ROOT).as_posix() for path in paths] or any(item["records"] != 99 for item in manifest["outputs"]):
        manifest_errors.append("wrong output paths/counts")
    if manifest.get("schema_version") != "1.0.0" or manifest.get("dataset_version") != "corpus-b0-rag-adapter-1.0.0":
        manifest_errors.append("incorrect schema/data version")
    if manifest.get("dataset_content_id") != sha(b"\0".join(path.read_bytes() for path in paths)):
        manifest_errors.append("incorrect dataset_content_id")
    expected_mapping = [{"old_id": r["id"], "chunk_id": r["id"], "source_id": r["metadata"]["source_id"]} for r in original_zh]
    if manifest.get("id_mapping") != expected_mapping:
        manifest_errors.append("old chunk/source ID mapping changed")
    if manifest.get("limitations") != {"official_rulebook": False, "official_season": None, "historical_revision_body_independently_verified": False, "translation_expert_reviewed": False}:
        manifest_errors.append("incorrect dataset reliability boundary")
    check("dataset_manifest_hashes_versions_and_99_ID_mapping", manifest_errors)

    summary = {"documents": len({r.get("document_id") for r in zh}), "chinese_records": len(zh), "parallel_records": len(parallel), "unique_ids": len(set(r.get("id") for r in zh)), "available_source_pages": len(sources), "referenced_source_pages": len({r.get("source_id") for r in zh}), "null_parent_ids": sum(r.get("parent_id") is None for r in zh), "chunk_types": {kind: sum(r.get("chunk_type") == kind for r in zh) for kind in ("paragraph", "table", "unknown")}, "needs_rule_review": sum(r.get("needs_rule_review") is True for r in zh), "expert_reviewed": sum(r.get("expert_reviewed") is True for r in zh)}
    check("summary_matches_actual_records_and_manifest", [] if summary == manifest["summary"] else ["manifest summary mismatch"])
    table_rows = [r for r in zh if r.get("chunk_type") == "table"]
    check("table_headers_rows_conditions_and_review_notes_preserved_whole", [] if len(table_rows) == 1 and table_rows[0].get("id") == "L14-04" and table_rows[0].get("content_zh") == parallel_by_id["L14-04"]["text_zh"] else ["penalty table unit is missing, split, retyped or modified"])
    return {"summary": summary, "manifest": manifest_path.relative_to(ROOT).as_posix(), "dataset_content_id": manifest.get("dataset_content_id"), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/processed")
    parser.add_argument("--report", default="reports/task3_dataset_validation.json")
    args = parser.parse_args()
    report_path = checked_path(args.report)
    if not any(report_path.is_relative_to(ROOT / name) for name in ("reports", ".tmp")) or report_path.suffix.lower() != ".json":
        raise ValueError("Validation receipt must be a JSON file under reports/ or .tmp/")
    result = {"task": 3, "criteria": "Unchanged task 3 in docs/DEVELOPMENT_PLAN_AND_REPORT.md", "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"), "command": ".venv/Scripts/python.exe scripts/validate_rag_dataset.py --data-dir " + args.data_dir + " --report " + args.report}
    try:
        result.update(inspect_dataset(checked_path(args.data_dir)))
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        result["checks"] = result.get("checks", []) + [{"check": "inputs_and_outputs_parse_without_error", "passed": False, "errors": [f"{type(exc).__name__}: {exc}"]}]
    result["passed_checks"] = sum(item["passed"] for item in result["checks"])
    result["total_checks"] = len(result["checks"])
    result["status"] = "PASS" if result["passed_checks"] == result["total_checks"] else "FAIL"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Task 3 dataset: {result['status']}; checks: {result['passed_checks']}/{result['total_checks']}")
    if result.get("summary"):
        print(json.dumps(result["summary"], ensure_ascii=True))
    for item in result["checks"]:
        if not item["passed"]:
            print(item["check"], json.dumps(item["errors"][:5], ensure_ascii=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
