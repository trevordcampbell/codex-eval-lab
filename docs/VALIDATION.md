# Validation — unreleased source targeting 0.5.0

Recorded October 2, 2026. This record distinguishes tested implementation bytes,
review-only documentation, and later source/packaging changes. It is not a
published release, tag or hosted-CI result. Comparative measurements are separately scoped below.

## Exact core evidence

Implementation commit `0ce0131badf71741054cef9b3b20852083e42ea5` is based on
0.4.0 main commit `8b8578a`. Commit `4d1ad4d05c0120938e0754c90f0ed40a7a861fe3`
adds the [machine-readable validation record](validation/optimizer-upgrade-core.json),
including SHA-256 for every measured runtime module. That runtime still reported
version 0.4.0. Runtime hashes, not a shared version string, identify the tested code.

- The final full core suite reported **510 tests, OK with 3 optional skips**
- Earlier checks reported 509 tests with 3 skips, then 65 independent targeted tests
  and 20 bounded-response/feedback tests; these are separate runs, not counts to add
  together or substitutes for the final aggregate
- The recorded environment used isolated Python 3.12.14 with MCP 2.2.0. The three
  skips were two optional OpenAI SDK transport tests (SDK not installed) and an
  opt-in installed-Codex-binary argument test (not enabled). No paid provider
  operation was run. Exact historical shell-command flags were not recovered;
  unittest discovery on the isolated final source is the recorded scope
- Independent review reported no unresolved concrete high- or medium-severity
  integrity finding in the reviewed core scope; this is a scoped code review,
  not certification of security or scientific validity

The record's `live_study: "not yet started"` describes its capture time. It does
not provide a current study status or a result. The later [completed transfer pilot](validation/optimizer-transfer-pilot.md) records
New/Old/Direct results separately and makes no claim of superiority, SOTA or
universal improvement. The meta-design exercise retained the original archive
policy; no successful policy mutation or live component ablation is claimed.

## What the new regressions cover

The upgrade adds tests for opt-in archive decisions and deterministic parent/operator
routing; fresh paired cohorts and unchanged final gates; counted native handoffs;
source/prompt/feedback/response receipt binding and later revalidation; partial,
duplicate, stale and malformed submission refusal; terminal no-proposal stopping;
ordinary-file and bounded response reads; and deterministic bounded author feedback.

Exact-JSON controls are challenged with deliberately permissive and incorrectly
strict graders: boolean/number confusion, missing or extra structure, changed values,
array-order mistakes, valid numeric equivalents and object-key order. Tests preserve
wire representation for order probes, bounded coverage, budget accounting and private
receipt boundaries. These synthetic checks establish mechanics and selected
failure-mode coverage, not independently correct specifications or model improvement.

## Final local packaging checks

The final integrated runtime and test files are byte-identical to tested revision
`ff3f164`; later changes are documentation and publication evidence. On October 2,
the isolated Python 3.14.8 environment passed all **39 packaging/plugin tests**.
Official Node 26.10.0 (vendor checksum verified) and npm 12.2.0 rebuilt the pinned
UI; every generated asset and notice was byte-identical, and **17 UI tests passed**.
This is DOM/protocol and reproducible-build evidence, not native visual rendering.

Source/wheel/plugin packaging uses the final integrated files. The wheel installed
in a clean Python 3.14.8 environment with no optional SDKs and passed CLI/import
checks. The plugin passed checksum/structure and relocated-launcher validation.
All four skills installed in a temporary repository with synchronized references.
A fresh offline automation demo completed 736 zero-dollar synthetic trials, three
scripted proposals and a sealed qualified final; this is not model improvement.
Build tools were build 1.6.1, wheel 0.48.0 and setuptools 84.0.0. The external
artifact manifest binds final Git revision, archive hashes and retained build logs.
No package registry upload, tag, hosted deployment or hosted CI result is implied.
Historical measured runtime hashes remain unchanged.

