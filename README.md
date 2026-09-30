# Codex Eval Lab

**Give “make this better” a goal, a test, and a reason to believe the result.**

A prompt gets longer. A parser gets another special case. An agent gains a new tool.
Each change sounds useful. The harder question is whether it actually helps the
application, and whether that improvement survives examples it has never seen.

Codex Eval Lab gives that work a repeatable path: build an evaluation, inspect what
fails, try a scoped change, and check the selected version on a final held-out set.
Four Codex skills guide the decisions; a small execution engine records the trials
and enforces the experiment's mechanical rules.

Keep your application, model provider, SDK, and language. The lab wraps their existing
entry points rather than asking you to adopt a new agent framework.

**0.1.0 alpha · Python 3.11+ · no third-party core runtime dependencies · [MIT](LICENSE)**

This is experimental infrastructure. The offline workflow is tested; authenticated
live Codex, live provider judges, and actual Docker execution still need operator
validation. It does not train model weights or promise an improvement.

## Start here

From a source checkout or extracted release, install the engine and skills:

```sh
git clone https://github.com/trevordcampbell/codex-eval-lab.git
cd codex-eval-lab
python -m pip install -e .
python scripts/install_skills.py --scope user
```

Then open your application in Codex and ask:

```text
$build-eval Build an evaluation for our support-ticket router. Reuse our existing
runner and model provider. Help me choose representative cases, review the labels,
and validate the grader before running a baseline. Track routing accuracy, latency,
and cost. Ask me to approve the cases, grader, and execution budget separately.
```

Prefer to see the whole loop first? Run the free, offline example:

```sh
python scripts/demo.py --out ../eval-lab-offline-demo
```

Open `../eval-lab-offline-demo/report.html`. No API key, Codex installation, network
access, or paid calls are needed. Use a new output directory outside the repository.
The example uses **scripted proposals, not an AI optimizer**.

To install skills only for a particular application, use
`python scripts/install_skills.py --repo /absolute/path/to/your-app` instead of
`--scope user`. The installer copies self-contained skills into `.agents/skills`,
refuses conflicts, and leaves permissions and authentication unchanged. It records
the Python interpreter used for installation so installed skills can invoke the
engine without relying on the GUI's PATH; install the engine with that interpreter
and keep its environment available. Refresh/restart Codex if needed, then use its
skill picker or explicit `$` invocation where supported.

## A worked example: improve a ticket router

The included [routing fixture](examples/routing) is deliberately small. It sends
messages containing `invoice` to billing, `crash` to technical support, and
`tracking` to shipping. Everything else goes to `other`.

That simplicity makes the experiment easy to inspect. The point is to understand
what was measured, why a change was retained, and what the result does **not** prove.

### 1. Give “better” a concrete meaning

For this fixture, the objective is routing accuracy. The editable surface is one
file, `app.py`. The grader is an exact comparison with the approved category, and
it stays outside that editable surface.

The [configuration](examples/routing/eval.toml) also specifies the minimum useful
improvement, a zero-cost guardrail, two repetitions per case, and a maximum of three
proposal calls. Those choices become part of the frozen experiment.

For a real router, deciding what belongs in the evaluation is the important work.
Which queues matter? What should happen when a message mentions both an invoice and
a delivery? Is `other` a correct outcome or an expensive mistake? The build skill
helps you turn those decisions into reviewed inputs, labels, and grading rules.
It cannot decide your product's meaning of success for you.

### 2. Build the measurement before changing the application

The fixture contains 80 synthetic cases split into development, validation, and
final-test sets. Its application and grader are separate processes: the application
gets the input; the grader gets that trial's actual output and expected category.

On your own project, `$build-eval` produces the runnable suite and baseline evidence.
You review actual cases, check a pilot of the grader, and approve execution. For
outputs with many valid answers, the grader may need a calibrated rubric or human
judgment rather than an exact match.

Use the second skill to challenge the measurement:

```text
$audit-eval Audit this suite before we optimize. Check related-case leakage,
label ambiguity, grader disagreements, infrastructure failures, and run-to-run
noise. Tell me whether it can detect an improvement worth shipping.
```

The skill performs a guided review. The `eval-lab audit` command checks the suite's
structure and discloses risks, but cannot establish label truth, production
representativeness, or judge quality by itself.

### 3. Read the failures and propose an explanation

The toy router searches for lowercase words without normalizing its input.
`please check my invoice` reaches billing; `PLEASE CHECK MY INVOICE` does not.
That gives us a testable hypothesis: normalize case before applying the same rules.

The scripted fixture proposes adding this line at the start of `route`:

```python
text = text.casefold()
```

