# Search broadly; confirm a sealed result separately

A conservative search gate can discard an inconclusive candidate that might still
be useful as a future parent. Whether retaining it helps is an empirical question:
changing the policy also changes later prompts and author choices. Historical
pilot outcomes or replayed decisions cannot isolate that causal effect. Exposed
pilot finals are reproduction evidence and must not be reused to tune this revision.

This revision introduces an **opt-in exploratory search policy**. Existing suites
retain conservative selection. Exploratory selections are explicitly unconfirmed;
the original final-test primary-superiority and guardrail-noninferiority checks
remain unchanged. A valid but inconclusive proposal can become a useful search
parent without acquiring a release claim.

## Freeze the objective before search

Specify the decision the output will support, the population/task unit, primary
metric and direction, useful-effect threshold, hard validity rules, and guardrail
tolerances. Explain why an improvement in that metric matters. A within-group
choice score and a global ranking score are different objectives; secondary
metrics must not replace the primary after outcomes are observed. Repetitions
and correlated tasks do not become independent search runs.

Check baseline headroom and measurement noise on development data. Validate the
actual adapter/grader protocol with positive and negative controls, including
type/shape boundaries when appropriate. Never improve an optimizer by changing
its cases, reference, grader, safety rules, cost ledger or heldout split mid-run.

## Versioned exploratory configuration

```toml
[search_policy]
schema_version = 1
mode = "archive"
archive_size = 8
parent_strategy = "diverse" # or "incumbent" for an ablation
allocation = "round_robin" # optional heuristic: "ucb"
operators = ["refine", "repair", "rewrite"]
diversity_scale = 0.1      # primary metric units; freeze before observing results
reward_scale = 0.1         # primary gain counted as a full allocation reward
exploration = 1.0
```

Omit this section for the existing conservative policy. Changes require a new
experiment. These parameters are part of the source-bound automation plan.

After complete paired development/validation matrices, the exploratory incumbent
changes only when the primary mean improves against the incumbent and original
baseline, with every empirical guardrail within its prespecified tolerance against
the original baseline. Missing, invalid, nonfinite or indeterminate measurements
are never treated as successful zeros. Statistical gates are also recorded, but
are not required for exploratory parent selection. Empirical guardrails are
search heuristics; their uncertainty remains part of the separate final check.

The bounded archive preserves the baseline and current incumbent. Remaining slots
take the highest development scores with distinct behavior buckets, using earliest
record order for ties. The descriptor is the per-case primary gain relative to
the baseline, rounded in units of `diversity_scale`. It uses training data only.
This suppresses small measurement jitter but does not prove semantic diversity,
equivalence or novelty. All original candidates and results remain in the audit
store even when they leave the active archive.

`refine` uses the incumbent. With diverse parents, `repair` and `rewrite` rotate
through other eligible archive entries deterministically. The three operator
instructions are fixed strings in the controller; the author interprets them. They do not implement separate verified repair/rewrite algorithms,
learn a policy, mutate themselves or guarantee that a proposal follows the intended
strategy. This is a modest deterministic routing portfolio. The selected parent,
operator, policy digest and allocation state are persisted before each proposal.

Round-robin cycles in configured order. UCB tries each operator once in that order,
then maximizes mean reward plus `exploration * sqrt(log(attempts+1)/operator_calls)`.
Reward is `min(1, positive_selected_gain/reward_scale) / evaluation_trials`.
Failed dispatched opportunities count with zero reward. Ties use configured order.
Model inference costs are unavailable to that reward and stay explicitly unknown.
This heuristic has no regret guarantee in an adaptive program-search environment.
A run that ends before revisiting operators does not test adaptive allocation.

With `paired_ab_ba`, actual incumbent/candidate and original/candidate comparisons
still use the existing fresh, separately retained cohorts. Archive ranking is a
noisy development heuristic; it never substitutes old timing rows for a new
comparison. Unfinished half-pairs remain invalid and cannot be replayed for free.

## Native authors with immutable evidence

Native Codex can use its authorized environment tools even when a standalone
Codex CLI is unavailable. The bridge itself does not dispatch a model. An external
host must enforce author permissions, admit the actual call, supervise its timeout,
and return one ordinary JSON response file. This is not a `native` optimizer backend
for `automate`; the one-command path still needs a working configured `codex` or
`command` backend and separate integration verification.

First audit a new suite and initialize a new state under existing authority:

