# Codex Eval Lab

**Tell Codex what to improve. Let it build the measurement and run the experiment.**

Codex Eval Lab turns an improvement goal into a reviewable change with an evidence
trail. Codex inspects the application, designs the contract and cases, validates the
grading, proposes changes, and explains the result. A local runner freezes the
measurement, enforces scope and budgets, selects candidates, and seals the winner
before the final comparison.

The default is end-to-end automation within your instructions. You should not have
to construct evaluation forms, label answers a program can check, or approve every
iteration. Codex asks when a domain decision or required permission is genuinely
missing. A visual evidence viewer is available when useful; it is optional.

0.4.0 · Python 3.11+ · standard-library core · [MIT](LICENSE)

## Start with a goal

Install the runner and four Codex skills:

```sh
git clone https://github.com/trevordcampbell/codex-eval-lab.git
cd codex-eval-lab
python -m pip install -e .
python scripts/install_skills.py --scope user
```

Open your application in Codex and give it a bounded job:

```text
$build-eval Make this parser faster while preserving exact output. Inspect the
project and build an evaluation yourself. Keep the current language and toolchain.
You may edit parser.rs and run local tests, up to four proposal sessions, and a final
held-out comparison within 20 minutes. No production data, paid external APIs or
deployment. Ask me only for a material domain decision or missing permission.
```

Codex works through the whole job:

1. Inspect the actual entry point, tests, constraints and improvement headroom
2. Build a precise contract, grouped cases, adapters and independent outcome checks
3. Challenge those checks with boundary cases, known-wrong outputs and a separate
   reference; identify any remaining judgment or evidence gap
4. Freeze a source-bound plan and baseline, then generate and measure scoped
   proposals within the authorized limits
5. Select, seal, run the preauthorized final test, and report the result, uncertainty,
   regressions and costs, including an honest unsuccessful result

Existing valid evaluation and calibration work is reused. The skills wrap the
project's current runner and provider through a small JSON-in/JSON-out adapter;
you don't need to rewrite the application in Python. `$audit-eval`, `$hillclimb`
and `$report-eval` are also available for a specific stage.

## Make the evidence as automatic as the task allows

For exact outcomes, executable checks do the routine judging. Codex can derive
boundary examples from a specification, implement a separate reference, and
inject incorrect outputs to test whether the grader catches them.

The new native oracle path supports JSON-input/output tasks. It executes the
reference and actual grader on positive and negative controls, then checks every
frozen case for reference/expected-label/grader consistency. Each call is budgeted
and retained. Artifact-dependent tasks need a separately validated adapter workflow;
the generic oracle preflight does not yet transport generated files.

Keep the claim precise: executable checks passed. Model-authored cases and
specifications remain model-authored. Two implementations can share a mistaken
assumption; two agreeing models do not establish ground truth. Finite checks cannot
prove universal correctness, source independence or production representativeness.
Those assumptions stay visible with the result.

When the outcome genuinely requires judgment, the existing expert-calibration path
remains strict. Reuse validated domain anchors within their scope, inspect actual
traces and disagreements, and involve an expert where needed. Keep model suggestions
separate from human labels. Each semantic criterion needs independent calibration
and adequate support; a composite score cannot hide an unverified judge. Model-only
heuristic scores can guide honestly labeled exploration, but cannot certify gains
through the end-to-end readiness gate.

![Codex turns a task into source-derived checks, a separate grader and a fixed baseline.](docs/assets/eval-design.svg)

The [evidence guide](docs/EVIDENCE.md) covers semantic calibration. The
[automation guide](docs/AUTOMATION.md) describes executable controls, provenance,
all-case consistency and remaining assumptions.

## The runner enforces the experiment

The model proposes structured edits; the controller applies and measures them.
Only approved files can change. Cases, grader, objective, guardrails and measurement
design remain frozen. An evaluator fix starts a new experiment and baseline.

Development evidence informs proposals. Validation selects candidates. A candidate
must pass the gates against both the incumbent and original baseline, preventing
small tolerated regressions from accumulating. Related groups, rather than
repetitions of the same case, are the uncertainty resampling unit.

The final test is separate. The runner seals exact source identities before opening
it, using permission already included in the plan. A failed final comparison is
retained and consumes that holdout; it is not permission to tune on its failures.
For timing-sensitive experiments, persisted paired AB/BA cohorts remeasure
references beside candidates. They reduce slow drift, not every source of noise.