The existing [0.4.0 validation record](VALIDATION-0.4.0.md) covers 445 tests, the
offline automation demo and 17 UI DOM/protocol tests on that prior revision. It is
historical evidence, not a fresh execution of this upgrade. The
[0.3.0](VALIDATION-0.3.0.md) and [0.2.0](VALIDATION-0.2.0.md) records also remain intact.

## Boundaries that still apply

- Native prepare/submit is external host orchestration. It does not establish
  authenticated standalone Codex CLI execution or a live one-command `automate` run
- Native model identity, inference cost and token usage may be unavailable. Unknown
  stays unknown; reservations and imported labels do not prove provider execution
- Evaluation trial/dollar limits depend on honest adapter reports and reservation
  bounds. They are not provider-side hard caps or a universal compute budget
- Local execution and receipts are cooperative same-account safeguards, not
  hostile-code isolation, authenticated authorship or private-file read protection
- Actual Docker execution, current native macOS/Windows behavior, hosted CI and
  production-representative outcomes require separate verification
- CPU kernel-efficiency measurements are not automatically wall-latency, full-workflow
  speed or inference-cost measurements. Define and report the measured quantity
- The historical Rust example used the 0.2 engine/custom driver. Its public finals
  are reproduction data; it does not validate this revision's automation integration


## Historical focused native workflow checks

The [static preparation record](validation/native-workflow-hardening-static.json)
includes exact changed-source hashes and deferred commands. An isolated copy
derived from `247c1f0366eaa65fd64f20164c3048a89803b912`
stages additive `start-native` and `evaluate-turn --call-id` commands. Static source
and test preparation was performed while scored measurements used their unchanged
frozen runtime. No test, demo, profiling run or native author was executed for this
patch during those measurements. It is not included in the earlier 510-test record,
and no comparative benchmark result establishes its behavior.

The study owner subsequently opened an explicit measurement-free window. The
[separate focused validation record](validation/native-workflow-hardening-focused.json)
and [raw output](validation/native-workflow-hardening-focused.txt) show **56 tests,
OK in 19.292 seconds**, for `tests.test_native_workflow` and `tests.test_native`.
This covers the new native API regressions in blocked/paired modes and the earlier
native workflow. No scored operation ran concurrently with these tests.
Exact runtime/test hashes and the command are recorded. This is a focused pass,
not full-suite, live-model or comparative performance validation.

Prepared offline regressions cover no-dispatch evaluation, missing/wrong/native
call binding, duplicate integrity checks, pending/indeterminate author/trial blocks,
whole-matrix resume, interrupted decision/receipt/report persistence, paired half-pair
refusal, exact-plan authorization and budget rejection, protected final capacity,
final sealing with pending authors, and additive CLI arguments. Static syntax and
reference synchronization checks are separate from executing these tests.

At this focused capture, broader dedicated automation/search/proposal-receipt
suites, full discovery, demos and package checks were pending. Subsequent full
regression outcomes are recorded below. Static AST syntax, exact extracted evaluator-body
comparison, reference synchronization and diff checks have passed. Do not call this
fully verified or attribute the frozen study's scores to these new APIs.


### Subsequent finalization lifecycle guard: focused checks passed

Independent static review identified a pre-existing hole: an applied native author
was no longer pending, so `finalize` could seal the incumbent while its evaluation
round remained active. The isolated follow-up now checks unresolved authors, active
rounds and pending/indeterminate trials before the final-result return and any final
seal/resume. It preserves existing seals and prevents recovery from permitting more
holdout rows. This intentionally tightens lifecycle admission, including saved-final
retrieval, without changing scoring, paired schedules or qualification thresholds.
The 56-test record above predates this additional guard. In a second explicit
measurement-free window, the current guard/runtime passed **128 tests, OK in 31.450
seconds** across `tests.test_native_workflow`, `tests.test_native`,
`tests.test_engine_optimizer` and `tests.test_paired_measurement`. See the
[exact validation record](validation/native-workflow-finalguard-focused.json) and
[raw output](validation/native-workflow-finalguard-focused.txt). New regressions
cover active/pending/recovered blocks, incomplete sealed finals, complete-boundary
resumes and clean completed-final retrieval after expiry in blocked and paired modes.
No scored operation overlapped that test run; at that capture, dedicated suites, full
discovery, demos and packaging were still pending. Later outcomes follow below. Static review found no remaining
concrete defect in its reviewed scope. Plain `start` help now also discloses its
existing configured oracle preflight execution.


