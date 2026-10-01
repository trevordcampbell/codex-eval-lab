# Optional atomic model judging

Start with [`openai_atomic_grader.py`](openai_atomic_grader.py) for the reviewed,
independently calibrated criterion workflow. It is an optional provider adapter,
not a required migration. Your application, optimizer and judge can use different
providers. This example uses OpenAI's Responses API with strict structured output;
the locked SDK is **OpenAI 3.22.1**. Tests use fake clients and an offline SDK
transport. No live provider judging or semantic calibration is claimed.

## One criterion, one independent decision

The adapter reads the frozen `reviewed_rubric` JSON created by
`eval-lab review rubric`, supplied explicitly with `--rubric`. The complete CLI
grader accepts a **semantic-only rubric**: every criterion must have `kind: judge`.
It validates the artifact's schema/hash, required meaningful fields, unique IDs and
metrics, and the 1–128 criterion limit before making any call. Original review,
anchor provenance and human-label validity are checked by the separate evidence
workflow, not proved by this adapter's hash check.

Every criterion receives its own fresh call, the same observed task/output/trace
and approved reference, and only its own criterion text. Calls do not share a
conversation, sibling verdicts, deterministic results or composite scores. A fail
or abstention on one criterion does not skip another. The provider sees neither
rubric reviewer/anchor metadata nor a human-label artifact. `expected` must contain
only an approved task reference; never put private calibration labels or rationales
there or in the input/output/trace. Payload fields are untrusted evidence, never
instructions to the judge. This prompt boundary is tested structurally; it does
not establish immunity to prompt injection.

The output retains each criterion's own `status` and `explanation` in
`criterion_results`, alongside its named metric: **pass=1, fail=0**. An `abstain`
keeps its reason and has **no fabricated numeric score**. Other criteria still run;
the evidence gate rejects the nondecision and retains raw results for diagnosis.
Without a gate, declare every criterion metric so a missing score still invalidates
the trial. Completed calls report the actual served model and summed input,
cached-input and output tokens, with cost summed across every criterion call.

## Install and configure an approved suite

Use the hash-locked optional dependency environment and test it before approval:

```sh
python -m pip install --require-hashes -r requirements/judge.txt
PYTHONPATH=src python -m unittest tests.test_atomic_judge -v
```

Copy `openai_atomic_grader.py`, your approved frozen `rubric.json`, and the dependency
lock into the suite. The adapter is standalone; it does not import the legacy grader
or depend on repository-relative imports. Include all three and any wrappers in
`harness_paths`. A representative configuration is:

```toml
harness_paths = ["openai_atomic_grader.py", "rubric.json", "judge-requirements.txt"]

[execution]
grader_command = ["{python}", "{suite}/openai_atomic_grader.py", "--rubric", "{suite}/rubric.json"]
```

Merge those fields into a complete suite configuration, not a second execution
section. Do not use `-S`, which disables the SDK's site-packages. Declare each
criterion's exact `metric` with bounds 0..1 and a maximized objective or guardrail.
Configure `expected_app_model` and `expected_judge_model` for evidence-gated suites.
The approved judge ID must exactly equal **every actual served response's model**;
an alias resolving to a different ID fails closed. No model names or prices are
guessed here. Explicitly allow these names in `execution.grader_env`:

```text
OPENAI_API_KEY
EVAL_JUDGE_MODEL
EVAL_JUDGE_APPROVED
EVAL_JUDGE_INPUT_USD_PER_MTOK
EVAL_JUDGE_CACHED_INPUT_USD_PER_MTOK
EVAL_JUDGE_OUTPUT_USD_PER_MTOK
EVAL_JUDGE_MAX_OUTPUT_TOKENS
```

Supply all three token prices from your applicable provider rates, and an exact
supported model with Responses structured-output support. Set
`EVAL_JUDGE_APPROVED=1` only after the operator approves sending these data and
incurring these costs. Configuration and rubric are validated **before** the CLI
constructs the network-capable client. This flag records operator intent; it cannot
authenticate human approval against another process under the same OS account.

The per-call output-token limit defaults to 1024 and accepts 128–32768; choose a
bound supported by the selected model. Calls run sequentially, each with a
45-second SDK timeout and `max_retries=0`. Budget the grader timeout for **all N
criterion calls**, plus overhead, and the whole-trial reservation for the
application plus **all N calls' possible input/output charges**. The token limit is
per call, not a total cost ceiling. Repeated evidence in each prompt incurs repeated
input charges. The engine's budget is not a provider-side hard spend cap.

On any request, response, model, usage or parsing failure, including a later call
after earlier paid calls succeeded, the adapter exits unsuccessfully without a
partial result. The controller conservatively retains the whole-trial reservation.
Do not catch that exception and report zero or only the earlier known cost, retry
silently, or treat it as a valid task failure. Usage-based estimates exclude taxes
and services outside this adapter; missing/invalid token usage is an error.

## Calibrate every semantic criterion before optimization

Follow the [evidence workflow](../../docs/EVIDENCE.md): inspect tuning traces, freeze
the rubric, obtain independent human criterion labels, and collect actual judge
predictions without showing the judge those labels. Run this same approved adapter
on every calibration trace, even when a deterministic check fails. Freeze the whole
evaluator and record `eval-lab evidence fingerprint --suite ...` in judge
configuration **before** sealing outputs.

For each trace and criterion, map the returned raw result into a prediction row:
`trace_id`, original `trace_sha256`, `criterion_id`, `status`, `reason` (the result's
`explanation`), and `model` (the actual returned model). Never derive these from a
composite score. Preserve `abstain`; a failed collection is an unresolved/error
case, not a free pass. Keep billing records and do not retry unknown outcomes.
Then use `eval-lab judge-results`, `eval-lab calibrate`, and
`eval-lab calibration-review` to inspect per-criterion disagreements and support.
Build and check the evidence bundle only after the prespecified lower-bound policy
passes. Approval to spend and approval to open the application final test are
separate. See the [protocol](../../docs/PROTOCOL.md) for raw response rules.

## Composing deterministic and semantic checks

The CLI and `grade(request, client, env, rubric)` produce a **complete grader
response for one semantic-only rubric**. They reject code-kind criteria rather than
silently asking an LLM to execute deterministic checks or silently dropping them.

`grade_criteria(request, client, env, criteria)` is a **semantic helper**, not an
automatic full mixed evaluator. An approved wrapper can validate its complete mixed
rubric through the evidence workflow, select its unchanged judge-kind criteria,
and call this helper with a retry-disabled client after approval/configuration
validation. Execute code-kind checks independently in deterministic code. Do not
gate semantic calls on code or composite outcomes. Merge disjoint raw criterion
results and metrics with exact coverage of the full approved rubric; then compute
any optional composite metric without replacing those raw results. Account for
every component's costs and propagate failures conservatively. Include wrapper,
rubric and helper in the evaluator fingerprint and calibrate that exact composition.

## Legacy illustrative example

[`openai_grader.py`](openai_grader.py) remains compatible with existing users of the
generic normalized `quality` (original ordinal 0–4) and binary `grounded` example.
It is illustrative, **not the recommended readiness flow**: it does not emit
independent criterion results and its scalar score is not a calibrated cardinal
utility. Likewise, `scripts/calibrate_judge.py` remains an aggregate agreement,
confusion and kappa demonstration, not per-criterion readiness evidence. Use the
atomic workflow above for new semantic-grader optimization.

Official [structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs)
was checked October 1, 2026. The real SDK contract is tested through `httpx2.MockTransport`
with no network, credentials or paid calls; live model behavior still needs approved
domain-specific validation.
