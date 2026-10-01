# Codex Eval Lab: evidence-grounded critique and implementation requirements

Research checked 1 October 2026 UTC. This section records the source review, independently of implementation and validation. See EVIDENCE.md for shipped behavior and VALIDATION.md for executed checks.

## Bottom line

Build a trace-review and evaluator-validation workflow before optimizing the agent against its scores. The strongest differentiator is an inspectable chain from a real failure, to a human judgment, to an individually validated check, to a reproducible optimization decision. A polished aggregate score cannot substitute for that chain.

## What the critique actually establishes

Hamel Husain’s September 30 walkthrough with Isaac Flath used apartment-leasing conversations. It describes premature selection of a call-transfer failure, cumbersome Markdown/chat annotation, approval requested from label totals, and a four-check evaluator mixing one LLM judgment with three code checks. He preferred narrower checks and directly inspectable code/prompts. Importantly, he praised the tool’s issue discovery and agreed with much of Anthropic’s underlying guidance. This is evidence about the observed eval-building interaction, not a controlled comparison or a demonstrated failure of hillclimbing. The article does not report a hillclimb experiment. [Original review](https://hamel.dev/blog/posts/claude-auto-evals/)

Three qualifications keep the critique fair:

- A composite business rule can legitimately require several conditions. The defect is obscuring component correctness and failure attribution, not combining results at all.
- Deterministic checks remain useful. They need implementation tests and a valid definition of the property; a regex that consistently measures the wrong proxy is still wrong.
- Known contractual constraints and regression cases can be encoded before exploratory review. Require discovery for uncertain failure priorities, not an unnecessary ceremony before every obvious invariant. Anthropic explicitly advocates early capability tests as well as realistic failures and human calibration. [Agent-evaluation guidance](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

### Public discussion and current responses

The public X page exposed three replies before a “See all the replies” login gate. No login was attempted. This is an accessible sample, not overall community sentiment:

- Lance Martin acknowledges that the latest skill instructs an example viewer but does not lead the user through data before prioritizing; he says he plans to add that. This is a concrete acknowledgment and proposed change, not verification of a shipped fix. [Author response](https://x.com/RLanceMartin/status/2105491203898888629)
- Logan objects to approving graders from label counts and asks to see incorrect calls. [Reply](https://x.com/notloganhogg/status/2105473879355592908)
- SeldomSolemn asks which claims held up on real agent traces. [Reply](https://x.com/SeldomSolemn/status/2105495870590599438)

The visible tone is constructive skepticism plus an appreciative author response. The user-supplied themes about masking, human anchors, drift, and shared blind spots are methodologically important, but I could not independently attribute those additional themes to unseen replies. [Original discussion](https://x.com/HamelHusain/status/2105471347736682953)

### Do not freeze the comparison at the launch post

Anthropic’s September 28 post already describes reviewed inputs, a separate judge model, graded examples, repeated-output stability checks, infrastructure diagnostics, and overfitting controls. Its hillclimb illustration repeatedly selects changes using “test” performance. That makes those scores development feedback, even when transcripts are hidden. [Launch article](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)

The currently retrieved hillclimb guide explicitly offers a third validation slice with a final untouched test set for larger suites; its default remains train/test with the test score selecting the winner. It also includes environment fingerprints and no-change controls. Therefore, “Anthropic has no holdout protection” would be false. The stronger requirement is to distinguish selection data from final evidence consistently. [Current hillclimb guide](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/evals/eval-hillclimb.md)

The current build guide supports an existing viewer or its sanitized report builder, explicitly warns about unsafe HTML rendering, and has confusion-matrix guidance. It still describes input approval after choosing a flow, rather than a full human-led failure-discovery workflow. The retrieved source defaults to Markdown in one input-review path, despite the launch post’s simple-page description. Version differences and agent adherence both matter; do not claim that text in a skill proves actual behavior. [Current build guide](https://github.com/anthropics/skills/blob/main/skills/claude-api/shared/evals/build-eval.md)

## P0: requirements before a score is trusted

### 1. Separate discovery from classification

**Implement:** an explicit discovery state, followed by a human-confirmed failure definition and prioritization decision. Discovery records should support free-text observations and evidence spans without forcing a premature fixed taxonomy. The agent can propose categories and candidate examples; its proposals remain visibly distinct from human-confirmed labels. Prioritization should retain example IDs, severity, recurrence evidence, and why the failure matters.

**Pass criteria:** with an unfamiliar trace corpus, the workflow cannot silently promote suggested labels into gold or mark an evaluator “validated.” The reviewer can inspect at least one concrete supporting failure and a boundary/non-failure example for each chosen criterion. A known invariant may use a documented fast path. No universal sample count is a proof of adequate discovery.

Hamel and Shankar’s error-discovery workflow separates broad exploration from deeper investigation, and explicitly treats agent suggestions as provisional. [Error discovery](https://github.com/ai-evals-course/evals-skills/blob/main/skills/error-discovery/SKILL.md), [Review loop](https://github.com/ai-evals-course/evals-skills/blob/main/skills/error-discovery/review-loop.md)

### 2. Make labeling happen beside the evidence

**Implement:** a readable full conversation, paired tool calls/results, relevant context, timestamps or event order, and per-criterion labels with notes. Support `pass`, `fail`, `uncertain`, and `not_applicable`; keep unlabeled distinct. Include persistent autosave, undo, resume, stable trace URLs, and clear human/model provenance. Hide judge verdicts during initial human labeling to reduce anchoring; reveal them in disagreement review. Keep the exact rubric and judge prompt one click away.

**Pass criteria:** reload after labeling preserves label, note, criterion version and trace identity; uncertain cases cannot enter binary confusion counts unnoticed; a user can open every false-pass/false-fail row directly at its evidence. Render malicious trace HTML as inert text or a safely sandboxed artifact; no remote tracking image or script executes.

The custom-review guidance supports domain-native rendering, full traces, defer, autosave and reload testing. [Review-interface guidance](https://github.com/ai-evals-course/evals-skills/blob/main/skills/build-review-interface/SKILL.md)

### 3. Validate each component independently

**Implement:** each check needs an ID, type (`code` or `judge`), criterion, applicability rule, evidence, result and version. Compute a composite only after preserving those results. Calibrate the LLM component against criterion-specific human labels even when a deterministic check also fails. Do not let short-circuiting make the judge disappear from its validation dataset; mark legitimately skipped checks explicitly.

**Why this is essential:** consider 10 human-confirmed consent failures plus 10 good calls. A code rule happens to flag every failing call, while the consent judge incorrectly passes all 20. An AND composite can be 100% correct although the judge catches 0% of consent failures. This is a constructed counterexample, not a measured result from Hamel’s test.

**Pass criteria:** a fixture reproduces that counterexample and reports perfect composite accuracy alongside zero judge failure recall, with promotion blocked. Include a deterministic-pass subset as a deployment-relevant diagnostic, but do not use that subset as the sole judge validation population. Test code checks with positive, negative, boundary and malformed fixtures; test that event order and tool success are interpreted correctly. Distinguish `error`, `not_run`, and `not_applicable` from pass/fail.

### 4. Give the judge a real confusion matrix

**Implement:** compare frozen judge predictions against expert labels for its exact criterion. Declare `positive_label = fail` and report:

- TP: human fail, judge fail
- FN / false pass: human fail, judge pass
- TN: human pass, judge pass
- FP / false fail: human pass, judge fail
- Failure recall = TP / (TP + FN)
- Good-output specificity = TN / (TN + FP)
- False-pass and false-alarm counts, class support, confidence intervals and all disagreements

Use explicit names throughout. Hamel’s recent FAQ uses failure-positive polarity, while the current `validate-evaluator` skill uses pass-positive polarity; their TPR/TNR names therefore reverse. This is a real integration trap. [FAQ](https://hamel.dev/blog/posts/evals-faq/how-do-i-know-if-i-can-trust-my-automated-eval.html), [Validation skill](https://github.com/ai-evals-course/evals-skills/blob/main/skills/validate-evaluator/SKILL.md)

**Pass criteria:** all-pass and all-fail judges fail the appropriate gates even on imbalanced data; zero class support yields “not estimable,” not 0 or 100%; a known matrix has exact expected metrics. Show Wilson/binomial intervals for class rates and clustered uncertainty where observations share a source. Thresholds must be chosen for consequences and sample uncertainty; an arbitrary 90% point estimate or 100 labels is not universal assurance. Reviewer approval and measured validation should be different states.

## P1: requirements before optimization claims

### 5. Keep two kinds of splits conceptually separate

There are two learning problems: tuning the judge and tuning the application. Each needs its own documented exposure policy. Judge few-shot examples are training data; repeatedly inspected judge disagreements are development data; final judge calibration uses untouched labeled examples. Application hillclimbing gets train examples and selection/validation scores, then a separate final confirmation set after freezing the candidate.

**Implement:** immutable split manifests, dataset/content hashes, group IDs, and provenance for near-duplicates, conversation families and synthetic descendants. Keep a family in one split. Group by customer/session/source when independence requires it. Keep answer keys and final-test assets outside the optimizing agent’s accessible workspace and tools. A prompt saying “do not read” is not isolation.

**Pass criteria:** duplicated or derived families spanning splits are rejected; tuning access to final labels/transcripts fails; promotion records when a test was first opened; using final results to revise the candidate retires that test from final-test status. Small datasets may yield explicitly exploratory results instead of pretending to support a reliable final estimate. Preserve a versioned final confirmation artifact even if the result is disappointing.

Repeated adaptive use of data changes the validity of ordinary statistical estimates; hiding individual examples does not erase feedback from repeated aggregate scores. [Dwork et al.](https://arxiv.org/abs/1411.2664)

### 6. Use sampling for the right purpose

**Implement:** distinguish a probability/random monitoring sample from an enriched challenge/discovery set. Combine random traces with diversity coverage, known incidents and targeted rare-error searches; retain selection reasons and sampling probabilities when known. Report each population separately. Never infer production failure prevalence from a balanced judge-calibration set or an agent-selected hard set.

**Pass criteria:** every batch retains random exploration; dashboards identify enriched slices; an all-pass random sample does not close rare-risk coverage; changes in sample mix do not masquerade as model improvements. Priority estimates name their denominator and sampling caveats.

Random review can miss rare cases; classifier-based selection can miss unknown failure modes. Targeted review is useful precisely because it changes what is selected. [Sampling guidance](https://hamel.dev/blog/posts/evals-faq/how-can-i-efficiently-sample-production-traces-for-review.html)

### 7. Measure a candidate change rather than a moving test

**Implement:** freeze the evaluator, task definitions and reference labels during an application-comparison run. Record application and evaluator commit/hash, requested and served model, parameters, tools, environment, repetitions, retries, cost and errors. Compare baseline/candidate on the same cases; aggregate repeated trials within cases and use a paired, case/group-level bootstrap for generalization uncertainty. Repeats estimate within-case stochasticity; they do not create new independent user tasks.

**Pass criteria:** a rubric/check change invalidates direct comparisons until baseline and candidate stored outputs are regraded consistently; same-code control runs detect environment shifts; timeouts remain visible and cannot improve the headline through silent denominator removal. Report both valid-grade performance and operational completion/error rates. Require effect size plus uncertainty against a predeclared decision margin. Preserve regression suites even when saturated; harder discovery/capability suites serve a different purpose.

Answer leakage is a demonstrated agent-evaluation failure mode, including public benchmark solutions reached through search. Restrict evaluator secrets structurally and inspect suspicious winning traces. [Anthropic’s contamination investigation](https://www.anthropic.com/engineering/eval-awareness-browsecomp)

## P1/P2: judge independence and drift

### 8. Treat different-model judging as a safeguard, not proof

Same-model generation/judging is a risk factor, not automatically invalid. A different provider/family can still share a blind spot or implement the rubric badly. Compare candidate judges against the same human labels; prefer the one meeting criterion-specific failure-detection and false-alarm requirements. Hide generator identity, randomize pairwise ordering, test order reversal, and retain an independently labeled adversarial slice where the generator is confidently wrong.

**Pass criteria:** the judge detects human-verified failures regardless of generator family; order swaps and authorship labels do not materially change verdicts; disagreement between models routes to human adjudication rather than majority voting being called truth. Re-evaluate the generator-family slices after a model change.

Rubric-based research finds self-preference even for objectively checkable criteria, with ensembles mitigating rather than eliminating it. These results demonstrate a possible mechanism, not a guaranteed bias size for Codex Eval Lab. Hamel’s model-selection FAQ explicitly allows the same model if it validates against human labels. [Rubric-bias study](https://arxiv.org/abs/2604.06996), [Model-selection FAQ](https://hamel.dev/blog/posts/evals-faq/what-model-or-llm-should-i-use-to-build-automated-evals.html)

### 9. Detect three distinct forms of drift

**Implement:** maintain a fixed, human-labeled anchor set of stored outputs, plus fresh production review. Track independently:

1. **Evaluator drift:** a model/prompt/runtime change alters grades on unchanged anchors
2. **Population drift:** new inputs or slice proportions reduce reliability despite stable anchor performance
3. **Criteria drift:** experts change their definition of acceptable behavior after seeing cases

Record a rubric version, label-author/adjudication history and effective date. Replay old and new judges on the same anchors. Recalibrate on fresh labels when prompts, models, tools, context or population change. A materially changed rubric needs relabeling/bridge evaluation; do not splice the resulting scores into one unchanged historical metric.

**Pass criteria:** a deliberately modified judge trips an anchor alert; shifted slice data triggers review without a judge change; revised criteria mark old calibration stale. An alert identifies what changed and links affected false passes/false fails. There is no unqualified “validated forever” badge.

Criteria drift is supported by empirical research showing that users refine evaluation criteria while grading outputs. [Who Validates the Validators?](https://arxiv.org/abs/2404.12272)

## Minimal delivery sequence

1. Trace import, stable IDs, readable viewer, persisted human annotations, criterion evidence and provenance
2. Independent check records, gold-vs-judge disagreement review, explicit-polarity confusion metrics and masking fixtures
3. Split/lineage manifests, sealed final-test access, immutable evaluator identity, paired comparison reports
4. Anchor replay, fresh stratified reviews, drift/stale-calibration gates, cross-model robustness tests

A useful first milestone is not “the agent generated evals.” It is: an expert can open a real trace, record a defensible judgment, see exactly where the judge disagrees, and determine whether that judge is reliable enough for the intended decision.

## Verification limits

- The original article and three X replies were read in the cloud browser after web search returned inadequate content. Remaining X discussion was login-gated; no unseen reply was inferred.
- GitHub files above are mutable `main` links as retrieved on October 1. Their exact publication/update commits were not pinned, and their existence does not prove the installed plugin’s version or runtime compliance.
- These are design and test requirements for Codex Eval Lab, not claims about its current implementation. See the implementation map below; source recommendations are not automatically claims that every proposed feature ships.


## Implementation map for 0.2

- Trace-first discovery: sealed review packets, tuning-only blind annotation UI,
  human draft import, failure-mode anchors and frozen atomic criteria
- Judge masking: independent raw criterion outputs, concrete disagreement records,
  per-criterion recall/specificity/precision, missing and nondecision failure states
- Sample uncertainty: independent-group accounting, prespecified support and
  simultaneous Hoeffding lower-bound gates; exploratory point mode is not readiness
- Lineage: packet/output/rubric/judge/evaluator fingerprints, reviewer attestations,
  frozen evidence, served application/judge model checks, reapproval after changes
- Drift: offline comparison of actual old/new outputs on the same human anchors;
  no automatic population-monitoring service or self-relabeling
- Human interface: read-only MCP tools, optional MCP Apps tuning review, standalone
  labeling and calibration-disagreement views, explicit draft export/restore
- Deliberate limits: no authenticated proof of humanity in a same-user local workflow;
  no auto-saved sensitive labels; no invariant-only rubric shortcut; no production
  HTTPS/OAuth service or public-directory listing created by the local package

The original experiment controller, budget reservations, grouped splits, fresh
proposal sessions and sealed final test remain in place. New source tests exercise
composite masking, confidence insufficiency, stale evidence, private-data exclusion,
untrusted text, actual UI-export/CLI-import behavior and MCP protocol requests.

[Workflow](EVIDENCE.md) · [Plugin architecture](PLUGIN_ARCHITECTURE.md) ·
[Plugin use](PLUGIN.md) · [Validation](VALIDATION.md)
