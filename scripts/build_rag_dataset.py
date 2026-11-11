"""Adapt frozen Corpus B0 to a stable RAG schema without re-chunking it.

Only new derived files are written. Inputs are matched by ID, not row order.
The JSONL files and dataset manifest are deterministic; run dates belong in the
execution/validation reports rather than the data's content hash.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_REL = "data/processed/wikipedia_zh_2026-11-10"
SOURCE_REL = "data/processed/wikipedia_2026-11-10/sources.json"
LOCK_REL = "data/manifests/task1_task2_baseline_lock.json"
SCHEMA_VERSION = "1.0.0"
DATASET_VERSION = "corpus-b0-rag-adapter-1.0.0"
OUTPUT_NAMES = ("rag_chunks_zh.jsonl", "rag_chunks_parallel.jsonl")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def read_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate input IDs: {path.name}")
    return rows


def chunk_type(text: str) -> str:
    lines = text.splitlines()
    for index in range(1, len(lines)):
        cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
        headers = lines[index - 1].strip().strip("|").split("|")
        if len(cells) >= 2 and len(headers) == len(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            return "table"
    if "|" in text or re.search(r"```|~~~|<\/?[A-Za-z][^>]*>", text):
        return "unknown"
    return "paragraph" if text.strip() else "unknown"


def row_hash(row: dict) -> str:
    return sha(canonical({key: value for key, value in row.items() if key != "record_sha256"}))


def file_entry(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": path.relative_to(ROOT).as_posix(), "size_bytes": len(data), "sha256": sha(data)}


def project_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Derived output paths must stay inside this project")
    return path


def prepare() -> tuple[list[dict], list[dict], list[dict]]:
    lock = read_json(ROOT / LOCK_REL)
    for item in lock["files"]:
        if sha((ROOT / item["path"]).read_bytes()) != item["sha256"]:
            raise ValueError(f"Frozen input changed: {item['path']}")
    corpus = ROOT / CORPUS_REL
    chinese = read_rows(corpus / "chunks_zh.jsonl")
    bilingual = read_rows(corpus / "parallel_zh_en.jsonl")
    parallel_by_id = {row["id"]: row for row in bilingual}
    if len(chinese) != 99 or len(bilingual) != 99 or {r["id"] for r in chinese} != set(parallel_by_id):
        raise ValueError("Expected exactly 99 aligned input IDs")
    source_rows = read_json(ROOT / SOURCE_REL)
    sources = {row["source_id"]: row for row in source_rows}
    if len(sources) != len(source_rows) or len(sources) != 18:
        raise ValueError("Expected 18 unique source manifest records")
    zh_out, parallel_out = [], []
    for original in chinese:
        item = parallel_by_id[original["id"]]
        meta = original["metadata"]
        if meta != item["metadata"]:
            raise ValueError(f"Input metadata conflict: {original['id']}")
        prefix, content = original["text"].split("\n\n", 1)
        if content != item["text_zh"] or item["title_zh"] != meta["section_path"][-1]:
            raise ValueError(f"Input title/body conflict: {original['id']}")
        if original["id"] not in prefix or not content.strip() or not item["text_en"].strip():
            raise ValueError(f"Missing input text or heading: {original['id']}")
        if sha(content.encode("utf-8")) != meta["translated_body_sha256"] or sha(item["text_en"].encode("utf-8")) != meta["source_text_sha256"]:
            raise ValueError(f"Input content hash mismatch: {original['id']}")
        source = sources[meta["source_id"]]
        for old, source_key in (("source_url", "url"), ("source_revision_id", "revision_id"), ("source_revision_status", "revision_status"), ("license", "license"), ("license_url", "license_url"), ("contributors_url", "contributors_url")):
            if meta[old] != source[source_key]:
                raise ValueError(f"Source conflict: {original['id']} {old}")
        row = {
            "schema_version": SCHEMA_VERSION,
            "dataset_version": DATASET_VERSION,
            "id": original["id"],
            "chunk_id": original["id"],
            "parent_id": None,
            "chunk_type": chunk_type(content),
            "title_zh": item["title_zh"],
            "content_zh": content,
            **copy.deepcopy(meta),
            "source_title": source["title"],
            "source_language": source["language"],
            "source_revision_timestamp": None,
            "source_revision_verified": False,
            "source_acquisition_method": source["acquisition_method"],
            "source_acquired_date": source["acquired_date"],
            "source_page_raw_sha256": source["raw_sha256"],
            "source_page_clean_sha256": source["text_sha256"],
            "source_raw_files": copy.deepcopy(source["raw_files"]),
            "translation_status": "ai_translated_unreviewed",
            "content_zh_sha256": sha(content.encode("utf-8")),
            "provenance": {
                "chinese_input": f"{CORPUS_REL}/chunks_zh.jsonl",
                "parallel_input": f"{CORPUS_REL}/parallel_zh_en.jsonl",
                "source_manifest": SOURCE_REL,
            },
        }
        parallel = copy.deepcopy(row)
        parallel["content_en"] = item["text_en"]
        parallel["content_en_sha256"] = sha(item["text_en"].encode("utf-8"))
        row["record_sha256"] = row_hash(row)
        parallel["record_sha256"] = row_hash(parallel)
        zh_out.append(row)
        parallel_out.append(parallel)
    input_paths = [ROOT / item["path"] for item in lock["files"]]
    input_paths.extend((ROOT / SOURCE_REL, ROOT / "data/manifests/sources.csv", ROOT / LOCK_REL))
    return zh_out, parallel_out, [file_entry(p) for p in input_paths]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="data/processed", help="New derived files only; paths resolve from the project root")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace different derived output; frozen input paths remain prohibited")
    args = parser.parse_args()
    try:
        output_dir = project_path(args.output_dir)
        if output_dir.is_relative_to(ROOT / CORPUS_REL) or output_dir.is_relative_to(ROOT / "data/raw") or output_dir.is_relative_to(ROOT / "data/processed/wikipedia_2026-11-10"):
            raise ValueError("Cannot write into the frozen source directories")
        zh_rows, parallel_rows, inputs = prepare()
        outputs = [output_dir / name for name in OUTPUT_NAMES]
        manifest_path = ROOT / "data/manifests/rag_dataset_manifest.json" if output_dir == ROOT / "data/processed" else output_dir / "rag_dataset_manifest.json"
        payloads = [b"".join(canonical(row) + b"\n" for row in rows) for rows in (zh_rows, parallel_rows)]
        counts = {name: sum(row["chunk_type"] == name for row in zh_rows) for name in ("paragraph", "table", "unknown")}
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "dataset_version": DATASET_VERSION,
            "dataset_content_id": sha(b"\0".join(payloads)),
            "determinism": "No generated run timestamp in data; validation reports record execution time.",
            "schema_document": file_entry(ROOT / "docs/RAG_DATA_SCHEMA.md"),
            "implementation": [file_entry(ROOT / name) for name in ("scripts/build_rag_dataset.py", "scripts/validate_rag_dataset.py")],
            "inputs": inputs,
            "outputs": [{"path": path.relative_to(ROOT).as_posix(), "size_bytes": len(data), "sha256": sha(data), "records": 99} for path, data in zip(outputs, payloads)],
            "summary": {"documents": len({row["document_id"] for row in zh_rows}), "chinese_records": len(zh_rows), "parallel_records": len(parallel_rows), "unique_ids": len({row["id"] for row in zh_rows}), "available_source_pages": 18, "referenced_source_pages": len({row["source_id"] for row in zh_rows}), "null_parent_ids": sum(row["parent_id"] is None for row in zh_rows), "chunk_types": counts, "needs_rule_review": sum(row["needs_rule_review"] for row in zh_rows), "expert_reviewed": sum(row["expert_reviewed"] for row in zh_rows)},
            "id_mapping": [{"old_id": row["id"], "chunk_id": row["chunk_id"], "source_id": row["source_id"]} for row in zh_rows],
            "limitations": {"official_rulebook": False, "official_season": None, "historical_revision_body_independently_verified": False, "translation_expert_reviewed": False},
        }
        planned = list(zip(outputs, payloads)) + [(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")]
        protected = {(ROOT / item["path"]).resolve() for item in inputs}
        for path, data in planned:
            if path.resolve() in protected:
                raise ValueError(f"Refusing to replace input: {path}")
            if path.exists() and path.read_bytes() != data and not args.overwrite:
                raise ValueError(f"Different derived output exists; choose a new output directory or use --overwrite: {path.relative_to(ROOT)}")
        # All source checks and overwrite checks finish before the first write.
        for path, data in planned:
            if path.exists() and path.read_bytes() == data:
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            stage = path.with_name(path.name + ".building")
            stage.write_bytes(data)
            stage.replace(path)
        print(json.dumps({"status": "PASS", "summary": manifest["summary"], "manifest": manifest_path.relative_to(ROOT).as_posix()}, ensure_ascii=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
