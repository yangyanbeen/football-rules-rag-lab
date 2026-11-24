"""Run the real E27 strict-selection A/B special set through the audit Worker."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

IDS = ("T022", "D019", "T026", "D003", "D012", "D004", "D009", "D036")


def load_questions():
    values = {}
    for name in ("dev_40.json", "regression_50.json"):
        rows = json.loads((ROOT / "optimization" / "datasets" / name).read_text("utf-8"))
        for row in rows:
            values.setdefault(row["question_id"], row["question"])
    missing = [qid for qid in IDS if qid not in values]
    if missing:
        raise ValueError(f"missing questions: {missing}")
    return values


def main(out: Path):
    from task13_audit_client import call_worker

    out.mkdir(parents=True, exist_ok=False)
    questions = load_questions()
    schedule = []
    for index, qid in enumerate(IDS):
        # Alternate AB/BA order so one model state/order does not own a variant.
        first = "A" if index % 2 == 0 else "B"
        schedule.extend((dict(qid=qid, variant=first), dict(qid=qid, variant="B" if first == "A" else "A")))
    (out / "schedule.json").write_text(json.dumps(schedule, ensure_ascii=False, indent=2) + "\n", "utf-8")
    rows = []
    for index, item in enumerate(schedule, 1):
        os.environ["FOOTBALL_STRICT_SELECTION"] = "1" if item["variant"] == "B" else "0"
        os.environ["OLLAMA_HOST"] = "127.0.0.1:11434"
        os.environ["OLLAMA_MODELS"] = str(ROOT / ".runtime" / "phase2" / "e10-models")
        os.environ["OLLAMA_NO_CLOUD"] = "1"
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            os.environ[key] = ""
        started = time.perf_counter()
        value = {"qid": item["qid"], "variant": item["variant"], "question": questions[item["qid"]]}
        try:
            result, trace, elapsed = call_worker(questions[item["qid"]])
            value.update(
                status=result.get("status"),
                selected_ids=result.get("selected_ids"),
                answer=result.get("answer"),
                citations=result.get("citations"),
                answerable=result.get("answerable"),
                trace=trace,
                elapsed_seconds=elapsed,
                result=result,
            )
        except Exception as exc:
            value.update(status="worker_error", error=f"{type(exc).__name__}: {exc}", elapsed_seconds=time.perf_counter() - started)
        rows.append(value)
        (out / f"{index:02d}-{item['qid']}-{item['variant']}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(json.dumps({"done": index, "total": len(schedule), "qid": item["qid"], "variant": item["variant"], "status": value.get("status"), "selected_ids": value.get("selected_ids"), "elapsed_seconds": value.get("elapsed_seconds"), "error": value.get("error")}, ensure_ascii=False), flush=True)
    summary = {"status": "COMPLETED", "calls": len(rows), "rows": rows, "source_commit": os.popen("git rev-parse HEAD").read().strip(), "strict_env": "per-call 0/1"}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    main(args.out)
