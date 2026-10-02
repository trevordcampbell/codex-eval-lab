---
name: hillclimb
description: Autonomously improve scoped application code, prompts, skills, parameters or tools against a fixed trusted eval, using bounded proposals, guarded selection and a preauthorized final test. Use for requested metric optimization; never invent wins, change protected evaluators or deploy without authority.
---

# Own the bounded improvement loop

Read `references/SEARCH_POLICY.md`, `references/AUTOMATION.md`, `references/OPERATING_GUIDE.md` and
`references/SECURITY.md`. If the eval is missing or untrusted, use `$build-eval` and
`$audit-eval` to build it. Codex should design, inspect, diagnose and iterate; do not
send the user a list of manual setup chores or ask permission for every iteration
already covered by their request.

Require an executable-oracle control gate for exact outcomes or the existing
expert-calibrated atomic evidence path for semantic/mixed outcomes. Preserve the
basis and limitations. A model-written expected answer, convincing rationale or
two-model consensus is not human/expert ground truth. Objective control replay can
be automatic without asserting human review. Read `references/EVIDENCE.md` before
working with expert labels; do not replace them or loosen calibration to pass.

## Establish the scope once

Use a clear primary objective, minimum useful effect, guardrails, editable paths,
prohibited changes, evaluation cost/trial/wall limits, separate optimizer-call/time
limits and final-test intent. Reuse the user's real provider and toolchain. Confirm
only missing decisions or required action-policy authority. A flag cannot grant
that authority; record the actual user scope and source in the authorization note.
Unknown optimizer dollars are unknown, never zero.

Prefer `automation-plan` then `automate` for a requested complete improvement
when a working configured command or Codex CLI proposal backend is available.
Otherwise use the explicit native host bridge below; it is a different dispatch
path and does not verify one-command live CLI integration. The local CLI freezes the source-bound plan and evaluator, runs preflight and baseline,
launches fresh Codex proposals, applies only scoped edits, compares to incumbent and
original baseline, retains raw decisions, reserves final capacity, seals the winner,
opens the preauthorized final comparison and writes the result/report. No hosted
execution service or mandatory UI gate is involved. Use `resume-automation` for the
same frozen plan after investigating interruptions; do not create duplicate work.

If final opening was not approved, use the individual start/loop/report commands
and ask once when that new action is needed. If the user asked only for a baseline
or short experiment, honor that stopping point rather than broadening the task.

## Separate exploratory search from release evidence

For a new experiment, consider opt-in archive search when conservative selection
would discard useful inconclusive stepping stones. Freeze its primary metric,
empirical guardrails, diversity/reward scales, archive capacity and operator policy.
Keep hard validity and final release checks unchanged. Use conservative default
selection when archive assumptions are unsuitable or have not been assessed.

Archive admission, a better observed mean and an author hypothesis are not release
qualification. Preserve best-found, validation champion and final release outcome
separately. Do not change thresholds or secondary objectives after outcomes. Use
fresh paired measurements for timing; noisy development ranks are only heuristics.
Do not claim UCB or portfolio efficacy from a run that never revisits an operator.

For native Codex orchestration, initialize a new `automation-plan` with
`start-native` to protect final capacity. Configured oracle preflight executes now
under existing authority; record its actual calls. Then prefer `prepare-turn` /
`submit-turn` followed by `evaluate-turn STATE --call-id CALL_ID`. Never substitute
generic `loop` for native completion retries; it can dispatch another backend call.
The active-only command validates the exact call and safely returns an unchanged
verified completion receipt on repetition. This reserves each opportunity, snapshots the exact public
source/prompt/feedback before dispatch, and captures the response before scoped
application. Send the captured prompt bytes and verify the workspace source before
calling an author. Keep every failed/malformed turn counted. A pending admission
is not evidence of execution; preserve its status and do not silently redispatch.
Record actual model/usage when available, otherwise unknown. This file protocol
does not claim that the standalone Codex CLI executed successfully.

## Keep measurement and proposal separate

Feed proposals only `feedback` development data or an `export-workspace` handed to
a separate trust domain. Never pass the plan/full report/calibration-validation or
held-out transcripts to the proposer. A fresh local context is not a read-isolation
guarantee. If a proposal author did receive validation feedback, record that actual
exposure; don't retroactively call it development-only.

Each proposal gives one causal hypothesis and reversible complete scoped edits.
Fix ordinary implementation failures within scope. Do not change frozen cases,
grader, metric direction, tolerance, budgets, retries or heldout definitions to
make a candidate win. Measurement fixes mean a new experiment and baseline.
Do not hardcode answers, task IDs or benchmark solutions.

Use honest stop outcomes: no credible proposals, patience, limits, or protected final
reserve. The runner records invalid proposals/errors as blockers; investigate rather
than bypassing the guard. Completed trials and proposals are reused; pending unknown
outcomes are conservatively accounted and never silently replayed. Use `recover` or
`unlock` only after confirming no old process is running. Keep failed receipts.

## Finish and explain

Once authorized, final sealing/opening need not wait for a ceremonial human click.
A failed final comparison is still a completed measurement, not permission to tune
on that holdout. Report basis, exact selected source, final delta/uncertainty,
regressions, budget and unknown costs. Export selected source only into a new review
directory. Do not overwrite, push, merge, publish or deploy without corresponding
authority. Do not claim universal improvement or live-model validation from fixtures.
