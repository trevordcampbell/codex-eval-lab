# Validation — Codex Eval Lab 0.3.0

Recorded October 1, 2026. This is a dated record of local checks on the 0.3.0
source revision. It does not establish publication, tagging or hosted-CI status.
Consult the exact revision's [GitHub Actions results](https://github.com/trevordcampbell/codex-eval-lab/actions)
for hosted CI; local checks are not hosted-CI results.

## Current local scope

The final 0.3.0 source revision passed **379 tests, zero skips** on
Linux x86_64 using Python 3.14.8, MCP 2.2.0 and OpenAI SDK 3.22.1. This includes
**21 new regression tests** for the temporal protocol and manual decision audit
trail. The complete suite was rerun after the version metadata and MCP server
version binding were updated.

The tests cover deterministic adjacent AB/BA schedules, per-case/overall order
balance, complete matching case/repetition/seed matrices, fresh incumbent and
original-baseline cohorts, source-hash reference deduplication, independent A/A
roles, budget limits, conservative indeterminate recovery, no partial-pair retry,
source/schedule identity, final seals, development-only optimizer evidence,
cohort-specific reports and atomic manual promotion/rejection records.

A synthetic unchanged-code monotone-drift regression demonstrates an artifact:
blocked measurements can clear the improvement gate while balanced adjacent
pairs do not. This is a constructed protocol counterexample, not empirical
performance evidence about Rust or any production application. Pairing reduces
slow drift but does not eliminate environmental confounding or adaptive selection.

## Offline integration demonstrations

The final 0.3.0 revision reran both completely offline routing workflows:

| Design | Trials | Cohorts | Decisions | Evaluation cost |
| --- | ---: | ---: | --- | ---: |
| Default variant-blocked | 560 | Not applicable | Keep first proposal, reject next two, final passes | $0 |
| Opt-in paired AB/BA | 800 | 6 | Keep first proposal, reject next two, final passes | $0 |

These use synthetic cases and hand-authored proposals. They do not establish live
Codex performance, model quality, production latency or independent holdout
security. See the new [paired routing record](validation/paired-routing-demo.json)
and [default routing record](validation/default-routing-demo-0.3.json).

The SDK checks use offline transports; the Codex CLI 0.159.3 check uses isolated
configuration and `--help` to stop before model execution. No authenticated model,
provider request or paid service call occurred during this revision's validation.

## Packaging and UI

The source version is 0.3.0 across Python, skill installer, MCP server, plugin
manifests and review UI metadata. The dependency locks remain unchanged apart from
the UI package's own version. The review UI was rebuilt with Node 26.10.0; all 17 DOM/protocol tests passed,
with zero skips. Source archive, sdist, wheel and self-contained plugin builds
passed, including plugin structure/checksums and relocated launcher validation.
The wheel installed into a fresh isolated target directory and its CLI doctor
reported version 0.3.0. This is an install-target smoke check, not a repeated
clean-virtualenv cross-platform certification. The release manifest is regenerated
from the reviewed allowlist after final documentation updates. Native host
rendering, real browser download dialogs, actual Docker
execution and macOS/Windows execution remain unverified.

## Reproduction

Use the committed dependency locks and existing commands:

```sh
python -m unittest discover -v
python scripts/sync_skill_references.py --check
python -m codex_eval_lab doctor
python scripts/package_release.py --out /a/new/source-archive-directory
python -m build --no-isolation --outdir /a/new/package-directory
python scripts/build_plugin.py --out /a/new/plugin-directory
python scripts/validate_plugin.py /a/new/plugin-directory/catalog/plugins/codex-eval-lab
```

Set `PYTHONPATH=src` when the checkout is not installed. Set
`EVAL_LAB_CODEX_BINARY` to the already provisioned stable CLI to include its
no-model argument check. Optional SDK contract tests require the pinned extras.
Review dependencies before installation; none are fetched by the tests.

## Prior validation retained

The complete [0.2.0 validation record](VALIDATION-0.2.0.md) and its
[machine-readable summary](validation/summary-0.2.0.json) are retained unchanged.
They include the earlier Python 3.11/3.14 checks, UI/toolchain audit, historical
0.1 benchmark and coverage evidence, and their original limitations. Those
measurements do not certify 0.3.0. Statement coverage has not been remeasured for
this revision.

Existing frozen Rust experiment source and state are separate and unchanged.
Its performance findings are not claimed as validation of the new measurement
protocol. Read [the operating guide](OPERATING_GUIDE.md) before approving a new
paired experiment; a protocol change must not be retrofitted into old state.
