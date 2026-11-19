# Phase 2 experiments

Only E1 is authorized in this iteration. The production prompt and frozen baseline remain unchanged until a candidate passes review and regression gates.

Datasets were sealed in commit 9c4f06a before candidate prompts or new model calls. New holdout40 is AI-authored and AI source-checked; human review is pending. It uses source paragraphs not used as gold in the original90, but shares the same corpus and author, so it is not a human-reviewed blind benchmark. Never read it in the E1 runner.

E1 replays the exact user/evidence messages captured by the frozen baseline graph. Only the system prompt changes. A is the byte-identical original. B adds question understanding and evidence matching. C adds numeric/condition/exception checks to B. All variants fit within A's byte length, preserving the exact same packed context and 6200-byte full-message limit. Existing schema, parser, up-to-two-attempt repair and safe rendering are reused unchanged. The model never receives evaluation labels.

Run with the isolated Task17 Python and a local pinned Ollama service:

`python -B optimization/run_experiments.py --trace-manifest <private baseline trace manifest> --out <new private run directory> --split dev --variants A B C`

Order rotates ABC/BCA/CAB by question. Deterministic pre-generation refusals are copied from their frozen graph traces and recorded as zero model calls, rather than bypassing version guards. Raw messages, schemas, model responses, parsing results and hashes stay in the private run directory. A neutral warm-up is recorded separately and excluded from quality and latency metrics. Source-supported semantic scoring is a separate post-run step; model self-reported confidence is never a score.
