# Statistics, selection and what a result means

## Estimand

The core computes an unweighted mean over cases, after averaging repetitions within
each case. Related case groups are the resampling unit. Group bootstrap resampling
retains the member cases and uses their count in the denominator. This estimates a
case-weighted mean while accounting for declared related-case clustering. It is not
an importance-weighted production traffic estimator. Represent frequency in the case
design or add a separately validated adapter/analysis for weighted objectives.

The baseline and candidate must have exactly matching case × repetition keys and
seeds. Missing/error/indeterminate trials invalidate comparison. Grades are checked
against declared finite bounds. No errors are silently dropped and no retries are
used to select the best attempt. Adapters must apply provided randomness controls;
matching seed fields do not make a provider honor seeds it does not support.

## Acceptance

For each primary/guardrail metric, candidate-minus-baseline case differences are
oriented so positive means favorable, then bootstrapped by related group. The
percentile interval uses a deterministic random seed. The primary metric's lower
bound must strictly exceed the minimum useful improvement. Each guardrail's lower
bound must be at least minus the tolerated regression. The minimum number of
independent validation groups is enforced, not the number of repeated trials.

The configured confidence is Bonferroni-adjusted across the primary and guardrail
intervals **for one candidate comparison**. That does not correct adaptive repeated
selection across candidates. Both the incumbent and original baseline comparisons
must pass, preventing a series of small tolerated regressions from accumulating
against the original system. No method makes these exploratory validation numbers
independent evidence once they are used for selection.

A held-out final test is opened only after the choice is sealed. It provides a
separate comparison, assuming its data were not previously inspected or leaked. It
can fail even after a convincing validation win. Do not tune on its failures and
continue calling it a test set.

## Important limitations

Percentile bootstrap intervals can be degenerate when all observed differences are
identical, are unreliable with very few independent groups, and do not capture unseen
failure modes. Repeated samples of the same task are not new tasks. No interval here
repairs labeling error, benchmark contamination, data leakage, selection bias,
nonstationarity, a once-built stochastic artifact, or a wrong objective.

The package does not currently implement confidence sequences, sequential
alpha-spending, hierarchical build-level resampling, weighted estimands, analytic
paired-proportion tests, or multiple independent search restarts with a meta-holdout.
Do not substitute an unqualified `1/sqrt(cases * repeats)` estimate for those issues.

For noisy latency/throughput: warm the application; isolate workloads and hardware;
keep correctness as a guardrail; measure the kernel rather than interpreter startup
when appropriate; repeat unchanged builds; interleave A/B or unchanged controls;
report units, hardware, environment and measured dispersion. A program's self-reported
runtime can be gamed—use a trusted external timer/counter when optimizing adversarial code.
The example's kernel timing is a cooperative demonstration, not an adversarial benchmark.

For an objective whose metric has a ceiling/floor, compare remaining headroom against
the minimum useful effect and baseline variance before launching the loop. The skill
requires that review; v0.1 does not automatically infer every metric's attainable
ceiling or an adequate power calculation from a bounds declaration.

## Judge calibration uncertainty (0.2)

Calibration measures each atomic criterion separately from composite business
metrics. Failure is the positive class. It reports missed failures, false alarms,
failure recall, failure precision and good-output specificity with explicit
class-conditional denominators. Undefined quantities remain null. Every missing,
uncertain, skipped, abstained or errored row is visible and blocks readiness.

Rows are grouped by their declared independent source. Rates first average the
relevant binary outcomes within a group, then give eligible groups equal weight.
Raw confusion counts describe rows; they are not independent sample counts.
This group-average estimand differs from a traffic-weighted production metric.

The prespecified lower-bound policy uses finite-sample Hoeffding bounds on bounded
independent group means, with a simultaneous correction for three rate checks per
criterion. This is deliberately conservative and retains uncertainty even for a
small sample with perfect observed agreement. Intervals rely on the declared
group independence and fixed sampling/criteria; they do not establish those
assumptions. A group construction that hides dependence invalidates inference.

Point-estimate policy is available for exploration, but a semantic-judge evidence
gate requires lower-bound readiness. Confidence and thresholds must be chosen
before inspecting the validation result. A failed support/bound check should
prompt more independent data or better measurement, not post-hoc threshold tuning.

Curated failures alter class prevalence. In particular, precision measured on a
failure-enriched set does not estimate production positive predictive value. Label
provenance, sampling notes, label uncertainty, model-role overlap and rubric drift
must be reviewed independently of any interval. Same-anchor judge drift reports
are diagnostic; after using them for judge tuning, collect fresh confirmation data.

## Opt-in temporal pairing for timing-sensitive experiments

Statistical pairing by case, repetition and seed is not temporal pairing. The
legacy/default path executes whole variant matrices separately and caches each
variant's validation results. Slow machine load or clock/thermal drift can then
look like an application change. Use the frozen opt-in measurement design for a
new timing-sensitive experiment:

```toml
[measurement]
design = "paired_ab_ba"
```

This mode shuffles case × repetition pairs with a deterministic recorded seed,
then executes each reference/candidate pair adjacently. First position is balanced
AB/BA within each case (exactly when repetitions are even, within one when odd)
and overall (within one when the total number of pairs is odd). Which position
gets the odd extra slot is randomized. The complete schedule, source labels and
source hashes are persisted before its first call. Application random seeds still
match within each pair. Statistics still average repetitions within cases and
resample related-case groups; repeated calls do not create additional independent
cases. The primary objective, effect threshold and guardrails are unchanged.

Each candidate's selection measures fresh paired cohorts against the incumbent
and the original baseline. If the two references have the same source hash, one
cohort serves both checks. Otherwise there are two separate cohorts, including
separate candidate measurements; their results are not pooled. Legacy cached rows
cannot substitute for either reference. The selected source and original baseline
hashes are sealed before a fresh final-test cohort. Even an unchanged final winner
uses two independent A/A measurement roles rather than comparing a row to itself.

This reduces slow drift; it does not eliminate carryover, nonlinear or rapid drift,
shared load shocks, or multiple adaptive-selection effects. AB/BA is not ABBA and
does not cancel every within-pair change. Repeats of the same workload need not be
independent environmental replicates. Use unchanged controls and prespecified
warmup, timer, workload, hardware and run-level checks. Self-reported kernel timing
remains cooperative evidence unless the measurement is independently trusted.

An interrupted half-pair is not completed later and represented as adjacent. Its
record and charges are retained, pending work can be marked indeterminate with
`recover`, and the cohort cannot drive selection or final confirmation. Resuming
at a complete pair boundary is supported without repeating completed calls. An
invalid final cohort keeps its winner sealed; recovery never reopens selection.
