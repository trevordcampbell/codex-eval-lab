# Capability map and roadmap

This is a feature/implementation comparison, not a head-to-head model benchmark.
“Beyond the blog” describes an additional mechanism in this project, not proof that
it is absent from every current Claude implementation.

| Capability | Implementation in 0.1.0 | Boundary |
|---|---|---|
| Guided evaluation design | build-eval skill with mandatory case/grader/execution review | Agent and human do domain work; no universal automatic gold labels |
| Realistic case sourcing | Operating procedures prioritize production evidence and user examples | No built-in connectors silently retrieve private logs |
| Multiple grading approaches | Arbitrary JSON grader subprocess; deterministic fixtures; optional structured OpenAI rubric adapter; categorical calibration tool | Rubric, pairwise, visual and domain judges require adapters and calibration |
| Quality/cost/latency objectives | Any finite declared numeric metric; direction, minimum effect, guardrails | No arbitrary multiobjective Pareto search or nonlinear aggregation built in |
| Iterative diagnosis and edits | Fresh Codex or custom-command proposals with development traces | Live Codex not exercised here; bounded-context prompting not automatic trace retrieval |
| Resume and experiment records | Transactional SQLite reservations/results, pending-attempt recovery, active-round resume | Indeterminate attempts invalidate comparisons rather than magically recover unknown outputs |
| Immutable measurement | Snapshot config/cases/harness/assets, source and runtime-file fingerprints | Same-user malicious code can still tamper with the entire process; no OS boundary |
| Train/validation/test separation | Grouped splits; training-only feedback; final test sealed before execution | Group validity and original designer knowledge require human governance |
| Selection uncertainty | Paired group-cluster bootstrap, per-comparison guardrail multiplicity adjustment | No adaptive confidence sequence or power-analysis guarantee |
| Cost accounting | Explicit per-adapter usage, conservative reservations, caps before each trial | No universal provider-side hard cap; optimizer dollars are separate/unknown |
| Code changes | Scoped full-file replacements, new in-scope files, manual candidates | Automatic deletion and binary patches intentionally unsupported |
| Reports | Self-contained escaped HTML, cohort scores, decisions, evidence and accounting | Does not directly render untrusted generated HTML/SVG or provide remote collaboration |
| CI/release tooling | Read-only CI workflow, unit/integration tests, skills installer, hash manifests, publisher | Hosted CI and actual GitHub publication must be verified separately |
| Stronger deployment separation | Development-only workspace export + scoped proposal import | Operator provisions separate machines/accounts/VMs; no managed remote service |

## Deliberate design choices

The model proposes edits as structured data. The controller applies them, rather than
asking the model to both operate and obey the whole evaluation system. This makes
scope validation, rollback-by-snapshot, deterministic trial accounting and final-test
rules independently testable. It does not by itself sandbox malicious code.

The default optimizer gets development evidence only, not validation aggregates.
Validation still influences which candidate is retained; therefore adaptive selection
bias remains a statistical concern. The untouched final test is the confirmatory
measurement, subject to representative data and a genuinely protected test boundary.

Paid application/judge calls are not conflated with Codex's own subscription/API usage.
No unknown price is reported as zero. No external model prices or “latest model” IDs
are hardcoded in the core.

## Prioritized follow-on work

1. Authenticated live Codex regression matrix and a real user-application study with
   unchanged controls, preregistered metric/scope and independent final tests.
2. Separately deployed evaluator service with authenticated proposal exchange,
   read isolation, quotas and pinned workers; trusted provider egress broker.
3. More provider-native and existing-eval-framework adapters, tested against their
   actual APIs; calibrated pairwise and multimodal graders.
4. Large trace retrieval/selection with bounded optimizer context; joint tracing
   for nested tools/subagents and measured sampling policies.
5. Hierarchical build-variance resampling, precision/recall cohort tooling,
   sequential confidence procedures and an explicit multiple-search ledger.
6. Parallel candidate workers with atomic reservations, resource isolation and
   deterministic paired seed allocation; richer human review of safe artifacts.

These are **not represented as already implemented**. The current sequential engine
is intentionally inspectable and testable rather than pretending to be a universal
production evaluation platform.
