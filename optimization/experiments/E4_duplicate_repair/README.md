# E4 artifacts and reproduction

This experiment changes only duplicate normalization and private graph auditing. Prompt A, schema, model, retrieval, context packing, source checks, body hashes and the two-attempt ceiling stay fixed. The production code changes were committed as `790ba09`; baseline `e8b0fd6` and E1 results are preserved.

Use `.runtime/task17/venv/Scripts/python.exe` from the project root. New model runs require the existing pinned loopback Ollama service; use a new output directory to preserve prior traces.

```powershell
# Offline contracts and captured-response replay, with zero live inference:
python -B optimization/verify_e4_duplicate_repair.py --out .runtime/phase2/e4-unit-repeat.json
python -B optimization/verify_e4_controls.py . .runtime/phase2/e4-controls-repeat.json
python -B optimization/run_e4_regression.py --mode replay --out .runtime/phase2/e4-replay-repeat

# Fresh full-graph evaluation on the original 90 questions; Prompt A only:
python -B optimization/run_e4_regression.py --mode live --out .runtime/phase2/e4-live-repeat

# Recompute the archived actual run's semantic metrics without new inference:
python -B optimization/score_experiments.py .runtime/phase2/e4-live90/score-dev --reviews optimization/experiments/E4_duplicate_repair/source_reviews.tsv --out .runtime/phase2/e4-live-dev-metrics.json
python -B optimization/score_experiments.py .runtime/phase2/e4-live90/score-test --reviews optimization/experiments/E4_duplicate_repair/source_reviews.tsv --out .runtime/phase2/e4-live-test-metrics.json
python -B optimization/summarize_e4.py --browser-report .runtime/phase2/e4-browser/report.json --out optimization/reports
```

The archived runs are `.runtime/phase2/e4-replay90` and `e4-live90`. Each stores per-question messages, schema, raw responses, normalized selections, parser comparison, graph timings, hashes and completion receipts. D016 and D010 are the first two live cases and are included in the same 90 unique questions. Warm-up is stored separately and excluded. The 22 historical errors and 18 unanswerable cases are subsets, not extra samples. The new holdout40 remains sealed and unused.

The source-review ledger reuses byte-identical answers or previously reviewed question/source combinations and separately audits new combinations against the same frozen corpus. It is Codex AI review, not a claim of new human or referee expert approval. The legacy scorer's `selection_seconds_*` keys are generic fields; E4 derived views contain full graph wall time. The E4 report recomputes and names graph end-to-end metrics explicitly.

Parser tests passed 32/32, mechanism checks 25/25, actual graph technical completion 90/90, and browser checks 8/8. The shared refusal gate remains incomplete because D036 answered conditionally rather than obeying its `must_refuse` label (17/18). No label was changed and no E5 code was implemented. The repair remains on its separate local branch for review.
