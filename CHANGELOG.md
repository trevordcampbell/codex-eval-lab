# Changelog

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
