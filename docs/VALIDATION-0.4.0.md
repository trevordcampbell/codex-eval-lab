# Validation — Codex Eval Lab 0.4.0 core

Recorded October 1, 2026. These are local source checks, not publication, tagging,
hosted CI or a claim about a redesigned UI. The prior [0.3 record](VALIDATION-0.3.0.md)
and [0.2 record](VALIDATION-0.2.0.md) remain available.

## Regression and independent review

The final core passed **445 tests** on Linux x86_64 with Python 3.14.8, MCP 2.2.0
and OpenAI SDK 3.22.1. The actual installed Codex CLI 0.159.3 was checked with
isolated configuration and `--help`; no model turn or provider request occurred.
The complete suite also passed independently from a separate source copy. An
initial system-Python run hit its preexisting old-MCP API mismatch; the pinned
supported environment passed, rather than weakening the plugin tests.

New coverage includes byte-bound plans and real CLI dispatch, positive/negative
oracle controls, all-case reference/grader consistency, truthful provenance, strict
metric parity, stale/forged/partial receipts, duplicate/private-group leakage,
private error redaction, direct local executable launchers, recorded toolchain
identity, preflight accounting, known-cost failures, no replay after missing
receipts, indeterminate optimizer blockers, final capacity and final sealing.

The independent audit reproduced and verified fixes for accounting and privacy
edge cases. It additionally checked failed final comparisons in both measurement
modes, unchanged budgets on resume, the existing synthetic expert-calibration path,
core import without site packages, and exclusion of private receipts from default
reports/development exports. No unresolved blocker remained in that reviewed scope.

The runner now shares one grader-protocol validator between preflight and real
trials. Parity tests cover missing/extra metrics, runner-owned metrics, booleans,
nonfinite/out-of-range numbers, raw criterion statuses and retained trace values.
Known reported costs are retained even when another response field is invalid or
a subprocess exits unsuccessfully after emitting its cost.

## Executed automation demonstration

`python scripts/automation_demo.py --out <new-external-directory>` ran from a
separate frozen copy of the final 0.4.0 runtime:

- 80 synthetic cases, grouped partitions, two repetitions per application trial
- 16 reference/positive/negative anchor calls plus 160 private case-consistency calls
- 560 application-plus-grader trials across baseline, three candidate proposals
  and the final comparison; **736 total reserved/completed ledger attempts**
- The first scripted proposal was selected; both deliberately harmful proposals
  were rejected; the selected source passed the sealed final comparison
- Final routing accuracy 70% → 100%; measured evaluation charges $0
- Three scripted optimizer calls; optimizer dollars remain null/unknown in the
  generic accounting schema, not a claimed measurement of model spending
- A report, bound plan, raw controller-private receipt, exact snapshots, decisions
  and machine-readable automation result were generated

This is executed integration evidence for the machinery, not live model-discovered
improvement. See the [record](validation/automation-demo-0.4.0.json).

## Reports, packaging and skills

The existing UI behavior was preserved; all **17 DOM/protocol tests** passed. No
visual redesign was integrated, and screenshot/host-rendering checks are not claimed.
The two workflow SVGs were updated to avoid mandatory human-control wording and
parsed as well-formed XML; visual raster inspection was unavailable.

Default HTML reports now use bounded trace previews, preserving raw SQLite/JSONL
records and an explicit full-trace export option. New provenance sections distinguish
executed controls from expert calibration and disclose model authorship, finite
claim scope and trust assumptions without embedding private control rows.

SQLite still commits every trial. Blocked-mode JSONL is derived once per invocation,
including ordinary interruption/failure; resume reconstructs it without replaying
completed trials. Tests verify both the single materialization and recovery path.
This removes a code-level quadratic rewrite pattern; no measured end-to-end speedup
is attributed to it.

The four automation-first skills passed the skill validator, and bundled reference
copies match source docs. Source/plugin packaging tests retain specification text,
Rust source and skill metadata. Distribution version metadata is 0.4.0 across the
runner, installer, source package, plugin and unchanged UI package. Dependency
versions were not changed. Local archive/wheel/plugin validation results are recorded
with the delivery artifacts; no remote publish or install is implied.

## Honest boundaries

- The executable-oracle route is trusted local JSON-input/output code, with no case
  file assets, generated artifact transport, credential environment or paid checks;
  up to 1,000 combined anchor and all-case calls within the experiment budget
- Reference agreement and mutation rejection are finite executable evidence, not
  proof of specification truth, independent authorship, source authenticity,
  semantic correctness or production representativeness
- The existing expert semantic calibration path remains separate and strict; mixed
  semantic/deterministic tasks use it rather than hiding a judge behind an oracle
- Same-account local code is not a hostile-code or private-file security boundary;
  cost reservations are not provider-side hard caps
- An unresolved proposal-dispatch/commit phase is preserved and blocked; automatic
  reconstruction of that uncertain phase is not implemented
- Authenticated Codex/provider integration, actual Docker execution and native
  macOS/Windows execution remain unverified here
- The included historical Rust source example reports a real model-guided synthetic
  study on the 0.2 engine/custom timing driver. It did not use this 0.4 workflow,
  its public final data are no longer unseen, and a complete replay was not rerun
- Native Codex plus an authorized coding environment runs experiments. The
  Sites-hosted plugin remains a read-only companion for inspecting evidence; it
  does not create an execution runtime in every ChatGPT/mobile client
