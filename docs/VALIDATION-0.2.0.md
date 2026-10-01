# Validation — Codex Eval Lab 0.2.0

Updated October 1, 2026. This record distinguishes final local checks for the
0.2.0 working tree, hosted CI, and historical 0.1 measurements. Local checks do
not establish live model performance or production security.

## Current local checks

On Linux x86_64, with the frozen atomic judge example included:

| Environment | Result |
| --- | --- |
| Python 3.11.16, MCP 2.2.0 and OpenAI 3.22.1 | **358 tests passed, zero skips** |
| Python 3.14.8, MCP 2.2.0 and OpenAI 3.22.1 | **358 tests passed, zero skips** |
| Python 3.14.8, dependency-free core | **358 discovered: 354 passed, 4 expected SDK skips** |

Every environment passed `pip check`. The core-only skips are two installed
OpenAI SDK contracts and two installed MCP SDK protocol checks; all four passed
with the optional extras. Before the final 32 atomic-judge tests were added,
Python 3.14.7 also passed all then-current 326 tests, without skips. That earlier
result is not a 358-test pass.

The core continues to require no third-party runtime dependencies. Both optional
extras and packaging tools were installed from the committed hash locks. Packaging
used pip 26.2.1, setuptools 84.0.0, build 1.6.1 and wheel 0.48.0. See the
[dependency record](DEPENDENCIES.md) for versions, sources and compatibility limits.

The final checks cover:

- Existing configuration, grouped splits, paired statistics, guardrails, frozen
  evaluator/source changes, edit scope, time/output limits, budget reservations,
  recovery, final-test sealing, report escaping and release/install safeguards
- Content-bound review packets, human annotations and criterion anchors,
  independent judge-tuning/validation groups, per-criterion calibration support
  and uncertainty, disagreement reporting, drift and executable evidence gates
- Adversarial stale/tampered records, incomplete or skipped criteria, malformed
  provider evidence, model/usage mismatches and approval-boundary handling
- Both rubric and atomic OpenAI judge adapters using the installed 3.22.1 SDK
  with an offline HTTP transport, explicit retry policy and served-usage costs
- MCP 2.2.0 real client dispatch and stdio protocol, read-only tool scope,
  resource metadata and relocated plugin launcher behavior
- Codex CLI 0.159.3 in an isolated temporary home: version, help flags and the
  complete adapter argument shape, with `--help` short-circuiting execution

No authenticated Codex run, provider request or paid call occurred. The real SDK
checks verify local request/response contracts with synthetic fixtures, not live
service behavior or the accuracy of a model judge.

### Python 3.14.8 build scope

The current Python.org stable source release was built locally because available
prebuilt 3.14 toolchains lagged at 3.14.7. SQLite 3.53.4 transactions, ctypes native
calls and OpenSSL 3.5.7 context creation were verified after installation. The
source-built interpreter lacks nine optional extensions because host development
headers were unavailable: `_bz2`, `_curses`, `_curses_panel`, `_dbm`, `_gdbm`,
`_lzma`, `_tkinter`, `_uuid` and `readline`. Project tests passed; this is not a
claim of a complete general-purpose Python build or a CPython regression-suite run.

### Browser UI and packaging

The pinned UI was rebuilt and tested on **Node 26.10.0 Current and Node 24.21.0
LTS**, each with npm 12.2.0: **17 tests passed on each, zero skips**. Both clean
locked installs and dependency-tree checks passed. The generated assets were
byte-for-byte identical across those two builds. The tests use the released
MCP Apps 2.0.3 App/AppBridge classes and cover connection, packet selection,
annotation persistence, validated draft import/export, cancellation, asynchronous
race handling, filters and disagreement navigation.

These are executable DOM/protocol tests with synthetic window transport. They do
not verify native host rendering, pixel layout, browser-enforced CSP or real
browser download dialogs. Native in-app rendering remains unverified.

