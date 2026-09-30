# Validation — Codex Eval Lab 0.1.0

Updated September 30, 2026. This record distinguishes current local checks,
verified GitHub checks, and earlier recorded experiments.

## Current local checks

On Linux / Python 3.12.14, the editorial update passed **186 tests, zero failures**.
Two tests were added to the original 184-test suite to verify documentation SVG
packaging and symlink rejection. Runtime engine code is unchanged.

Skill-reference synchronization passed after copying the updated operating guide
into all four self-contained skills. All source hashes in RELEASE_MANIFEST.json
were regenerated. Both new SVG figures were rendered and visually inspected;
they contain no scripts, external references, or embedded HTML.

Reproduce after installing the package:

```sh
python -m unittest discover -v
python scripts/sync_skill_references.py --check
```

The tests cover configuration validation, grouping/leakage, metric and cost checks,
paired statistics, guardrails, frozen evaluator/source changes, malformed proposals,
protected files, time/output limits, recovery, final-test sealing, report escaping,
private-data filtering, packaging and non-overwriting installation behavior.
Simulated Codex and provider responses test integration contracts, not live services.

## GitHub publication and hosted CI

The complete structured repository is public at
https://github.com/trevordcampbell/codex-eval-lab .

Initial publication commit `d01b1770bcee381f77b54b417874016c1880aaab` was independently
verified: all 89 initial files matched the reviewed source by path, Git blob hash,
byte size, and mode. The editorial update adds two original documentation figures.

[The initial publication CI run](https://github.com/trevordcampbell/codex-eval-lab/actions/runs/36675694829)
passed on Python 3.11, 3.12, and 3.13: installation, the original 184-test suite,
skill synchronization and CLI smoke checks. The full offline demo passed on
Python 3.13; it was intentionally skipped on the other versions.

For later revisions, including the 186-test editorial update, use that revision's
[GitHub Actions results](https://github.com/trevordcampbell/codex-eval-lab/actions)
as the authoritative hosted-CI status. A local pass is not a hosted-CI result.
The bundled private-repository `gh` publishing script itself remains untested live;
this public repository was published through a separate authenticated workflow.

## Reproduced offline experiment

The routing demo was rerun successfully during publication: **560 trials**, three
scripted proposals, no pending reservations, and **$0 evaluation cost**. It retained
case normalization and rejected two deliberately harmful proposals. Its recorded
final accuracy on 20 synthetic cases was **0.70 → 1.00**.

These are synthetic inputs and hand-authored proposals. They verify experiment
mechanics, not Codex intelligence, real customer performance, or secret-holdout
security. See [recorded results](validation/routing-demo.json) and the
[sample report](sample-report.html).

```sh
python scripts/demo.py --out ../new-offline-demo
```

## Earlier measurements retained for provenance

The original Linux / Python 3.13.5 report measured **91.4% core statement coverage**
(1,332 / 1,458 statements) with the then-current 184-test suite. Coverage was not
remeasured for this update; the number excludes scripts and optional adapters.

The original separate **120-trial** software benchmark used a hand-authored ordered
hash-deduplication change. Its recorded final case-averaged median kernel timing
was approximately **1.097489 ms → 0.023789 ms**, with measured correctness passing.
It is cooperative self-reported kernel timing, not a Codex-discovered speedup or
end-to-end latency result. See [record](validation/benchmark-demo.json).

The original wheel build, clean-environment wheel installation and CLI check passed.
The original HTML report was rendered at desktop and mobile widths in Chromium;
search/disclosure behavior passed without horizontal overflow or JavaScript errors.
These earlier records are preserved in `docs/validation/` with their measurement
scope; they do not certify every later environment or integration.

## Still unverified

- Authenticated live Codex optimization and live provider-judge requests
- Actual Docker container execution and its platform-specific behavior
- macOS and Windows execution
- Live execution of the bundled `gh` publisher

No model-quality parity, superiority, universal improvement, or production-security
certification is established by these checks. Read [security](SECURITY.md) before
running untrusted code, using sensitive data, or making paid calls.
