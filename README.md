# Codex Eval Lab

**Turn “make this better” into a reproducible, inspectable improvement loop.**

Four reusable Codex skills plus a provider-neutral execution engine for building
application evaluations, auditing the measurement, proposing improvements, and
confirming a selected change on untouched test cases.

**0.1.0 alpha · Python 3.11+ · no third-party core runtime dependencies · MIT**

This is working experimental infrastructure, not a hosted service, model-training
feature, or a claim that an agent can improve every task. The included automatic
Codex adapter is contract-tested with a simulated CLI; authenticated live Codex
and Docker execution still require operator validation. See [validation](docs/VALIDATION.md).

## What you get

| Component | Purpose |
|---|---|
| `$build-eval` | Turn an application goal into reviewed cases, graders, a reproducible runner and an approved baseline. |
| `$audit-eval` | Check representativeness, leakage, outcome validity, noise, grader calibration and operational safety. |
| `$hillclimb` | Improve one objective under explicit scope, quality constraints, iteration limits and budgets. |
| `$report-eval` | Explain measured changes, uncertainty, failures, tradeoffs and final-test results without claiming unsupported wins. |
| `eval-lab` | Execute frozen experiments, enforce trial reservations and selection gates, resume work, and produce local reports. |

The **application, optimizer and grader are independent**. Keep your existing model
provider, programming language, CLI, tests, benchmark, retrieval system or agent.
Adapt a JSON stdin/stdout boundary rather than migrate to a new agent framework.
Images, PDFs, repository fixtures, screenshots and other artifacts can travel as
explicit case assets; grading remains application-specific.

## Install

From a downloaded source release or a checkout:

```sh
python -m pip install -e .
python scripts/install_skills.py --scope user
```

Or install skills only in an existing application repository:

```sh
python scripts/install_skills.py --repo /absolute/path/to/your-app
```

The installer copies self-contained skills to `.agents/skills`, refuses conflicting
existing skills, and does not change Codex permissions or authentication. The installer also records the current Python interpreter in each installed skill,
so it can use `python -m codex_eval_lab` even when the GUI does not inherit your PATH.
Install the engine with that same interpreter and keep its environment available.
Refresh/restart Codex if newly installed skills do not appear. Use its skill picker
or `$build-eval` / `$hillclimb` in CLI/IDE environments that support explicit `$` invocation.

## First: a completely offline demonstration

```sh
python scripts/demo.py --out ../eval-lab-offline-demo
```

Open `../eval-lab-offline-demo/report.html`. The demo exercises the actual controller,
case runner, grader, budget ledger, proposal checks, rejection logic and final test.
It intentionally uses a **scripted proposal fixture, not a model**: one useful
case-normalization change followed by harmful proposals. No API key, Codex install,
network access or money is required. Its synthetic scores are not model benchmarks.

## Then: use actual Codex

