# Upcoming 0.5.0: review and migration guide

Status: **unreleased**. This guide describes the implementation in commit
`0ce0131badf71741054cef9b3b20852083e42ea5`, with its validation record added by
`4d1ad4d05c0120938e0754c90f0ed40a7a861fe3`, based on 0.4.0 main `8b8578a`.
It does not announce a GitHub release, tag, registry upload or hosted deployment.

The measured runtime still identifies itself as 0.4.0. Its exact module hashes are
in [the original core record](validation/optimizer-upgrade-core.json). A later
packaging-only 0.5.0 version bump changes identity bytes; it must not be described
as the byte-identical runtime that produced that record or the frozen study.

## Separate native workflow hardening

This checkout also stages additive `start-native` and `evaluate-turn` commands
built after the comparative runtime was frozen. They are product safety/ergonomics
changes, not a component tested by that benchmark. They reuse the existing
plan-reservation and active-round selection logic without modifying scientific
gates. A subsequent lifecycle guard also rejects active rounds and unresolved
trial work before any final seal, saved-final return or sealed-final continuation;
recovery cannot reopen selection or authorize additional indeterminate final calls.
Clean final retrieval and complete-boundary resumes remain supported. This is an
intentional safety tightening, not an unchanged old lifecycle guarantee. Validation
status is recorded separately in [VALIDATION.md](VALIDATION.md).
Do not replace an active frozen runtime with this source.

## What changes

- **Optional exploratory archive:** Keep selected useful development behaviors as
  future parents. Conservative selection remains the default. Archive admission,
  empirical search selection, validation confidence gates and sealed final release
  qualification are distinct outcomes
- **Fixed operator routing:** `refine`, `repair` and `rewrite` are fixed prompt
  instructions with deterministic parent selection. Round-robin is the default;
  optional UCB is a heuristic over selected gain per evaluation trial. It excludes
  unknown inference cost, has no regret guarantee here and does not learn operators
- **Counted native handoff:** `prepare-turn` reserves one author opportunity and
  snapshots source/prompt/feedback. The authorized host dispatches the model.
  `submit-turn` captures its response before scoped application. The measured
  runtime used `loop --rounds 1` to evaluate an active round; the later hardened
  route uses `evaluate-turn --call-id` with no dispatch fallback. This is external
  orchestration, not evidence that
  one-command live `automate` or authenticated standalone Codex CLI execution works
- **Bounded feedback:** A frozen byte budget retains complete all-row numeric
  aggregates, worst-first per-case metrics as space allows, at most three marked
  payload examples, exact omissions and the original feedback hash. Full rows
  remain in controller state and continue to drive statistics
- **Exact-JSON controls:** Optional generated type, shape and value negatives,
  plus numeric-equivalence and object-key-order positives, challenge the actual
  grader. They require a narrow asserted equality contract; they are not semantic
  calibration, independent labels, domain truth or production error-rate evidence
- **Reviewable receipts:** Exact dispatch/response records, pinned digests,
  bounded ordinary-file reads, later revalidation and preserved unknown attempts
  make cooperative evidence inspectable. Same-account writers can still fabricate
  all records; these mechanisms do not authenticate a user/model or isolate reads

There is no core dependency addition: Python 3.11+ standard library remains sufficient.
Declared optional MCP, judge and UI dependency ranges remain compatible. The
release judge lock was separately updated to OpenAI 3.23.0 after offline compatibility
checks; historical tested locks remain preserved. Trevor Campbell's authored
ownership, MIT license and bundled third-party notices remain intact.

## Choose the smallest change for a new experiment

1. **Keep conservative search:** Omit `[search_policy]`. Existing proposal JSON,
   application/grader adapters, metrics, thresholds and guardrails still apply.
   This preserves selection defaults, not an old state's runtime compatibility
