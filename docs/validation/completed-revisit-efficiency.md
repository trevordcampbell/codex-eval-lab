# Completed-matrix revisit: final local performance result

Incremental primary versus the first patch: **4.790964×** median paired self-CPU ratio, corresponding to **79.13% less CPU**. The fixed useful-effect threshold was **1.10×**.

Direct original-to-final comparison: **7.982878×** median paired self-CPU ratio, corresponding to **87.47% less CPU**. This combined gain is measured in its own six-run contrast; no median ratios were multiplied.

Both statements apply to a completed synthetic 12-case train-baseline revisit. They are not claims of statistical significance, universal production speedup, or faster LLM inference.

## Frozen design and integrity

- Final candidate: ff3f164dcb6bb830ea62d9e43a6bf5c8a1e1bbbb
- Incremental baseline: 9a599187d152a7eace4d6101dc49d775cf7b2210
- Direct combined baseline: 60c5883b215806f21e52f48f773c9b30bd81027f
- Preregistered plan SHA-256: 5e93804e27802f4104751d5968044a55dc21a89f92221e7476e4e40b35524e03
- Final engine SHA-256: 3af1d2f2c4f1c88793467db1a697c3d1fb817e0fae78727da7f33d6929aa0f19
- Same pinned Python 3.12.14 executable/environment in both contrasts. Every run used fresh synthetic state and deterministic randomized adjacent unchanged/changed ordering.
- Incremental contrast: five workloads, three pairs each, seed 20261003, 30 runs, 600-second cap. Direct combined contrast: cases12 only, three pairs, seed 20261004, six runs, 180-second cap.
- All 36 comparison runs completed; every exact semantic golden matched. Candidate source identities and interpreter hashes match across the two contrasts. No incomplete runs supplied performance observations.
- Candidate invariants: 57/57 passed in 4.089s. Candidate diagnostic golden exactly matches both previous implementations. Full current-runtime/source-integrity validations were independently completed before timing.
- Candidate validation, diagnostics and timing ran separately from independent results auditing; the final timing process exited at 17:16:29 UTC.
- The rejected early candidate stale-entry bug and its two source repairs were evaluated before this timing. Only final ff3f164 was measured. No scientific study/controller/frozen runtime was modified.

## Primary measurements

| Contrast | Baseline CPU median s | Candidate CPU median s | Median paired ratio | All three paired ratios | Median paired candidate−baseline s |
|---|---:|---:|---:|---|---:|
| Incremental: 9a599187 → ff3f164 | 0.433175 | 0.090415 | 4.790964 | 5.082992, 4.553213, 4.790964 | -0.342760 |
| Direct combined: 60c5883 → ff3f164 | 0.737582 | 0.092359 | 7.982878 | 7.087092, 8.140582, 7.982878 | -0.633508 |

Arm medians and paired-ratio medians are distinct estimators; do not divide the displayed arm medians to reconstruct the reported paired ratio. Three observations give descriptive local evidence, not a confidence interval.

## Complete secondary results

Every reported timing below is unprofiled. Each ratio is the median of three paired unchanged/changed ratios. All individual arm timings, ratios and signed deltas appear in completed-revisit-efficiency-pairs.json (216 metric-pair rows) and completed-revisit-efficiency.json.

### incremental

#### Wall time

