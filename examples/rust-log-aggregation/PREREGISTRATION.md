# Rust request-log aggregation experiment, frozen before proposals

## Authorization and provenance
User requested using Codex Eval Lab to actually hillclimb a Rust task and identify utility/problems. Operator authorization covers this bounded local synthetic experiment and final evaluation. The assistant designed/reviewed the technical measurement; no claim the user manually labeled or inspected these synthetic cases. No model judge, credentials, authenticated Codex CLI, or paid API calls are used. Native model authors proposals after development feedback; the published engine imports structured proposals, snapshots, measures, gates and reports them. This is not a prerecorded scripted winner.

Engine: public GitHub commit 841a8ac4396bedd992b956338e42efbd9d4954c8, downloaded by exact commit into engine/. Exact file hashes and compiler/hardware identity are in artifacts/environment.json. Published checkout is untouched.

## Workload
Parse UTF-8 request logs, each row endpoint TAB status TAB bytes. LF separates rows, single terminal CR is stripped; trailing LF adds no empty row. Exactly three fields; endpoint starts '/' and has no Unicode Cc control characters. Numeric fields contain only nonempty ASCII decimal digits; leading zeros allowed. Status 100..599; bytes <=u64::MAX. Invalid rows are skipped and counted. Return endpoint-sorted (count,error_count,total_bytes), errors status>=400, sum uses u128. Empty input has zero rows. Output formatting and input read are outside kernel timing.

Baseline is a newly constructed idiomatic split/Vec/owned String/BTreeMap implementation, not code from production. No deliberately quadratic baseline. Synthetic data is not representative of actual production traffic.

## Measurement and invariants
Only app/aggregate.rs can be changed. Protected reference.rs is the unchanged original baseline; driver.rs, runner.py, build configuration and independent Python oracle remain fixed. Complete output including invalid count must match the Python oracle; reference output must also match. Before freeze, 3 test methods include 259 calls covering hand-derived boundary cases, 80 random properties, shuffled/doubled variants and invalid rows. Unicode separators, u64 overflow, 5000 leading zeros, signs, Unicode digits and CRLF included.

rustc1.98.1, edition2024, opt-level3, codegen-units1, debuginfo0, explicit x86_64-unknown-linux-gnu. Default target CPU; no native tuning. Compile cache key includes all three Rust source hashes, complete compiler identity, target and flags. Binary hash verified before use. Compilation times recorded separately. No Cargo dependencies.

CPU affinity pins wrapper/child to one available virtual CPU; no exclusive hardware, governor or thermal control. Same binary contains candidate and reference. Black-box input and complete result every invocation. Two untimed warmups per implementation. Each trial has four counterbalanced ABBA/BAAB blocks, with initial order determined by trial seed; each block has two samples per implementation. Each sample processes enough full inputs to cover approximately131072 rows, bounded1..256 iterations. All8+8 raw ns/sample observations retained. No outlier deletion or best-of-retry.

Primary metric = mean over four blocks of ln(mean(candidate ns in block)/mean(reference ns in block)). Engine improvement = baseline primary minus candidate primary, a ratio-of-ratios. Acceptance lower confidence bound must exceed ln(1.05), meaning >1.05× normalized speedup (4.76% time reduction), and correctness regression tolerance zero. Raw unnormalized ns are reported separately. Timing normalization reduces temporal drift; bootstrap is not a model of all hardware noise.

Kernel includes parse, allocation, aggregation, sort/output struct construction and result destruction for each iteration. It excludes stdin reading and stdout serialization. external_process_ns includes Rust process startup, stdin transfer, warmup, candidate+reference blocks and output. Engine latency_s is adapter subprocess latency (Python/cache/binary/read/write), excludes lab copying and grading, and may include cold compile unless prebuilt. Neither is production end-to-end request latency.

## Cases, grouping, noise and holdout
Six equal synthetic profiles: low cardinality, high cardinality, zipf-like skew, Unicode, malformed, mixed. Ten independent RNG-seeded realizations/profile. Four train, three validation, three final groups/profile; 512/8192-row related variants stay in one group. Total60 groups120 cases; train24groups48cases; validation18groups36cases; final18groups36cases. Three outer repetitions; engine groups bootstrap and averages repetitions within cases. Shared generator families mean independence is conditional on this generator, not diverse production populations.

5000 bootstrap samples,95% confidence with engine within-comparison adjustment for primary+correctness. Adaptive validation is exploratory; final groups remain uninspected until seal. Cooperative same-OS discipline, no hostile read isolation. Only development case rows/feedback given to proposal author; final outputs not inspected to tune. Final opened once after seal and never used for another proposal.

Unchanged controls before and after search, plus a deliberately injected plausible wrong-fast shortcut, are controls, not optimizer-discovered changes. Max4 adaptive improving proposals; stop after3 successive rejects/no credible next hypothesis. Bounds2400 eval trials,4-hour experiment window,$0 external evaluation charges; no paid optimizer process. Native model session usage is external to engine budget and not measured as dollars. Manual imports will be logged separately.

## Pre-freeze technical review
Independent reviewer caught Unicode splitlines output corruption and arbitrary-digit Python integer-limit mismatch. Both fixed before freeze; regression fixtures added. Reviewer also caught blocked timing risk in stock runner; immutable contemporaneous reference normalization is built into this suite before freeze. This is custom benchmark engineering, not out-of-box lab timing functionality. Stock engine itself is unchanged.
