"""Audit the original task 1/2 delivery requirements without rebuilding corpus data.

Run with the project Python: .venv/Scripts/python.exe scripts/audit_task1_task2.py
The default report is reports/task1_task2_acceptance.json; use --output to
preserve earlier evidence. Full file-manifest verification is performed
separately after all delivery documents are saved.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import pathlib
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone


ROOT = pathlib.Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "third_party/kotaemon-v0.12.0"
CORPUS = ROOT / "data/processed/wikipedia_zh_2026-11-10"
EXPECTED_COMMIT = "9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9"
REPORT_PATH = ROOT / "reports/task1_task2_acceptance.json"
CHECKS: list[dict] = []


def read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(task: str, name: str, passed: bool, details=None) -> None:
    CHECKS.append({"task": task, "check": name, "passed": bool(passed), "details": details})


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(UPSTREAM), *args], text=True, encoding="utf-8"
    ).strip()


def audit_fixed_inputs() -> dict:
    lock = read_json(ROOT / "data/manifests/task1_task2_baseline_lock.json")
    changed = [item["path"] for item in lock["files"] if sha256(ROOT / item["path"]) != item["sha256"]]
    prefix_changed = []
    for item in lock["append_only_files"]:
        prefix = (ROOT / item["path"]).read_bytes()[: item["original_size_bytes"]]
        if hashlib.sha256(prefix).hexdigest() != item["original_prefix_sha256"]:
            prefix_changed.append(item["path"])
    check("shared", "technical_and_task_specs_and_Corpus_B0_unchanged", not changed, changed)
    check("shared", "existing_delivery_text_preserved_before_supplements", not prefix_changed, prefix_changed)
    return {"frozen_files": len(lock["files"]), "append_only_reports": len(lock["append_only_files"])}


def audit_task1() -> dict:
    manifest = read_json(CORPUS / "corpus_manifest.json")
    zh = [json.loads(line) for line in (CORPUS / "chunks_zh.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    parallel = [json.loads(line) for line in (CORPUS / "parallel_zh_en.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    sources = read_json(ROOT / "data/processed/wikipedia_2026-11-10/sources.json")
    with (ROOT / "data/manifests/sources.csv").open(encoding="utf-8-sig", newline="") as handle:
        source_csv = list(csv.DictReader(handle))
    zh_ids = [item["id"] for item in zh]
    parallel_ids = [item["id"] for item in parallel]
    source_ids = {item["source_id"] for item in sources}
    check("task1", "five_documents_99_aligned_unique_units_18_sources", len(manifest["documents"]) == 5 and len(zh) == len(parallel) == len(set(zh_ids)) == len(set(parallel_ids)) == 99 and set(zh_ids) == set(parallel_ids) and len(sources) == len(source_csv) == 18)
    changed_docs = [doc["markdown"] for doc in manifest["documents"] if sha256(CORPUS / doc["markdown"]) != doc["sha256"]]
    check("task1", "five_markdown_hashes_match_corpus_manifest", not changed_docs, changed_docs)
    source_errors = []
    for item in zh:
        meta = item["metadata"]
        lines = meta.get("source_lines")
        valid_lines = isinstance(lines, list) and len(lines) == 2 and all(isinstance(x, int) for x in lines) and 0 < lines[0] <= lines[1]
        if not item.get("text", "").strip() or not str(meta.get("source_url", "")).startswith("https://") or meta.get("source_id") not in source_ids or not valid_lines:
            source_errors.append(item["id"])
    check("task1", "nonempty_text_and_valid_source_URL_ID_lines", not source_errors, source_errors)
    checksum_errors = []
    for item in parallel:
        meta = item["metadata"]
        for field, hash_field in (("text_zh", "translated_body_sha256"), ("text_en", "source_text_sha256")):
            text = item.get(field, "")
            if not text.strip() or hashlib.sha256(text.encode("utf-8")).hexdigest() != meta[hash_field]:
                checksum_errors.append([item["id"], field])
    check("task1", "bilingual_content_checksums_match", not checksum_errors, checksum_errors)
    laws = sorted({item["metadata"]["law_number"] for item in zh})
    check("task1", "laws_1_through_17_covered", laws == list(range(1, 18)), laws)
    required_source_fields = ("url", "revision_id", "revision_status", "raw_sha256", "text_sha256", "license", "license_url", "contributors_url")
    incomplete_sources = [item["source_id"] for item in sources if not all(item.get(field) for field in required_source_fields) or not all((ROOT / name).is_file() for name in item["raw_files"])]
    check("task1", "source_versions_license_and_raw_snapshots_present", not incomplete_sources, incomplete_sources)
    csv_by_id = {item["source_id"]: item for item in source_csv}
    source_by_id = {item["source_id"]: item for item in sources}
    inconsistent_sources = [sid for sid, item in source_by_id.items() if sid not in csv_by_id or any(csv_by_id[sid].get(field) != item.get(field) for field in ("url", "revision_id", "text_sha256", "license", "license_url"))]
    check("task1", "source_CSV_and_JSON_content_consistent", len(csv_by_id) == len(source_by_id) == 18 and not inconsistent_sources, inconsistent_sources)
    specification = importlib.util.spec_from_file_location("corpus_source_audit", ROOT / "scripts/build_rules_document.py")
    builder = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(builder)
    snapshot_errors = []
    source_lines = {}
    for item in sources:
        sid = item["source_id"].replace("wiki-", "")
        numbered, raw, paths = builder.source_lines(sid)
        cleaned, included = builder.current_rules(sid, numbered)
        source_lines[item["source_id"]] = numbered
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != item["raw_sha256"] or hashlib.sha256(cleaned.encode("utf-8")).hexdigest() != item["text_sha256"] or included != item["included_source_lines"]:
            snapshot_errors.append(item["source_id"])
    check("task1", "raw_and_clean_source_hashes_recomputed_from_18_snapshots", not snapshot_errors, snapshot_errors)
    excerpt_errors = []
    for item in parallel:
        meta = item["metadata"]
        start, end = meta["source_lines"]
        excerpt = "\n\n".join(builder.clean(text) for number, text in sorted(source_lines[meta["source_id"]].items()) if start <= number <= end and text.strip() and not text.startswith(("[Button", "[Input", "[edit")))
        if excerpt != item["text_en"]:
            excerpt_errors.append(item["id"])
    check("task1", "all_99_English_excerpts_recoverable_from_declared_source_lines", not excerpt_errors, excerpt_errors)
    for name in ("build_rules_document.py", "build_chinese_rules.py"):
        script = ROOT / "scripts" / name
        compile(script.read_text(encoding="utf-8-sig"), str(script), "exec")
    check("task1", "corpus_builder_syntax_without_running_builders", True)
    check("task1", "existing_validation_report_PASS", read_json(CORPUS / "validation_report.json")["status"] == "PASS")
    check("task1", "project_Git_not_initialized", not (ROOT / ".git").exists())
    journal = (ROOT / "docs/EXPERIMENT_LOG.md").read_text(encoding="utf-8")
    check("task1", "audit_date_command_and_results_delivered_in_experiment_log", "TASK-001-DELIVERY" in journal and "scripts/audit_task1_task2.py" in journal and "99" in journal and "2026-11-10" in journal)
    check("task1", "audit_report_and_manifest_delivered", (ROOT / "docs/PROJECT_AUDIT.md").is_file() and (ROOT / "data/manifests/project_file_manifest.json").is_file())
    package_state = {}
    for name in ("requests", "beautifulsoup4", "torch", "transformers", "sentence-transformers", "huggingface-hub", "chromadb", "faiss-cpu", "qdrant-client", "lancedb", "langchain", "langgraph"):
        try:
            package_state[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            package_state[name] = "not installed in project .venv"
    environment = {"python": sys.version.split()[0], "executable": sys.executable, "packages": package_state, "ollama_model_cache_present": (ROOT / ".models/ollama/manifests").is_dir(), "local_ollama_binary_present": (ROOT / ".runtime/ollama/ollama.exe").is_file(), "hardware_acceleration": "not rechecked in this supplement; no hardware-performance claim"}
    return {"documents": 5, "knowledge_units": len(zh), "parallel_units": len(parallel), "sources": len(sources), "raw_snapshot_files": len(list((ROOT / "data/raw/wikipedia_2026-11-10").glob("*.txt"))), "review_marked_units": sum(bool(x["metadata"].get("needs_rule_review")) for x in zh), "expert_reviewed_units": sum(bool(x["metadata"].get("expert_reviewed")) for x in zh), "supplement_environment": environment}


def splitter_configuration(config: dict) -> dict:
    path = UPSTREAM / "libs/ktem/ktem/index/file/pipelines.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "TokenSplitter")
    arguments = {keyword.arg: keyword.value for keyword in call.keywords}
    defaults = {name: ast.literal_eval(arguments[name].values[-1]) for name in ("chunk_size", "chunk_overlap")}
    flow_tree = ast.parse((UPSTREAM / "flowsettings.py").read_text(encoding="utf-8"))
    developer = {}
    for node in ast.walk(flow_tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ("FILE_INDEX_PIPELINE_SPLITTER_CHUNK_SIZE", "FILE_INDEX_PIPELINE_SPLITTER_CHUNK_OVERLAP"):
                    developer[target.id] = ast.literal_eval(node.value)
    size = config.get("chunk_size") or developer.get("FILE_INDEX_PIPELINE_SPLITTER_CHUNK_SIZE") or defaults["chunk_size"]
    overlap = config.get("chunk_overlap") or developer.get("FILE_INDEX_PIPELINE_SPLITTER_CHUNK_OVERLAP") or defaults["chunk_overlap"]
    return {"class": "kotaemon.indices.splitters.TokenSplitter", "delegate": "llama_index.core.node_parser.text.token.TokenTextSplitter", "reader": "kotaemon.loaders.TxtReader", "chunk_size_tokens": size, "chunk_overlap_tokens": overlap, "persisted_values": {"chunk_size": config.get("chunk_size"), "chunk_overlap": config.get("chunk_overlap")}, "developer_overrides": developer, "separator": ast.literal_eval(arguments["separator"]), "backup_separators": ast.literal_eval(arguments["backup_separators"]), "tokenizer_default": "tiktoken / gpt-3.5-turbo / cl100k_base", "evidence": [{"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)}, {"path": (UPSTREAM / "flowsettings.py").relative_to(ROOT).as_posix(), "sha256": sha256(UPSTREAM / "flowsettings.py")}], "resolution_method": "Persisted collection configuration plus exact pinned route defaults; zero means inherit, not zero-length chunks."}


def audit_task2(ui_path: str, model_path: str, startup_log: str | None) -> dict:
    head = git("rev-parse", "HEAD")
    clean = not git("status", "--porcelain", "--untracked-files=no")
    check("task2", "pinned_upstream_commit_and_clean_source", head == EXPECTED_COMMIT and clean, {"commit": head, "tracked_source_clean": clean})
    check("task2", "isolated_Python_3_10_or_newer", sys.version_info >= (3, 10) and pathlib.Path(sys.prefix).resolve() == (ROOT / ".venv").resolve(), {"version": sys.version.split()[0], "executable": sys.executable})
    lock_path = UPSTREAM / "uv.lock"
    locked = {}
    for block in lock_path.read_text(encoding="utf-8").split("[[package]]"):
        name = re.search(r'^name = "([^"]+)"', block, re.M)
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        if name and version:
            locked.setdefault(name.group(1), set()).add(version.group(1))
    versions = {}
    for name in ("kotaemon", "ktem", "gradio", "chromadb", "lancedb", "llama-index-core", "langchain", "theflow", "tiktoken"):
        installed = metadata.version(name)
        matches = installed == "0.12.0" if name in ("kotaemon", "ktem") else installed in locked.get(name, set())
        versions[name] = {"installed": installed, "lock_versions": sorted(locked.get(name, set())), "matches": matches}
    check("task2", "critical_dependency_versions_match_pinned_lock", all(x["matches"] for x in versions.values()), versions)
    db_path = UPSTREAM / "ktem_app_data/user_data/sql.db"
    with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        config = json.loads(connection.execute('SELECT config FROM ktem__index WHERE id=1').fetchone()[0])
        source_count = connection.execute('SELECT count(*) FROM index__1__source').fetchone()[0]
        relations = dict(connection.execute('SELECT relation_type,count(*) FROM index__1__index GROUP BY relation_type'))
        settings = {}
        for (payload,) in connection.execute('SELECT setting FROM settings'):
            for key, value in json.loads(payload).items():
                if key.startswith("index.options.1.") and key.rsplit(".", 1)[-1] in ("top_k", "retrieval_mode", "use_reranking", "use_llm_relevant_scoring"):
                    settings[key] = value
        local_models = {}
        for table in ("llm_table", "embedding"):
            payload, is_default = connection.execute(f'SELECT spec,"default" FROM {table} WHERE name=?', ("ollama",)).fetchone()
            specification = json.loads(payload)
            local_models[table] = {key: specification[key] for key in ("__type__", "model", "base_url") if key in specification}
            local_models[table]["default"] = bool(is_default)
    check("task2", "local_models_selected_in_application", local_models["llm_table"].get("model") == "qwen2.5:3b" and local_models["embedding"].get("model") == "bge-m3" and all(item["default"] for item in local_models.values()), local_models)
    splitter = splitter_configuration(config)
    check("task2", "splitter_parameters_resolved_from_persisted_config_and_source", splitter["chunk_size_tokens"] == 1024 and splitter["chunk_overlap_tokens"] == 256, splitter)
    store = read_json(UPSTREAM / "ktem_app_data/user_data/docstore-simple/index_1.json")
    check("task2", "five_documents_and_50_smoke_chunks_persisted", source_count == 5 and relations.get("document") == relations.get("vector") == len(store) == 50, {"source_files": source_count, "relations": relations, "docstore_documents": len(store)})
    evidence = read_json(ROOT / ui_path)
    questions = evidence.get("qa", [])
    check("task2", "real_UI_HTTP_200_and_three_nonempty_Chinese_answers", evidence.get("http_status") == 200 and evidence.get("information_panel_present") is True and len(questions) == 3 and all(x.get("question") and x.get("answer") for x in questions), {"captured_at": evidence.get("captured_at"), "url": evidence.get("url"), "answers": [{"question_id": x["question_id"], "answer_characters": len(x["answer"])} for x in questions]})
    models = read_json(ROOT / model_path)
    model_names = {model["name"] for model in models["models"]}
    check("task2", "local_chat_and_embedding_models_available", {"qwen2.5:3b", "bge-m3:latest"}.issubset(model_names), models)
    files = ("docs/UPSTREAM_VERSION.md", "docs/LOCAL_SETUP.md", "scripts/run_baseline_check.ps1", "scripts/run_kotaemon_local.py", "scripts/kotaemon_runtime_env.py", "scripts/prepare_kotaemon_assets.py", "docs/KOTAEMON_BASELINE.md", "reports/task2-indexing-windows-overlay-final-2026-11-10.log")
    check("task2", "required_delivery_files_present", all((ROOT / name).is_file() for name in files), list(files))
    baseline = (ROOT / "docs/KOTAEMON_BASELINE.md").read_text(encoding="utf-8")
    check("task2", "splitter_and_actual_dependency_versions_added_to_baseline", all(token in baseline for token in ("TokenSplitter", "1024", "256", "4.39.0", "0.5.16", "0.25.1")))
    example = ROOT / ".env.example"
    check("task2", "nonsecret_environment_example_delivered", example.is_file() and "KH_OLLAMA_URL=http://127.0.0.1:11434/v1/" in example.read_text(encoding="utf-8"))
    if startup_log:
        startup = (ROOT / startup_log).read_text(encoding="utf-8-sig")
        check("task2", "documented_runner_really_started_server_after_import_checks", all(text in startup for text in ("gradio: import OK", "Starting the pinned app", "Running on local URL:", "127.0.0.1:7860")), startup_log)
    from kotaemon_runtime_env import configure_local_runtime
    try:
        assets = configure_local_runtime()
        import tiktoken
        encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        check("task2", "verified_local_tokenizer_cache_really_loads", encoding.name == "cl100k_base" and bool(encoding.encode("越位规则")), assets)
    except Exception as exc:
        check("task2", "verified_local_tokenizer_cache_really_loads", False, f"{type(exc).__name__}: {exc}")
    public_paths = [ROOT / name for name in files] + [ROOT / ui_path, ROOT / model_path, example]
    if startup_log:
        public_paths.append(ROOT / startup_log)
    secret_pattern = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bghp_[A-Za-z0-9]{36}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b")
    secret_hits = [path.relative_to(ROOT).as_posix() for path in public_paths if secret_pattern.search(path.read_text(encoding="utf-8-sig", errors="replace"))]
    check("task2", "no_high_confidence_secrets_in_public_delivery_evidence", not secret_hits, {"flagged_paths": secret_hits, "scope": "Delivered setup/baseline/version documents, scripts, selected runtime evidence, and environment example; model specs exported through a nonsecret whitelist."})
    return {"commit": head, "python": sys.version.split()[0], "uv_lock_sha256": sha256(lock_path), "dependencies": versions, "splitter": splitter, "retrieval_settings": settings, "application_local_models": local_models, "model_runtime_evidence": model_path, "ui_evidence": ui_path, "startup_log": startup_log, "quality_observation": "Raw smoke answers and citation behavior are retained. Task 2 has no answer-accuracy threshold; known defects remain open for the original later retrieval/answer tasks.", "formal_retrieval_or_answer_metrics": "not measured"}


def probe_local_services() -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    result = {}
    for name, url in (("application", "http://127.0.0.1:7860/"), ("model_version", "http://127.0.0.1:11434/api/version"), ("models", "http://127.0.0.1:11434/api/tags")):
        try:
            with opener.open(url, timeout=8) as response:
                result[name] = {"url": url, "status": response.status}
                if name != "application":
                    result[name]["data"] = json.load(response)
        except Exception as exc:
            result[name] = {"url": url, "error": f"{type(exc).__name__}: {exc}"}
    names = {item["name"] for item in result.get("models", {}).get("data", {}).get("models", [])}
    check("task2", "fresh_loopback_HTTP_and_local_models_reachable", all(item.get("status") == 200 for item in result.values()) and {"qwen2.5:3b", "bge-m3:latest"}.issubset(names), result)
    return result


def audit_log_snapshots() -> list:
    manifest = read_json(ROOT / "data/manifests/runtime_log_snapshots.json")
    snapshots = manifest["snapshots"]
    invalid = [item["archive_path"] for item in snapshots if not (ROOT / item["source_path"]).is_file() or not (ROOT / item["archive_path"]).is_file() or sha256(ROOT / item["archive_path"]) != item["sha256"] or (ROOT / item["archive_path"]).stat().st_size != item["size_bytes"]]
    check("shared", "frozen_log_snapshots_match_recorded_hashes", bool(snapshots) and not invalid, invalid)
    return snapshots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ui-evidence", default="reports/task2-ui-evidence-2026-11-10.json")
    parser.add_argument("--model-evidence", default="reports/task2-model-runtime-2026-11-10.json")
    parser.add_argument("--startup-log")
    parser.add_argument("--output", default=str(REPORT_PATH.relative_to(ROOT)))
    parser.add_argument("--live", action="store_true", help="Also probe the current loopback services instead of relying only on saved evidence")
    args = parser.parse_args()
    report_path = (ROOT / args.output).resolve()
    if not report_path.is_relative_to(ROOT):
        raise ValueError("Report output must stay within the project")
    report = {"generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"), "command": ".\\.venv\\Scripts\\python.exe scripts/audit_task1_task2.py " + " ".join(sys.argv[1:]), "criteria": "docs/DEVELOPMENT_PLAN_AND_REPORT.md tasks 1 and 2 (unchanged)", "fixed_inputs": audit_fixed_inputs(), "task1": audit_task1(), "task2": audit_task2(args.ui_evidence, args.model_evidence, args.startup_log), "log_snapshots": audit_log_snapshots()}
    if args.live:
        report["current_services"] = probe_local_services()
    report["checks"] = CHECKS
    report["status"] = "PASS" if all(item["passed"] for item in CHECKS) else "FAIL"
    for task in ("task1", "task2"):
        report[task + "_status"] = "PASS" if all(item["passed"] for item in CHECKS if item["task"] in (task, "shared")) else "FAIL"
    report["project_file_manifest_note"] = "Run update_project_manifest.py and --verify after this report and all documents are saved; that read-only final verification avoids a self-referential hash."
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Task 1: {report['task1_status']}; Task 2: {report['task2_status']}; checks: {sum(item['passed'] for item in CHECKS)}/{len(CHECKS)}")
    for item in CHECKS:
        if not item["passed"]:
            print("FAIL:", item["check"], json.dumps(item["details"], ensure_ascii=True))
    print(f"Report: {report_path.relative_to(ROOT)}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