```sh
eval-lab audit SUITE
eval-lab automation-plan SUITE --app APP --out NEW_PLAN.json
eval-lab start-native SUITE --app APP --state NEW_STATE --plan NEW_PLAN.json \
  --approve-plan --authorization-note "Actual bounded user instruction and its source"
```

`start-native` reuses the exact `automation-plan` validation, initialization and
protected final trial/evaluation-dollar reserve used by `automate`. It stops before
search and final comparison. Configured oracle preflight **executes now**, under
existing authority, with actual calls/charges in the shared ledger and the returned
initialization receipt. Private all-case oracle checks are not candidate final-test
execution; never expose their raw receipt to an author. The return includes
`plan_sha256`, `protected_final_trials`, `protected_final_reserved_eval_usd`, actual
`oracle_preflight.trials` and `budget`. The same record is retained as
`native_initialization` in controller state. No flag grants permission, and protected
capacity cannot extend the experiment deadline or guarantee valid completion.

Existing plain `start` remains available and does not gain a protected final reserve.
It cannot be upgraded in place. Use a new plan/state with `start-native` when a
protected native workflow is intended. Each iteration uses a **new** public directory
outside private state:

```sh
eval-lab prepare-turn NEW_STATE --out NEW_PUBLIC_WORKSPACE --approve-optimizer \
  --authorization-note "Actual bounded user instruction and its source" \
  --instruction-file PUBLIC_TASK.txt
# Preserve the returned call_id. Give a fresh author all three pinned inputs:
# - exact NEW_PUBLIC_WORKSPACE/evidence/prompt.txt content
# - NEW_PUBLIC_WORKSPACE/app/ as its public source directory
# - NEW_PUBLIC_WORKSPACE/evidence/response-contract.json (schema path/content)
# The author returns PROPOSAL.json conforming to that response contract.
# Do not edit the handoff app/ or evidence/ files or expose private state.
eval-lab submit-turn NEW_STATE --call-id CALL_ID --response PROPOSAL.json \
  --elapsed-s ACTUAL_SECONDS --outcome completed
# Only after submit-turn returns status "applied", evaluate that active round:
eval-lab evaluate-turn NEW_STATE --call-id CALL_ID
```

Replace uppercase names with actual paths/returned values; the host dispatch between
commands is intentionally explicit. The host must make the exact prompt, public
source and response contract available together before dispatch; a prompt filename
alone is not the response schema. Supply the pinned schema's path or exact content,
without rewriting its requirements or adding private controller state. `PUBLIC_TASK.txt`
must contain only authorized public task context, never the plan, private evaluator
or held-out results. `prepare-turn`
may execute still-needed baseline measurements before preparing the author context.
Read commands' JSON results rather than assuming exit status implies a proposal exists.

`evaluate-turn` is active-only: it can evaluate/resume this exact applied native
call, but cannot reserve another author or invoke any configured optimizer backend.
Missing, pending, indeterminate, mismatched and no-proposal calls fail closed.
Completed calls return their identical saved evaluation receipt after rechecking
current evaluator/runtime, source and proposal receipt identities, decision export,
optimizer completion, and absence of unresolved work or another active round. This
read-only duplicate path is allowed after expiry; new evaluation is not. Recovered
indeterminate trials and interrupted half-pairs remain invalid and are never replayed.

The returned `native_evaluation_receipt` records the call/label, parent/incumbent/
baseline/candidate source identities, original manifest/evaluator/dispatch/response
digests, `decision_sha256`, search/confidence outcomes and completion-time budget.
It is committed with active-round retirement in `native_turn:CALL_ID` in SQLite;
`evaluation_receipt_sha256` binds that saved object. Its budget is the original
completion snapshot, not a later live balance. Selection evidence stays private and
`release_qualified` remains false until separate final confirmation. If report
rendering is interrupted after receipt commit, the receipt remains available; use
`report` to rebuild that derived export.

Generic `loop` keeps its existing automatic-dispatch behavior. Do not use it as a
native completion/retry command: with no active round it can call the configured
backend. Start the next native opportunity with another `prepare-turn`. An empty
edit list is a durable no-more-proposals stop, not permission to dispatch an author.
Do not mix generic `loop` completion with `evaluate-turn` for the same call: only
the latter commits a native evaluation receipt.

Each prepared handoff reserves exactly one optimizer opportunity before external
dispatch. Malformed, failed and timed-out responses remain counted. Missing or
unreadable responses and partial/indeterminate submissions retain a blocker; do not
fabricate a success response or retry invisibly. Use `--outcome failed` or `timeout`
when submitting an actual captured response for that outcome. The host must preserve
actual admission, elapsed time and available model/usage evidence separately: the
current CLI accepts elapsed time/outcome but no verified model/token/cost import.
The native ledger initializes those unknown usage fields to null. They cannot be
inferred from a reservation, prompt length or configured model. No CLI flag creates
spending or data-access authority.