### Full discovery on 60c5883: completed with two environment-related errors

A later explicit measurement-free window ran full discovery on the exact clean
`60c5883b215806f21e52f48f773c9b30bd81027f` source. It completed **560 tests in
78.098 seconds: 555 passed, 2 errors, 3 skipped, exit 1**. This aggregate run failed;
it must not be reported as a full-suite pass. The [machine-readable record](validation/native-workflow-full-discovery.json)
and [complete output](validation/native-workflow-full-discovery.txt) retain the exact
command, timestamps, runtime/test hashes, errors, skips and environment.

Both errors occurred in optional MCP protocol integration. This interpreter has
MCP **1.29.0**, below the declared `mcp>=2.2.0,<3` requirement. The modern-client test
cannot import `mcp.Client`; the stdio test's server explicitly refuses the installed
SDK and closes, after which the client reports `McpError: Connection closed`.
The three skips are two optional OpenAI-SDK transport checks (SDK absent) and the
installed-Codex argument check, deliberately disabled by unsetting its opt-in flag.

Automation, search-policy and proposal-receipt suites all passed as part of this
full discovery, with per-suite counts in the record; no separate rerun was started.
The command exited before the window boundary, and a process check found no
unittest/plugin-server processes remaining. No scientific runtime/controller was
changed and no scored measurement ran concurrently.

At this failed-run capture, the supported-environment rerun and standalone
demo/package/UI checks remained pending; no repair or retry was performed in that
window. The later supported reruns below preserve this failure and its exact scope. Earlier passing
focused runs remain scoped evidence; they do not erase this failed aggregate run.


### Supported rerun and separate current-release environment: full passes

After all scored scientific cohorts finished, the unchanged hardening runtime from
`60c5883` was rerun with the previously provisioned Python 3.12.14/MCP 2.2.0
interpreter. **560 tests completed in 78.509 seconds: 557 passed, 3 optional skips,
exit 0.** See the [supported-environment record](validation/native-workflow-supported-312.json)
and [raw output](validation/native-workflow-supported-312.txt). The two missing
OpenAI-SDK transport tests and deliberately disabled installed-Codex opt-in test
remain explicit. The earlier global-MCP failure is retained unchanged.

A separate release environment then acquired uv **0.12.22** from PyPI into isolated
tooling and used its managed **prebuilt Python 3.14.8**. It installed MCP **2.2.0**
and OpenAI **3.23.0** from hash-pinned requirements. Pydantic **2.13.5** still requires
and uses exactly pydantic-core **2.46.5**. No global interpreter or SDK was changed.

- Full discovery: **560 tests in 78.858 seconds, 559 passed, 1 skip, exit 0**
- Separate automation/search/receipt and real-SDK offline transport subset:
  **80 tests in 27.775 seconds, all passed, no skips, exit 0**
- Both real OpenAI SDK transport checks now ran and passed using offline mocks
- The sole full-suite skip is the deliberately disabled installed-Codex opt-in
  argument check; no authenticated CLI/model or live provider call was made
- Final release/plugin requirement verification and dependency consistency checks
  passed; all 31 installed packages are compatible

The [current-release record](validation/native-workflow-release-3148.json) contains
exact code/test hashes, commands, acquisition/runtime metadata, lock identities,
full/dedicated results and raw-log links. These are separately labeled product and
release checks; they do not make the frozen benchmark's older environment current.
Every install/test process exited before the independent profiling window opened.

Only after those checks passed was `requirements/judge.txt` updated to OpenAI
3.23.0. Its prior bytes and original resolver/date header are preserved in
[`requirements/history/judge-2026-10-01-openai3.22.1.txt`](../requirements/history/judge-2026-10-01-openai3.22.1.txt).
All other judge dependency pins, the declared extra range, plugin/CI locks and
runtime/test source are unchanged. Standalone demos, release builds and native-host
UI verification remain separate pending checks; no publication is implied.

