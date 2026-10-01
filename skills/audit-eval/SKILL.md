---
name: audit-eval
description: Audit an evaluation before trusting its scores or optimizing against it. Check case provenance, leakage, grading calibration, real-outcome wiring, uncertainty, budgets, reproducibility, and contamination. Does not authorize paid evaluation or application changes.
---

# Audit the measuring instrument

Read `references/OPERATING_GUIDE.md`, `references/PROTOCOL.md`, and
`references/SECURITY.md`. Inspect existing artifacts before inventing a new harness.
Start with `eval-lab audit <suite>` where the suite uses the lab protocol. Otherwise
perform equivalent checks on the existing framework; do not force a migration.

Audit five layers: task validity and provenance; dataset/split integrity; runner and
fixture fidelity; grader calibration; metric/uncertainty/selection validity. Look
for duplicates across users/documents/templates, incumbent-generated gold, missing
negative cases, unreachable criteria, trivial cases and contaminated public answers.
Verify real output/end-state grading, same-call traces, model identity, parameter
propagation to subagents, error denominators, hidden retries, and actual cost records.

Check repeated unchanged runs, stochastic-build variance, attainable headroom,
minimum useful effect, independent group counts and environment drift. Reject
pseudo-replication from treating many repeats as many tasks. Adaptive validation is
not untouched test evidence. A same-user folder or a fresh context is not an OS
isolation boundary; inspect actual mounts, accounts, network and credential exposure.

Use development traces only for optimizer-facing diagnosis. Test inspection is a
human-only final-stage action and consumes that holdout's independence. Do not fetch
production data, call models or rerun expensive benchmarks without authorization.
For a rubric judge, request human calibration labels rather than accepting confident
rationales. Include known-good, known-bad and order-reversed pairwise controls.

Deliver findings with severity, concrete evidence/location, effect on validity,
and a recommended fix. Distinguish checks that passed, failed, and could not be tested.
An executable harness is not automatically a trustworthy eval. Recommend stopping
optimization when the instrument is unreliable, not quietly changing it mid-climb.

## Inspect measurement evidence, not only agreement

Read `references/EVIDENCE.md`. Check raw per-criterion judge verdicts against
independent human labels, including missed failures and false alarms. Inspect the
actual calls and both rationales. A deterministic failure that makes a composite
score correct does not validate an LLM component. Missing/skipped/abstained judgments
are not correct answers. Require both human-pass and human-fail support; undefined
rates must remain undefined. Report failure recall and good-output specificity with
explicit polarity and denominators, not ambiguous TPR/TNR alone.

Check related-case separation between judge tuning and judge validation, frozen
rubric/judge/output hashes, anchor provenance, and configured versus served model
identities. Same-model roles are a bias warning; changing providers is not proof of
independence. Recheck fixed human anchors and inspect fresh samples after meaningful
judge, rubric or source-distribution changes. Never silently relabel ground truth
to improve agreement. A gate marked not_configured is not a successful evidence audit.
