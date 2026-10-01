# Automation-first native workflow

Codex owns the reasoning and authoring work: inspect the application, derive the
contract, construct cases and controls, audit the evidence, propose scoped changes,
and explain the result. The local runner owns mechanical execution, immutable
snapshots, budgets, selection and final-test sealing. The Sites-hosted plugin remains a
read-only evidence companion. It can guide and inspect from clients without a
coding runtime; execution requires native Codex and an authorized local/coding
environment. Installing that hosted MCP does not make Rust execution available
on ChatGPT/mobile. No hosted shell or arbitrary-code endpoint is added.

## Give Codex the job once

A useful request is: "Improve this parser's speed while preserving exact output.
Use the existing toolchain. You may change parser.rs, run local tests and the
bounded eval, and automatically select and open the final comparison. No network,
paid calls, production records or deployment. Stop after 4 proposals or 20 minutes."

The skills turn that into concrete files and a plan. They should not ask the user
to author JSON, fill labeling forms, or approve each iteration of an already
covered objective workflow. Missing spend authority, sensitive-data transmission,
security changes and unresolved domain choices still need the host's action-policy
confirmation. A CLI flag records existing permission; it cannot create permission.
The planning/authoring model's usage is outside the runner's evaluation accounting.

For a suite with evidence and authority already established:

```sh
eval-lab automation-plan <suite> --app <app> --out <new-plan.json>
eval-lab automate <suite> --app <app> --state <new-state> \
  --plan <new-plan.json> --approve-plan \
  --authorization-note "<actual bounded permission and its source>"
```

`automation-plan` is read-only and executes no application, grader or reference
code. The plan binds exact evaluator/baseline file hashes, objective, guardrails,
editable paths, execution argv, model configuration, measurement design, all
existing budget limits and final-test intent. `automate` rejects a stale or edited
plan, freezes the evaluator, executes the required preflight, runs the bounded
search, seals the winner, performs the final comparison and writes the report plus
`automation-result.json`. It does not overwrite the source tree or deploy a result.

The original individual commands remain available for targeted work. Use
`resume-automation <state>` only for an experiment initialized with a frozen
automation plan. It reuses durable proposals and completed trials. It does not
restart a failed attempt, change the winner after sealing, reset charges or extend
the budget. Pending/indeterminate execution requires the existing recovery process;
an invalid measurement is a blocker, not a reason to keep sampling until it passes.

## Three distinct evidence situations

- **Executable checks passed:** An independently runnable reference agrees with
  source-derived boundary anchors; the actual grader accepts positive outputs and
  rejects specified known-wrong mutations, with raw executed results. The
  machine-readable basis is `executable_oracle_validated`, and status is
  `executable_checks_passed`. This means those finite checks passed. It does not
  mean the specification is true, useful, representative or independently authored
- **Expert calibrated:** The existing trace-first human/expert labels, bound atomic
  criteria, held-out calibration and uncertainty-aware support gates pass. Its
  existing evidence path is unchanged. Local reviewer records remain attestations,
  not authenticated identities
- **Unverified:** Missing controls, unsupported model judgments, model consensus,
  stale evidence or failed checks do not establish readiness. Automatic execution
  through finalization is blocked. Legacy manually scoped commands still disclose
  their missing gate rather than silently upgrading their evidence

A model can derive exact controls from a specification and run them without a
human labeling every row. Record the author as `model`. Do not copy those results
into human-review annotations or call two-model agreement ground truth. A
model-written specification itself remains a trust assumption unless independently
established. Semantic business judgments still use the expert-calibration path.
For a mixed semantic/deterministic grader use that existing atomic expert-evidence
workflow; this first executable-oracle implementation does not combine the two
configuration tables or let a deterministic score conceal an uncalibrated judge.

## Executable oracle contract

Add `[oracle] contract = "oracle.json"` to a new suite. See the complete runnable
example at `examples/automation`. The contract is a strict, versioned JSON object:

