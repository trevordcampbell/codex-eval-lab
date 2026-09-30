# Release validation — Codex Eval Lab 0.1.0

Recorded September 30, 2026, on Linux x86_64 / Python 3.13.5.

## Automated tests

**184 tests passed; zero failures.** The measured core statement coverage was
**91.4% (1,332/1,458 statements)**.
This percentage covers `src/codex_eval_lab`, not every script or optional adapter.
The test count includes CLI workflows, release/installer checks, a fake-provider judge
and a simulated Codex process. These are not live service tests.

The suite covers configuration errors, duplicate/group leakage, unknown metrics,
finite costs, paired statistics, regression guardrails, source/evaluator/runtime
changes, malformed proposals, protected edits, timeout/output bounds, interrupted
reservations and active-round resume, test sealing, escaped HTML, private-data
filtering, release hashes and non-overwriting installation/publishing behavior.

```sh
PYTHONPATH=src python -m coverage run --source=src/codex_eval_lab -m unittest discover -v
python -m coverage report
python scripts/sync_skill_references.py --check
```

`coverage` is a development-only tool. The tests themselves use `unittest` and do
not require it. See [test log](validation/tests.txt) and [summary](validation/summary.json).

## Complete offline hillclimb

The routing study ran **560 application-plus-grader trials** across 80 synthetic
cases with two repetitions, with three scripted proposal calls. It accepted the
case-normalization change and rejected two deliberately harmful proposals. The
selected variant's final held-out accuracy was **0.70 → 1.00**, a 0.30 absolute
delta on 20 final cases. Both the objective gate and zero-cost guardrail passed.
There were no pending trials at completion and evaluation cost was $0.

**This is a scripted functional test, not an evaluation of Codex's intelligence
or evidence of performance on real user traffic.** Dataset/example source is public
and synthetic; it is not a private benchmark. The fixture proposals were intentionally
chosen to test keeping and rejection. The untouched-by-controller final split tests
the lifecycle, not an adversarially secret holdout deployment.

See [recorded results](validation/routing-demo.json) and the
[annotated sample report](sample-report.html). Reproduce with:

```sh
python scripts/demo.py --out ../new-offline-demo
```

## Non-LLM software performance study

A separate **120-trial** synthetic integer-list study used a hand-authored replacement
of quadratic membership scanning with ordered hash deduplication. The final
case-averaged median kernel timing was approximately **1.097489 ms →
0.023789 ms**, while all measured correctness checks remained passing.
Both final gates passed. No optimizer/model calls were made.

This demonstrates a numeric minimization objective with a correctness constraint.
It is not a Codex-discovered speedup, a cross-machine benchmark or an end-to-end
application-latency result. Kernel timings are self-reported by cooperative test
code; use an independent timing harness for untrusted candidates.

[Recorded results](validation/benchmark-demo.json). Reproduce with:

```sh
python scripts/benchmark_demo.py --out ../new-benchmark-demo
```

## Packaging and report checks

The Python wheel built with `pip wheel --no-build-isolation --no-deps .`, installed
with `--no-index --no-deps` in a fresh virtual environment, and ran `eval-lab doctor`.
The installed core required no third-party runtime dependencies.

Generated HTML was rendered in system Chromium through Playwright `set_content`,
with desktop and 390-pixel mobile viewports. There were no page JavaScript errors;
all 320 development-case disclosures were searchable; an unmatched search hid all
of them; the mobile document had no horizontal overflow. The desktop and mobile
renderings were visually inspected. Native `file://` navigation was blocked by this
environment's browser policy, so file-URL loading itself was not verified.

## Publication validation — September 30, 2026

The public repository was created at
https://github.com/trevordcampbell/codex-eval-lab during the publishing session.
The source is being published as a normal directory tree, not a ZIP-only repository.
Fresh validation on Linux / Python 3.12.14 passed all 184 tests, skill-reference
synchronization, CLI doctor, and the complete 560-trial offline demonstration.
All original source hashes were checked before the README and this validation
record were updated. The release manifest is regenerated for those edits.

The initial source-delivery environment did not execute GitHub-hosted CI. The
publication session checks the committed revision separately; consult that
revision's GitHub Actions results and release notes for its hosted-CI status.
The bundled private-repository `gh` publishing script itself has not been live-tested;
this public publication uses a separate authenticated GitHub workflow.

## Remaining validation limits

Authenticated live Codex runs, actual provider judge requests, Docker containers,
and macOS/Windows execution remain unverified. CLI and provider integration
contracts are tested with simulated responses; command tests are not equivalent
to live compatibility. The original 91.4% coverage figure above is retained from
the initial Python 3.13.5 validation, not remeasured in the publication environment.

No claim of Claude-versus-Codex quality parity, superiority, universal improvement,
or production security certification is made by these checks.
