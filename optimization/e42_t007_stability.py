"""Repeat T007 with frozen retrieval and the opt-in generation selector."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
QUESTION = "守门员能佩戴手套，其他队员是否也被允许戴手套？"


def set_variant(candidate: bool) -> None:
    os.environ.update({
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MODELS": str(ROOT / ".runtime" / "phase2" / "e10-models"),
        "OLLAMA_NO_CLOUD": "1",
        "FOOTBALL_SOURCE_FACTS": "1",
        "FOOTBALL_SELECTION_AUDIT": "1" if candidate else "0",
        "FOOTBALL_ANCHOR_GUARD": "1" if candidate else "0",
        "FOOTBALL_GENERATION_DECISION": "1" if candidate else "0",
        "FOOTBALL_STRICT_SELECTION": "1" if candidate else "0",
        "FOOTBALL_PACKING_FILL_TOP10": "0",
        "FOOTBALL_RERANK_OUTPUT_K": "10",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ[key] = ""


def main(out: Path) -> None:
    from task13_audit_client import call_worker

    out.mkdir(parents=True, exist_ok=False)
    rows = []
    for repetition in range(1, 5):
        for variant in ("A", "B"):
            set_variant(variant == "B")
            started = time.perf_counter()
            row = {"qid": "T007", "variant": variant, "repetition": repetition}
            try:
                result, trace, elapsed = call_worker(QUESTION)
                row.update(status=result.get("status"), selected_ids=result.get("selected_ids"),
                           citations=[c.get("chunk_id") for c in result.get("citations", [])],
                           answer=result.get("answer"), trace=trace, seconds=elapsed)
            except Exception as exc:
                row.update(status="worker_error", error=f"{type(exc).__name__}: {exc}",
                           seconds=time.perf_counter() - started)
            rows.append(row)
            print(json.dumps({k: row.get(k) for k in ("qid", "variant", "repetition", "status", "selected_ids", "seconds", "error")}, ensure_ascii=False), flush=True)
    result = {"status": "COMPLETED", "experiment": "E42_t007_stability", "rows": rows,
              "required_ids": ["L04-05"], "default_candidate": "off"}
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    main(parser.parse_args().out)
