---
name: build-eval
description: Design or extend a representative, runnable evaluation for an application, agent, model, skill, software benchmark, or generated artifact. Use for eval design, case curation, outcome grading, and baseline construction; not merely to rerun an ordinary unit test.
---

# Build a trusted, runnable eval

Read `references/OPERATING_GUIDE.md` and `references/PROTOCOL.md` before building.
Run `eval-lab doctor` to establish whether the engine is installed. If it is absent,
explain the missing prerequisite; do not claim these instructions alone install it.
Do not change the application's provider, SDK, language or architecture to fit an
example. The engine is optional plumbing around the project's real entry point.

## Walk through real traces before choosing evals

Start with the user's approved, redacted development traces and existing failures,
not a metric menu or generated labels. Build a review packet and let the user inspect
inputs, actual outputs, tool calls and outcomes in context. Keep judge predictions
and agent-suggested labels hidden during the first human pass. The human marks
pass/fail/uncertain, explains what went wrong, and identifies failure modes.
Do not ask the user to bless an aggregate score or label-count table.

Use representative samples and separately identified stress cases. Preserve source,
time window, sampling rationale and related-case groups. Never import final-test
or experiment-validation traces into development review. Calibration validation
is a distinct partition and must not be used to invent/tune criteria.

Only after this walkthrough, summarize human-observed failure modes and ask which
are worth measuring. Link each proposed atomic criterion to reviewed tuning anchors.
Offer a separate deterministic check for exact invariants and an independently
calibrated judge for semantic judgments. Do not combine several behaviors into one
criterion that hides the reason for failure. If the user has no suitable data,
help them collect a small authorized sample; synthetic demonstrations do not become
human-reviewed production evidence.

Read `references/EVIDENCE.md` for the review and calibration commands. Record actual
human judgments; do not fill review forms or set confirmation flags on their behalf
without those judgments. A local reviewer field is an attestation, not authentication.

## Establish the contract

Inspect the requested codebase and existing evaluation/test infrastructure first.
Identify one flow, its actual inputs/state/assets, observable outcome, baseline,
practical constraints and proposed editable surface. Reuse what works; wrap an
existing harness. For mixed-language repositories, use the current runner rather
than rewriting application logic in Python.

Propose concrete defaults. Gather only missing decisions: representative input
sources; output/end-state grading; important metrics/guardrails; budget and execution
permissions. Check retention and sensitive data before pulling production records.
Prefer human-verified real cases; label synthetic/stress cases honestly. Use stable
case IDs and group related users, conversations, documents and templates.

Show actual cases in the user's preferred review format. Get explicit approval of
cases/labels (or a disclosed stratified review for a large set). Do not infer approval
from silence. Define deterministic outcome checks first; use calibrated rubric or
blinded pairwise judging where the output requires judgment. Get separate approval
of the grader after reviewing a pilot and disagreements. Never use the tested model's
answers as unverified ground truth.

## Build the runnable path

Create a versioned suite with eval.toml, cases.jsonl, a thin app adapter, a separate
grader and declared fixtures. The app receives no expected answers. Log the actual
application output/trace, served model, usage, artifact paths and independent grade
from the same trial. Internal retries must be explicit and charged. For coding and
tool agents, grade hidden tests and end state, not success claims in transcripts.

Add smoke and negative-control tests. Run `eval-lab audit <suite>` before paid calls.
Explain what the automated audit cannot establish: representativeness, label truth,
judge calibration, model wiring, real-world proxy validity and environment drift.
Size independent cases/repeats against the minimum useful effect and noise; do not
silently reduce the experiment to fit a budget.

Obtain approval for commands, scope, isolation mode, per-trial reservation, total
evaluation limits and separate optimizer usage. For an approved suite:

```sh
eval-lab start <suite> --app <application-root> --state <external-state-dir> \
  --approve-cases --approve-grader --approve-execution --note "<actual human approval>"
eval-lab run <state> --label baseline --split train
eval-lab run <state> --label baseline --split validation
eval-lab report <state> --out <state>/report.html
```

Never set approval flags without the corresponding authorization. There is no
universal sandbox in local mode. Use Docker for app isolation and the documented
export/import workflow with a separate trust domain for real optimizer/holdout
separation. Do not claim merely placing files outside the repo hides them.

## Handoff

Deliver exact commands, case/group/repeat counts, baseline evidence, limitations,
actual versus unknown costs and report location. Leave the final test unopened.
Transition to `$hillclimb` only with a working trusted eval and approved plan. An
agent that reviewed all cases must not become the optimizer with that same context;
use fresh proposal sessions or an exported development-only workspace.
