# Changelog

## Unreleased (target 0.5.0) — exploratory search and stronger eval controls

- Separate post-score hardening validation: 560 tests pass on Python 3.12.14/MCP
  2.2.0 with 3 optional skips; 560 pass on prebuilt Python 3.14.8/MCP 2.2.0/OpenAI
  3.23.0 with 1 disabled CLI opt-in skip, plus 80 dedicated offline checks
- Release-only judge lock advances to OpenAI 3.23.0 after those checks; all other
  pins/ranges remain unchanged, and the old lock is retained verbatim. Historical
  environments, failed runs and scientific evidence keep their original identities

- Separately staged native workflow hardening: `start-native` reuses exact-plan
  final reserves and reports oracle preflight; `evaluate-turn --call-id` is
  active-only with bound, idempotent completion receipts and no author-dispatch
  fallback. A finalization lifecycle guard also blocks active rounds and pending/
  indeterminate trials, including saved-final retrieval and sealed-final resume;
  clean final retries and scientific thresholds are unchanged. Validation is tracked
  separately; these commands were not used by the frozen comparative benchmark

- Opt-in exploratory archive and deterministic proposal operators, separate from
  unchanged sealed final-release gates; explicit search-selected, validation and
  release outcomes, with fresh paired timing comparisons preserved
- Counted native proposal preparation/submission, controller-owned tamper-evident
  prompt/source/feedback/response records, durable no-proposal stopping, strict
  bounded response reads, and no replay of pending or partial attempts
- Shared bounded author feedback with complete numeric summaries, deterministic
  marked examples, exact omission counts and original-feedback hashes
- Opt-in exact-JSON type/shape/value negatives and object-order positive controls,
  with budgeted raw execution, source binding, family coverage and explicit limits
- Standard-library core and conservative defaults remain; novel search policies
  require a new experiment. No SOTA, live-model advantage or hosted execution claim
  follows from passing machinery tests. No final comparative results are included
- The measured implementation is commit `0ce0131`; its full validation record was
  added in `4d1ad4d`: 510 tests, OK with 3 optional skips. These results precede
  the separate packaging-version change; see [validation](docs/VALIDATION.md)
- Existing configurations keep conservative selection when the archive opt-in is
  absent. Frozen runs require their exact original runtime; no in-place migration
  or retrospective evidence upgrade is supported


## 0.4.0 — automation-first revision (local validation)

- Native byte-bound automation plans and bounded start/search/seal/finalize/report
  orchestration, with eligible resume and protected final trial/dollar capacity
- Separate executable-oracle provenance: model-authored source-derived controls,
  executed positive/negative checks, and reference→grader consistency for every
  frozen JSON-only case; unchanged semantic expert-label calibration gates
- Raw reserved/charged preflight receipts, conservative failure accounting, replay
  refusal and pending optimizer blockers; no CLI flag grants user authority
- Optional evidence UI, automation-first skills, escaped report evidence basis and
  source/trust assumptions; no hosted arbitrary-code execution service
- Bounded default report previews with explicit full-trace opt-in, and SQLite-backed
  once-per-invocation JSONL materialization instead of per-trial full rewrites
- Offline executable automation fixture and historical model-guided Rust source
  example with explicit old-engine provenance; no live new-controller model claim

## 0.3.0 — 2026-10-01

Opt-in temporal pairing for new timing-sensitive experiments. The frozen
`paired_ab_ba` measurement design persists adjacent, counterbalanced schedules;
selects with fresh incumbent/original-baseline reference cohorts; and seals both
source identities before a fresh final-test comparison. Cohort/role trial keys
retain historical rows, share budget accounting, and reject interrupted half-pairs
rather than silently retrying or treating delayed measurements as adjacent.

Manual selection attempts now retain both rejection and actual-promotion records.
Promotion and its audit event commit atomically; reports show these actions and
separate paired cohorts. `compare` remains read-only. Documentation explains the
additional trial budgets, selection-time execution, recovery rules and inferential
limits. The default blocked mode remains available with explicit audit warnings.

This is a new measurement protocol, not a retrospective correction to existing
results. Existing frozen experiments require their original runtime; do not edit
their manifests or databases to retrofit this mode. No scientific objective,
threshold, guardrail or inference method is changed automatically. Local checks
and current hosted-CI status are distinguished in docs/VALIDATION.md. No paid
provider call, deployment or public release is implied by this source revision.

## 0.2.0 — 2026-10-01

Trace-first human review packets, atomic anchored criteria, independently measured
judge confusion metrics and simultaneous group-level uncertainty bounds, immutable
label/output/evaluator provenance, opt-in recomputed evidence gates, explicit raw
criterion results, same-anchor judge drift diagnostics, offline annotation and
disagreement viewers, and a distributable local MCP/skills plugin. Read-only MCP
uses explicit startup artifact scope and a bundled optional MCP Apps UI.

Existing CLI engine behavior remains available; evidence gates are opt-in and
legacy suites disclose their absence. Real semantic-grader skills require the new
measurement review workflow. Native host UI and production remote/public-directory
delivery remain separately unverified; this release does not deploy a service.

## 0.1.0 — 2026-09-30

Initial alpha. Four Codex skills; provider-neutral JSON application/grader
protocol; strict TOML suites; frozen source/evaluator snapshots; grouped splits;
paired cluster-bootstrap gates; cumulative evaluation reservations and limits;
SQLite recovery; automatic Codex or custom-command hillclimbing; final-test
sealing; development-only external workspace exchange; offline HTML reporting;
zero-dollar routing and software-performance examples; installer, publishing,
release, calibration, and test tools.

This release has local automated tests and a scripted end-to-end demonstration.
Live Codex, Docker runtime, other operating systems, and GitHub-hosted CI require
separate verification. See docs/VALIDATION.md for the exact tested scope.