Once search has stopped and every applied round has completed, inspect status and,
only under the existing final-test authority, seal the selected source and write a
review report. Finalization rejects active rounds and pending/indeterminate trials
in either ledger, as well as unresolved authors. These checks also run before
returning a saved final result or resuming a sealed/incomplete final. Recovery does
not permit more held-out calls after an indeterminate trial or remove the existing
seal. Clean completed results stay read-only/idempotent; clean complete-matrix or
complete-pair-boundary resumes preserve the original sealed selection:

```sh
eval-lab status NEW_STATE
eval-lab finalize NEW_STATE --approve-final
eval-lab report NEW_STATE --out REVIEW_REPORT.html
```

A failed sealed final is retained and consumes the holdout. An unresolved author
attempt or invalid measurement requires investigation, not forced finalization.

Preparation writes controller-owned exact prompt, canonical development feedback, response contract,
invocation context and source hashes to fresh files. Their receipt digest is pinned
in SQLite before dispatch. Submission validates those inputs, captures the exact
response, and applies only scoped replacements to the pinned parent snapshot.
Overwritten feedback, source swaps, duplicate or partial submissions fail closed.
The public handoff copy is revalidated at submission; the authoritative controller
copy is revalidated during later evaluation/report/finalization. After successful
submission, author-workspace cleanup cannot remove the original evidence.
Automated command/Codex proposal paths also capture immutable dispatch evidence.
Public receipt metadata contains identity and digests, not private model text.

Author feedback has a frozen byte budget (`search.max_feedback_bytes`, default
65,536). Small feedback stays unchanged. Larger packets preserve complete all-row
numeric aggregates, worst-first per-case metrics, and bounded marked JSON-text
previews for at most three distinct cases. Exact omission counts and the full
feedback hash are recorded. Full rows remain in state and drive grading/statistics.
Rows tie-break by case ID and repetition. Apply the same format/budget to every
study arm. Historical engines under this shared adapter are described as such,
not as byte-identical historical prompts. The chosen source/operator is adaptive
selection feedback; private allocation reward statistics never enter author context.

The same-account host is a cooperative boundary. It must keep evaluator/state and
heldout files out of author prompts and workspaces; file hashes are not adversarial
read isolation or authenticated authorship. A controller that controls both files
and ledger can fabricate records. Imported opaque token/model values are not proof
of provider identity. Unknown native usage is not zero usage.

## Report distinct outcomes

Reports expose `best_found`, `validation_champion`, `release_champion`, and
`release_status`. `best_found` is the sequential search-selected incumbent, not a
retrospective global ranking of every candidate in the archive. `validation_champion`
tracks recorded confidence-gate acceptance, not an independently confirmed result.
Until final confirmation, neither archive admission nor search
selection is release qualification. If the sealed final fails, the selected source
and failure remain recorded and the release champion remains the original baseline.
The baseline label means the fallback source, not evidence that the baseline itself
meets every possible production requirement. Final failure consumes the holdout.

## Test the optimizer, not just its bookkeeping

Policy evaluation needs independent complete optimization runs. Meta-tuning tasks
and every attempt's costs belong in the accounting. Freeze the policy, public
prompts, resources and final task selection before exposing outer results. Compare
with an iterative Direct author given the same starting artifacts, eligible
feedback and opportunity limits; report actual usage instead of padding it.

Useful ablations separately remove exploratory selection, archive parents and
portfolio routing. Replay can diagnose changed choices on recorded candidates; it
cannot establish how a live author would have searched under different feedback.
Simulated/scripted policies test machinery. They are not evidence of native-model
advantage. Small pilots should report all run-level outcomes and costs without a
universal superiority claim or treating inner cases as independent author runs.

The design draws on diverse program populations and evaluation cascades in
[AlphaEvolve](https://arxiv.org/abs/2506.13131), budget allocation in
[Hyperband](https://www.jmlr.org/papers/v18/16-558.html), and the distinction between
adaptive tuning and holdout inference in
[adaptive data analysis](https://proceedings.neurips.cc/paper_files/paper/2015/file/bad5f33780c42f2588878a9d07405083-Paper.pdf).
These sources motivate testable choices; they do not establish that this
implementation improves outcomes. Current code does not implement a validated
early-pruning cascade, confidence sequences or a universal compute budget.