| Workload | Phase | Baseline median s | Candidate median s | Paired median ratio | All three paired ratios |
|---|---|---:|---:|---:|---|
| small | fresh_initialize | 0.818478 | 0.795747 | 1.0165 | 1.0295, 1.0024, 1.0165 |
| small | fresh_baseline | 0.349509 | 0.340086 | 1.0277 | 1.0277, 1.0065, 1.0858 |
| small | completed_baseline_revisit | 0.168991 | 0.094265 | 1.8416 | 1.7927, 1.8442, 1.8416 |
| small | paired_selection | 0.657658 | 0.633726 | 1.0281 | 1.0451, 0.9964, 1.0281 |
| cases12 | fresh_initialize | 1.944899 | 1.967137 | 0.9887 | 0.9329, 0.9887, 1.0067 |
| cases12 | fresh_baseline | 0.972558 | 0.951396 | 1.0074 | 1.0375, 0.9838, 1.0074 |
| cases12 | completed_baseline_revisit | 0.433774 | 0.090443 | 4.7961 | 5.0733, 4.5815, 4.7961 |
| cases12 | paired_selection | 1.896356 | 1.859388 | 0.9977 | 0.9937, 0.9977, 1.0385 |
| cases24 | fresh_initialize | 3.823308 | 3.818424 | 0.9955 | 1.0650, 0.9679, 0.9955 |
| cases24 | fresh_baseline | 1.943855 | 2.015250 | 0.9571 | 1.1087, 0.9571, 0.9472 |
| cases24 | completed_baseline_revisit | 0.875419 | 0.104015 | 8.3253 | 9.0047, 8.3253, 7.8237 |
| cases24 | paired_selection | 3.910389 | 3.968681 | 0.9832 | 1.0227, 0.9832, 0.9629 |
| payload16k | fresh_initialize | 0.830143 | 0.823586 | 1.0138 | 0.9868, 1.0138, 1.0328 |
| payload16k | fresh_baseline | 0.399389 | 0.410586 | 0.9986 | 1.0323, 0.9727, 0.9986 |
| payload16k | completed_baseline_revisit | 0.211497 | 0.104294 | 2.0279 | 1.8810, 2.0279, 2.0490 |
| payload16k | paired_selection | 0.712309 | 0.718790 | 0.9910 | 0.9159, 0.9910, 1.0728 |
| history12 | fresh_initialize | 0.785367 | 0.798111 | 0.9980 | 0.9837, 0.9980, 1.0042 |
| history12 | fresh_baseline | 0.513494 | 0.485689 | 1.0209 | 1.0695, 1.0209, 1.0146 |
| history12 | completed_baseline_revisit | 0.341337 | 0.160232 | 2.0982 | 2.0982, 2.2209, 1.9927 |
| history12 | paired_selection | 0.920566 | 0.908597 | 1.0132 | 0.9998, 1.0132, 1.0235 |

#### Process self CPU

| Workload | Phase | Baseline median s | Candidate median s | Paired median ratio | All three paired ratios |
|---|---|---:|---:|---:|---|
| small | fresh_initialize | 0.184721 | 0.182976 | 1.0095 | 1.0574, 0.9534, 1.0095 |
| small | fresh_baseline | 0.186532 | 0.176701 | 1.0556 | 1.0556, 1.0116, 1.1081 |
| small | completed_baseline_revisit | 0.168962 | 0.094249 | 1.8416 | 1.7927, 1.8441, 1.8416 |
| small | paired_selection | 0.311814 | 0.309101 | 1.0195 | 1.0309, 0.9568, 1.0195 |
| cases12 | fresh_initialize | 0.357821 | 0.381084 | 0.9390 | 0.9014, 0.9390, 1.0279 |
| cases12 | fresh_baseline | 0.484669 | 0.464350 | 1.0119 | 1.0788, 0.9680, 1.0119 |
| cases12 | completed_baseline_revisit | 0.433175 | 0.090415 | 4.7910 | 5.0830, 4.5532, 4.7910 |
| cases12 | paired_selection | 0.919324 | 0.872304 | 1.0277 | 0.9998, 1.0277, 1.0809 |
| cases24 | fresh_initialize | 0.761550 | 0.747961 | 0.9864 | 1.1856, 0.9369, 0.9864 |
| cases24 | fresh_baseline | 0.965439 | 1.036136 | 0.9213 | 1.1638, 0.9213, 0.9144 |
| cases24 | completed_baseline_revisit | 0.875320 | 0.103990 | 8.2827 | 9.0061, 8.2827, 7.8242 |
| cases24 | paired_selection | 1.950460 | 1.985004 | 0.9615 | 1.0402, 0.9615, 0.9453 |
| payload16k | fresh_initialize | 0.204101 | 0.200714 | 1.0169 | 0.9070, 1.0728, 1.0169 |
| payload16k | fresh_baseline | 0.234397 | 0.227928 | 0.9984 | 0.9654, 1.0284, 0.9984 |
| payload16k | completed_baseline_revisit | 0.211463 | 0.104282 | 2.0278 | 1.8811, 2.0278, 2.0494 |
| payload16k | paired_selection | 0.372538 | 0.393332 | 0.9760 | 0.8740, 0.9760, 1.0306 |
| history12 | fresh_initialize | 0.172808 | 0.184137 | 0.9564 | 0.9253, 0.9680, 0.9564 |
| history12 | fresh_baseline | 0.350933 | 0.322888 | 1.0306 | 1.0995, 1.0306, 1.0210 |
| history12 | completed_baseline_revisit | 0.341309 | 0.160230 | 2.0982 | 2.0982, 2.2211, 1.9928 |
| history12 | paired_selection | 0.594312 | 0.563534 | 1.0375 | 1.0017, 1.0546, 1.0375 |

