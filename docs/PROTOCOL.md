# Adapter protocol: any application, any language

The core only requires executables that read one JSON request from stdin and write
**exactly one JSON object** to stdout. Logs go to stderr. Commands are argv arrays,
not shell strings. Wrap an existing runner rather than rewriting it. The core has
no dependency on a model provider, agent SDK, web framework, or programming language.

## Application request

```json
{
  "schema_version": 1,
  "case_id": "refund-01",
  "input": {"message": "Please explain this refund"},
  "rep": 0,
  "seed": 197553,
  "assets": [".eval-inputs/0-source.png"],
  "artifacts_dir": "/isolated-output-directory"
}
```

Only this case's declared assets are copied into the disposable app directory.
The request does **not** contain expected answers, a split name, or the evaluator
location. Case IDs may be task-visible; do not encode labels or splits in real IDs.
The synthetic examples deliberately include split markers for leakage tests.
A seed is supplied; adapters must actually apply it wherever supported. Supplying
one does not make external APIs deterministic. Record ignored randomness controls.

## Application response

```json
{
  "output": {"answer": "A refund was issued"},
  "model": "actual-served-model-or-program-version",
  "usage": {"cost_usd": 0.001, "input_tokens": 123, "output_tokens": 45},
  "trace": [{"role": "assistant", "content": "A refund was issued"}],
  "metadata": {"tool_calls": 1}
}
```

`output` can be any JSON value. `usage.cost_usd` is **mandatory**, finite, and
nonnegative. An explicitly free deterministic adapter reports zero. Never use zero
as a substitute for unknown cost. Include every internal retry and downstream model
or tool charge in that figure. Set SDK retry policy explicitly; the lab never retries
silently. Return the model from the actual response, not just the configuration.
The optional expected model fields make a mismatch invalidate the run.

Keep image/video/binary artifacts in `artifacts_dir`, not base64 in a transcript.
An output may describe their paths relative to that directory. Graders can inspect
those artifacts. The HTML report preserves the artifact-directory reference and
shows bounded model-content previews as escaped text, with explicit truncation/omission
and raw-state locations (see the operating guide); it intentionally does not execute arbitrary HTML/SVG
or automatically render/download external media. For rich media review, use a
separately sandboxed viewer. Artifact disk usage needs an OS/container quota for
untrusted apps; the core caps stdout/stderr, not arbitrary disk writes.

## Grader request

The separate, trusted grader receives `input`, `expected`, `output`, optional
`trace`, `case_id`, `rep`, `seed`, and `artifacts_dir`. It receives the **same output**
that was produced by the measured application call; never rerun to obtain a nicer
answer. The grader is allowed to read private labels and output artifacts. Do not
make grading depend on the candidate's claims about its own success.

## Grader response

```json
{
  "metrics": {"quality": 1.0, "format_valid": 1.0},
  "explanation": "All three approved criteria satisfied",
  "model": "actual-judge-model-or-grader-version",
  "usage": {"cost_usd": 0.0005}
}
```

Every declared metric must be present, with no undeclared extras. Values must be
finite numbers, not booleans or numeric strings. Convert booleans to 0/1 explicitly.
Configured bounds are enforced. The runner owns `latency_s` and `cost_usd` when those
metrics are declared. `latency_s` measures app subprocess time including startup;
`cost_usd` includes application **and grader** charges. To optimize production cost
without judge cost, return a separate `production_cost_usd` metric from the grader
using a trustworthy application output/trace field, and disclose its provenance.
For kernel performance use a separate metric like `kernel_ms` and warm repeated
measurements, as in `examples/benchmark`.

A legitimate task failure returns a valid result with a failure score (for example
quality 0). A crashing adapter, malformed JSON, missing cost, wrong served model,
timeout, or failed infrastructure is **not** a valid zero-scoring task. Such trials
invalidate comparison, retain evidence, charge conservatively, and halt execution.
Do not silently remove them from the denominator or turn them into successes.

## Cases

Each line of `cases.jsonl` is an object:

