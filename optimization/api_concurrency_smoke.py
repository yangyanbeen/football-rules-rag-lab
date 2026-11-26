"""Measure the current HTTP API queue with real normal-answer requests."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import statistics
import time
import urllib.request
from pathlib import Path


QUESTION = "请按出界位置与最后触球队，区分界外球、球门球和角球的通常归属。"


def call(url: str, index: int, timeout: float) -> dict:
    body = json.dumps({"question": QUESTION}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url + "/chat", data=body, headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
        return {"index": index, "ok": True, "status": payload["result"]["status"],
                "seconds": time.perf_counter() - started,
                "selected_ids": payload["result"].get("selected_ids", [])}
    except Exception as exc:
        return {"index": index, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                "seconds": time.perf_counter() - started}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    batches = []
    for concurrency in (1, 2, 4):
        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            rows = list(pool.map(lambda i: call(args.base_url, i, args.timeout), range(concurrency)))
        durations = [row["seconds"] for row in rows]
        batches.append({"concurrency": concurrency, "wall_seconds": time.perf_counter() - started,
                        "completed": sum(row["ok"] for row in rows),
                        "p95_seconds": max(durations) if durations else None,
                        "durations": rows})
    result = {"question": QUESTION, "batches": batches,
              "method": "real HTTP /chat calls; p95 is max for these small batches"}
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