The controller validates the proposed file replacement, snapshots the candidate,
and runs it through the fixed evaluator. Two subsequent proposals intentionally
break routing. They are rejected, and the search stops at its patience limit.

This is useful behavior even in a tiny example: a proposal is a candidate, not a
command to accept a change. A failed experiment leaves evidence and does not replace
the selected version.

For your application, ask Codex to search within a similarly concrete boundary:

```text
$hillclimb Improve routing accuracy using this approved evaluation. Change only
the routing prompt and parser. Keep the provider and grader fixed. Propose the
minimum useful gain, latency and cost guardrails, and separate evaluation and
optimizer limits for my approval before running. Diagnose development failures
and test one coherent hypothesis at a time. Ask before opening the final test.
```

The automatic Codex adapter starts fresh proposal sessions with source and
**development-only evidence**. It returns structured edits; the controller checks
scope and applies them. A session that has reviewed private test cases must not be
reused as the optimizer.

### 4. Verify the selected change on the final test

The engine uses three distinct roles for data:

- **Development (`train`):** evidence the optimizer can inspect to propose changes
- **Validation:** repeated comparisons used to select candidates
- **Final test:** a separate comparison opened only after the selected source hash is sealed

Acceptance gates compare a candidate with both the incumbent and the original
baseline, including guardrails. The engine requires complete paired trials and uses
group-cluster bootstrap intervals after averaging repetitions within each case.
Validation still participates in adaptive selection, so it is not independent proof
of a win. See the [statistical assumptions and limitations](docs/STATISTICS.md).

The recorded offline run selected the normalization change. Final accuracy on 20
synthetic test cases rose from **0.70 to 1.00**, with 560 application-plus-grader
trials across the full experiment and $0 evaluation cost. Both deliberately harmful
proposals were rejected. See the [recorded results](docs/validation/routing-demo.json)
and [sample report](docs/sample-report.html).

**These numbers demonstrate the machinery, not Codex's intelligence or performance
on real tickets.** The proposals are hand-authored, and the public synthetic data
are not a secret benchmark.

For a real run, close with:

```text
$report-eval Explain the selected change against the original baseline. Include
final-test results and uncertainty, regressions, failed trials, evaluation costs,
and separate optimizer usage. Say clearly if the evidence does not support merging.
```

If the final result disappoints, keep it in the report. Continuing to tune on those
failures would require a new experiment and a fresh final test.

## Run the same workflow with actual Codex