```json
{"id":"case-001","input":{"message":"..."},"expected":"billing","tags":["billing","hard"],"group":"conversation-17","assets":[],"metadata":{"origin":"human-verified production-derived"}}
```

Required: `id`, `input`. Optional: `expected`, `tags`, `group`, `assets`, `metadata`,
`split`. `tags[0]` is the stratification label. Group related requests, users,
conversations, documents, or templates so related cases cannot cross splits.
Identical JSON inputs with identical asset paths must share a group. This is an
exact-duplicate check, **not** a semantic deduplicator; review paraphrases and
near-duplicates yourself. Assets are suite-relative ordinary files, never symlinks.

With no explicit splits, the runner uses deterministic, stratified 60/20/20 group
allocation. Tiny strata may have no validation/test groups; audit discloses that and
automatic optimization refuses insufficient validation groups. Alternatively assign
`split` (`train`, `validation`, or `test`) to **every** case. Related groups still
cannot cross splits. The labels mean development, adaptive selection, and final
confirmation—not model-weight training.

## Configuration

Use `examples/routing/eval.toml` as a complete, zero-dollar reference. Important
fields:

| Section | Contract |
| --- | --- |
| Top level | `schema_version=1`, `name`, `cases`, `repetitions`, `seed`, explicit `source_paths`, `harness_paths` |
| `execution` | `mode=local` or `docker`, `app_command`, `grader_command`, two timeouts, output limit, optional env allowlists and model assertions |
| `metrics.NAME` | Optional finite `minimum`/`maximum` and description |
| `objective` | Declared metric, `maximize`/`minimize`, minimum meaningful improvement, confidence, minimum validation **groups**, bootstrap count |
| `guardrails` | Array of metric, direction, and maximum permitted regression (absolute metric units) |
| `budget` | Evaluation dollar ceiling, conservative **whole-trial** reservation (app + judge), max trials, wall-time window, separate optimizer call limit |
| `search` | Explicit editable path patterns, max rounds, patience, maximum replacement bytes |
| `optimizer` | `codex` or `command`, optional model, timeout, explicit environment allowlist |

The core rejects unknown configuration keys rather than ignoring typos. Directions
are explicit: lowering `cost_usd` is not the same as raising `quality`. Guardrail
tolerances are absolute, not relative percentages. Use a log/normalized metric via
your adapter to express relative objectives.

Supported command substitutions: `{python}`, `{app}`, `{suite}`, `{artifacts}`.
`{python}` is the current Python interpreter, or `python3` inside Docker. The
application cannot reference `{suite}`. There is no shell expansion. For a Rust
binary use `["{app}/target-binary"]`; for Node use `["node","{app}/runner.mjs"]`.
Build/install dependencies before approval; include lockfiles and pin images/toolchains.
Declare all grader helpers and fixtures in `harness_paths`; the runner cannot discover
every dynamically loaded dependency or hash a remote service for you.

## Proposal contract

```json
{"hypothesis":"Normalize case before classifying; category semantics should not change","edits":[{"path":"app.py","content":"complete replacement file contents"}],"notes":"Check that proper-noun-sensitive behavior does not regress"}
```

The controller validates every path and the total byte limit **before** copying a
candidate. Off-scope paths, traversal, symlinks, duplicate edits, and no-op changes
are rejected. File creation is supported within the allowlist. Deletion, binary
edits, model-weight fine-tuning, and arbitrary shell patch application are not part
of the v0.1 proposal format. Adapt a different artifact through a textual manifest
or use a manually registered candidate. Never edit the frozen evaluator to win.

## Measurement evidence (0.2)

Optional `[evidence]` configuration contains exactly `bundle = "relative-path.json"`.
It references a recomputable bundle of review packet, human walkthrough, anchored
rubric, criterion labels, judge configuration, raw outputs and prespecified policy.
The engine freezes this file with the evaluator. See [EVIDENCE](EVIDENCE.md) for the
artifact schemas and workflow. Absence is reported as `not_configured`, never ready.