- `schema_version: 1`, a bounded `claim_scope`, source kind/reference, and author
  kind/reference. Source kinds are synthetic, project_fixtures or production_sample;
  authors are model, human or imported, never an inferred expert approval
- `specifications`: suite-relative source files declared in `harness_paths`
- `reference_command`: explicit argv using `{python}` and declared `{suite}/file`
  paths, with a separate entry point from the grader; `reference_rationale`
  explains its construction and limitations
- `criteria`: distinct `{id, metric}` deterministic binary maximize gates
- `measurement_metrics`: remaining graded gate metrics, each with a metric,
  candidate_reported or trusted_harness basis, and an explicit assumption. This
  records measurement trust; the runner does not prove a timer or proxy valid
- `anchors`: at least two declared groups, each with id, group, development role,
  specification_derived or established_fixture basis, source_ref, derivation,
  input, expected grader answer, correct output and known-wrong output mutations
- Each mutation names its id, output and criteria that must fail. Every criterion
  must have both positive and negative support in at least two declared groups
- `trust_assumptions`: explicit remaining assumptions; `max_wall_time_s`: a
  preflight limit from 1 to 300 seconds, within the experiment's total wall limit

Anchor and all-case consistency calls together are capped at 1,000 per preflight.
The reference receives an application-shaped input without expected answers.
The actual grader receives the fixed anchor input, expected value and output.
Its raw atomic criteria and binary metrics must match each positive/negative
control; constant-pass graders fail. Imported readiness flags are not accepted.
Checks run in fresh disposable source copies so build caches cannot alter frozen
files. Each attempt is reserved in SQLite before launch. Complete responses,
stdout, stderr, elapsed time and failure information are retained in the receipt.
No credential environment is passed to this free-local preflight. Nonzero reported
cost is an error; incurred charges are still recorded. Failure/unknown-cost
attempts are charged conservatively at least their reserved amount. Local code
is trusted and can still make undeclared external calls: this is not isolation or
a provider-side spending guarantee.

After anchors pass, the controller checks every frozen case: call the reference
with input/seed but no expected label, then pass that exact JSON output to the actual
grader with the case's frozen expected data. Every deterministic criterion must
pass. Both calls are budgeted, and the grader request is bound to the preceding
reference response. This catches generator/label/reference/grader inconsistency;
it still does not prove the specification or reference correct. It validates the
instrument before search and does not measure any candidate on the final set.
The oracle route currently supports JSON-input/output cases without file assets
or artifact-dependent grading. Artifact evaluations need a separately validated
workflow instead of falsely claiming identical preflight coverage.

Raw case-consistency results, especially final inputs/outputs, are controller-private.
Only aggregate counts and status appear in the public gate/report. Never provide
`oracle-receipt.json` to the proposer or hosted viewer. The independent reference
and source-derived controls remain visible only in the controller/evaluator domain.

Initialization binds the contract, actual harness bytes, cases, configuration,
launcher executable hashes, environment identity and raw receipt. Later operations
recompute receipt consistency without rerunning preflight code. Missing, changed,
failed, duplicate or partial controls cannot count as ready. Locally fabricated
identities/results are not cryptographically prevented from a same-account actor.

Source independence and correctness of derivations are assertions to audit. A
separate implementation can share the same misunderstanding. Extend task-specific
preflight with actual-output metamorphic and differential tests; merely testing an
oracle against its own derived expected outputs is insufficient. The generic
runner verifies source binding and fixed controls, not every domain property.

## Budgets, stopping and failure records

The plan must fit anchor control calls, two consistency calls per frozen case, baseline, one complete first candidate comparison
and a conservative two-arm final comparison. Final trial and dollar reservation
capacity is enforced by the store and cannot be consumed by non-test execution.
Before each new proposal, the controller checks capacity for its full comparison
and protected final reserve. In paired AB/BA mode it accounts for the two distinct
incumbent/original-baseline cohorts when needed. Calls stop at the frozen round,
patience, trial, evaluation-dollar or optimizer-call limits. Optimizer dollars
remain separate and may be unknown. No routine iteration needs another approval.

