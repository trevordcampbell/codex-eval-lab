# Challenge the grader before searching

A grader can pass every declared control and still accept plausible wrong answers.
An exact matcher can also reject valid alternate representations. More agreement
between one generator, its reference and its grader does not resolve these problems:
they can share an assumption. Preserve independently sourced specifications and
fixture derivations, then challenge the instrument separately from the application.

## Opt-in generated exact-JSON controls

For a **new** oracle suite whose sole deterministic criterion judges the entire
JSON output, add this optional field to its oracle contract:

```json
"generated_controls": {
  "kind": "exact_json",
  "criterion": "correct",
  "numeric_equality": "mathematical",
  "max_per_anchor": 32
}
```

`criterion` must name the single declared deterministic criterion. Other explicitly
trusted measurement metrics may remain present. This contract is deliberately
narrow: every field/value and array position is required, unexpected object fields
are wrong, object-key order is irrelevant, and equivalent finite numeric values
such as `1` and `1.0` are accepted. JSON booleans are distinct from numbers, so
`true` is not `1` and `false` is not `0`. Numeric equality uses the parser's finite
Python integer/float values, with no approximate tolerance. Do not use this mode
for arbitrary semantic answers, tolerances, unordered arrays, optional fields,
partial-credit components, or multiple interacting correctness criteria. Use
explicit source-derived controls and an appropriate validated grader instead.

The runner creates deterministic development-anchor probes in these families:

- Valid alternatives: reorder object keys; change an exactly representable integer
  to an equal float or an integral float to an equal integer
- Type mismatches, including booleans substituted for numbers
- Changed scalar values; missing and extra object fields
- Missing and extra array elements; swaps of unequal neighboring array elements

The grader must pass the valid alternatives and reject the negative controls.
An order-preserving oracle-only wire encoding ensures key-order probes actually
reach the subprocess; the representation digest is bound into each generated
request descriptor. A control erased by transport is not credited as coverage.
Array order is never treated as a positive invariance.

The generator uses each declared development anchor, never private evaluation
outputs. It does not remove the existing source-derived anchors, separate reference,
hand-authored known-wrong controls or all-case consistency checks. Those remain
required. Existing contracts without the opt-in retain their original call set.
Opting in changes evaluator semantics and budget: create a new state and baseline,
retain prior failed attempts, and preserve the original runtime for frozen runs.

## Bounded coverage and audit receipts

`max_per_anchor` is an integer from 1 to 64. Generation round-robins across available
families before filling more examples within one family. Probes identical to the
canonical positive or an already declared negative are not counted again. Exact
wire duplicates across generated probes are omitted. Alternate valid encodings
are intentionally distinct positive probes; they are not new independent labels.

The opt-in supports anchor outputs of at most 128 JSON nodes, depth 16 and 65,536
UTF-8 encoded bytes. It rejects unsupported or nonfinite outputs rather than
pretending they received coverage. Mutation outputs must be distinct from the
correct value under the declared equality and from other declared mutations.

The audit and validated gate expose `control_coverage`: generated positive/negative
counts, per-family counts and declared group counts, available unique probes,
applicable-but-unselected families, families with no applicable unique probe,
omitted-by-cap counts and capped-anchor counts. A small cap may select only valid
alternatives; check the coverage rather than interpreting "enabled" as adequate.
Group counts describe declared groups and do not prove independence. A structural
family may have no unique probe after deduplication, even if another family already
covers an overlapping corruption. The report does not invent support for it.

Generated calls count toward the existing combined 1,000-call preflight cap and the
plan's trial/dollar projection. Every actual call must be reserved first. Failures
retain raw responses, streams, elapsed time and budget charges. Receipt validation
reconstructs the exact deterministic request set and checks response/metric
contracts without replaying executions. Public summaries contain only aggregate
development coverage; raw oracle receipts still contain private all-case checks
and must never enter proposer context.

## What this catches, and what remains unproved

Offline regressions include graders that pass their old positive, trivial negative
and all-case checks but accept a boolean for a number, ignore required fields,
ignore extra fields or disregard array order. Separate regressions reject graders
that incorrectly fail equivalent numeric spellings and object-key orders. A
fixture-specific predicate supplies the passing grader independently of the
mutation generator. These demonstrate the intended blind spots and mechanics on
synthetic data; they are not measured live-model improvement.

Generated labels derive from an **asserted exact-JSON contract**. They do not prove
that contract matches the real task, that the original anchor is correct, or that
the reference is independently authored. Family/count increases are not calibration
sample-size gains. Do not compute a production error rate, confidence interval or
expert-calibration claim from these probes.

Application-level properties remain separate work. For example, permuting input
records may preserve an aggregation result, adding a disconnected graph component
may preserve an existing shortest path, or composing parser encode/decode may
preserve a value. Execute such properties against actual application outputs,
including known-wrong applications; checking only the reference can miss application
bugs. Do not assume a transformation is valid without its task specification.

## A practical automated audit loop

1. Inspect the real outcome contract and enumerate plausible wrong outputs and
   legitimate alternate outputs before seeing optimization results
2. Derive boundary anchors from explicit source clauses or established fixtures;
   record model authorship and shared assumptions honestly
3. For eligible exact-JSON tasks, enable generated controls and inspect every
   applicable-but-unselected or unsupported family. Add task-specific adversarial
   controls for blind spots the generic generator cannot establish
4. Verify that deliberately broken graders fail and a separately implemented valid
   grader passes. Verify each application metamorphic property on actual outputs,
   and ensure a relevant known-wrong application is rejected
5. For semantic criteria, retain independent human/expert calibration, both classes,
   missed-failure and false-alarm support, group-aware uncertainty and an untouched
   confirmation set. Same-model consistency is only a diagnostic
6. Freeze the specification, cases, grader, control policy and budget before search.
   If measurement fails, stop and start a new experiment after fixing it; do not
   soften a frozen grader or tune on its final holdout

A useful result separates: specification/label trust, instrument discrimination,
application correctness, search selection and fresh final confirmation. Success at
one layer does not establish the others.
