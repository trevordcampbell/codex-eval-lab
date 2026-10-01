# A real Rust hillclimb using Codex Eval Lab

> Preserved historical study report. References below to full state, review exports
> and the optional toolchain installer belong to the separate full study bundle,
> not this lightweight source-only example. See README.md here for the included
> files and current replay instructions. This was not a 0.4 automation-CLI run.

Selected source: **round-2**. Executed with the published engine at `841a8ac4396bedd992b956338e42efbd9d4954c8`.

## Result
Final gate **passed**: normalized paired kernel speedup **1.631×**, 97.5% per-metric group-bootstrap interval **1.533–1.733×** (95% family confidence for the two checked metrics). This is the exponentiated change in block-paired log(candidate/reference), a ratio-of-ratios. It is not a production end-to-end latency claim.

Final raw case-averaged median kernel time: **0.7031 ms → 0.3581 ms**. Exact output correctness: **100.0% → 100.0%** across 36 final cases in 18 seeded groups, 3 outer repetitions per implementation. Every final trial remeasured the immutable reference beside the candidate.

All 36 observed final case means improved in raw and normalized timing. Normalized case speedups ranged 1.177–2.463×. These are descriptive case means, not per-case statistical claims.

| Final profile | Normalized speedup vs original |
|---|---|
| high-cardinality | 1.468× |
| low-cardinality | 1.807× |
| malformed | 1.782× |
| mixed | 1.868× |
| unicode | 1.399× |
| zipf-like | 1.525× |
| 512-row batches, across profiles | 1.415× |
| 8192-row batches, across profiles | 1.881× |

Profile estimates are descriptive: only three independent seeded groups per profile; no subgroup confidence claims.

**2,016 completed trials**, no pending trials. **39.5 minutes** from frozen start to final completion, excluding initial design/toolchain setup. External evaluation charges **$0**; native model session cost is unmeasured. The experiment was substantially slower than the Rust kernels: copying, grading, hashing, persistence, model-authoring gaps and coordination are separate from the optimized computation.

## Candidate history

| Variant | Change | Validation decision | Development normalized speedup vs same-trial reference |
|---|---|---|---|
| baseline | Unchanged starting-point implementation | baseline | 0.995× |
| unchanged-before | Original source A/A before search | unchanged diagnostic control | 1.002× |
| round-1 | Initial preflight wrote bytecode into snapshot; no trial ran | preflight blocked; zero trials | not measured |
| round-1-clean | Borrowed HashMap keys, allocation-free splitting, sort unique outputs | accepted | 1.171× |
| negative-sign-shortcut | Injected invalid-sign shortcut | rejected | 1.263× |
| round-2 | Fused byte parsing with checked overflow and Unicode fallback | accepted | 1.594× |
| round-3 | Validate endpoint controls on first insertion | rejected | 1.784× |
| round-4 | Round 3 idea plus exact status-grammar recognition | rejected | 1.751× |
| unchanged-after | Original source A/A after search | unchanged diagnostic control | 1.001× |

Round 3 preserved correctness and had a favorable speed point estimate, but its lower bound was 1.04986×, below the prespecified 1.05× gate. That is insufficient evidence for the minimum effect, not evidence it is slower; no rerun or threshold relaxation was used.

Proposals were authored live by a native model after reading engine-exported development feedback plus controller acceptance/rejection and one qualitative near-threshold validation explanation, then imported through the supported CLI. They were not prerecorded scripted wins. The incorrect sign shortcut was deliberately injected as a negative control. No authenticated Codex CLI or provider/API call was made. Native model session usage is not measured in dollars.

## What was measured

- Newly written, straightforward BTreeMap/owned-string baseline; no production app was supplied
- UTF-8 TSV request-log parsing, per-endpoint counts/errors/u128 byte totals, invalid-row counting and sorted output
- Six equal synthetic profiles: low/high cardinality, skew, Unicode, malformed and mixed; 512/8192-row batches
- 120 cases from 60 independent seeded realizations, two related sizes/group; 24 development, 18 validation and 18 final groups
- Exact independent Python oracle; baseline and accepted candidates also pass 259 hand-derived/property/metamorphic/adversarial executions
- rustc 1.98.1 stable, LLVM 22.1.8, edition 2024, -C opt-level=3 -C codegen-units=1 -C debuginfo=0, explicit x86_64-unknown-linux-gnu target; no external Rust dependencies
- AMD EPYC 9V74 virtualized shared host, one CPU affinity, no exclusive core/governor control
- 3 outer repetitions; 2 warmups per implementation; 4 seeded balanced ABBA/BAAB blocks; 8 candidate and 8 reference samples/trial; approximately 131072 rows/sample, 1..256 full iterations
- Primary mean of 4 per-block log ratios. Required lower bound >ln(1.05), zero correctness regression; 5000 related-group bootstrap samples. 95% family confidence adjusts each of 2 metrics to 97.5%; adaptive candidate selection remains exploratory
- Complete sample values retained; no outlier removal, silent retry, missing trial deletion or final-data tuning
- Only aggregate.rs editable. Reference, driver, adapter and grader frozen before first proposal. Build cache includes every Rust source hash, full compiler identity, target/flags and verifies binary digest