2. **Explore archive parents:** Add the complete frozen example in
   [SEARCH_POLICY.md](SEARCH_POLICY.md#versioned-exploratory-configuration). Choose
   primary-unit diversity/reward scales and limits before observing results. Do
   not weaken validity or final superiority/noninferiority gates
3. **Bound author feedback explicitly:** Add `max_feedback_bytes = 65536` to the
   existing `[search]` table. The allowed range is 4,096–2,000,000 UTF-8 bytes;
   omission uses 65,536 at proposal time. Small packets stay unchanged. If required
   summary/header data cannot fit, preparation fails instead of silently dropping it
4. **Challenge an exact-output grader:** Add `generated_controls` to a new oracle
   contract using [EVAL_DESIGN.md](EVAL_DESIGN.md). Do not paste a second `[search]`
   table or treat the JSON fragment as a complete contract. Existing anchors,
   reference, hand-authored negatives and all-case checks remain required
5. **Use a native author:** Follow the complete
   [prepare/submit example](SEARCH_POLICY.md#native-authors-with-immutable-evidence).
   Keep the public handoff unchanged until submission, supervise the real author
   externally, and preserve unknown model/token/dollar fields honestly. The later
   `start-native` initialization path reuses exact-plan final reserves; it runs
   configured oracle preflight but stops before search. Follow each applied call
   with `evaluate-turn --call-id`. Plain `start` retains its unprotected behavior;
   protected capacity still cannot extend the wall-time deadline

Both opt-ins change the source-bound plan. Generated controls also add preflight
calls under the existing 1,000-call cap and experiment budget. Recompute the plan
and fit all preflight, baseline, candidate and final capacity before beginning.
The host's authority and security policy still govern every actual execution.

## Preserve frozen experiments

There is **no in-place state migration**. Keep each frozen state with its exact
runtime and environment; do not edit manifests, hashes, SQLite or receipts to make
an upgraded runner accept it. Even a version-only change to `__init__.py` changes
the runtime fingerprint. Do not install a new editable package over an active run.

Use a separate checkout/environment, new suite/plan/state and new baseline after
an upgrade. Existing source-format compatibility does not retroactively certify
old evidence. Changes to cases, reference, grader, objective, controls, measurement,
search policy or relevant toolchain assumptions require the same fresh process.
Previously exposed finals remain reproduction evidence, not a fresh holdout.

For fair comparisons, predeclare and equalize eligible artifacts, feedback format,
opportunities and resources; count failed and meta-design attempts. Shared bounded
feedback on an older engine is an explicitly modified adapter, not its original
byte-identical prompt. Native inference costs can remain unknown. A CPU-kernel
metric is not automatically end-to-end wall latency or whole-workflow efficiency.

## Before integration or publication

The documentation patch is separate from the proposed synchronized metadata bump.
Review and integrate them deliberately after scored measurements stop. Source
commits are not publication authority. No remote push, release/tag, upload or
registry publication is part of this checklist's completed status.

1. Review the source diff, original runtime hash record, authorship/license fields,
   and unresolved validation limits. Keep the original record unchanged
2. Apply the version-only patch across `pyproject.toml`, runtime `__version__`, skill
   installer metadata, source archive name/manifest, both plugin manifests, UI
   package/lockfile, UI source and the bundled UI identity string. These set 0.5.0
   as a source version while the changelog remains explicitly unreleased
3. In a measurement-free window, run the full core suite, reference synchronization
   check, offline scripted demo and applicable optional-SDK tests with recorded
   interpreter/dependency versions. Report failures and skips, not just a count
4. Rebuild the pinned UI and run its interaction/protocol tests. A staged edit of
   the bundled identity string is not a verified regeneration. Confirm only the
   expected identity bytes change and preserve third-party notices
5. Build source/wheel/plugin artifacts outside the repository, validate the plugin,
   verify content hashes and packaging allowlists, and regenerate
   `RELEASE_MANIFEST.json` against the final integrated bytes. Recheck skill copies
6. Record exact final-commit validation and any hosted CI separately. Require the
   corresponding authority before any remote publication or installation

Relevant commands (run only in that isolated validation window):

```sh
PYTHONPATH=src python -m unittest discover -v
python scripts/sync_skill_references.py --check
python scripts/automation_demo.py --out ../eval-lab-0.5.0-demo
# Use the repository's pinned toolchain and installed dependencies:
npm --prefix plugin-ui run build
npm --prefix plugin-ui test
python -m build --outdir ../eval-lab-0.5.0-dist
python scripts/package_release.py --out ../eval-lab-0.5.0-source
python scripts/build_plugin.py --out ../eval-lab-0.5.0-plugin
python scripts/validate_plugin.py ../eval-lab-0.5.0-plugin/catalog/plugins/codex-eval-lab
```

All output directories must be fresh. The completed local checks are recorded in
[VALIDATION.md](VALIDATION.md#final-local-packaging-checks); the external artifact
manifest binds their final source and archive identities. The original 510-test
aggregate remains historical. No machinery result establishes SOTA, policy
superiority or universal improvement.

## Measured outcomes and verification cost

The completed [workflow pilot](validation/optimizer-transfer-pilot.md) did not beat
strong iterative Direct on its primary endpoint. Archive remains opt-in; the initial
policy was retained and no live component ablation was achieved. The separate
[verification patch](validation/verification-efficiency.md) reuses an executable
digest only within one oracle toolchain check. Every later verification boundary
resolves and reads fresh content; expected role-command bindings and frozen digests
remain enforced. Existing states must retain their original runtime.

A later completed-result shortcut applies only to exact successful non-test matrices.
It retains fresh entry/exit manifest, oracle, receipt and source checks, plus exact
full-ledger identity across the shortcut; incomplete/failed/indeterminate states
use ordinary handling. No actual execution boundary is omitted. The direct combined
[performance result](validation/completed-revisit-efficiency.md) is separately measured
from the earlier duplicate-hash patch; historical experiments retain their old runtime.
