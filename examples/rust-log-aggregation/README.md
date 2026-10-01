# Measured Rust request-log aggregation example

This example preserves a genuine four-proposal, model-guided Rust hillclimb. The historical run used Codex Eval Lab commit 841a8ac4396bedd992b956338e42efbd9d4954c8 (0.2.0) with custom immutable-reference ABBA/BAAB pairing inside its protected Rust driver. It did **not** use the newer automation-first controller or new engine paired-cohort mode. The source selected by that original run confirmed 1.631× normalized paired kernel speedup on 36 sealed synthetic final cases, with exact correctness. See REPORT.md for confidence, candidate rejections and limitations.

The checked-in aggregate results are historical evidence, not results from rerunning this example. Source proposals were authored live after measurements; replaying them now is not another live model search.

## Reproduce using the current repository engine

From the repository root, with Linux x86_64 Rust 1.98.1 available:

    PYTHONPATH=src python examples/rust-log-aggregation/reproduce.py --rustc /absolute/path/to/rustc --out /a/new/run-directory --approve-local-benchmark

The script generates the deterministic corpus when absent, copies the frozen-style evaluator into a fresh state, replays archived source proposals, remeasures controls and candidates, reapplies selection gates, and opens one final comparison. It uses whichever engine is installed/on PYTHONPATH; that version must be recorded by the new run and must not be mislabeled as the historical 0.2 run. For exact historical engine bytes, use the full study bundle or checkout the commit above separately.

Files: app/ is the baseline plus protected driver/reference/wrapper; winner/aggregate.rs is the selected module; suite/ contains the independent Python oracle and configuration; generate_suite.py creates the 120 synthetic cases; proposals/ and artifacts/candidate-history.jsonl preserve live-authored changes and outcomes. No credentials, paid APIs, large state, compiled binary or downloaded toolchain is included.

These original final data are now public for reproduction. They must not be reused as fresh unseen confirmation for additional tuning. The replay helper passed syntax/help checks; a second full replay was not run.