Install and authenticate the Codex CLI using the
[official instructions](https://developers.openai.com/codex/cli). No credentials are
included here. These commands prepare a **new, unapproved** suite using the real
Codex adapter instead of the scripted fixture:

```sh
python scripts/prepare_codex_demo.py --out ../eval-lab-codex-suite
eval-lab doctor
eval-lab audit ../eval-lab-codex-suite
```

Review its cases, grader, editable files, and limits. The following approval flags
record a human's actual approval; an agent must not grant itself permission to spend
money or run code.

After approval, freeze the experiment and run the loop:

```sh
eval-lab start ../eval-lab-codex-suite \
  --app ../eval-lab-codex-suite/app --state ../eval-lab-codex-state \
  --approve-cases --approve-grader --approve-execution \
  --note "Reviewed synthetic cases, grader, source scope and execution budget."
eval-lab loop ../eval-lab-codex-state --approve-optimizer
eval-lab report ../eval-lab-codex-state --out ../eval-lab-codex-state/report.html
```

The loop runs the baseline and candidates. Codex consumes your account's plan
allowance or API billing as applicable. **Optimizer charges are separate from the
evaluation-dollar budget**, even when this toy application's trials are free.
The adapter records CLI usage and limits calls/time; it does not convert unknown
optimizer charges into a claimed dollar cap.

After selection and separate approval to open the final test:

```sh
eval-lab finalize ../eval-lab-codex-state --approve-final
eval-lab report ../eval-lab-codex-state --out ../eval-lab-codex-state/report.html
eval-lab export-best ../eval-lab-codex-state --out ../eval-lab-reviewed-winner
```

Export creates a new directory for review. It never overwrites your working tree,
merges a pull request, or deploys the application. State belongs outside both the
application and suite trees and should not be committed to source control.

## Bring your own application

The application, optimizer, and grader are independent. A thin adapter can wrap an
existing CLI, test suite, retrieval pipeline, agent, or benchmark. The core expects
one JSON request on stdin and one JSON response on stdout; logs go to stderr.

An application response can be as small as:

```json
{"output": {"your": "result"}, "usage": {"cost_usd": 0}}
```

And its independent grader can return:

```json
{"metrics": {"accuracy": 1}, "usage": {"cost_usd": 0}}
```

Zero is valid only for genuinely free work. Paid adapters must account for actual
usage, including judge calls, internal retries, and uncertain failures. Images,
PDFs, repository fixtures, and other files can be declared case assets; grading
their outputs remains application-specific. The [protocol](docs/PROTOCOL.md) covers
the full request shapes, artifacts, metrics, model identity, and configuration.

Other starting points:

- **Optimize runtime while preserving correctness:** the
  [software benchmark](examples/benchmark) demonstrates ordered deduplication with
  a hand-authored algorithm change. Run
  `python scripts/benchmark_demo.py --out ../eval-lab-benchmark-demo` for a free
  study. Its self-reported kernel timing is for cooperative code, not hostile candidates
- **Evaluate open-ended answers:** the [optional model grader](examples/judges)
  supplies a structured OpenAI rubric adapter with explicit model/pricing inputs
  and a no-network human/judge calibration tool. It has fake-client tests, not
  live-provider validation
- **Use an existing optimizer or review every edit:** register candidates manually,
  or exchange development workspaces and structured proposals using the
  [operating guide](docs/OPERATING_GUIDE.md)

## What the lab protects, and what it cannot

The engine snapshots approved source and evaluator files, checks fingerprints,
validates edit scope, reserves trial spending, and keeps durable SQLite records.
Timeouts, malformed results, and indeterminate attempts remain visible; they are
not silently retried or dropped to improve a score. Reports escape model-generated
content and load no external resources.

Those controls have important boundaries:

- **Local mode trusts the code.** It is not a hostile-code sandbox, and a read-only
  optimizer session does not hide files readable by the same OS user. Do not give
  it production credentials or unreviewed code
- **Docker isolates application execution only.** It disables the application's
  network but does not isolate the local optimizer. Truly private holdouts need a
  separate trust domain; `export-workspace` / `import-proposal` provides the exchange
  protocol, not a managed remote evaluation service
- **Spending limits depend on honest adapters.** Reservations cannot reverse provider
  charges or guarantee a provider-side cap. Configure provider limits too, and
  account for optimizer usage separately
- **An evaluation is a model of your goal.** No statistical interval fixes bad labels,
  leakage, missing production cases, or a misleading metric. Fixing the evaluator
  requires a new approved experiment rather than changing the rules mid-search

Read [security](docs/SECURITY.md) before using sensitive data, paid adapters, or
untrusted execution. No universal improvement, deployment readiness, or
Claude-versus-Codex superiority is claimed.

## Reference and development

- [Operating guide](docs/OPERATING_GUIDE.md): design, calibration, approval, recovery, and application recipes
- [Protocol](docs/PROTOCOL.md) and [statistics](docs/STATISTICS.md): execution contracts and selection rules
- [Compatibility](docs/COMPATIBILITY.md), [capabilities and roadmap](docs/CAPABILITIES.md), and [validation record](docs/VALIDATION.md)
- [Contributing](CONTRIBUTING.md) and [changelog](CHANGELOG.md)

The release validation records 184 passing tests, including simulated Codex and
provider contracts. These do not substitute for authenticated live integrations.
To run the checks locally:

```sh
python -m unittest discover -v
python scripts/sync_skill_references.py --check
```

Use `eval-lab --help` for all commands. Commands return JSON; errors use stderr and
a nonzero exit status.

<details>
<summary>Package or publish your own reviewed source release</summary>

A supplied source release includes `RELEASE_MANIFEST.json`. The publisher verifies
all manifest hashes and the authenticated owner, stages only listed files into a
new temporary Git repository, and refuses existing repositories. It creates a
**new private repository** using your local GitHub CLI authentication:

```sh
python scripts/publish_github.py --repo YOUR-LOGIN/codex-eval-lab --dry-run
python scripts/publish_github.py --repo YOUR-LOGIN/codex-eval-lab
```

For an edited checkout, first run
`python scripts/package_release.py --out ../release` and extract the resulting
archive. Review it before publishing. The publisher does not include unrelated
local history or use credentials supplied in chat.

</details>

## Inspiration and provenance

This independent implementation was inspired by Lance Martin's
[Automating eval design and hillclimbing with Claude](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)
(September 28, 2026). The article is a useful companion on choosing measurements
and interpreting an improvement. This repository implements its own skills,
controller, adapters, and experiment lifecycle; no Anthropic source files are
vendored.

Codex integration follows the official [skills](https://developers.openai.com/codex/skills)
and [non-interactive execution](https://developers.openai.com/codex/noninteractive)
documentation. This is not an official OpenAI or Anthropic product.
