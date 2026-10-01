# Trace review and judge calibration

An optimizer can follow a perfectly reproducible score that measures the wrong
thing. This workflow makes measurement review a separate, inspectable stage before
hillclimbing. It preserves the existing three-way application experiment split.

## Two different learning problems

1. **Judge development:** explore tuning traces, write criteria, then validate the
   fixed judge against human-labeled calibration-validation groups.
2. **Application optimization:** show the optimizer development (`train`) evidence,
   select with experiment validation, and open the final test only after sealing
   the selected source.

Calibration `partition` (`tuning`/`validation`) is not an application `split`.
Imported experiment traces may only come from `train`. The evidence gate also
rejects ID, group and exact-input overlap with the experiment's private
validation/test cases, including when an importer omitted a split marker.
Near-duplicate detection and truthful group assignment still require domain review.

## 1. Explore actual traces before inventing a rubric

Prepare approved, appropriately redacted JSONL records. Each has `id`, `group`,
`partition`, `input`, `output`, and a nonempty `trace` event list. Optional
`experiment_split` must be `train`; repeated observations include `case_id` and `rep`
and share their original group. Do not copy secrets or unauthorized production data.
Preserve actual outputs and tool results, rather than a model's retrospective claim.

```sh
eval-lab review create --traces traces.jsonl --reviewer 'Actual reviewer' \
  --source 'Approved source, time window, sampling strategy and redaction notes' \
  --out packet.json
eval-lab review render --packet packet.json --out review.html
```

Use `--source-kind synthetic` for generated fixtures. Their results only exercise
the workflow. Open `review.html` locally and inspect the tuning traces. Record
pass/fail/uncertain, a rationale, and free-form failure modes. Judge predictions
are absent from this first pass. Model suggestions never become human labels.
The page exports a draft; it does not approve a grader or run an experiment.

After the human completes the review, import their exported JSON:

```sh
eval-lab review annotate --packet packet.json --annotations annotations.json \
  --reviewer 'Actual reviewer' --confirm-human-review --out reviewed.json
```

Files are create-only. Make a new version for corrections. Confirmation flags and
reviewer fields record a real decision; an agent must not use them to impersonate
a reviewer. A local CLI cannot authenticate humanity against a process with the
same operating-system access. Content hashes detect stale/changed artifacts, not
forgery by that same operator.

## 2. Define atomic criteria from reviewed failures

Prioritize failures with the human before writing checks. Each criterion has:

- `id`, unique `metric`, and `kind` (`code` or `judge`)
- `description`, `failure_mode`, `pass_when`, and `fail_when`
- `anchors`: reviewed tuning IDs supporting an actual failure and a passing case

Use independently inspectable checks. A composite policy may still combine them,
but it cannot replace the raw decision of any component. For known invariants,
ordinary existing deterministic tests remain useful; this strict trace-derived
rubric path intentionally requires reviewed anchors.

```sh
eval-lab review rubric --packet packet.json --review reviewed.json \
  --criteria criteria.json --reviewer 'Actual reviewer' \
  --confirm-human-review --out rubric.json
eval-lab review render --packet packet.json --rubric rubric.json --out labeling.html
```

Only after freezing the rubric, label the independent calibration-validation
examples by criterion. Export the draft and import it:

```sh
eval-lab review label --packet packet.json --rubric rubric.json --labels labels.json \
  --reviewer 'Actual reviewer' --confirm-human-review --out human-labels.json
```

Each row is bound to its trace hash and criterion. Missing judgments remain missing;
uncertainty is retained and blocks readiness rather than being forced into a class.
Changing a rubric invalidates its old labels. Importing a file cannot prove when a
person viewed it; protect calibration validation during rubric development.

## 3. Measure the judge independently

Before collecting predictions, finalize the suite and run
`eval-lab evidence fingerprint --suite ./suite`. Record the returned value in
`judge_config.evaluator_fingerprint`; sealed outputs bind it and cannot be rebound
to another evaluator afterward. Configure `execution.expected_app_model` and
`execution.expected_judge_model` to match the recorded roles and actual served IDs.

Obtain actual predictions for every criterion from the configured judge, including
cases where a code check also fails. The library does not silently call a provider.
Run an existing approved grader or adapter separately, with explicit cost limits.
Do not show it human labels. Prediction rows contain `trace_id`, `trace_sha256`,
`criterion_id`, `status`, `reason`, and the actual served `model`.

`pass`, `fail`, `abstain`, `skipped`, and `error` are distinct. Short-circuited judges
remain skipped; deterministic checks cannot fill their results. Bind imports to
the exact rubric and judge configuration:

```sh
eval-lab judge-results --packet packet.json --rubric rubric.json \
  --judge-config judge.json --rows predictions.json --out judge-outputs.json
eval-lab calibrate --packet packet.json --rubric rubric.json \
  --labels human-labels.json --judge-config judge.json \
  --outputs judge-outputs.json --policy policy.json --out calibration.json
```