![Codex proposes scoped changes; the runner selects, seals and performs the final comparison within approved limits.](docs/assets/hillclimb-loop.svg)

Reservations precede execution. Oracle checks, application and grader calls,
failures and unknown outcomes stay in the ledger. Automation protects trial and
evaluation-dollar capacity for the final comparison. Optimizer usage is separate;
unknown charges stay unknown. These are scheduling limits based on honest cost
bounds, not provider-side hard caps.

Native commands are available when you want to inspect the plan directly:

```sh
eval-lab automation-plan <suite> --app <app> --out <new-plan.json>
eval-lab automate <suite> --app <app> --state <new-state> \
  --plan <new-plan.json> --approve-plan \
  --authorization-note "<the actual bounded permission>"
eval-lab resume-automation <state>
```

The plan binds exact bytes, execution settings, scope, limits and final-test intent.
A flag records permission already granted; it cannot grant authority for spending,
private-data transmission, security changes or other consequential actions.
Interrupted or indeterminate attempts are never silently retried. Reports preserve
raw local evidence while showing bounded trace previews by default.

## What we have actually run

### A model-guided Rust improvement

The [Rust request-log aggregation study](examples/rust-log-aggregation/README.md)
contains four live model-authored proposals, an intentionally incorrect negative
control, unchanged controls, rejection decisions and a sealed synthetic final test.
The selected implementation achieved a **1.631× normalized paired kernel speedup**
with **100% exact output correctness** on 36 final cases in 18 seeded groups.
The [full result](examples/rust-log-aggregation/REPORT.md) explains the interval,
workload, measured quantity, observed failures and limits.

This is historical evidence from the 0.2 engine with a custom protected Rust timing
driver. It did not use the new automation CLI or authenticated Codex CLI proposals.
Its public final cases are now reproduction data, not a fresh holdout. The source-only
replay helper has been syntax/help checked; this revision has not rerun the complete
historical benchmark. Native model-session cost was unmeasured.

### A repeatable automation check

```sh
python scripts/automation_demo.py --out ../eval-lab-automation-demo
```

This executes real local oracle controls, all-case consistency checks, baseline,
three scripted proposals, selection, a sealed final comparison and a self-contained
report. No API key, network or paid model call is needed. It tests the machinery;
the proposals are scripted and cases synthetic, so it is not a live model benchmark.
The earlier [routing](examples/routing) and [timing](examples/benchmark) fixtures
remain available.

## Optional plugin and evidence UI

The local plugin packages the same skills with read-only MCP evidence tools and an
optional MCP Apps UI. Native Codex uses its own authorized environment tools to
run the CLI. The hosted/read-only plugin does not execute experiments, run arbitrary
code or approve anything on your behalf.

```sh
python -m pip install -e ".[plugin]"
python scripts/build_plugin.py --out ../eval-lab-plugin
python scripts/validate_plugin.py ../eval-lab-plugin/catalog/plugins/codex-eval-lab
```

See the [plugin guide](docs/PLUGIN.md) for installation, host support and artifact
scoping. UI availability is distinct from evidence readiness. Local execution and
fresh proposal contexts are cooperative boundaries, not hostile-code or private-file
isolation. Use a separately provisioned trust domain for genuinely hidden holdouts.

## References and limits

- [Automation](docs/AUTOMATION.md): workflow, evidence categories, budgets and migration
- [Operating guide](docs/OPERATING_GUIDE.md) and [protocol](docs/PROTOCOL.md): commands,
  adapters and configuration
- [Statistics](docs/STATISTICS.md) and [security](docs/SECURITY.md): uncertainty,
  adaptive selection, spending and isolation
- [Evidence](docs/EVIDENCE.md): expert labels, atomic judge calibration and drift
- [Validation record](docs/VALIDATION.md): verified and unverified integrations
- [Capabilities](docs/CAPABILITIES.md), [dependencies](docs/DEPENDENCIES.md),
  [contributing](CONTRIBUTING.md) and [changelog](CHANGELOG.md)

An upgrade does not rewrite a frozen experiment. Preserve its original runtime;
new evaluator/runtime semantics need a new state and baseline. No measured outcome
here guarantees improvement on unsampled tasks or production traffic.

This independent project was inspired by Lance Martin's
[Automating eval design and hillclimbing with Claude](https://claude.dev/blog/automating-eval-design-and-hillclimbing/).
It is not an official OpenAI or Anthropic product.
