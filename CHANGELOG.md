# Changelog

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
