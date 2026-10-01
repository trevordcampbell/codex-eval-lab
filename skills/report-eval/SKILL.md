---
name: report-eval
description: Summarize completed or in-progress evaluation experiments with scores, uncertainty, costs, errors, hypotheses, and source provenance. Use for experiment review and decision reports; keep held-out details out of optimizer-facing exports and never invent results.
---

# Report what was actually measured

Read `references/OPERATING_GUIDE.md` and `references/PROTOCOL.md`. Locate the approved
experiment state and use durable records, not remembered chat claims. Run:

```sh
eval-lab status <state>
eval-lab report <state> --out <report.html>
```

The default report contains development details and held-out aggregates only where
available. A report can still expose validation selection feedback; do not supply
it as proposal context. Use `eval-lab feedback` for optimizer-facing development data.
Only use `--include-private` when explicitly requested by an authorized human, and
warn that it must not be fed into subsequent optimization. Unopened test cases remain
hidden even from that report.

Lead with the decision: selected candidate, whether final confirmation happened,
and what actually changed. Report baseline/candidate scores, paired deltas, intervals,
independent cases/groups, repeats, constraints/regressions and complete versus failed
runs. Give exact artifact/commit/source identity and reproducibility conditions.
Separate measured eval charges, conservative unknown-cost reservations and optimizer
usage; missing optimizer dollar accounting is unknown, not zero or included.

Mark adaptive validation as exploratory. Never claim a synthetic scripted fixture
is a real Codex/model benchmark, that a configured CI job ran, or that a score gain
proves broad capability improvements. Note unavailable checks and limitations.
Render model content as escaped text and never execute embedded HTML/SVG/scripts.
Do not publish private data or upload reports without explicit authorization.

## Report the validity of the grader separately

Read `references/EVIDENCE.md`. Include whether trace review and evidence gates were
configured and passed, criterion-level support, missed failures, false alarms,
abstentions, undefined rates, independent group counts and calibration version.
Separate component and composite results. Keep historical evidence distinguishable
from current drift checks; no reapproval is implied by a prior pass. Never include
private calibration or final-test records in optimizer-facing reports or messages.