#### Waited-for child CPU

| Workload | Phase | Baseline median s | Candidate median s | Paired median ratio | All three paired ratios |
|---|---|---:|---:|---:|---|
| small | fresh_initialize | 0.462124 | 0.460780 | 1.0126 | 0.9883, 1.0126, 1.0222 |
| small | fresh_baseline | 0.113850 | 0.115191 | 0.9824 | 0.9824, 1.0382, 0.9430 |
| small | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| small | paired_selection | 0.251788 | 0.234353 | 1.0676 | 1.1028, 1.0676, 1.0050 |
| cases12 | fresh_initialize | 1.124599 | 1.156142 | 0.9651 | 0.8708, 0.9651, 1.0469 |
| cases12 | fresh_baseline | 0.343054 | 0.337987 | 1.0150 | 0.9988, 1.0182, 1.0150 |
| cases12 | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| cases12 | paired_selection | 0.708031 | 0.713009 | 1.0037 | 1.0230, 0.9423, 1.0037 |
| cases24 | fresh_initialize | 2.209775 | 2.256682 | 0.9697 | 1.0846, 0.9433, 0.9697 |
| cases24 | fresh_baseline | 0.724482 | 0.756545 | 0.9304 | 1.1030, 0.9069, 0.9304 |
| cases24 | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| cases24 | paired_selection | 1.437034 | 1.470481 | 1.0162 | 1.0216, 1.0162, 0.9357 |
| payload16k | fresh_initialize | 0.451701 | 0.465066 | 0.9988 | 0.9694, 0.9988, 1.0449 |
| payload16k | fresh_baseline | 0.133869 | 0.124124 | 1.0787 | 1.0931, 0.7890, 1.0787 |
| payload16k | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| payload16k | paired_selection | 0.255634 | 0.257271 | 0.9936 | 0.9580, 0.9936, 1.1208 |
| history12 | fresh_initialize | 0.459178 | 0.423720 | 1.0903 | 1.0903, 0.9835, 1.0972 |
| history12 | fresh_baseline | 0.114169 | 0.115742 | 0.9864 | 0.9864, 1.0240, 0.9457 |
| history12 | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| history12 | paired_selection | 0.227229 | 0.238437 | 0.9489 | 0.9489, 0.9385, 1.0142 |

### direct_combined_primary

#### Wall time