Install and authenticate the Codex CLI on your machine using the
[official instructions](https://developers.openai.com/codex/cli). No credentials are
included in this project. Prepare a separate suite that replaces the scripted
optimizer with the real Codex adapter:

```sh
python scripts/prepare_codex_demo.py --out ../eval-lab-codex-suite
eval-lab doctor
eval-lab audit ../eval-lab-codex-suite
```

Review the cases, grader, editable scope, source files and budget. Only after approval:

```sh
eval-lab start ../eval-lab-codex-suite \
  --app ../eval-lab-codex-suite/app --state ../eval-lab-codex-state \
  --approve-cases --approve-grader --approve-execution \
  --note "Reviewed synthetic cases, grader, source scope and execution budget."
eval-lab loop ../eval-lab-codex-state --approve-optimizer
eval-lab report ../eval-lab-codex-state --out ../eval-lab-codex-state/report.html
```

Codex usage consumes your account's plan allowance or API billing as applicable.
**Optimizer usage is separate from the evaluation-dollar budget.** The adapter
records CLI usage and limits calls/time; it does not invent a dollar conversion.

Once selection is finished and you approve opening the held-out test:

```sh
eval-lab finalize ../eval-lab-codex-state --approve-final
eval-lab report ../eval-lab-codex-state --out ../eval-lab-codex-state/report.html
eval-lab export-best ../eval-lab-codex-state --out ../eval-lab-reviewed-winner
```

The final test seals the selected source hash before it runs. The experiment cannot
then keep optimizing against that test. Export creates a **new directory**; it never
overwrites your working tree, merges a PR or deploys an application.

## Use the skills on your own application

Ask Codex:

```text
$build-eval Build an evaluation for our document extraction flow. Reuse our
existing provider, SDK and tests. Propose representative cases and the grading
method for my approval. Track accuracy, missing fields, latency and request cost.
```

Then:

```text
$hillclimb Improve extraction accuracy without worsening the approved latency
or cost constraints. Change only the extraction prompt and parser. Keep the
grader fixed, use the approved limits, and obtain approval before the final test.
```

The skills handle the interactive research and design work. The engine handles
mechanical execution. Human approval remains necessary: command flags record
approval; they do not give an agent permission to approve its own paid experiments.

For an existing runner, implement a thin application/grader adapter or have the skill
wrap it. The required response shapes are small:

```json
{"output": {"your": "result"}, "usage": {"cost_usd": 0}}
```

```json
{"metrics": {"accuracy": 1}, "usage": {"cost_usd": 0}}
```

These zeros are valid only for genuinely free work. Paid adapters must account for
actual usage, including judge calls, retries and uncertain failures. The
[protocol reference](docs/PROTOCOL.md) specifies cases, assets, outputs, metrics,
model identity, traces, subprocess environments and configuration.

## How the loop works

```text
Reviewed cases + grader + scope + limits
                     │
            freeze experiment
                     │
      baseline development + validation
                     │
       fresh Codex proposal session
       (source + development evidence only)
                     │
           validate scoped edits
                     │
      isolated candidate / repeated trials
                     │
    paired validation gates + regression guards
               ┌─────┴─────┐
              keep       reject
               └─────┬─────┘
             repeat or stop
                     │
        seal selected candidate hash
                     │
      one final held-out comparison
                     │
        report + export for review
```

Acceptance requires a useful improvement against the incumbent **and** the original
baseline, with guardrails intact. Statistical comparison uses paired group-cluster
bootstrap intervals after averaging repetitions within cases. It refuses incomplete
or mismatched trial matrices. This is not a confidence sequence or a guarantee against
adaptive overfitting; see [statistics](docs/STATISTICS.md).

A proposal is a causal hypothesis and scoped UTF-8 file replacements, not permission
for the model to rewrite the evaluator. The automatic adapter uses a fresh read-only
Codex session and structured output. The controller applies edits after validation.
No model weights are trained by this project.

## Operational guarantees and boundaries

**Implemented:** explicit source/fixture snapshots; evaluator and runtime-file
fingerprints; scope checks for automatic and manually registered candidates;
reserved spending before each trial; durable SQLite results; no silent retry of
uncertain work; command time/output limits; grouped splits; complete-pair gates;
final-test sealing; development-only feedback; escaped offline reports.

**Not guaranteed:** improvement on arbitrary goals, correctly designed human labels,
provider-side billing caps, exact backend determinism, hostile-code security from a
local process, secrecy of files readable by the optimizer's OS user, or deployment
readiness. Dollar bounds depend on truthful, bounded adapters. New error candidates
are invalid, not quietly removed from the denominator.

Local mode is for trusted/cooperative code. Docker mode restricts application execution
and disables its network; it does **not** isolate the optimizer. For truly private
holdouts, export the application and development evidence with `export-workspace`,
run the optimizer in another trust domain, and return only a proposal using
`import-proposal`. The repository supplies that exchange protocol, not a remotely
managed execution service. Read [security](docs/SECURITY.md).

## Examples and documentation

- [Routing](examples/routing): executable zero-dollar integration fixture.
- [Software benchmark](examples/benchmark): order-preserving deduplication,
  runtime minimization and correctness guardrails. Self-reported kernel timing is
  suitable for cooperative code; use an external timing harness against hostile code.
  Run `python scripts/benchmark_demo.py --out ../eval-lab-benchmark-demo` for a
  zero-dollar study with a hand-authored algorithm change.
- [Optional model grader](examples/judges): structured OpenAI rubric adapter with
  explicit model/pricing inputs, plus a no-network human/judge calibration tool.
  The adapter has fake-client tests, not live-provider validation.
- [Operating guide](docs/OPERATING_GUIDE.md): eval design, judge calibration,
  representation, variance, approval and recovery; recipes across application types.
- [Protocol](docs/PROTOCOL.md), [statistics](docs/STATISTICS.md),
  [security](docs/SECURITY.md), [compatibility](docs/COMPATIBILITY.md),
  [parity and roadmap](docs/CAPABILITIES.md), [validation](docs/VALIDATION.md).

Inspect `eval-lab --help` for the full command surface. All commands return JSON;
errors use stderr and nonzero exit status. Experiments live outside the application
and evaluation-suite trees and should not be committed to source control.

## Tests and publishing

```sh
python -m unittest discover -v
python scripts/sync_skill_references.py --check
```

A supplied source release contains `RELEASE_MANIFEST.json`. To publish that reviewed
release to a **new private repository** using your own local GitHub CLI authentication:

```sh
python scripts/publish_github.py --repo YOUR-LOGIN/codex-eval-lab --dry-run
python scripts/publish_github.py --repo YOUR-LOGIN/codex-eval-lab
```

The publisher checks every manifest hash, stages only those files into a new temporary
Git repository, verifies the authenticated owner and refuses existing repositories.
It does not push your unrelated local history or use credentials supplied in chat.
From an edited checkout, first create a new reviewed archive with
`python scripts/package_release.py --out ../release`, then extract that archive.

## Sources and provenance

Original implementation inspired by Anthropic's
[Automating eval design and hillclimbing](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)
(September 28, 2026). Codex integration follows the official
[skills](https://developers.openai.com/codex/skills) and
[non-interactive execution](https://developers.openai.com/codex/noninteractive)
documentation inspected September 30, 2026. No Anthropic source files are vendored.
This is an independent project, not an official OpenAI or Anthropic product.