To inspect the actual wrong calls beside both explanations:

```sh
eval-lab calibration-review --packet packet.json --rubric rubric.json \
  --labels human-labels.json --judge-config judge.json \
  --outputs judge-outputs.json --policy policy.json --out disagreements.html
```

This is a human-only artifact. Do not send calibration-validation traces into a
judge-tuning or optimizer conversation.

The report uses **failure as the positive class**:

- Missed failure: human fail, judge pass
- False alarm: human pass, judge fail
- Failure recall: how much human-confirmed failure the judge catches
- Good-output specificity: how often genuinely passing outputs remain passing
- Failure precision: how often a judge failure corresponds to a human failure

Reports contain concrete disagreements and both explanations, class support,
unresolved cases, raw confusion counts, and independent group counts. Rates are
averaged within related groups first, then across groups. Replicas do not create
new independent support. An undefined rate is `null`, never 100%.

Choose policy thresholds and support requirements before comparing judges. The readiness gate for semantic judges requires prespecified lower-confidence
bounds. Point-estimate mode is exploratory only and cannot authorize that gate.
Confidence bounds concern declared independent groups and their specified estimand. They cannot repair bad labels or a biased sample. In particular,
precision on an oversampled failure set is not production precision. Different
models can share blind spots; recorded same-family/unknown-family overlap requires
an explicit risk justification, and changing a model name proves no independence.

A failed calibration writes an inspectable artifact and returns a nonzero exit code.
Do not relax the policy after observing a failure just to make the command succeed.

## 4. Bind readiness to the executable evaluator

Add an evidence path to the evaluation suite:

```toml
[evidence]
bundle = "review-evidence.json"
```

Build the bundle after the suite's grader/configuration is finalized:

```sh
eval-lab evidence build --suite ./suite --packet packet.json --review reviewed.json \
  --rubric rubric.json --labels human-labels.json --judge-config judge.json \
  --outputs judge-outputs.json --policy policy.json --out ./suite/review-evidence.json
eval-lab evidence check --suite ./suite
```

The gate recomputes readiness from the embedded source artifacts. It does not trust
an imported `passed: true`. It binds the grader source, configuration and model
identity, requires complete independent criteria, and freezes the evidence with the
evaluator. A changed artifact or grader requires fresh calibration and a new
approved experiment. Atomic success metrics use pass=1/fail=0 and must affect a
maximized objective or guardrail; cost/latency can remain separate minimized goals.

Graders in this mode return `criterion_results`, keyed by criterion ID, with raw
`status` and `explanation`, in addition to numeric `metrics`. Read the protocol
for its exact strict schema. Skipped/error or inconsistent component results
invalidate the trial and remain recorded for diagnosis.

The gate is opt-in for backward compatibility. `not_configured` means no mechanical
measurement-evidence gate was applied. The four skills require this workflow for
real semantic-grader optimization; an old synthetic demo is not a validity badge.
Approval of execution, spending and the final test remains separately required.

Include the grader's dependency lockfiles and other behavior-defining artifacts in
`harness_paths`, and actually run the locked environment. A source digest cannot
prove an external service stayed unchanged or that an operator installed the lock.
Provider-side changes require fresh anchor checks even when a model ID is unchanged.

## 5. Replay anchors and investigate drift

Use the same frozen human labels to compare old/new judge configurations and actual
predictions. `eval-lab calibration-drift --help` lists the source artifacts needed;
it recomputes both sides instead of trusting two supplied summary reports.

Treat changes in criteria, served model, prompt, adapter or sampled population as
reasons to review validity. Repeatedly tuning on the same anchors makes those anchors
development data. Obtain fresh held-out groups for confirmation. The command checks
judge-output drift; it is not an autonomous population-drift monitoring service.

## Plugin and trust boundaries

The optional plugin exposes read-only tools and an MCP Apps review surface where the
host supports it. Standalone HTML works without native rendering. Human draft
exports are imported through the explicit workflow above. No MCP tool approves
labels, starts paid experiments, or opens application final-test details.

MCP `_meta` keeps detail out of the ordinary model result, but is not encrypted
storage or a human-authentication boundary. App-only visibility is also not
permission. Read [security](SECURITY.md) before providing sensitive traces.

## Objective outcomes and automation

The native executable-oracle path is separate from this expert-label workflow.
See [AUTOMATION.md](AUTOMATION.md) for source-derived boundary anchors, executed
reference/positive/negative controls, bounded orchestration and truthful provenance.
No machine-created output is imported as a human annotation, and no agreement
threshold in the semantic calibration path is relaxed. Use this existing path for
mixed semantic/deterministic criteria; the two top-level evidence configurations
are intentionally exclusive in the first oracle version.
