# Phase 2 experiments

Latest local status (2026-11-22): E15 low-memory fixed90 passed quality and resource gates. The sealed40 was subsequently used once: resource gates passed, citation support27/59 failed the predeclared threshold. Overall delivery is not accepted; no merge/push or default promotion. See [final E15 report](reports/E15_low_memory_final_report.md) and [low-memory usage](../docs/LOW_MEMORY_MODE.md). The original40 is now exposed and must not be reused as unseen data for tuning acceptance.

The following E1 instructions describe the historical first experiment; later experiments and their frozen plans/reports remain separate. The production prompt and original baseline artifacts are preserved.

Datasets were sealed in commit 9c4f06a before candidate prompts or new model calls. New holdout40 is AI-authored and AI source-checked; human review is pending. It uses source paragraphs not used as gold in the original90, but shares the same corpus and author, so it is not a human-reviewed blind benchmark. Never read it in the E1 runner.

E1 replays the exact user/evidence messages captured by the frozen baseline graph. Only the system prompt changes. A is the byte-identical original. B adds question understanding and evidence matching. C adds numeric/condition/exception checks to B. All variants fit within A's byte length, preserving the exact same packed context and 6200-byte full-message limit. Existing schema, parser, up-to-two-attempt repair and safe rendering are reused unchanged. The model never receives evaluation labels.

Run with the isolated Task17 Python and a local pinned Ollama service:

`python -B optimization/run_experiments.py --trace-manifest <private baseline trace manifest> --out <new private run directory> --split dev --variants A B C`

Order rotates ABC/BCA/CAB by question. Deterministic pre-generation refusals are copied from their frozen graph traces and recorded as zero model calls, rather than bypassing version guards. Raw messages, schemas, model responses, parsing results and hashes stay in the private run directory. A neutral warm-up is recorded separately and excluded from quality and latency metrics. Source-supported semantic scoring is a separate post-run step; model self-reported confidence is never a score.

Raw baseline90 and E1 runs are archived locally under `.runtime/phase2/`. The ignored `baseline/e8b0fd6/trace_manifest.local.json` points to the archived baseline traces. A source-review ledger and scoring script are committed so metrics can be recomputed without another model call:

`python -B optimization/score_experiments.py .runtime/phase2/e1-dev-1795089536973 --reviews optimization/experiments/E1_selection_prompt/source_reviews.tsv --out .runtime/phase2/recomputed-dev.json`

`python -B optimization/score_experiments.py .runtime/phase2/e1-test-1795090942706 --reviews optimization/experiments/E1_selection_prompt/source_reviews.tsv --out .runtime/phase2/recomputed-test.json`

The first run's replay adapter omitted the boundary suffix from the failed display message only. D016's raw responses, strict parsing failures and quality score are preserved unchanged; the adapter now includes the same failure notice and boundary as the graph. This presentation correction was made after measurement and does not retroactively modify the raw run or its producer hash.
