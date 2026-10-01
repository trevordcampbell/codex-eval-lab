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

## Live Codex smoke workflow


Install and authenticate the Codex CLI on your machine using the
[official instructions](https://developers.openai.com/codex/cli). No credentials are
included in this project. Prepare a separate suite that replaces the scripted
optimizer with the real Codex adapter:

```sh
python scripts/prepare_codex_demo.py --out ../eval-lab-codex-suite
eval-lab doctor
eval-lab audit ../eval-lab-codex-suite
```

Review the cases, grader, editable scope, source files and budget. Only after approval:

```sh
eval-lab start ../eval-lab-codex-suite \
  --app ../eval-lab-codex-suite/app --state ../eval-lab-codex-state \
  --approve-cases --approve-grader --approve-execution \
  --note "Reviewed synthetic cases, grader, source scope and execution budget."
eval-lab loop ../eval-lab-codex-state --approve-optimizer
eval-lab report ../eval-lab-codex-state --out ../eval-lab-codex-state/report.html
```

Codex usage consumes your account's plan allowance or API billing as applicable.
**Optimizer usage is separate from the evaluation-dollar budget.** The adapter
records CLI usage and limits calls/time; it does not invent a dollar conversion.

Once selection is finished and you approve opening the held-out test:

```sh
eval-lab finalize ../eval-lab-codex-state --approve-final
eval-lab report ../eval-lab-codex-state --out ../eval-lab-codex-state/report.html
eval-lab export-best ../eval-lab-codex-state --out ../eval-lab-reviewed-winner
```

The final test seals the selected source hash before it runs. The experiment cannot
then keep optimizing against that test. Export creates a **new directory**; it never
overwrites your working tree, merges a PR or deploys an application.


## New timing-sensitive experiments: paired AB/BA mode

The opt-in mode below is for a newly approved experiment. Do not edit an existing
manifest, evaluator, database or runtime fingerprint to retrofit it. Existing
frozen runs must continue with their original runtime; their historical results
remain variant-blocked. A changed runtime is intentionally rejected on old state.
No command migrates a frozen experiment or re-labels old measurements as paired.

1. Copy the suite to a new review directory and add the following to its
   `eval.toml`, before `start`:

   ```toml
   [measurement]
   design = "paired_ab_ba"
   ```

2. Keep the scientific objective, effect threshold, guardrails and workload design
   prespecified. Review and approve the changed measurement protocol and its
   additional budget. Do not reuse an already exposed final test for independent
   confirmation; use an appropriate fresh holdout when prior test evidence has
   informed development. Keep the original state and report for the record.
3. Run `audit`, then `start` into a new state directory with explicit case, grader
   and execution approvals. Use this runtime for every command on that new state.
4. Run development measurements as usual, register a candidate, then invoke
   `select --candidate LABEL`. In this mode selection performs the fresh
   reference/candidate validation calls. A rejection exits nonzero and retains
   both the records and the current selection. Use `compare --candidate LABEL`
   to inspect its recorded comparison to the original baseline; pass
   `--baseline INCUMBENT` for its incumbent comparison. `loop` uses the same
   paired protocol automatically. Do not run standalone validation matrices.
5. Once development is over, request final-test approval and use
   `finalize --approve-final`. The one winner and both source hashes are sealed
   before any final-test call. `report` shows cohort-specific comparisons.

### Budget before approving

For V validation cases and R repetitions, one candidate needs 2 × V × R
application-plus-grader trials while incumbent and original baseline have the same
source hash. After they differ, each candidate needs 4 × V × R trials: two fresh
reference/candidate cohorts, including two measurements of the candidate. Add
ordinary development calls and 2 × T × R final-test trials for T test cases. The
unchanged final winner also costs 2 × T × R for a genuine A/A control. Both dollar
reservations and wall-time approval must cover this work; optimizer charges remain
separate. No budget is increased automatically. Before starting a pair the engine
checks that the remaining trial and cost budget can cover both calls.

### Interruptions and diagnostics

An interruption at a completed pair boundary may resume with the identical
persisted schedule; completed rows are not replaced or repeated. If the first arm
completed but the second did not, that half-pair is invalid. A pending attempt is
indeterminate; use the existing `recover --confirm-no-running-process` procedure
only after confirming no process is active. Recovery conservatively charges its
reservation and does not retry the attempt. Do not manually delete the partial
pair or generate another cohort to cherry-pick a clean result. Review the failure
and start a new approved experiment if valid confirmation is still needed. A
failed final cohort does not unseal the winner.

To inspect unchanged controls before a search, register an unchanged copy under a
new label in a separately approved diagnostic experiment, then use `select` and
`compare` as above. The lack of a credible improvement is expected; it is not a
command failure to hide by rerunning until accepted. A control passing an
improvement gate is a measurement warning, not evidence that identical code became
better. Keep diagnostic results separate from a confirmatory experiment.

### Manual decisions in the report

Every completed manual `select` attempt records both gate comparisons and whether
it actually promoted the candidate. Rejections remain visible in the HTML report;
a promotion and its audit event commit together. This applies to both measurement
modes. `compare` remains read-only and does not create a decision or promote an
eligible candidate. Save its JSON output separately if you need a record of an
analysis-only comparison. In paired mode the underlying measured cohort comparison
is already durable independently of promotion.


### Bounded HTML case previews

Normal `report` output bounds inline case evidence: at most 4,096 serialized
Unicode characters per top-level field value/key, 16,384 per row, 512 per title,
200 rows, and 1,048,576 UTF-8 bytes for all escaped trace HTML including row
markup. Truncation markers count toward character caps. Long nested values are
text fragments and may not be parseable JSON. Limits apply across legacy and
paired-cohort rows together, after the usual privacy gates. The report discloses
shown, truncated and omitted row counts. Rows are the first eligible records in
report order, not a representative sample; search covers displayed text only.

This changes presentation only: all numerical analyses, comparisons and sample
counts use complete records. The cap is for the inline trace portion, not score,
decision or provenance sections. It does not bound the memory needed to load raw
state or calculate statistics. Full records remain in the experiment's
`state.sqlite3` (`trials` or `paired_trials`); each record's `artifact_dir` points
to retained raw process streams/artifacts relative to the state directory.
The HTML identifies the database location and lookup keys, without loading or
linking external content. Keep state private: it may also hold sealed test data.

For an intentionally unbounded inline export, use `eval-lab report STATE --out
REPORT.html --full-traces`. It can be very large and contain sensitive content.
This option does not authorize held-out detail export: `--include-private` is
still separate, and neither flag reveals unfinished final-test details. Keep all
private reports away from the optimizer. Preview limits are not redaction.

## Native automation-first workflow

See [AUTOMATION.md](AUTOMATION.md) for the default end-to-end objective workflow:
Codex authors and audits the suite, `automation-plan` creates a byte-bound read-only
plan, `automate` executes within existing authorization through a sealed final test,
and `resume-automation` continues eligible durable work. The plan protects final
trial/dollar capacity; preflight calls count toward the same evaluation budget.
Do not retrofit frozen historical experiments. A new evaluator/runtime requires a
new experiment and baseline. Exact controls need no human-label attestation;
semantic criteria retain their existing expert calibration requirements.
