# Narrow shipping-core optimization: complete local A/B result

Preregistered primary passed: **1.6489×** median paired unchanged/changed self-CPU ratio, above the fixed **1.10×** useful-effect threshold. This corresponds to **39.36% less CPU** for the synthetic 12-case completed-baseline revisit.

All three paired primary ratios: 1.692746, 1.648948, 1.635682. Median baseline/candidate CPU: 0.680178s / 0.412170s. Median paired candidate-minus-baseline CPU difference: -0.267686s.

This is a bounded local synthetic result, not a claim of statistical certainty, live model improvement or universal production speedup.

## Scope and verification

- Baseline: 60c5883b215806f21e52f48f773c9b30bd81027f
- Candidate: 9a599187d152a7eace4d6101dc49d775cf7b2210
- Runtime delta: only duplicate executable hashing inside one oracle.toolchain call; fresh content reads remain on every subsequent call. No broad semantic cache or completed-job fast path.
- Prespecified PATCH_PLAN_V2.json retained the 1.10 numerical threshold; its wording correctly identifies that threshold as a 9.09% CPU reduction.
- Same pinned Python 3.12.14 executable/environment, deterministic randomized adjacent ordering, three paired runs per workload, new state in each arm.
- All 30 scheduled A/B runs completed inside the 600-second cap. Exact semantic goldens matched across all runs in every workload. No incomplete or failed observations were used.
- Candidate focused invariant pack: 57/57 passed. Candidate diagnostic golden exactly equals baseline diagnostic. Prior external validations and integrity probes are recorded separately in candidate-validation.json and the candidate source records.
- All benchmark, diagnostic and test processes owned by this harness exited. Scientific study/controllers/frozen runtimes were untouched.

## All secondary results

Every value below is unprofiled. Ratios are medians of three paired unchanged/changed ratios. Absolute times are per-arm medians; the ratio of two medians is not necessarily the median paired ratio. All individual values and signed deltas are retained in verification-efficiency-pairs.json and verification-efficiency.json.

### Wall time

| Workload | Phase | Baseline median s | Candidate median s | Paired median ratio | All three paired ratios |
|---|---|---:|---:|---:|---|
| small | fresh_initialize | 0.834093 | 0.797997 | 1.0319 | 1.0319, 1.0268, 1.0681 |
| small | fresh_baseline | 0.507254 | 0.347610 | 1.4593 | 1.4977, 1.4593, 1.3738 |
| small | completed_baseline_revisit | 0.291651 | 0.165193 | 1.7743 | 2.0479, 1.7632, 1.7743 |
| small | paired_selection | 0.870962 | 0.653339 | 1.3621 | 1.3774, 1.3109, 1.3621 |
| cases12 | fresh_initialize | 1.992500 | 2.001283 | 1.0049 | 1.0049, 1.0473, 0.9707 |
| cases12 | fresh_baseline | 1.248770 | 1.010762 | 1.2466 | 1.2355, 1.2596, 1.2466 |
| cases12 | completed_baseline_revisit | 0.680502 | 0.412238 | 1.6496 | 1.6927, 1.6496, 1.6355 |
| cases12 | paired_selection | 2.426966 | 1.842612 | 1.3022 | 1.3573, 1.2845, 1.3022 |
| cases24 | fresh_initialize | 3.923787 | 3.947500 | 0.9979 | 0.9885, 0.9979, 1.0113 |
| cases24 | fresh_baseline | 2.543032 | 2.000532 | 1.2709 | 1.3033, 1.2675, 1.2709 |
| cases24 | completed_baseline_revisit | 1.372208 | 0.862278 | 1.6046 | 1.6393, 1.5501, 1.6046 |
| cases24 | paired_selection | 4.944263 | 3.920150 | 1.2620 | 1.2620, 1.2611, 1.2676 |
| payload16k | fresh_initialize | 0.879430 | 0.821255 | 1.0362 | 1.1219, 1.0166, 1.0362 |
| payload16k | fresh_baseline | 0.506721 | 0.385079 | 1.3159 | 1.4245, 1.3159, 1.3048 |
| payload16k | completed_baseline_revisit | 0.333351 | 0.198959 | 1.6690 | 1.7541, 1.6690, 1.6650 |
| payload16k | paired_selection | 0.931936 | 0.695070 | 1.3408 | 1.3484, 1.3408, 1.3033 |
| history12 | fresh_initialize | 0.840137 | 0.806881 | 1.0412 | 1.0412, 1.0587, 0.9331 |
| history12 | fresh_baseline | 0.609659 | 0.512927 | 1.1886 | 1.1886, 1.2890, 1.1373 |
| history12 | completed_baseline_revisit | 0.438939 | 0.329676 | 1.3314 | 1.2827, 1.5399, 1.3314 |
| history12 | paired_selection | 1.131021 | 0.901534 | 1.2546 | 1.1892, 1.3298, 1.2546 |

