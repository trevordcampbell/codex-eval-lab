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