Skill-reference synchronization and CLI `doctor` passed. Source release ZIP,
sdist, wheel and self-contained local plugin builds passed. Repeated plugin
builds were byte-for-byte identical; plugin validation checked structure,
checksums and the relocated no-scope launcher. The root release manifest is
regenerated from the release allowlist and excludes itself from its file hashes.
The 0.2.0 wheel was built, but a clean-environment wheel installation has not been
repeated for this revision.

Reproduce the Python checks after installing the desired dependency set:

```sh
python -m pip install --require-hashes -r requirements/ci.txt
python -m pip install --require-hashes -r requirements/plugin.txt -r requirements/judge.txt
python -m pip install -e '.[plugin,judge]'
python -m pip check
python -m unittest discover -v
python scripts/sync_skill_references.py --check
```

To include the no-model CLI check, set `EVAL_LAB_CODEX_BINARY` to an isolated
Codex 0.159.3 executable. Without it, that optional check is skipped. For core-only
validation, omit both optional dependency locks and install `-e .` instead.

## Hosted CI and publication

The repository is public at
[trevordcampbell/codex-eval-lab](https://github.com/trevordcampbell/codex-eval-lab).
Hosted CI for the final **0.2.0 commit is pending verification** in this local
record. Consult the exact commit's
[GitHub Actions results](https://github.com/trevordcampbell/codex-eval-lab/actions);
a local pass is not a hosted-CI result. The workflow tests Python 3.11–3.14, plus
optional extras and UI builds on the newest stable and LTS Node lines.

The historical initial publication commit
`d01b1770bcee381f77b54b417874016c1880aaab` was verified by path, Git blob hash,
size and mode for all 89 initial files. Its
[CI run](https://github.com/trevordcampbell/codex-eval-lab/actions/runs/36675694829)
passed the original 184 tests on Python 3.11–3.13 and the offline demo on Python
3.13. Those results do not certify 0.2.0. The bundled `gh` publisher has not been
executed live; publication used a separate authenticated workflow.

## Historical 0.1 measurements retained for provenance

The original Linux/Python 3.13.5 run measured **91.4% core statement coverage**
(1,332 / 1,458 statements) with 184 tests. The later editorial check on Python
3.12.14 passed 186 tests. **Coverage has not been remeasured for 0.2.0**; the old
percentage excludes scripts, optional adapters and the newly added runtime code.
These records remain separately labeled in [summary.json](validation/summary.json).

The recorded offline routing study used 560 application-plus-grader trials and
three hand-authored proposals at $0 evaluation cost. It retained normalization,
rejected two harmful proposals and recorded final synthetic accuracy of
0.70 → 1.00 on 20 cases. See the [record](validation/routing-demo.json) and
[sample report](sample-report.html). This is historical fixture evidence, not
live Codex performance or secret-holdout security.

The historical 120-trial software benchmark used a hand-authored ordered
hash-deduplication change, recording case-averaged median kernel timing of about
1.097489 ms → 0.023789 ms with measured correctness passing. This is cooperative
self-reported kernel timing, not a Codex-discovered speedup or end-to-end latency
result. See the [benchmark record](validation/benchmark-demo.json).

The original 0.1 wheel installation in a clean environment and desktop/mobile
Chromium report checks passed. They do not certify the new plugin or every later
revision. Older raw reports under `docs/validation/` retain their historical scope.

## Still unverified

- Hosted CI for the exact final 0.2.0 commit
- Authenticated live Codex optimization and live provider-judge requests
- Native Codex/MCP Apps host rendering and production-hosted authenticated service
- Actual Docker container execution; macOS and Windows execution
- Clean-environment 0.2.0 wheel installation and current statement coverage
- Live execution of the bundled `gh` publisher

No model-quality parity, superiority, universal improvement or production-security
certification is established. Read [security](SECURITY.md) before running
untrusted code, using sensitive data or making paid calls.