Normal stopping reasons (round limit, patience, no more proposals, protected final
capacity, optimizer-call limit) proceed to the preauthorized final comparison.
Malformed/out-of-scope proposals and invalid/unknown trials block rather than
silently finalizing. Crashes, environment changes or the wall-time deadline can
still prevent completion even when final trial/dollar capacity was reserved.
An expired experiment is not automatically extended.

Failed preflight attempts retain `oracle-receipt.json`, SQLite charges and
`initialization-failed.json`. They do not become an executable experiment. Fixing
an oracle or contract requires a new experiment directory and preserves the failed
record. An interrupted receipt is not silently replayed. Later runner failures
retain a blocker and raw evidence; follow the existing status/recovery instructions.

## Holdouts and reuse

Anchor IDs, groups and exact inputs cannot overlap the experiment's selection or
final cases. Reusable domain anchors must retain their source, derivation, contract
version and development exposure. They are useful for checking a new grader but
cannot be relabeled as a fresh holdout. Near-duplicate/semantic dependence still
requires domain review. A context that designed or saw holdouts must not be reused
as the proposer; use fresh development-only proposal sessions or a genuinely
separate trust domain. Acceptance feedback remains adaptive even without raw
validation transcripts.

The full plan, controller summary and report can expose selection feedback. Never
feed them to the proposer. `feedback` and `export-workspace` remain development-only.
Preserve exact prompts and any manually supplied selection feedback in the audit
trail; do not claim development-only isolation if a human or model actually saw
validation details. Final failure consumes the holdout and does not permit retuning.

## Migration and verification

Existing frozen 0.3 experiments keep their original runtime; do not install these
files into an active state/runtime. There is no in-place migration or retroactive
evidence approval. Use a new suite, new plan, new state and baseline. Changing a
specification, fixture, reference, grader, judge, metric or measurement design
requires the same new-experiment process.

Run `python scripts/automation_demo.py --out <new-external-directory>` for a real
local execution of the complete scripted synthetic workflow. The model did not
search during that demo; hand-authored proposals test selection and rejection.
The command calls no provider, makes no human-label claim and does not validate
production usefulness. Native authenticated Codex and live provider operation
still require their own authorized integration verification.

### Disposable builds and derived exports

Prebuild/test application candidates in disposable source copies before registering
immutable candidates. Set `PYTHONDONTWRITEBYTECODE=1`; put Rust targets and other
build caches outside snapshots. Bind reusable cache keys to candidate source,
protected driver/reference code, compiler identity and flags. Do not ignore arbitrary
changed files or weaken snapshot hashes to accommodate a cache mistake.

The runner commits each trial durably to SQLite. Development/blocked-mode JSONL
exports are materialized once at the end of an invocation, including ordinary
failure or interruption, rather than rewritten in full after every trial. After a
hard kill, the next run reconstructs exports from SQLite without repeating completed
trials. Read SQLite-backed status/report data for current progress; JSONL can lag an
active invocation. This removes a known quadratic serialization pattern; it is not
a measured end-to-end speedup claim.

An optimizer interrupted between dispatch and committing its active proposal remains
unresolved. The controller refuses another proposal or automated finalization,
even after generic recovery marks the call indeterminate. It preserves the raw
response/usage when available. This release does not automatically reconstruct and
apply an uncertain proposal-commit phase: inspect it and start a separately identified
experiment if necessary rather than buying an invisible retry.

Source-derived anchors and all-case reference/grader consistency establish finite
agreement with this executable contract, not independently established domain truth.
Exact input/group separation catches direct reuse only, not all semantic leakage.
Free-local oracle preflight rejects nonempty `grader_env` rather than quietly testing
a different environment from actual trials.
