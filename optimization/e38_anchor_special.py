"""Run E38's four deterministic evidence-anchor checks."""
from __future__ import annotations

import argparse, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
IDS = ("D022", "T019", "T022", "T036")


def load_questions():
    values = {}
    for name in ("dev_40.json", "regression_50.json"):
        for row in json.loads((ROOT / "optimization" / "datasets" / name).read_text("utf-8")):
            values[row["question_id"]] = row
    return values


def main(out: Path):
    from task13_audit_client import call_worker

    out.mkdir(parents=True, exist_ok=False)
    os.environ.update({
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MODELS": str(ROOT / ".runtime" / "phase2" / "e10-models"),
        "OLLAMA_NO_CLOUD": "1", "FOOTBALL_SOURCE_FACTS": "1",
        "FOOTBALL_SELECTION_AUDIT": "1", "FOOTBALL_GENERATION_DECISION": "0",
        "FOOTBALL_STRICT_SELECTION": "0", "FOOTBALL_ANCHOR_GUARD": "1",
        "FOOTBALL_PACKING_FILL_TOP10": "0", "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ[key] = ""
    qs = load_questions(); rows = []
    for index, qid in enumerate(IDS, 1):
        started = time.perf_counter(); row = {"qid": qid, "question": qs[qid]["question"],
            "expected_points": qs[qid]["expected_answer_points"]}
        try:
            result, trace, elapsed = call_worker(qs[qid]["question"])
            row.update(status=result.get("status"), answer=result.get("answer"),
                       selected_ids=result.get("selected_ids"), citations=result.get("citations"),
                       generation_decision=result.get("generation_decision"),
                       selection_anchor_guard=result.get("selection_anchor_guard"), trace=trace,
                       elapsed_seconds=elapsed)
        except Exception as exc:
            row.update(status="worker_error", error=f"{type(exc).__name__}: {exc}",
                       elapsed_seconds=time.perf_counter()-started)
        rows.append(row)
        (out / f"{index:02d}-{qid}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2)+"\n", "utf-8")
        print(json.dumps({"done": index, "total": len(IDS), "qid": qid,
                          "status": row.get("status"), "selected_ids": row.get("selected_ids"),
                          "seconds": row.get("elapsed_seconds"), "error": row.get("error")}, ensure_ascii=False), flush=True)
    (out / "summary.json").write_text(json.dumps({"status":"COMPLETED","experiment":"E38_anchor_special",
        "source_commit":os.popen("git rev-parse HEAD").read().strip(),"rows":rows}, ensure_ascii=False, indent=2)+"\n", "utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)