## Usefulness and friction

The engine successfully froze the evaluator, preserved source snapshots, ran complete matrices with durable reservations, kept the correct winning changes, rejected an incorrect plausible shortcut, sealed the selection before a separate final comparison, and exported a reviewable winner. Exact candidate/source/budget evidence is in artifacts/results.json and state/.

Important limitations encountered:

1. Stock runner schedules a whole variant before the next. Close latency claims would be vulnerable to machine drift. This experiment required custom protected per-trial reference pairing before freeze; that is benchmark engineering, not automatic lab behavior
2. Compiled-language integration has no first-class immutable build stage in this shipped engine. We supplied a source/compiler/flags-keyed protected compile cache and separated compile timing from kernel timing
3. Manual imported proposals do not populate the automated optimization decision history. Rejection comparisons are not automatically persisted by compare. We explicitly retained CLI responses, all decisions and hypotheses in artifacts/candidate-history.jsonl
4. Manual proposal imports are not engine optimizer calls; max_optimizer_calls is not a native-session meter. Operator limited this run to the preregistered proposal count
5. Independent review found two bugs in our newly written adapter/oracle before freeze: Unicode separators misparsed by splitlines, and long zero-padded integers exceeding Python int string limits. Regression fixtures caught both. These were adapter bugs, not engine correctness bugs
6. Importing the frozen wrapper during operator preflight accidentally created Python bytecode in its snapshot. Source-integrity checks correctly blocked execution before any trial. The attempt is preserved; identical source was imported with a new label and tested only in disposable copies
7. Stock self-contained HTML embeds every complete development input/output. The interim report was 173 MB before the search finished, so this bundle also provides a compact report and separately retained raw records
8. A 144-trial train pass took 107 seconds while its adapter subprocesses summed to about 42 seconds. The remainder includes grader, copying, integrity and persistence overhead. Source inspection also shows full growing JSONL output rewritten after every trial, a quadratic scaling risk; this run does not isolate each overhead source
9. Structural audit cannot establish oracle truth or representative data. This exact oracle did not need a semantic judge or fabricated human labels; evidence-gate status remains honestly not_configured

Negative-control detail: the sign shortcut clears the speed gate against the original baseline but fails correctness (69.4%). Against the incumbent its speed lower bound also misses threshold; both gates fail. It was never selected.

Proposal-feedback qualification: raw data exports were development-only. The author also received acceptance/rejection decisions and the qualitative statement that round 3 narrowly missed its validation bound. No numeric validation aggregate/CI or validation/final rows were shared. This is adaptive validation information, preserved in artifacts/author-feedback-provenance.json; the final set remained unopened until seal.

## Interpretation limits

- Synthetic seeded groups share generator families, not independent production populations; results describe sampled batches, not real request frequency
- No all-unique corpus, sub-512-row request, disk/network I/O, peak memory/RSS metric or adversarial collision benchmark
- Standard randomized HashMap preserves default collision resistance but its seeds/layout are not controlled by the lab seed; repetitions sample that variation
- Kernel includes parse/allocation/aggregation/sort/result destruction; excludes stdin read/stdout formatting. External process duration includes both benchmark arms. Engine latency_s is Python adapter subprocess time, excluding lab copying/grading. Neither is production end-to-end latency
- Shared-host noise and compiler/build-level variation are not fully captured by bootstrap. Protected contemporaneous reference reduces temporal confounding
- Correctness 1.0 and a degenerate zero regression interval cover observed cases only; unobserved bugs remain possible
- Cooperative same-OS holdout discipline; no hostile-code isolation. Final rows were not shown to the proposal model and were not inspected for tuning
- This demonstrates model-guided external proposals plus real engine mechanics, not authenticated Codex CLI autonomy or model superiority

## Reproduce and inspect

Read PREREGISTRATION.md first. On Linux x86_64 with Rust 1.98.1 installed, run:

    python reproduce.py --rustc /absolute/path/to/rustc --out /a/new/directory --approve-local-benchmark

The optional install_toolchain.py uses official pinned Rust download URLs and verified SHA256 digests with explicit installation approval. The replay script was syntax/help checked; a second complete replay was not run.

Reproduction replays the archived live-authored source proposals and obtains fresh timing samples; it does not reproduce the live model interaction. Results can differ. Original sources/proposals, complete summaries, source/compiler/binary hashes, timing samples and SQLite event history are preserved. The original final data must not be reused as fresh unseen confirmation for further tuning.

The lightweight read-only review export is review-evidence/review-run.json. It contains only development observations, aggregate validation decisions and artifact digests; no validation or final case rows/labels.
