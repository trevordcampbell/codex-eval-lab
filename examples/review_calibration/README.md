# Trace review and criterion calibration, offline fixture

Run from the repository root:

```sh
python examples/review_calibration/demo.py --out /tmp/new-review-demo
```

This free, deterministic demonstration actually executes a tiny adapter and freezes
its input, output and events before making a rubric. It creates trace-bound review,
atomic grounding and format criteria, per-criterion labels, judge results, a
recomputable evidence bundle, and a drift comparison with a deliberately broken
judge. No provider is called. The names, human annotations and judges are scripted
fixture data, not real human review, production evidence or model performance.

The broken grounding judge misses failures even though the format check is right.
Inspect `broken-calibration.json`: each missed failure retains its trace ID, trace
hash, human rationale and judge reason. Nothing is hidden behind an aggregate score.

Every calibration group in this tiny synthetic fixture is declared for exercising
the workflow, not empirically established as independent or representative. The
illustrative policy explicitly uses permissive 0.3 lower-bound thresholds and eight
groups per class. Do not copy these thresholds into a production acceptance plan.
The report's Hoeffding bounds, policy and assumptions remain visible, including
nonzero uncertainty for perfect agreement. Curated failure sampling does not
estimate deployment precision or production error frequency.

For real work, review real captured traces, define defensible independent groups,
freeze the rubric using tuning traces only, then collect human criterion labels on
held-out calibration groups. Keep these calibration partitions distinct from the
engine's experiment splits: experiment validation/test traces cannot be imported.
Get `codex-eval-lab evidence fingerprint --suite ...` before collecting judge outputs
and put that value in `judge_config.evaluator_fingerprint`. Changed grader source,
rubric, judge config, labels or output data invalidates existing evidence. Local
hashes and imported human attestations do not prove identity or prevent a
cooperating operator from fabricating a new set of artifacts.

The minimal rubric API requires an observed failing tuning anchor and passing
anchor per criterion. Known invariant checks without observed failures can remain
outside the reviewed rubric until an explicit negative fixture is reviewed; this
version does not auto-invent criteria or pretend synthetic suggestions are labels.
