---
name: build-eval
description: Design and build runnable evaluations for applications, agents, models, skills and software benchmarks; automate contracts, cases, objective oracle checks and baselines, then scoped improvement when authorized. Use for eval design and outcome grading, not merely rerunning an ordinary unit test.
---

# Build the measurement and do the work

Read `references/AUTOMATION.md` and `references/PROTOCOL.md`. Run `eval-lab doctor`.
If unavailable, inspect `references/installation.json` where installed. Reuse the
project's actual provider, language, entry point and toolchain. Do not redesign the
application around a toy example or pretend the skill itself installs a runner.

The default is Codex doing the work. Inspect the requested flow and existing tests;
derive a concrete contract, representative/stress cases, grouped splits, adapters,
oracles, controls, scope and budgets. Make sensible reversible choices from the
user's goal. Do not make users fill evaluation forms, label mechanically checkable
answers, or approve each already-authorized iteration. Ask only for material
unresolved domain judgments, unavailable data, spend or action-policy authority.
Do not infer permission from silence, a plan file or an approval flag.

## Choose evidence suited to the task

For exact behavior, prefer executable outcomes: tests, end state, independent
reference algorithms and source-derived boundary anchors. Write the specification
and expected-result derivations explicitly, with truthful model/human/imported
origins. Independently implement the reference, use positive and known-wrong
mutation controls, and test metamorphic transformations on the application's
actual outputs where meaningful. Never certify an oracle by comparing it only
with labels produced by the same oracle. Two-model agreement is not ground truth.

For a new single-criterion full-output exact-JSON task, read
`references/EVAL_DESIGN.md` and enable its bounded generated controls.
Check plausible wrong outputs and valid alternatives, including boolean/number
confusion, missing/extra fields, ordered arrays, object-key order and numeric
spellings. Inspect capped or inapplicable family coverage. These derived probes
test the grader, not independent truth or application metamorphic correctness;
do not infer exact-JSON semantics for a semantic or mixed grader.

For JSON-only objective cases, the runner also checks every frozen case via the
reference and actual grader before search; keep private receipts out of proposer
context. Artifact-dependent outcomes need the separately validated task-specific
path until that preflight transport is supported.

Build `[oracle]` and its strict contract following `references/AUTOMATION.md` and
`examples/automation` in the checkout. Author the files yourself. Exact controls
need no human labeling ceremony; source authenticity, correctness of the intended
contract, representativeness and implementation independence remain explicit trust
assumptions. A model-generated case stays synthetic; an executable result does not
make its label human-reviewed or prove its production importance.

For semantic/business judgments, read `references/EVIDENCE.md`. Reuse genuinely
validated domain anchors when their content, source scope and criteria still
apply; preserve their exposure. Inspect approved redacted development traces,
record the real human/expert judgments and rationale, then form atomic criteria.
Keep model suggestions separate. Calibrate each semantic criterion on independent
judge-validation groups with the existing support and lower-bound gates. Do not
invent annotations or fill human confirmation fields. Escalate the actual ambiguity
and representative disagreements, not a blank form or every routine case. For a
mixed semantic/deterministic grader use that expert-evidence path so a deterministic
component cannot conceal an unverified semantic one.

## Build and audit before searching

Use actual inputs/state/assets and grade actual output/end state. Keep expected
answers private from the application; success claims are not outcomes. Record served
model, usage including retries, errors and raw per-criterion results. Add malformed,
negative and boundary cases, preserve sampling origin and independent groups.
Keep exposed controls out of validation/final groups and never inspect a final
holdout during optimization. If you saw heldouts while designing, use fresh
proposal sessions; a clean context is not an OS isolation boundary.

Run `eval-lab audit <suite>` (read-only), then `$audit-eval`. Resolve machine-checkable
failures yourself within scope. Explain uncertain domain assumptions succinctly.
Check measurement noise/headroom against the minimum useful effect. For timing use
trusted measurement, unchanged controls and a new paired AB/BA suite where warranted;
self-reported timers remain cooperative evidence. Do not silently shrink the scope
to fit a budget or change a frozen grader to improve scores.

## Execute within one explicit scope

For a requested end-to-end improvement, generate a plan with `automation-plan` and
use `automate` after existing authority covers exact commands, data, source scope,
eval limits, separate optimizer usage and final-test intent. See the command recipe
in `references/AUTOMATION.md`. The runner freezes/rechecks evidence, establishes the
baseline, iterates bounded fresh proposals, selects, seals, finalizes and reports.
No extra iteration approval is needed within that authority. Required spending,
private-data/security actions and new scope still follow host policy.

If the user requested measurement only, use the individual start/run/report commands
and leave final testing unopened unless included. Approval notes describe real
execution permission, not fictional human case review. Do not start provider calls,
Docker pulls, production side effects or arbitrary installations without authority.
Hosted evidence MCP tools stay read-only; native Codex drives the CLI with its own
authorized environment tools. The optional UI is for inspecting evidence, never a
mandatory gate or an agent-granted approval mechanism.

Deliver the concrete files, commands/run identity, evidence basis and unresolved
assumptions, measured result, costs versus unknown optimizer dollars, and report.
Changing evaluator bytes or semantics means a new experiment and baseline. Preserve
all failed attempts and the original runtime; do not retrofit old frozen runs.

Build and smoke-test candidate code in disposable copies before immutable
registration. Keep Python bytecode, Rust targets and other caches outside frozen
snapshots; bind cache keys to source, trusted driver/reference, compiler and flags.
Do not weaken hashing or ignore arbitrary changed files to hide a cache write.


When the author is the native host rather than a configured CLI backend, use a
new exact `automation-plan` with `start-native`, then `prepare-turn`, host dispatch,
`submit-turn` and `evaluate-turn --call-id`. Initialization runs configured oracle
preflight and protects final capacity through existing reservation semantics.
The active-only evaluation command cannot dispatch a new author. Keep the same
scope, receipt, uncertainty and final-authorization requirements; this additive
workflow was not used by the earlier frozen comparative benchmark.