## Completed transfer pilot and first verification optimization

The [transfer pilot](validation/optimizer-transfer-pilot.md) was independently
audited after all finals completed. It supports a negative primary New-versus-Direct
result, a positive secondary point estimate versus Old, and no successful meta-policy
mutation. It is a synthetic descriptive study, not a universal performance guarantee.

Hash-deduplication candidate `9a599187d152a7eace4d6101dc49d775cf7b2210` ran
566 tests on Python 3.14.8/MCP 2.2.0/OpenAI 3.23.0: **565 passed, one deliberately
disabled no-model installed-Codex help/argument opt-in check skipped**. Six focused tests are part of that total.
Fifteen independent integrity probes and 57 isolated invariant checks also passed.
The separate [randomized performance comparison](validation/verification-efficiency.md)
used Python 3.12.14 with a 30,894,944-byte executable, 30 fresh-state runs and exact
semantic goldens. Its preregistered completed-revisit process-CPU ratio was 1.64895×
(39.36% reduction); all workloads/phases and A/A noise are retained. No broad cache,
execution-boundary check removal, model-quality improvement or 3.14 speed claim follows.

## Current Codex CLI 0.160.0: help/auth checked; live startup blocked

A separate bounded smoke installed the official npm CLI 0.160.0 into an isolated
prefix with lifecycle scripts disabled. Version/help and required adapter argument
checks passed, and harmless CLI status reported existing ChatGPT authentication.
The single actual `automate` attempt used a new six-case local fixture, one author
opportunity, read-only sandbox, no model/effort override, ephemeral execution and
documented scratch SQLite/log output locations. Managed rules remained in force.

The author process failed after 5.162 seconds with an in-process app-server
read-only-filesystem initialization error, before any model events, proposal or
usage were observed. The precise failing path/subsystem is unknown; scratch SQLite
files were created, so this must not be relabeled as the earlier SQLite-specific
failure. All 28 oracle calls and four baseline app/grader trials passed. One failed
author remained counted, no final test opened, and no retry or access/security
workaround was attempted. Served model and optimizer cost remain unknown.

The [sanitized receipt](validation/codex-cli-0.160.0-integration.json) records exact
CLI/core/fixture/plan identities and limitations. This confirms current help/auth
status and honest startup-failure handling; it does not verify live one-command
automation success. The successful native external-handoff study remains distinct.

## Exact completed-result revisit: final source and direct comparison

Candidate `ff3f164dcb6bb830ea62d9e43a6bf5c8a1e1bbbb` passed **577 tests, no
failures or skips**, on the separate Python 3.14.8/MCP 2.2.0/OpenAI 3.23.0 release
environment. The installed Codex 0.160.0 opt-in check was enabled; source confirms
it always uses `--help` and never dispatches a model. This does not erase the separate
real `automate` startup failure. A fresh offline scripted demo also completed 560
zero-dollar synthetic trials, three scripted proposals and a sealed final.

An independently caught intermediate-candidate stale-eligibility bug was corrected
before any candidate timing. The final shortcut requalifies after fresh entry
verification and binds the exact ordered full ledger rows, including raw result
and reserved/charged fields. After fresh exit checks it rejects any changed identity.
Initially nonqualifying legacy behavior and seed/bounds acceptance are unchanged;
this is not new validation of previously trusted stored result semantics. The
actual execution loop and final-test path remain unchanged.

The [second prespecified comparison](validation/completed-revisit-efficiency.md)
completed all 36 fresh-state runs with exact semantic goldens and 57 candidate
invariants. It measured incremental 9a599187-to-final and direct original60c5883-to-final
contrasts separately on the same Python 3.12.14/environment. The primary 12-case
completed-revisit median CPU ratios were 4.79096× and **7.98288×**, respectively.
The directly measured combined result is **87.47% less process CPU**; no separate
medians were multiplied. All phase/workload outcomes, including near-flat/regressing
secondary results, remain recorded. This is local synthetic phase evidence, not
whole-workflow, model-quality, 3.14-speed or universal performance evidence.