| Workload | Phase | Baseline median s | Candidate median s | Paired median ratio | All three paired ratios |
|---|---|---:|---:|---:|---|
| cases12 | fresh_initialize | 2.160691 | 2.000287 | 1.0314 | 1.0071, 1.1161, 1.0314 |
| cases12 | fresh_baseline | 1.297285 | 0.977338 | 1.2934 | 1.1864, 1.4366, 1.2934 |
| cases12 | completed_baseline_revisit | 0.738026 | 0.092384 | 7.9873 | 7.0903, 8.1577, 7.9873 |
| cases12 | paired_selection | 2.552038 | 1.881090 | 1.3102 | 1.2108, 1.3839, 1.3102 |

#### Process self CPU

| Workload | Phase | Baseline median s | Candidate median s | Paired median ratio | All three paired ratios |
|---|---|---:|---:|---:|---|
| cases12 | fresh_initialize | 0.490840 | 0.401534 | 1.0989 | 1.0945, 1.4679, 1.0989 |
| cases12 | fresh_baseline | 0.798455 | 0.469128 | 1.6554 | 1.4688, 1.9130, 1.6554 |
| cases12 | completed_baseline_revisit | 0.737582 | 0.092359 | 7.9829 | 7.0871, 8.1406, 7.9829 |
| cases12 | paired_selection | 1.555137 | 0.888108 | 1.6194 | 1.5843, 1.8470, 1.6194 |

#### Waited-for child CPU

| Workload | Phase | Baseline median s | Candidate median s | Paired median ratio | All three paired ratios |
|---|---|---:|---:|---:|---|
| cases12 | fresh_initialize | 1.270144 | 1.157564 | 1.0329 | 0.9989, 1.0973, 1.0329 |
| cases12 | fresh_baseline | 0.359345 | 0.368598 | 0.9749 | 0.8476, 1.0307, 0.9749 |
| cases12 | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| cases12 | paired_selection | 0.763058 | 0.752861 | 0.9775 | 0.8424, 0.9775, 1.0982 |

## Attribution and limits

Second-change mechanism: complete successful train/legacy-validation revisits use freshly validated entry and exit source/manifest/evaluator/receipt checks plus exact accepted-ledger/result identity. Eligibility is checked after fresh entry checks; exit rechecks compare the complete ledger identity, including stored result text and accounting. Noneligible, interrupted, pending, indeterminate or incomplete matrices retain the original execution loop. Final test and paired selection do not take the shortcut.

Instrumented cases12 revisit verifies the expected mechanism: full manifest/receipt validations fell 14→3, oracle response checks 1,092→234, file hashes 588→126 and logical Path-read bytes 437,426,416→93,741,942, with no raw trial calls. Fresh-baseline and paired-selection validation/raw-call counts were unchanged; their slight read-byte increases reflect the larger runtime source file. Initialization counts were unchanged. Instrumented durations were excluded from speedup estimates.

The second optimization targets revisits, not new app/grader calls. Other phase differences, including regressions/noisy child-process times, are retained above and are not evidence of faster adapters. Direct combined cases12 fresh-baseline wall ratio was 1.293364× and paired-selection wall ratio 1.310207×; these predominantly reflect the first executable-hash optimization. Direct initialization wall ratio was 1.031356×. Combined claims outside cases12 were not measured here.

Prior A/A context is retained in the private raw evidence: all 20 runs/goldens passed, with wall ratios from 0.847 to 1.071 across phases/cells. This does not eliminate environmental variation or provide a confidence bound. The workload uses synthetic constant-output scripts, a large shared Python executable, small fixtures and a same-machine process. History12 includes a completed four-trial historical matrix plus 12 retained proposal receipts. Results need not transfer to long-running production applications, different executable sizes, other storage or workloads.

The original harness setup error, first-patch evidence, early rejected second-candidate bug and final source-integrity evidence remain preserved. The neutral scientific controller is not measured or changed.

## Evidence

- [Complete secondary summary](completed-revisit-efficiency.json)
- [Every paired CPU/wall observation](completed-revisit-efficiency-pairs.json)
- The prespecified plan, randomized orders, per-run states, invariant/diagnostic
  logs and independent source/evidence review are retained in private recovery
  evidence; they are not distributed in this repository.