A gated semantic grader must assert both `execution.expected_app_model` and
`execution.expected_judge_model`. Record the evaluator fingerprint in judge
configuration before sealing its calibration outputs. Source/config/model changes
invalidate this binding; a new experiment is required for a changed evaluator.

Raw grader responses can additionally contain:

```json
{
  "metrics": {"confirmation_ok": 0},
  "criterion_results": {
    "confirmation": {"status": "fail", "explanation": "Required confirmation was absent."}
  },
  "usage": {"cost_usd": 0},
  "model": "actual-served-judge-id"
}
```

Statuses are `pass`, `fail`, `abstain`, `skipped`, or `error`. Explanation is required
and bounded. Each rubric criterion has one unique numeric success metric, pass=1
and fail=0; that metric must affect a maximized objective or guardrail. Minimized
cost/latency objectives remain supported separately. With an evidence contract,
coverage must be exact and values consistent. Nondecisions invalidate a trial;
the raw component evidence remains available for diagnosis. A composite business
metric may be an additional metric, but cannot substitute for component evidence.

Trace packets use calibration partitions `tuning` and `validation`. These are
separate from experiment splits. They carry immutable trace digests and explicit
provenance. File import does not verify provenance or human identity. Never pass
private calibration or application-heldout records into optimizer feedback.

## Temporal measurement mode

For new timing-sensitive experiments, optional `[measurement]` accepts exactly
`design = "paired_ab_ba"`. This is a frozen execution-design choice, not an adapter
field or a change to the configured objective. Omitting it preserves legacy
variant-blocked execution and cached validation references; an audit warns that
case/seed pairing alone does not protect against time drift.

In paired mode, `run --split train` still creates development feedback.
`select --candidate LABEL` executes or resumes fresh validation comparison cohorts
before applying the existing two-reference gates; `loop` does the same for each
proposal. A standalone validation `run` is refused so cached matrices cannot be
mistaken for temporally paired measurements. `compare` reads recorded paired
selection results and never executes adapters. `finalize --approve-final` creates
a fresh paired final cohort after sealing the winner and baseline source hashes.

SQLite keeps separate `paired_cohorts` and `paired_trials` records. A source label
identifies frozen code; a cohort and role identify a measurement. Original trial
rows are not replaced. Schedule JSON, per-role JSONL and comparisons are exported
under `paired-cohorts/`; the database remains authoritative after interruption.
Reports display separate cohort comparisons instead of pooling them into a
single per-source validation score. All legacy and paired attempts count toward
the same approved trial, cost and wall-time limits. See the operating guide for
budgeting and recovery behavior.

## Executable-oracle and orchestration contracts

A new suite may declare `[oracle] contract = "oracle.json"` instead of the expert
`[evidence]` bundle path. The strict schema and complete example are documented in
[AUTOMATION.md](AUTOMATION.md) and `examples/automation`. Oracle controls use a
separate declared local reference, specification-derived anchors, actual grader
responses and known-wrong output mutations. The artifact records model/human/imported
origin; it is not a human-review receipt. Free-local preflight requires an empty
`grader_env` to keep checks and actual grader execution consistent. Private cases
cannot also serve as exposed development controls. The runner checks declared anchors/mutations and separately runs the reference
on every frozen case without its expected value, then requires the actual grader
to pass that exact reference output under the frozen expected data. This detects
consistency errors; it does not prove reference/specification validity. Raw private
case receipts stay in the controller, never proposal or default report context.
This route supports JSON-only cases without file assets or artifact-dependent grading.

`automation-plan` records scope and bytes without executing code. `automate` verifies
that plan and consumes authority already granted through the user's host policy.
Every oracle check is reserved before execution in the same SQLite trial ledger
(split `oracle`, label `oracle-preflight`); it contributes to `budget.trials` and
charges. A separate raw receipt preserves commands' responses and streams. Final
capacity is protected for automated plans. `automation-result.json` exposes
provenance, selection/final status and accounting without private control rows.
