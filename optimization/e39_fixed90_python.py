"""UTF-8-safe fixed-90 runner for the E39 candidate.

The historical PowerShell launcher is kept for archival parity, but Windows
PowerShell 5.1 is slow and code-page sensitive when parsing the large Chinese
trace JSON. This runner uses the same worker boundary and flags, writes the
same per-question result shape, and leaves every raw worker trace untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def labels() -> list[dict]:
    values = []
    for name in ("dev_40.json", "regression_50.json"):
        values.extend(json.loads((ROOT / "optimization" / "datasets" / name).read_text("utf-8")))
    if len(values) != 90:
        raise ValueError(f"expected 90 labels, found {len(values)}")
    return sorted(values, key=lambda row: (row["question_id"][0], int(row["question_id"][1:])))


def env_for() -> None:
    os.environ.update({
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MODELS": str(ROOT / ".runtime" / "phase2" / "e10-models"),
        "OLLAMA_NO_CLOUD": "1",
        "FOOTBALL_SOURCE_FACTS": "1",
        "FOOTBALL_STRICT_SELECTION": "0",
        "FOOTBALL_GENERATION_DECISION": "0",
        "FOOTBALL_SELECTION_AUDIT": "1",
        "FOOTBALL_PACKING_FILL_TOP10": "0",
        "FOOTBALL_ANCHOR_GUARD": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ[key] = ""


def available_gib() -> float | None:
    try:
        import psutil
        return round(psutil.virtual_memory().available / (1024 ** 3), 3)
    except Exception:
        return None


def git_head() -> str:
    clean = {key: value for key, value in os.environ.items() if not key.startswith("GIT_CONFIG_")}
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, env=clean).strip()


def main(output: Path, resume: bool) -> None:
    if output.exists() and not resume:
        raise RuntimeError(f"output exists: {output}; use --resume")
    output.mkdir(parents=True, exist_ok=True)
    env_for()
    from task13_audit_client import call_worker

    all_labels = labels()
    manifest = {
        "status": "RUNNING", "experiment": "E39_fixed90_generation_candidate",
        "variant": "candidate", "source_commit": git_head(), "model": "qwen2.5:3b",
        "embedding": "bge-m3", "ollama_version": "0.40.16",
        "flags": {key: os.environ[key] for key in (
            "FOOTBALL_SOURCE_FACTS", "FOOTBALL_SELECTION_AUDIT", "FOOTBALL_ANCHOR_GUARD",
            "FOOTBALL_GENERATION_DECISION", "FOOTBALL_PACKING_FILL_TOP10")},
        "total": 90, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "completed": 0,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    for index, label in enumerate(all_labels, 1):
        qid = label["question_id"]
        path = output / f"{qid}-B.json"
        if resume and path.exists():
            continue
        started = time.perf_counter()
        before = available_gib()
        row = dict(label, name=qid, qid=qid, variant="candidate")
        try:
            result, trace, elapsed = call_worker(label["question"])
            row.update(result=result, status=result.get("status"), error=result.get("error"),
                       answer=result.get("answer"), selected_ids=result.get("selected_ids", []),
                       offered_ids=result.get("offered_ids", []), retrieved_ids=result.get("retrieved_ids", []),
                       refusal_reason=result.get("refusal_reason"), prompt_utf8_bytes=result.get("prompt_utf8_bytes"),
                       attempt_count=len(result.get("attempts", [])), attempts=result.get("attempts", []),
                       selection_audit=result.get("selection_audit"), generation_decision=result.get("generation_decision"),
                       fact_recovery=result.get("fact_recovery"), timing=result.get("timing"),
                       trace=trace, seconds=elapsed, resources={
                           "available_before_GiB": before, "available_after_GiB": available_gib(),
                           "available_min_GiB": min(x for x in (before, available_gib()) if x is not None)
                           if any(x is not None for x in (before, available_gib())) else None,
                       }, stderr="")
        except Exception as exc:
            elapsed = time.perf_counter() - started
            row.update(result=None, status="worker_error", error=f"{type(exc).__name__}: {exc}", answer=None,
                       selected_ids=[], offered_ids=[], retrieved_ids=[], refusal_reason=None,
                       prompt_utf8_bytes=None, attempt_count=0, attempts=[], selection_audit=None,
                       generation_decision=None, fact_recovery=None, timing=None, trace=None, seconds=elapsed,
                       resources={"available_before_GiB": before, "available_after_GiB": available_gib(),
                                  "available_min_GiB": before}, stderr="")
        path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", "utf-8")
        manifest["completed"] = index
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(json.dumps({"done": index, "total": 90, "qid": qid, "status": row["status"],
                          "selected_ids": row["selected_ids"], "seconds": row["seconds"],
                          "available_min_GiB": row["resources"]["available_min_GiB"],
                          "error": row["error"]}, ensure_ascii=False), flush=True)
    files = sorted(output.glob("[DT][0-9][0-9][0-9]-B.json"))
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    manifest.update({"status": "COMPLETED" if len(files) == 90 else "INCOMPLETE",
                     "completed": len(files), "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (output / "completed.json").write_text(json.dumps({"status": manifest["status"], "records": len(files), "hashes": hashes}, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (output / "summary.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"status": manifest["status"], "completed": len(files)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    main(args.out, args.resume)
