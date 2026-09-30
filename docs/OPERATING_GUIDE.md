# Operating guide for humans and coding agents

## Choose a measurable unit

Identify one task flow, the actual entry point, what one request includes, and what
observable outcome counts as success. A unit can be a classification, conversation,
retrieval query, completed coding task, UI journey, generated image, simulation,
compiler workload, or business-rule check. A cross-case benchmark can be one unit,
but do not pretend its aggregate score provides many independent observations.
The lab does not make an unobservable goal automatically measurable.

Reuse existing scripts, pytest/Jest/Cargo suites, browser tests, grading functions,
and tracing systems. Add a thin JSON stdin/stdout adapter only where needed. Evaluate
real outcomes through the actual entry point. Replace production writes with safe
fixtures/replay; document what those substitutions stop you from measuring.

## Design and approval

Prefer retainable, permissioned production examples; then bugs/support cases; then
human-authored examples; then synthetic variations anchored in real examples.
Include ordinary, hard, negative, ambiguous and must-not-fire situations. Separate
stress suites from a representative production-weighted metric. Do not let a model
under comparison supply its own unverified ground truth. Establish retention,
redaction, provenance and dataset licensing before copying private data.

Present concrete proposals, not an unbounded questionnaire. Obtain explicit human
approval of (1) actual cases and labels or a stratified sample plus dataset checks,
(2) the grading method after pilot calibration, and (3) commands, permissions,
editable scope, constraints, and spending. The CLI's approval flags record consent;
they are not proof of consent and are not an authentication mechanism. An agent
must not set them on its own to manufacture approval.

Keep the eval-design conversation separate from optimization. An agent that has
read all examples and answers cannot unsee them. Use the controller's fresh Codex
proposal sessions, or start a fresh conversation from an exported development-only
workspace. For adversarial isolation, that workspace must run under a different
OS identity/container/host with no access to evaluator storage—not just a different
folder or a sentence asking the model not to look.

## Choose a grader

Deterministic outcome checks are preferred for constrained outputs: exact labels,
JSON validity, executable hidden tests, database/end-state invariants, accessibility
checks, performance counters. For agents, verify what changed, not what the agent
said. Detect no-op solutions, forbidden modifications and unintended side effects.
Keep evaluation-only tests and reference answers outside candidate access.

For open-ended outputs, use explicit, checkable rubric criteria or blinded pairwise
comparison. Use an independently configured judge, mask model/variant identities,
randomize A/B order, reverse order on a calibration subset, and allow ties. Measure
agreement with human labels and inspect disagreement—not just a model's convincing
rationale. Calibrate known-good, known-bad, partial, verbose, and prompt-injection
outputs. Judge text is untrusted too. `scripts/calibrate_judge.py` supplies a small
label-agreement/confusion-matrix checker; it does not magically validate a rubric.

## Check the instrument before optimizing

Run `eval-lab audit SUITE`. Review duplicate/group leakage, source/fixture coverage,
model identity propagation, actual retries, expected labels, rubric calibration,
error handling and metric aggregation. Smoke-test that the mechanism being changed
actually reaches the app and affects the intended outcome. Try a disabled-mechanism
ablation and known good/bad controls where practical. A stronger model is a useful
sanity check, not a theorem that every task must rank every model the same way.

Use repeated unchanged baselines to estimate noise. More repeats measure instability
on existing tasks; more independent tasks broaden the sampled distribution. If a
prompt first generates an index, memory store or artifact, repeat that **build** too:
rescoring a single build does not estimate build variance. Use interleaved unchanged
controls when time, load, caches, hardware or remote services can drift. Rebaseline
when a materially relevant environment changes.

State the headroom, uncertainty, smallest useful improvement, and runtime/cost
requirements before spending optimization rounds. An eval unable to distinguish
plausible gains needs better cases or measurement, not a longer prompt or more
search iterations.

## Operate the loop

Approve a bounded plan. Record the primary objective and non-negotiable guardrails,
editable paths, maximum rounds, patience, eval trial/cost limits and separate Codex
usage limits. The core freezes the evaluator and each candidate, runs development
and validation, gives a fresh optimizer development-only evidence, applies one
coherent scoped proposal, then keeps it only when the measurement gates pass.
Guardrails are checked against the incumbent **and original baseline** to avoid
cumulative tolerated drift. Rejected candidates remain inspectable; the user's
working tree is never reset or overwritten. The report updates after each round.

Use `status` to inspect durable state. Re-running `run` resumes completed matrices
without repeating completed trials. A stopped loop resumes an already-generated
candidate before asking for another proposal. If a trial was in flight when the
process died, its outcome and cost are unknown: `recover` marks it indeterminate,
charges the reservation, and never pretends it succeeded or retries it for free.
A comparison containing that attempt is invalid. Investigate and create an explicitly
identified replacement/control or new experiment; do not quietly erase the attempt.

The wall-time limit is an **absolute window from experiment creation**, including
idle time, not just active CPU time. It cannot be extended silently. Budgets apply
to the experiment, not separately to each CLI invocation.

## Finish honestly

Pick the winner with development/validation only. Obtain approval for `finalize`,
which seals the choice **before** opening any test cases. It compares unchanged
baseline and selected candidate on that test set. A failed/interrupted final can
resume only the same selection. A completed test prevents further optimization in
that experiment. Reusing the same test data in a new experiment after inspecting
it does not make that data fresh; dataset governance remains the operator's job.

Report absolute scores, paired deltas, case/group/repetition counts, uncertainty,
regressions, error/incomplete runs, exact source/config identity, measured eval
charges, reserved/unknown charges, and optimizer usage separately. Never call
unknown optimizer dollars zero. A failed final confirmation is a real result.
No change can be the correct outcome. Export the selected source for review; the
lab does not push, merge, deploy, or execute production writes automatically.

## Capability recipes

| Goal | Unit | Outcome / grader | Typical editable surface |
| --- | --- | --- | --- |
| Improve retrieval | Query plus fixed corpus snapshot | Recall, ranking quality, grounded-answer rubric | Chunker, retriever, reranker, prompt |
| Improve coding agent | Task plus disposable repository | Hidden tests, scope/end-state checks, resource limits | Skills, instructions, tool descriptions, agent policy |
| Improve tool use | Scenario plus simulated external state | Final state, allowed actions, task completion | Tool schema, planner, error recovery |
| Reduce software latency | Representative workload | Warm timing plus correctness guardrail | Algorithm, data structure, compiled code |
| Improve UI workflow | Browser fixture plus user task | DOM/end-state assertions, accessibility checks, calibrated review | UI/app code, interaction policy |
| Improve creative artifacts | Brief plus assets | Structural checks and blinded human/model review | Prompts, templates, rendering pipeline |
| Reduce LLM cost | Production-derived requests | Task quality and true production cost/latency | Context, model routing, caching, tool strategy |
| Scientific workflow | Defined simulation or experiment | Reproducible domain-validated outputs | Search policy, code, parameters |

These are adapter patterns, not claims that domain-specific graders ship for every
possible task. Real-world experiments need their own safety, validity and approval
controls. Never trade away medical, security, legal, privacy or operational constraints
to improve a proxy score.
