# Optional model-based grading

`openai_grader.py` is a complete **optional adapter example**, not a default provider
migration. It accepts the standard grader request and returns normalized `quality`
and binary `grounded` metrics through OpenAI's structured Responses API. It has
fake-client contract tests; it was **not** executed against a live model.

Use your own existing provider/judge instead when appropriate. This example does not
require the application under evaluation or the optimizer to use the same provider.
Calibrate the rubric against independent human judgments before trusting its scores.
Do not grade factuality against model-generated “gold” without reviewing that gold.

Install the official `openai` Python SDK in your approved adapter environment, pin the
version you validate, and configure an exact supported served model identifier. No
model IDs, subscription costs, current token prices or API keys are guessed here.

Copy the grader into the suite, include it in `harness_paths`, configure
`grader_command`, declare `quality` and `grounded` (both bounded 0..1), and explicitly
allow these environment names in `execution.grader_env`:

```text
OPENAI_API_KEY
EVAL_JUDGE_MODEL
EVAL_JUDGE_APPROVED
EVAL_JUDGE_INPUT_USD_PER_MTOK
EVAL_JUDGE_CACHED_INPUT_USD_PER_MTOK
EVAL_JUDGE_OUTPUT_USD_PER_MTOK
EVAL_JUDGE_MAX_OUTPUT_TOKENS
```

Provide all prices from the current applicable provider pricing and set
`EVAL_JUDGE_APPROVED=1` only after approval. Set a bounded output-token limit (for
example 1024, subject to the chosen model). The controller's `grader_timeout_s` should
exceed the client's 45-second timeout. Do not use `-S` for this third-party SDK adapter.
SDK retries are disabled; errors stop the trial rather than silently making more calls.

Calculate an application-plus-judge upper reservation and total evaluation budget
before `start`. A client timeout may still incur provider cost. The ledger conservatively
charges the trial reservation on unknown outcomes; this is not a provider-side spend cap.
Token-derived cost uses cached/uncached input and output prices separately, and excludes
any services not called by this adapter. The grader compares the served model to the
operator's approved exact ID; aliases that resolve differently will fail closed.

The rubric is deliberately generic and should be rewritten, tested and approved for
your domain. Scalar rubric scores are not automatically calibrated cardinal utilities.
For blind pairwise grading, randomize positions, retain ties, run order-swapped control
cases and normalize preference rather than converting ordinal ratings casually.

Calibration data for `scripts/calibrate_judge.py` has this shape:

```jsonl
{"id":"review-1","human":"pass","judge":"pass"}
{"id":"review-2","human":"fail","judge":"pass"}
```

The calibration script reports agreement, confusion and kappa without calling a model.
It does not authorize deployment based on an arbitrary threshold.

Official API reference inspected September 30, 2026:
https://developers.openai.com/api/docs/guides/structured-outputs
