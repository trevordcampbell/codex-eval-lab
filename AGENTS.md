# Working on Codex Eval Lab

This repository contains executable evaluation infrastructure, not just prompts.
Read README.md, docs/PROTOCOL.md, docs/SECURITY.md and docs/STATISTICS.md first.

Use Python 3.11+ and the standard library for the core. Run:

```sh
python -m unittest discover -v
python scripts/demo.py --out /a/new/directory/outside/this/repository
```

Install the package with `python -m pip install -e .` or set `PYTHONPATH=src`
for tests. Do not execute live Codex, provider calls, Docker pulls, or production
side effects without explicit user approval. The scripted demo is free and offline.
Never represent its scores as evidence of a model's performance.

Protect evaluator immutability, complete paired comparisons, independent group
splits, reservation-before-execution, indeterminate recovery, and final-test sealing.
Do not disable checks to make a test pass. Add a regression test for every fix.
Changing a suite or its grader requires a new approved experiment, not a covert
edit to a frozen manifest. Do not read held-out data during optimization.

No implicit deployment, force pushes, credential discovery, or unreviewed public
publishing. Return proposed source changes for review. Keep docs and the copies
in each skill's references directory synchronized; run
`python scripts/sync_skill_references.py --check`.

Never claim universal improvement, statistical certainty, provider-side spend
limits, hostile-code isolation, or successful live integration without evidence.