### Process self CPU

| Workload | Phase | Baseline median s | Candidate median s | Paired median ratio | All three paired ratios |
|---|---|---:|---:|---:|---|
| small | fresh_initialize | 0.213271 | 0.176488 | 1.2507 | 1.2666, 1.1705, 1.2507 |
| small | fresh_baseline | 0.333835 | 0.184994 | 1.7964 | 1.7964, 1.8046, 1.6953 |
| small | completed_baseline_revisit | 0.291461 | 0.165161 | 1.7734 | 2.0514, 1.7633, 1.7734 |
| small | paired_selection | 0.545511 | 0.318079 | 1.7118 | 1.7422, 1.7118, 1.7079 |
| cases12 | fresh_initialize | 0.407511 | 0.391056 | 1.0628 | 1.0628, 1.1053, 1.0100 |
| cases12 | fresh_baseline | 0.757395 | 0.505732 | 1.4985 | 1.4490, 1.6059, 1.4985 |
| cases12 | completed_baseline_revisit | 0.680178 | 0.412170 | 1.6489 | 1.6927, 1.6489, 1.6357 |
| cases12 | paired_selection | 1.440183 | 0.857661 | 1.6207 | 1.7382, 1.6169, 1.6207 |
| cases24 | fresh_initialize | 0.833984 | 0.825991 | 1.0097 | 1.0097, 0.9967, 1.0695 |
| cases24 | fresh_baseline | 1.537336 | 1.015382 | 1.4827 | 1.5910, 1.4775, 1.4827 |
| cases24 | completed_baseline_revisit | 1.371895 | 0.862206 | 1.6020 | 1.6393, 1.5498, 1.6020 |
| cases24 | paired_selection | 2.987451 | 1.949819 | 1.5322 | 1.5322, 1.5192, 1.5487 |
| payload16k | fresh_initialize | 0.245810 | 0.209769 | 1.1980 | 1.2537, 1.0572, 1.1980 |
| payload16k | fresh_baseline | 0.344334 | 0.222004 | 1.5510 | 1.7439, 1.5510, 1.5282 |
| payload16k | completed_baseline_revisit | 0.333050 | 0.198947 | 1.6692 | 1.7432, 1.6692, 1.6640 |
| payload16k | paired_selection | 0.587529 | 0.370120 | 1.5855 | 1.5951, 1.5855, 1.5654 |
| history12 | fresh_initialize | 0.220273 | 0.193986 | 1.1805 | 1.1805, 1.2588, 0.8512 |
| history12 | fresh_baseline | 0.447024 | 0.350480 | 1.2755 | 1.2755, 1.4028, 1.1972 |
| history12 | completed_baseline_revisit | 0.438900 | 0.329659 | 1.3314 | 1.2826, 1.5398, 1.3314 |
| history12 | paired_selection | 0.805247 | 0.576630 | 1.3965 | 1.2913, 1.5035, 1.3965 |

### Waited-for child CPU

