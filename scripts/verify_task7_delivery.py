"""Read-only local Task 7 delivery gate; replay saved runs without model requests.

The replay helper alone parses actual evaluation questions and predictions.
This gate exposes aggregate metrics, latency and file hashes; it never prints
locked-test question text, individual rankings, labels or document bodies.
Private preservation checks require this workstation's original audit snapshot.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from dense_retrieval_eval import (CONFIG, SOURCES, SOURCE_FIELDS, TIMINGS,
                                  file_record, replay, require_committed_sources)
from eval_dataset import ROOT, CORPUS, digest, load_jsonl
import dense_retrieval_contracts as contracts


DEFAULT_BASE = ROOT / "reports/retrieval/dense_b0"
ORIGINAL_ROOT = ROOT.parent / "football-rules-rag-project"
ORIGINAL_SNAPSHOT = (ROOT.parent /
    "2026-11-06/new-chat/.tmp/github-publication/original-project-before.json")
HISTORICAL_REPORT_EXCEPTIONS = {
    "reports/README.md", "reports/all_experiments_summary.csv", "reports/resume_evidence.md"}


def read_json(path):
    return json.loads(Path(path).read_text("utf-8"))


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("Timestamp must be an ISO date string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("Timestamp must have a timezone")
    return result


def commit_time(commit):
    raw = subprocess.check_output(
        ["git", "show", "-s", "--format=%ct", commit], cwd=ROOT, text=True)
    return datetime.fromtimestamp(int(raw.strip()), timezone.utc)


def ancestor(older, newer):
    return subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                          cwd=ROOT, capture_output=True).returncode == 0


def index_inventory(path):
    return {p.relative_to(path).as_posix():
            {"size_bytes": p.stat().st_size, "sha256": digest(p.read_bytes())}
            for p in sorted(path.rglob("*")) if p.is_file() and p.name != "index_manifest.json"}


def verification_passed(record):
    if record.get("status") != "PASS":
        return False
    outcomes = record.get("checks")
    values = (list(outcomes.values()) if isinstance(outcomes, dict) else
              [row["passed"] for row in outcomes] if isinstance(outcomes, list) else [])
    return bool(values) and all(value is True for value in values)


def verification_time(record):
    for key in ("generated_at", "checked_at", "captured_at"):
        if key in record:
            return timestamp(record[key])
    raise ValueError("Verification report needs a timestamp")


def source_map_matches_corpus(directory, corpus):
    rows = read_json(directory / "source_map.json")
    return (isinstance(rows, list) and len(rows) == len(corpus) == 99
            and all(isinstance(row, dict) and set(row) == set(SOURCE_FIELDS) for row in rows)
            and len({row["chunk_id"] for row in rows}) == 99
            and {row["chunk_id"]: row for row in rows} ==
                {row["chunk_id"]: {field: row[field] for field in SOURCE_FIELDS} for row in corpus})


def verify(dev_dir, test_dir, authorization_path, usage_path, preservation_snapshot=ROOT/'.runtime/task7/before.json'):
    checks, errors, context = {}, [], {}

    def check(name, operation):
        try:
            checks[name] = bool(operation())
        except Exception as exc:
            # Exception messages from parsing real evidence could include a
            # question, label or source excerpt. Only expose the error class.
            checks[name] = False
            errors.append({"check": name, "exception_type": type(exc).__name__})

    def load_context():
        context.update(dev_manifest=read_json(dev_dir / "run_manifest.json"),
                       test_manifest=read_json(test_dir / "run_manifest.json"),
                       grant=read_json(authorization_path),
                       release=read_json(ROOT / "data/eval/dataset_manifest.json"),
                       before=read_json(preservation_snapshot),
                       lock=read_json(ROOT / "data/manifests/task1_task2_baseline_lock.json"),
                       local=read_json(ROOT / "data/manifests/local_data_files.json")["files"])
        return True

    check("all_required_manifests_and_private_preservation_baseline_available", load_context)

    def replay_split(split, directory):
        context[split] = replay(directory)
        return True

    check("development_independently_replays_without_models", lambda: replay_split("dev", dev_dir))
    check("test_independently_replays_without_models", lambda: replay_split("test", test_dir))
    for split, count, answerable, unanswerable, samples in (
            ("dev", 40, 32, 8, 120), ("test", 50, 40, 10, 150)):
        check(split + "_fixed_question_counts", lambda s=split, n=count, a=answerable, u=unanswerable:
              context[s]["quality"]["questions"] == n
              and context[s]["quality"]["answerable_denominator"] == a
              and context[s]["quality"]["unanswerable_excluded"] == u)
        check(split + "_all_questions_have_three_latency_samples", lambda s=split, n=count, k=samples:
              context[s]["latency"]["questions"] == n and context[s]["latency"]["samples"] == k
              and context[s]["latency_by_answerability"]["true"]["samples"] == (32 if s == "dev" else 40) * 3
              and context[s]["latency_by_answerability"]["false"]["samples"] == (8 if s == "dev" else 10) * 3)
        check(split + "_original_metrics_and_separate_coverage_present", lambda s=split:
              set(context[s]["quality"]["metrics"]) ==
                {"Recall@5", "Recall@10", "MRR@10", "all_gold_coverage@5"}
              and context[s]["quality"]["nDCG@10"] is None)
        check(split + "_four_separate_latency_stages_and_declared_percentiles", lambda s=split:
              set(context[s]["latency"]["stages"]) == set(TIMINGS)
              and all({"mean", "p50", "p95", "min", "max"} == set(row)
                      for row in context[s]["latency"]["stages"].values())
              and context[s]["latency"]["unit"] == "milliseconds"
              and context[s]["latency"]["percentile_method"] == "linear interpolation at q * (n - 1)")
        check(split + "_public_prediction_and_request_schema_no_bodies_vectors_answers", lambda s=split:
              s in context and context[s]["generation_model_requests"] == 0)
        check(split + "_source_commit_is_committed_and_predates_measurement", lambda s=split:
              require_committed_sources(context[s + "_manifest"]["source_commit"],current=False) is None
              and commit_time(context[s + "_manifest"]["source_commit"]) <=
                    timestamp(context[s + "_manifest"]["started_at"]))
        check(split + "_run_times_are_ordered", lambda s=split:
              timestamp(context[s + "_manifest"]["started_at"]) <=
              timestamp(context[s + "_manifest"]["completed_at"]))

    check("both_splits_share_identical_preregistered_measurement_configuration", lambda:
          context["dev_manifest"]["config"] == context["test_manifest"]["config"] == context["grant"]["config"])
    check("top10_three_measured_three_warmup_serial_no_cache_policy", lambda:
          context["dev_manifest"]["config"]["top_k"] == 10
          and context["dev_manifest"]["config"]["measured_repetitions"] == 3
          and context["dev_manifest"]["config"]["warmup_repetitions"] == 3
          and context["dev_manifest"]["config"]["concurrency"] == 1
          and context["dev_manifest"]["config"]["cache"] is False)
    check("same_model_index_corpus_and_all_public_input_snapshots", lambda:
          all(context["dev_manifest"][key] == context["test_manifest"][key] for key in
              ("model_artifact", "index_version", "index_manifest_sha256", "index_vector_fingerprint",
               "index_producer_implementation_sha256", "corpus_version", "corpus_sha256", "dataset_version", "input_snapshots")))
    check("test_is_final_report_and_not_parameter_selection", lambda:
          context["test_manifest"]["purpose"] == context["test"]["purpose"] == context["grant"]["purpose"] == "final_report"
          and context["test_manifest"]["used_for_parameter_selection"] is False
          and context["grant"]["used_for_parameter_selection"] is False)
    check("authorization_hash_and_directory_bind_completed_test", lambda:
          context["test_manifest"]["authorization"] == file_record(authorization_path)
          and context["grant"]["allowed_run_directory"] == test_dir.relative_to(ROOT).as_posix()
          and context["grant"]["config_sha256"] == digest(CONFIG.read_bytes())
          and context["grant"]["test_sha256"] == context["release"]["test_lock"]["sha256"]
          and context["grant"]["input_snapshots"] == context["test_manifest"]["input_snapshots"])
    check("development_completed_before_authorization_before_test_start", lambda:
          timestamp(context["dev_manifest"]["completed_at"]) <= timestamp(context["grant"]["prepared_at"])
          <= timestamp(context["test_manifest"]["started_at"]))
    check("authorization_source_commit_preexists_prepare_and_matches_test_source", lambda:
          require_committed_sources(context["grant"]["source_commit"],current=False) is None
          and context["grant"]["source_commit"] == context["test_manifest"]["source_commit"]
          and ancestor(context["dev_manifest"]["source_commit"], context["grant"]["source_commit"])
          and commit_time(context["grant"]["source_commit"]) <= timestamp(context["grant"]["prepared_at"]))
    check("authorized_development_manifest_and_summary_are_this_run", lambda:
          context["grant"]["development_manifest"] == file_record(dev_dir / "run_manifest.json")
          and context["grant"]["development_summary"] == file_record(dev_dir / "summary.json"))

    def development_verifications():
        records = context["grant"]["development_verification"]
        if not isinstance(records, list) or len(records) != 2:
            return False
        expected_producers = {"verify_dense_metric_arithmetic.py", "verify_dense_retrieval_contract.py"}
        seen = set()
        for record in records:
            path = (ROOT / record["path"]).resolve()
            value = read_json(path)
            hashes = value.get("source_sha256", {})
            producers = expected_producers.intersection(hashes)
            if len(producers) != 1:
                return False
            seen.update(producers)
            if (file_record(path) != record or not verification_passed(value)
                    or verification_time(value) > timestamp(context["grant"]["prepared_at"])
                    or not hashes or any(digest(contracts.git_blob(context['grant']['source_commit'],'scripts/'+name)) != sha
                                         for name, sha in hashes.items())):
                return False
        return seen == expected_producers

    check("both_authorized_synthetic_verifications_pass_and_predate_authorization", development_verifications)

    def usage_is_valid():
        events = load_jsonl(usage_path)
        manifest = context["test_manifest"]
        selected=contracts.usage_matches(events,manifest,test_dir.relative_to(ROOT).as_posix(),
                                          file_record(authorization_path),context['release'])
        if not selected:
            return False
        events=selected
        expected = {"run_id": manifest["run_id"], "run_directory": test_dir.relative_to(ROOT).as_posix(),
                    "split": "test", "purpose": "final_report", "used_for_parameter_selection": False,
                    "source_commit": manifest["source_commit"], "config_sha256": digest(CONFIG.read_bytes()),
                    "test_sha256": context["release"]["test_lock"]["sha256"],
                    "authorization": file_record(authorization_path)}
        return (all(all(event.get(key) == value for key, value in expected.items()) for event in events)
                and events[1].get("run_manifest") == file_record(test_dir / "run_manifest.json")
                and timestamp(manifest["started_at"]) <= timestamp(events[0]["recorded_at"])
                <= timestamp(manifest["completed_at"]) <= timestamp(events[1]["recorded_at"]))

    check("selected_test_run_two_events_bound_to_lock_config_authorization_manifest", usage_is_valid)
    check("original_dataset_manifest_and_formal_test_runs_not_rewritten", lambda:
          digest((ROOT / "data/eval/dataset_manifest.json").read_bytes()) ==
          context["before"]["tracked"]["data/eval/dataset_manifest.json"]
          and context["grant"]["original_dataset_manifest_not_modified"] is True)
    check("original_test_lock_remains_locked_with_identical_file_sha", lambda:
          context["release"]["test_lock"]["state"] == "locked"
          and digest((ROOT / "data/eval/retrieval_test.jsonl").read_bytes()) == context["release"]["test_lock"]["sha256"])

    def matching_corpus_metadata():
        corpus = load_jsonl(CORPUS)
        return source_map_matches_corpus(dev_dir, corpus) and source_map_matches_corpus(test_dir, corpus)

    check("both_99_source_maps_match_original_corpus_metadata_without_publishing_bodies", matching_corpus_metadata)
    def snapshot_covers_commit():
        before=context['before'];commit=before['base_commit'];contracts.ancestor(commit)
        names=subprocess.check_output(['git','ls-tree','-r','--name-only',commit],cwd=ROOT,text=True).splitlines()
        records=before['tracked']
        return (isinstance(records,dict) and set(names)<=set(records)
          and all(isinstance(sha,str) and len(sha)==64 and (ROOT/name).resolve().is_relative_to(ROOT) for name,sha in records.items())
          and all(digest(contracts.git_blob(commit,name))==records[name] for name in names))
    check("private_preservation_snapshot_covers_its_committed_baseline",snapshot_covers_commit)
    check("formal_dense_index_all_artifact_bytes_and_manifest_unchanged", lambda:
          context["before"]["index"] ==
          {**index_inventory(ROOT / "data/indexes/dense"), "index_manifest.json":
           digest((ROOT / "data/indexes/dense/index_manifest.json").read_bytes())})
    check("original_private_human_review_ledger_unchanged", lambda:
          digest((ROOT / ".runtime/eval_review/reviews.jsonl").read_bytes()) == context["before"]["ledger_sha256"])
    check("private_ledger_hash_still_matches_public_human_receipt", lambda:
          read_json(ROOT / "data/eval/human_review_receipt.json")["private_ledger_sha256"] == context["before"]["ledger_sha256"]
          and context["release"]["human_review"]["ledger_sha256"] == context["before"]["ledger_sha256"])
    check("all_original_eval_and_historical_report_bytes_unchanged", lambda:
          all(digest((ROOT / path).read_bytes()) == sha for path, sha in context["before"]["tracked"].items()
              if path.startswith(("data/eval/", "reports/")) and path not in HISTORICAL_REPORT_EXCEPTIONS))
    check("original_dense_manifests_and_application_configuration_unchanged", lambda:
          all(digest((ROOT / path).read_bytes()) == sha for path, sha in context["before"]["tracked"].items()
              if path.startswith("data/manifests/dense_") or path in
              ("config/dense_index.json", "config/rag_b0.json", "config/rag_b0_system.txt")))
    check("three_original_authority_documents_unchanged", lambda:
          all(digest((ROOT / path).read_bytes()) == context["before"]["tracked"][path] for path in
              ("docs/TECHNICAL_DESIGN.md", "docs/DEVELOPMENT_PLAN_AND_REPORT.md", "docs/UPSTREAM_VERSION.md")))
    check("ten_frozen_files_unchanged", lambda:
          len(context["lock"]["files"]) == 10 and all(
              (ROOT / row["path"]).stat().st_size == row["size_bytes"] and
              digest((ROOT / row["path"]).read_bytes()) == row["sha256"] for row in context["lock"]["files"]))
    check("four_append_only_historical_prefixes_unchanged", lambda:
          len(context["lock"]["append_only_files"]) == 4 and all(
              digest((ROOT / row["path"]).read_bytes()[:row["original_size_bytes"]]) == row["original_prefix_sha256"]
              for row in context["lock"]["append_only_files"]))
    check("all_61_private_local_corpus_files_unchanged", lambda:
          len(context["local"]) == 61 and all(
              (ROOT / row["path"]).stat().st_size == row["size_bytes"] and
              digest((ROOT / row["path"]).read_bytes()) == row["sha256"] for row in context["local"]))

    def original_project_preserved():
        snapshot = read_json(ORIGINAL_SNAPSHOT)
        return len(snapshot) == 178 and all(
            digest((ORIGINAL_ROOT / path).read_bytes()) == sha for path, sha in snapshot.items())

    check("original_project_178_static_files_unchanged", original_project_preserved)
    check("original_project_has_no_root_git", lambda: ORIGINAL_ROOT.is_dir() and not (ORIGINAL_ROOT / ".git").exists())
    check("task7_measurement_policy_configuration_still_matches_before_snapshot", lambda:
          digest(CONFIG.read_bytes()) == context["before"]["tracked"]["config/dense_retrieval_b0.json"])

    summaries = {}
    for split, directory in (("dev", dev_dir), ("test", test_dir)):
        if split in context:
            value = context[split]
            summaries[split] = {"run_id": value["run_id"], "purpose": value["purpose"],
                "questions": value["quality"]["questions"],
                "answerable_denominator": value["quality"]["answerable_denominator"],
                "unanswerable_excluded": value["quality"]["unanswerable_excluded"],
                "metrics": value["quality"]["metrics"], "latency": value["latency"],
                "latency_by_answerability": value["latency_by_answerability"],
                "summary": file_record(directory / "summary.json"),
                "run_manifest": file_record(directory / "run_manifest.json")}
    return {"status": "PASS" if checks and all(checks.values()) else "FAIL",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "passed": sum(checks.values()), "total": len(checks), "checks": checks,
            "failed_checks": [name for name, passed in checks.items() if not passed], "errors": errors,
            "kind": "task7_local_preservation_and_saved_run_replay_gate",
            "real_model_requests_in_this_script": 0, "corpus_reencodings_in_this_script": 0,
            "real_test_runs_started_by_this_script": 0,
            "test_questions_or_individual_rankings_exposed_by_this_script": False,
            "private_preservation_inputs_required": [str(Path(preservation_snapshot).relative_to(ROOT)).replace('\\','/'),
                ".runtime/eval_review/reviews.jsonl", "data/indexes/dense/",
                "61 local corpus files", "original project and its 178-file snapshot"],
            "replay_scope": "Existing dev/test artifacts are validated and independently rescored; only aggregates are exposed.",
            "private_scope": "Local hashes prove preservation against the saved snapshot; no new human review or expert rules certification is claimed.",
            "summaries": summaries,
            "source_sha256": {name: digest((ROOT / "scripts" / name).read_bytes()) for name in
                ("verify_task7_delivery.py", "dense_retrieval_eval.py", "dense_retrieval_contracts.py","retrieval_metrics.py")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--dev-dir", type=Path, default=DEFAULT_BASE / "dev")
    parser.add_argument("--test-dir", type=Path, default=DEFAULT_BASE / "test")
    parser.add_argument("--authorization", type=Path, default=DEFAULT_BASE / "test_authorization.json")
    parser.add_argument("--test-usage", type=Path, default=DEFAULT_BASE / "test_usage.jsonl")
    parser.add_argument('--preservation-snapshot',type=Path,default=ROOT/'.runtime/task7/before.json')
    args = parser.parse_args()
    report = (ROOT / args.report).resolve()
    if report.suffix != ".json" or not report.is_relative_to(ROOT / "reports"):
        parser.error("Use a new JSON report under this repository's reports/")
    if report.exists():
        parser.error("Refusing to overwrite an existing report")
    paths = [(ROOT / value).resolve() for value in
             (args.dev_dir, args.test_dir, args.authorization, args.test_usage)]
    if any(not path.is_relative_to(ROOT / "reports") for path in paths):
        parser.error("Run evidence and authorization must stay under reports/")
    preservation=(ROOT/args.preservation_snapshot).resolve()
    if not preservation.is_relative_to(ROOT/'.runtime'):parser.error('Private preservation snapshot must stay under .runtime/')
    result = verify(*paths,preservation_snapshot=preservation)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status": result["status"], "passed": result["passed"], "total": result["total"],
                      "failed_checks": result["failed_checks"],
                      "report": report.relative_to(ROOT).as_posix()}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
