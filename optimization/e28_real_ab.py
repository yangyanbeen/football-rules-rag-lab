"""Real 3B A/B for the generation-decision and context-packing candidates.

This runner keeps the frozen Worker entrypoint and changes one opt-in switch at
a time. It writes only private runtime results under .runtime/phase2.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

GENERATION_CASES = [
    ("D011", "wrong_evidence_selection"),
    ("D019", "wrong_evidence_selection"),
    ("T014", "wrong_evidence_selection"),
    ("T018", "wrong_evidence_selection"),
    ("T028", "wrong_evidence_selection"),
    ("D021", "evidence_coverage_incomplete"),
    ("D026", "evidence_coverage_incomplete"),
    ("T004", "evidence_coverage_incomplete"),
    ("T023", "evidence_coverage_incomplete"),
    ("T026", "evidence_coverage_incomplete"),
    ("T032", "evidence_coverage_incomplete_and_false_refusal"),
    ("D003", "false_refusal_with_evidence"),
    ("D012", "false_refusal_with_evidence"),
    ("D032", "false_refusal_with_evidence"),
    ("T009", "false_refusal_with_evidence"),
    ("T015", "false_refusal_with_evidence"),
    ("T017", "false_refusal_with_evidence"),
]

CONTEXT_CASES = [("T034", "context_packing"), ("T022", "context_budget_control")]


def questions():
    found = {}
    for name in ("dev_40.json", "regression_50.json"):
        for row in json.loads((ROOT / "optimization" / "datasets" / name).read_text("utf-8")):
            found.setdefault(row["question_id"], row["question"])
    wanted = {qid for qid, _ in GENERATION_CASES + CONTEXT_CASES}
    missing = sorted(wanted - set(found))
    if missing:
        raise RuntimeError(f"missing frozen questions: {missing}")
    return found


def env_for(kind, variant):
    value = dict(os.environ)
    value.update(
        {
            "OLLAMA_HOST": "127.0.0.1:11434",
            "OLLAMA_MODELS": str(ROOT / ".runtime" / "phase2" / "e10-models"),
            "OLLAMA_NO_CLOUD": "1",
            "FOOTBALL_SOURCE_FACTS": "0",
            "FOOTBALL_STRICT_SELECTION": "0",
            "FOOTBALL_GENERATION_DECISION": "1" if kind == "generation" and variant == "B" else "0",
            "FOOTBALL_PACKING_FILL_TOP10": "1" if kind == "context" and variant == "B" else "0",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        value[key] = ""
    return value


def run_one(qid, question, kind, variant, repetition, call_worker):
    os.environ.update(env_for(kind, variant))
    started = time.perf_counter()
    row = {
        "qid": qid,
        "kind": kind,
        "variant": variant,
        "repetition": repetition,
        "question": question,
    }
    try:
        result, trace, elapsed = call_worker(question)
        row.update(
            {
                "status": result.get("status"),
                "answer": result.get("answer"),
                "selected_ids": result.get("selected_ids"),
                "offered_ids": result.get("offered_ids"),
                "retrieved_ids": result.get("retrieved_ids"),
                "refusal_reason": result.get("refusal_reason"),
                "prompt_utf8_bytes": result.get("prompt_utf8_bytes"),
                "attempt_count": len(result.get("attempts", [])),
                "attempts": [
                    {k: a.get(k) for k in ("attempt", "error", "prompt_eval_count", "eval_count", "done_reason")}
                    for a in result.get("attempts", [])
                ],
                "generation_decision": result.get("generation_decision"),
                "fact_recovery": result.get("fact_recovery"),
                "trace": trace,
                "elapsed_seconds": elapsed,
                "result": result,
                "error": None,
            }
        )
    except Exception as exc:
        row.update(
            {
                "status": "worker_error",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_seconds": time.perf_counter() - started,
            }
        )
    return row


def main(out: Path, context_repetitions: int = 2):
    from task13_audit_client import call_worker

    if out.exists():
        raise RuntimeError(f"output already exists: {out}")
    out.mkdir(parents=True)
    qs = questions()
    rows = []

    schedule = []
    for index, (qid, category) in enumerate(GENERATION_CASES):
        first = "A" if index % 2 == 0 else "B"
        schedule += [
            ("generation", qid, category, first, 1),
            ("generation", qid, category, "B" if first == "A" else "A", 1),
        ]
    for qid, category in CONTEXT_CASES:
        for repetition in range(1, context_repetitions + 1):
            first = "A" if repetition % 2 else "B"
            schedule += [
                ("context", qid, category, first, repetition),
                ("context", qid, category, "B" if first == "A" else "A", repetition),
            ]

    for index, (kind, qid, category, variant, repetition) in enumerate(schedule, 1):
        row = run_one(qid, qs[qid], kind, variant, repetition, call_worker)
        row["category"] = category
        rows.append(row)
        (out / f"{index:03d}-{kind}-{qid}-{variant}-{repetition}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", "utf-8"
        )
        print(
            json.dumps(
                {
                    "done": index,
                    "total": len(schedule),
                    "kind": kind,
                    "qid": qid,
                    "variant": variant,
                    "repetition": repetition,
                    "status": row.get("status"),
                    "selected_ids": row.get("selected_ids"),
                    "offered_ids": row.get("offered_ids"),
                    "elapsed_seconds": row.get("elapsed_seconds"),
                    "error": row.get("error"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    summary = {
        "status": "COMPLETED",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "model": "qwen2.5:3b",
        "ollama_version": "0.40.16",
        "generation_cases": len(GENERATION_CASES),
        "generation_observations": len(GENERATION_CASES) * 2,
        "context_cases": len(CONTEXT_CASES),
        "context_repetitions": context_repetitions,
        "rows": rows,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--context-repetitions", type=int, default=2)
    args = parser.parse_args()
    main(args.out, args.context_repetitions)
