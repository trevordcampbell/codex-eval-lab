---
name: hillclimb
description: Iteratively improve an application, agent, prompt, skill, model configuration, or software implementation against an existing trusted eval. Use only for explicitly authorized metric optimization with scope, guardrails, and budgets; never fabricate an eval win or change protected graders.
---

# Hillclimb with evidence, not score-chasing

Read `references/OPERATING_GUIDE.md`, `references/PROTOCOL.md`, and
`references/SECURITY.md`. Confirm a runnable, audited evaluation with a reviewed
baseline. Otherwise route to `$build-eval`. Preserve the existing model provider
and application stack unless migration is itself an explicitly approved objective.

## Approve the experiment

Identify one primary objective (quality, cost, latency or another measurable outcome),
minimum useful improvement, guardrails, editable file patterns and prohibited changes.
Inspect baseline failure evidence only from development data. Verify headroom, variance,
model/parameter propagation, real entry-point wiring, grader calibration and repeat
semantics. Use unchanged controls and rebuild stochastic artifacts where relevant.
Do not spend rounds on a metric incapable of detecting the intended change.

Approve maximum rounds, patience, wall-time window, evaluation dollars/trials, separate
Codex/custom optimizer usage and checkpoint cadence. Never call unknown optimizer cost
zero. Explain local versus genuinely isolated execution. Approval flags are a record
of permission, not permission the agent can grant itself.

## Preferred automatic workflow

For a suite configured with optimizer.backend = "codex", after explicit approval:

```sh
eval-lab loop <state> --approve-optimizer --rounds <approved-count>
eval-lab status <state>
eval-lab report <state> --out <state>/report.html
```

The controller launches fresh Codex proposal sessions in read-only mode, captures
structured edits, validates scope, creates immutable candidates and runs the eval.
It does not permit the proposal model to edit the evaluator or deploy its own changes.
Each round develops one coherent causal hypothesis, keeps/rejects the whole change,
and records effects against incumbent and original baseline. Neither model weights
nor live production are automatically modified. Empty proposals/no credible gains
are legitimate stopping outcomes.

Do not pass a full report, validation transcript directory or test answers into a
proposal session. Use `eval-lab feedback` for development-only evidence. For stronger
separation, `export-workspace` to another trust domain and `import-proposal` on the
private evaluator machine. A local read-only sandbox is not a holdout read barrier.

## Manual or existing-agent workflow

Register a candidate or unchanged control, execute train/validation, compare, and
select only if gates pass:

```sh
eval-lab register <state> --app <candidate-root> --label <variant> --hypothesis "<cause>"
eval-lab run <state> --label <variant> --split train
eval-lab run <state> --label <variant> --split validation
eval-lab compare <state> --baseline <incumbent> --candidate <variant>
eval-lab select <state> --candidate <variant>
```

Never quietly alter cases, rubric, metric direction, environment, accepted errors,
retries or budget mid-climb. A measurement fix requires approval and a new experiment/
rebaseline. Prevent cumulative tolerated regressions. Never optimize by hardcoding
evaluation IDs, expected answers or public benchmark solutions.

## Recovery and final confirmation

Use durable status rather than guessing progress. A stopped round resumes its saved
proposal. An in-flight attempt with unknown outcome is conservatively charged by
`recover` and invalidates that candidate's comparison; do not erase/retry it invisibly.
Use `unlock` only after confirming the old process is gone.

Once a winner is selected, obtain final-test approval and run:

```sh
eval-lab finalize <state> --approve-final
eval-lab report <state> --out <state>/report.html
eval-lab export-best <state> --out <new-review-directory>
```

Report final held-out delta and uncertainty, regressions, failed trials, costs and
exact artifacts. A validation win is not a final result, and a failed final is not
permission to keep tuning on that test. Do not push, merge or deploy without separate
user authorization. Never guarantee improvement, universality, or model superiority.
