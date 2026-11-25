"""E39: isolated T022 expanded-rerank + evidence-selection pilot.

This runner deliberately does not enable the generation-decision layer,
selection audit, source-fact recovery, or anchor guard.  A controls-only
branch exposes the frozen top-10 prefix; the candidate expands the reranker
output to 20 and enables the opt-in evidence ordering pass.  It is a pilot,
not a fixed-90 gate.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git_head():
    # Codex injects indexed GIT_CONFIG_* variables.  A helper entry with an
    # empty value can make a child git process fail after a model subprocess;
    # the experiment identity does not need those injected credentials.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG_")}
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, env=env).strip()


def question():
    for name in ("dev_40.json", "regression_50.json"):
        for row in json.loads((ROOT / "optimization" / "datasets" / name).read_text("utf-8")):
            if row["question_id"] == "T022":
                return row
    raise RuntimeError("T022 is not present in the frozen labels")


def env_for(variant):
    value = dict(os.environ)
    value.update({
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MODELS": str(ROOT / ".runtime" / "phase2" / "e10-models"),
        "OLLAMA_NO_CLOUD": "1",
        "FOOTBALL_SOURCE_FACTS": "0",
        "FOOTBALL_SELECTION_AUDIT": "0",
        "FOOTBALL_GENERATION_DECISION": "0",
        "FOOTBALL_STRICT_SELECTION": "0",
        "FOOTBALL_ANCHOR_GUARD": "0",
        "FOOTBALL_PACKING_FILL_TOP10": "0",
        "FOOTBALL_RERANK_OUTPUT_K": "20" if variant == "B" else "10",
        "FOOTBALL_EVIDENCE_SELECT_EXPANDED": "1" if variant == "B" else "0",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value[key] = ""
    return value


def compact(result):
    retrieval = result.get("retrieval") or {}
    reranker = retrieval.get("reranker") or {}
    return {
        "status": result.get("status"),
        "error": result.get("error"),
        "refusal_reason": result.get("refusal_reason"),
        "retrieved_ids": result.get("retrieved_ids"),
        "offered_ids": result.get("offered_ids"),
        "selected_ids": result.get("selected_ids"),
        "citations": [c.get("chunk_id") for c in result.get("citations", [])],
        "prompt_utf8_bytes": result.get("prompt_utf8_bytes"),
        "attempt_count": len(result.get("attempts", [])),
        "reranker_return_ids": [r.get("chunk_id") for r in retrieval.get("results", [])],
        "reranker_full_top20": [r.get("chunk_id") for r in reranker.get("results", [])[:20]],
        "timing": result.get("timing"),
    }


def archived_inputs():
    """Use the already captured full reranker packet; do not rerun retrieval."""
    trace = ROOT / ".runtime" / "phase2" / "e36-fixed90-version-gate" / "T022-B.json"
    value = json.loads(trace.read_text("utf-8"))["result"]
    corpus = {
        json.loads(line)["chunk_id"]: json.loads(line)
        for line in (ROOT / "data" / "processed" / "rag_chunks_zh.jsonl").read_text("utf-8").splitlines()
        if line.strip()
    }
    retrieval = value["retrieval"]
    full = [row["chunk_id"] for row in retrieval["reranker"]["results"]]
    top10 = [row["chunk_id"] for row in retrieval["results"]]
    return value["question"], corpus, full, top10


def run_one(label, variant, repetition):
    os.environ.update(env_for(variant))
    started = time.perf_counter()
    row = {"qid": "T022", "variant": variant, "repetition": repetition,
           "question": label["question"], "flags": {
               "FOOTBALL_RERANK_OUTPUT_K": os.environ["FOOTBALL_RERANK_OUTPUT_K"],
               "FOOTBALL_EVIDENCE_SELECT_EXPANDED": os.environ["FOOTBALL_EVIDENCE_SELECT_EXPANDED"],
               "FOOTBALL_GENERATION_DECISION": "0", "FOOTBALL_ANCHOR_GUARD": "0",
           }}
    try:
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from answer_eval_core import config, parse_selection, render
        from answer_eval_engine import pack, request_json
        from answer_json_chat import selection_schema
        from rag_b0 import PinnedChat
        question_text, corpus, full, top10 = archived_inputs()
        ids = top10 if variant == "A" else full[:20]
        evidence = [corpus[cid] for cid in ids]
        cfg = config()
        prompt = (ROOT / cfg["prompt_file"]).read_text("utf-8")
        context, messages, size = pack(question_text, evidence, cfg, prompt)
        chat = PinnedChat(cfg)
        chat.verify_model()
        selection, attempts, error = request_json(
            chat, messages, cfg,
            lambda text: parse_selection(text, [r["chunk_id"] for r in context], cfg),
            selection_schema([r["chunk_id"] for r in context], cfg["max_selected_chunks"]),
        )
        if error:
            raise ValueError(error)
        selected = selection["chunk_ids"] if selection["answerable"] else []
        answer, citations = render(selected, {r["chunk_id"]: r for r in context})
        result = {
            "status": "answered" if selection["answerable"] else "refused",
            "error": None, "refusal_reason": selection.get("reason"),
            "answer": answer, "citations": citations, "selected_ids": selected,
            "retrieved_ids": ids, "offered_ids": [r["chunk_id"] for r in context],
            "prompt_utf8_bytes": size, "attempts": attempts,
            "timing": {"retrieval_seconds": 0.0, "generation_seconds": sum(a.get("seconds", 0.0) for a in attempts),
                       "total_seconds": sum(a.get("seconds", 0.0) for a in attempts)},
            "retrieval": {"results": [{"chunk_id": cid} for cid in ids],
                          "reranker": {"results": [{"chunk_id": cid} for cid in full]}},
        }
        row.update({"status": "completed", "result": result, "summary": compact(result)})
    except Exception as exc:
        row.update({"status": "blocked", "error": f"{type(exc).__name__}: {exc}"})
    row["elapsed_seconds"] = time.perf_counter() - started
    return row


def main(out, repetitions):
    out = Path(out)
    if out.exists():
        raise RuntimeError(f"output already exists: {out}")
    out.mkdir(parents=True)
    label = question()
    rows = []
    for repetition in range(1, repetitions + 1):
        for variant in (("A", "B") if repetition % 2 else ("B", "A")):
            row = run_one(label, variant, repetition)
            rows.append(row)
            (out / f"{len(rows):02d}-T022-{variant}-r{repetition}.json").write_text(
                json.dumps(row, ensure_ascii=False, indent=2) + "\n", "utf-8"
            )
            print(json.dumps({"done": len(rows), "total": repetitions * 2,
                              "variant": variant, "repetition": repetition,
                              "status": row["status"], "summary": row.get("summary"),
                              "error": row.get("error")}, ensure_ascii=False), flush=True)
    completed = sum(row["status"] == "completed" for row in rows)
    summary = {
        "status": "COMPLETED" if completed == len(rows) else "BLOCKED",
        "experiment": "E39_t022_expanded_rerank_evidence_selection",
        "source_commit": git_head(),
        "model": "qwen2.5:3b",
        "ollama_version": "0.40.16",
        "repetitions": repetitions,
        "rows": rows,
        "scope": "T022 only; no generation decision, selection audit, source facts, or anchor guard",
        "holdout_used": False,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({k: summary[k] for k in ("status", "experiment", "repetitions")}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=2)
    args = parser.parse_args()
    main(args.out, args.repetitions)