| Workload | Phase | Baseline median s | Candidate median s | Paired median ratio | All three paired ratios |
|---|---|---:|---:|---:|---|
| small | fresh_initialize | 0.467778 | 0.461987 | 0.9736 | 0.9723, 0.9736, 1.0784 |
| small | fresh_baseline | 0.123676 | 0.123517 | 1.0254 | 1.1727, 1.0254, 0.9612 |
| small | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| small | paired_selection | 0.256030 | 0.256703 | 1.0182 | 1.1218, 0.9594, 1.0182 |
| cases12 | fresh_initialize | 1.158788 | 1.235596 | 0.9747 | 0.9863, 0.9747, 0.8998 |
| cases12 | fresh_baseline | 0.374466 | 0.360712 | 1.0113 | 1.0381, 0.9473, 1.0113 |
| cases12 | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| cases12 | paired_selection | 0.739416 | 0.724660 | 1.0377 | 1.0377, 0.9967, 1.0661 |
| cases24 | fresh_initialize | 2.235142 | 2.369852 | 0.9891 | 0.9432, 0.9891, 0.9989 |
| cases24 | fresh_baseline | 0.780406 | 0.729075 | 1.0699 | 1.0699, 1.0662, 1.0925 |
| cases24 | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| cases24 | paired_selection | 1.441634 | 1.432860 | 0.9936 | 0.9899, 1.0195, 0.9936 |
| payload16k | fresh_initialize | 0.480273 | 0.455201 | 0.9911 | 1.1037, 0.9911, 0.9826 |
| payload16k | fresh_baseline | 0.122553 | 0.123181 | 0.9949 | 1.1016, 0.9387, 0.9949 |
| payload16k | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| payload16k | paired_selection | 0.265135 | 0.235058 | 1.1436 | 1.1647, 1.1436, 0.9729 |
| history12 | fresh_initialize | 0.446436 | 0.475898 | 0.9188 | 0.9179, 1.0762, 0.9188 |
| history12 | fresh_baseline | 0.118602 | 0.116305 | 1.0176 | 1.0115, 1.1151, 1.0176 |
| history12 | completed_baseline_revisit | 0.000000 | 0.000000 | n/a | n/a, n/a, n/a |
| history12 | paired_selection | 0.241298 | 0.238606 | 1.0064 | 0.9853, 1.1742, 1.0064 |

Initialization wall times were largely unchanged: median paired ratios ranged from 0.9979 to 1.0412, including the small cases24 regression rather than omitting it. Child-process timings are noisy and did not receive an application change; do not attribute their differences to faster app/grader code.

The cases12 fresh-baseline wall ratio was 1.2466×; paired-selection wall ratio was 1.3022×. These measure direct core operations and exclude initialization and neutral research-controller overhead.

## A/A controls and diagnostic mechanism

Twenty prior unchanged/unchanged runs completed with exact goldens. Across all wall-time phases/cells the paired control ratios ranged 0.847–1.071. The primary cases12 completed-revisit self-CPU control ratios were 0.994467, 1.024947. This context does not supply a confidence interval or eliminate other environmental noise.

Diagnostic mechanism, not speedup evidence: completed cases12 revisit preserved 14 receipt validations, 14 toolchain checks, 42 case loads and 1,092 response checks. File-hash calls fell 602→588 and logical Path-read bytes 869,951,040→437,426,416. The difference is almost entirely one redundant 30,894,944-byte interpreter hash per check; the small runtime-source-size difference is also counted. Paired-selection checks remained 26 receipts/2,028 responses while bytes fell 1,616,296,137→813,036,121. These are logical bytes, not physical disk I/O. Diagnostic timing was not used in the claimed ratio.

## Evidence and limits

- [Complete secondary summary](verification-efficiency.json)
- [Every paired CPU/wall observation](verification-efficiency-pairs.json)
- Raw randomized schedules, per-run states, invariant logs, profiles, A/A controls
  and the independent audit are retained in the private recovery evidence; they
  are not distributed in this repository.
- The original harness setup error and its correction remain retained; no product
  code was changed to fix that error.

The harness uses generated synthetic constant-output tasks, small standard-library subprocesses and a comparatively large Python executable. Absolute impact depends on launcher sharing, executable size and application workload. Three paired repetitions do not establish a confidence bound. The diagnostic profile still shows repeated semantic oracle validation, but this successful narrow patch is not evidence to authorize or adopt a broader cache.
