"""Synthetic regression tests for temporal pairing, not performance evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab import paired
from codex_eval_lab.config import load_config
from codex_eval_lab.engine import compare, finalize, initialize, manifest_for, register, run, select
from codex_eval_lab.optimizer import loop, export_workspace
from codex_eval_lab.report import render_report
from codex_eval_lab.stats import compare_rows
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError, digest, read_json
from .helpers import make_fixture


class ScheduleTests(unittest.TestCase):
    def test_deterministic_adjacent_balanced_and_complete(self):
        for count in (2, 3, 6):
            for reps in (1, 2, 3, 4):
                ids = [str(i) for i in range(count)]
                jobs = paired.schedule(ids, reps, 91)
                self.assertEqual(jobs, paired.schedule(list(reversed(ids)), reps, 91))
                self.assertEqual(len(jobs), 2 * count * reps)
                self.assertEqual(len({tuple(job) for job in jobs}), len(jobs))
                first_by_case = {id_: [] for id_ in ids}
                for a, b in zip(jobs[::2], jobs[1::2]):
                    self.assertEqual(a[1:], b[1:])
                    self.assertEqual({a[0], b[0]}, {"reference", "candidate"})
                    first_by_case[a[1]].append(a[0])
                firsts = [job[0] for job in jobs[::2]]
                self.assertLessEqual(abs(firsts.count("reference") - firsts.count("candidate")), 1)
                for orders in first_by_case.values():
                    self.assertLessEqual(abs(orders.count("reference") - orders.count("candidate")), 1)
        self.assertNotEqual(paired.schedule(ids, reps, 91), paired.schedule(ids, reps, 92))


class PairedTests(unittest.TestCase):
    def fixture(self, *, count=6, reps=2, edit=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        suite, app, state = make_fixture(root, cases_per_split=count, repetitions=reps)
        p = suite / "eval.toml"
        cfg = p.read_text() + '\n[measurement]\ndesign = "paired_ab_ba"\n'
        p.write_text(edit(cfg) if edit else cfg)
        initialize(suite, app, state, approvals={"cases": True, "grader": True, "execution": True})
        self.root, self.suite, self.app, self.state = root, suite, app, state
        self.calls = []
        return state

    def candidate(self, label="good", value=1):
        (self.app / "app.py").write_text(f'VALUE = {value}\n')
        register(self.state, self.app, label, "Synthetic regression test candidate")

    def trial(self, state, manifest, source, case, rep, **kwargs):
        self.calls.append((source.name, case["id"], rep))
        text = (source / "app.py").read_text()
        value = float(text.split("=", 1)[1]) if text.startswith("VALUE =") else 0.0
        return {"case_id": case["id"], "group": case["group"], "rep": rep,
                "seed": int(digest({"seed": manifest["config"]["seed"], "id": case["id"], "rep": rep})[:8], 16),
                "status": "ok", "metrics": {"quality": value, "cost_usd": 0},
                "charged_usd": 0, "input": case["input"], "expected": case["expected"]}

    def test_selection_fresh_cohorts_and_final_are_complete(self):
        self.fixture(); self.candidate()
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial):
            result = select(self.state, "good")
            self.assertTrue(result["accepted"])
            self.assertEqual(len(self.calls), 24)
            self.assertEqual(compare(self.state, "baseline", "good"), result)
            final = finalize(self.state, approved=True)
            self.assertTrue(final["accepted"])
            self.assertEqual(len(self.calls), 48)
            self.assertEqual(finalize(self.state, approved=True), final)
            self.assertEqual(len(self.calls), 48)
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(store.budget()["trials"], 48)
            self.assertEqual(store.results("baseline", "validation"), [])
            self.assertEqual(len(store.results("reference", "test", cohort="final")), 12)
            self.assertIn("baseline_source_hash", store.get("final_selection"))
        self.assertEqual(compare(self.state, "baseline", "good", "test")["measurement"]["cohort"], "final")
        with self.assertRaises(LabError): select(self.state, "good")
        with self.assertRaises(LabError): register(self.state, self.app, "later", "Blocked by final seal")

    def test_distinct_incumbent_and_original_get_fresh_reference_calls(self):
        self.fixture(count=2, reps=1); self.candidate("first", .4)
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial):
            select(self.state, "first")
            self.candidate("second", .8)
            select(self.state, "second")
        self.assertEqual(len(self.calls), 12)  # 4 for first; two fresh 4-call cohorts for second.
        with Store(self.state / "state.sqlite3") as store:
            plan = store.get("paired_selection:second")
            self.assertNotEqual(plan["vs_incumbent"], plan["vs_start"])
            self.assertEqual(store.budget()["trials"], 12)
            self.assertEqual(len(store.results("candidate", "validation", cohort=plan["vs_start"])), 2)
        self.assertEqual(compare(self.state, "first", "second")["baseline"], "first")
        self.assertEqual(compare(self.state, "baseline", "second")["baseline"], "baseline")

    def test_reference_source_hash_dedup_keeps_two_independent_roles(self):
        self.fixture(count=2, reps=1)
        register(self.state, self.app, "alias", "Unchanged reference identity")
        with Store(self.state / "state.sqlite3") as store: store.put("best", "alias")
        self.candidate()
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial): select(self.state, "good")
        self.assertEqual(len(self.calls), 4)
        with Store(self.state / "state.sqlite3") as store:
            plan = store.get("paired_selection:good")
            self.assertEqual(plan["vs_incumbent"], plan["vs_start"])
        self.assertEqual(compare(self.state, "baseline", "good")["measurement"]["source_hashes"]["reference"]["label"], "alias")

    def test_unchanged_final_winner_still_runs_independent_aa_calls(self):
        self.fixture(count=2, reps=1)
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial):
            result = finalize(self.state, approved=True)
        self.assertEqual(len(self.calls), 4)
        self.assertFalse(result["accepted"])
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(len(store.results("candidate", "test", cohort="final")), 2)
            self.assertEqual(len(store.results("reference", "test", cohort="final")), 2)

    def test_synthetic_monotone_drift_aa_no_longer_looks_like_a_gain(self):
        self.fixture(count=18, reps=2, edit=lambda s: s.replace('direction = "maximize"', 'direction = "minimize"'))
        register(self.state, self.app, "unchanged", "Unchanged A/A negative control")
        def drifting(*args, **kwargs):
            row = self.trial(*args, **kwargs)
            row["metrics"]["quality"] = .9 - .002 * len(self.calls)
            return row
        with patch("codex_eval_lab.engine.perform_trial", side_effect=drifting), self.assertRaises(LabError):
            select(self.state, "unchanged")
        result = compare(self.state, "baseline", "unchanged")
        self.assertFalse(result["accepted"])
        self.assertAlmostEqual(result["metrics"]["quality"]["raw_delta"], 0)
        # Same synthetic environmental drift in the old all-A-then-all-B order is accepted.
        with Store(self.state / "state.sqlite3") as store:
            manifest = manifest_for(self.state, store)
            spec = store.cohort(store.get("paired_selection:unchanged")["vs_start"])
            ids = manifest["splits"]["validation"]
            base, candidate = [], []
            for index, (case_id, rep) in enumerate((i, r) for i in ids for r in range(2)):
                common = {"case_id": case_id, "rep": rep, "seed": index, "status": "ok"}
                base.append({**common, "metrics": {"quality": .9 - .002 * index, "cost_usd": 0}})
                candidate.append({**common, "metrics": {"quality": .9 - .002 * (index + 36), "cost_usd": 0}})
            self.assertTrue(compare_rows(base, candidate, cases=manifest["cases"], ids=ids, cfg=manifest["config"])["accepted"])
            self.assertEqual(len(spec["schedule"]), 72)

    def test_cached_legacy_rows_do_not_feed_paired_selection(self):
        self.fixture(count=2, reps=1); self.candidate()
        with Store(self.state / "state.sqlite3") as store:
            manifest = manifest_for(self.state, store)
            for label in ("baseline", "good"):
                for case_id in manifest["splits"]["validation"]:
                    store.reserve(label, "validation", case_id, 0, manifest["config"]["budget"])
                    store.complete(label, "validation", case_id, 0, {"case_id": case_id, "rep": 0, "seed": 42,
                                   "status": "ok", "metrics": {"quality": 1 if label == "baseline" else 0, "cost_usd": 0}}, 0)
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial):
            self.assertTrue(select(self.state, "good")["accepted"])
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(store.budget()["trials"], 8)
            self.assertEqual(store.results("baseline", "validation")[0]["metrics"]["quality"], 1)
        report = self.root / "legacy-score-regression.html"
        render_report(self.state, report, include_private=True)
        scorecard = report.read_text().split('<section id="scores">', 1)[1].split('</section>', 1)[0]
        self.assertEqual(scorecard.count("See separate paired cohorts below"), 2)
        self.assertNotIn("<strong>1</strong>", scorecard)

    def interrupted_reserve(self, number):
        original = Store.reserve
        calls = 0
        def reserve(store, *args, **kwargs):
            nonlocal calls
            if kwargs.get("cohort"):
                calls += 1
                if calls == number: raise KeyboardInterrupt
            return original(store, *args, **kwargs)
        return reserve

    def test_resume_at_pair_boundary_does_not_repeat_results(self):
        self.fixture(count=3, reps=1); self.candidate()
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial):
            with patch.object(Store, "reserve", self.interrupted_reserve(3)), self.assertRaises(KeyboardInterrupt):
                select(self.state, "good")
            self.assertEqual(len(self.calls), 2)
            self.assertTrue(select(self.state, "good")["accepted"])
            self.assertEqual(len(self.calls), 6)
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(store.budget()["trials"], 6)

    def test_resume_after_first_arm_completed_invalidates_half_pair(self):
        self.fixture(count=3, reps=1); self.candidate()
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial):
            with patch.object(Store, "reserve", self.interrupted_reserve(2)), self.assertRaises(KeyboardInterrupt):
                select(self.state, "good")
            self.assertEqual(len(self.calls), 1)
            with self.assertRaisesRegex(LabError, "half-pair"): select(self.state, "good")
            self.assertEqual(len(self.calls), 1)
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(store.budget()["trials"], 1)
            self.assertEqual(store.get("best"), "baseline")

    def test_pending_recovery_charges_and_does_not_retry(self):
        self.fixture(count=2, reps=1, edit=lambda s: s.replace('max_eval_cost_usd = 0.0', 'max_eval_cost_usd = 10.0').replace('trial_reserve_usd = 0.0', 'trial_reserve_usd = 0.2'))
        self.candidate()
        def crash(*args, **kwargs):
            if len(self.calls) == 1: raise KeyboardInterrupt
            return self.trial(*args, **kwargs)
        with patch("codex_eval_lab.engine.perform_trial", side_effect=crash), self.assertRaises(KeyboardInterrupt):
            select(self.state, "good")
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(store.pending(), 1)
            self.assertEqual(store.recover(), 1)
            self.assertAlmostEqual(store.budget()["eval_charged_usd"], .2)
            self.assertEqual(store.pending(), 0)
        with patch("codex_eval_lab.engine.perform_trial", side_effect=AssertionError("Must not retry")), self.assertRaises(LabError):
            select(self.state, "good")

    def test_budget_does_not_start_unfunded_half_pair(self):
        self.fixture(count=3, reps=1, edit=lambda s: s.replace('max_trials = 1000', 'max_trials = 5'))
        self.candidate()
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial), self.assertRaisesRegex(LabError, "complete pair"):
            select(self.state, "good")
        self.assertEqual(len(self.calls), 4)
        with Store(self.state / "state.sqlite3") as store: self.assertEqual(store.budget()["trials"], 4)

    def test_final_seal_and_schedule_precede_first_test_call(self):
        self.fixture(count=2, reps=1)
        def check(*args, **kwargs):
            with Store(self.state / "state.sqlite3") as store:
                self.assertEqual(store.get("final_selection")["label"], "baseline")
                self.assertIsNotNone(store.cohort("final"))
            return self.trial(*args, **kwargs)
        with patch("codex_eval_lab.engine.perform_trial", side_effect=check): finalize(self.state, approved=True)

    def test_source_or_cohort_tampering_is_rejected(self):
        self.fixture(count=2, reps=1); self.candidate()
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial): select(self.state, "good")
        with Store(self.state / "state.sqlite3") as store:
            cohort = store.get("paired_selection:good")["vs_start"]
            spec = store.cohort(cohort); spec["arms"]["candidate"]["source_hash"] = "wrong"
            with self.assertRaises(LabError): store.add_cohort(cohort, spec)
            row = store.results("candidate", "validation", cohort=cohort)[0]
            row["cohort"] = "unrelated-cohort"
            store.db.execute("UPDATE paired_trials SET result=? WHERE cohort=? AND label='candidate' AND case_id=?", (json.dumps(row), cohort, row["case_id"]))
            store.db.commit()
        with self.assertRaisesRegex(LabError, "identity mismatch"): compare(self.state, "baseline", "good")
        (self.state / "candidates/good/app.py").write_text("tampered")
        with self.assertRaisesRegex(LabError, "Frozen candidate changed"): compare(self.state, "baseline", "good")

    def test_no_direct_validation_or_test_matrix_and_no_test_comparison(self):
        self.fixture(); self.candidate()
        with self.assertRaises(LabError): run(self.state, "good", "validation")
        with self.assertRaises(LabError): run(self.state, "good", "test")
        with self.assertRaises(LabError): compare(self.state, "baseline", "good", "test")
        with Store(self.state / "state.sqlite3") as store:
            manifest = manifest_for(self.state, store)
            with self.assertRaises(LabError): paired.execute(self.state, store, manifest, "fake", "baseline", "good", "test", allow_test=True)
            self.assertEqual(store.budget()["trials"], 0)

    def test_reports_use_cohorts_and_do_not_leak_holdout_details(self):
        self.fixture(count=2, reps=1); self.candidate()
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial):
            run(self.state, "baseline", "train")
            select(self.state, "good")
            output = self.root / "report.html"
            render_report(self.state, output)
            text = output.read_text()
            self.assertIn("Paired measurement cohorts", text)
            self.assertIn("SECRET-train", text)
            self.assertNotIn("SECRET-validation", text)
            self.assertNotIn("SECRET-test", text)
            render_report(self.state, output, include_private=True)
            self.assertIn("SECRET-validation", output.read_text())
            self.assertNotIn("SECRET-test", output.read_text())
            export_workspace(self.state, self.root / "export", label="baseline")
            self.assertNotIn("SECRET-validation", (self.root / "export/development-feedback.json").read_text())
            finalize(self.state, approved=True)
            render_report(self.state, output, include_private=True)
            self.assertIn("SECRET-test", output.read_text())

    def test_automatic_loop_uses_fresh_pairs_and_keeps_development_only(self):
        self.fixture(count=2, reps=1)
        # Real free adapters verify the complete integration rather than a mocked selector.
        result = loop(self.state, approved=True, rounds=1)
        self.assertEqual(result["best"], "round-0001")
        self.assertEqual(result["budget"]["trials"], 8)  # two development matrices, one 4-call pair cohort
        self.assertEqual(result["history"][0]["vs_start"]["measurement"]["design"], "paired_ab_ba")
        request = read_json(self.state / "optimizer-runs/call-0001/request.json")
        self.assertNotIn("SECRET-validation", json.dumps(request))
        self.assertNotIn("SECRET-test", json.dumps(request))

    def test_cost_budget_reserves_capacity_for_both_arms(self):
        self.fixture(count=2, reps=1, edit=lambda s: s.replace('max_eval_cost_usd = 0.0', 'max_eval_cost_usd = 0.3').replace('trial_reserve_usd = 0.0', 'trial_reserve_usd = 0.2'))
        self.candidate()
        with patch("codex_eval_lab.engine.perform_trial", side_effect=AssertionError("No affordable pair")), self.assertRaisesRegex(LabError, "complete pair"):
            select(self.state, "good")
        with Store(self.state / "state.sqlite3") as store: self.assertEqual(store.budget()["trials"], 0)

    def test_failed_final_half_pair_does_not_unseal_or_allow_new_cohort(self):
        self.fixture(count=2, reps=1)
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial):
            with patch.object(Store, "reserve", self.interrupted_reserve(2)), self.assertRaises(KeyboardInterrupt):
                finalize(self.state, approved=True)
            with self.assertRaisesRegex(LabError, "half-pair"): finalize(self.state, approved=True)
        self.assertEqual(len(self.calls), 1)
        with self.assertRaises(LabError): register(self.state, self.app, "later", "Must remain sealed")
        with self.assertRaises(LabError): compare(self.state, "baseline", "baseline", "test")
        with Store(self.state / "state.sqlite3") as store:
            manifest = manifest_for(self.state, store)
            self.assertIsNotNone(store.get("final_selection"))
            with self.assertRaises(LabError): paired.execute(self.state, store, manifest, "another-final", "baseline", "baseline", "test", allow_test=True)
            self.assertIsNone(store.get("final_result"))

    def test_manual_selection_records_rejection_and_actual_promotion_compare_is_read_only(self):
        self.fixture(count=2, reps=1, edit=lambda s: s.replace('[measurement]\ndesign = "paired_ab_ba"', ''))
        self.candidate("bad", 0); self.candidate("good", .8)
        with patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial):
            for label in ("baseline", "bad", "good"): run(self.state, label, "validation")
        with self.assertRaises(LabError): select(self.state, "bad")
        with Store(self.state / "state.sqlite3") as store:
            before = store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            self.assertEqual(store.get("best"), "baseline")
        self.assertTrue(compare(self.state, "baseline", "good")["accepted"])
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], before)
            self.assertEqual(store.get("best"), "baseline")
        select(self.state, "good")
        with Store(self.state / "state.sqlite3") as store:
            actions = [json.loads(row[0]) for row in store.db.execute("SELECT data FROM events WHERE kind='manual_selection' ORDER BY id")]
            self.assertEqual([(r["candidate"], r["promoted"]) for r in actions], [("bad", False), ("good", True)])
            self.assertEqual(store.get("best"), "good")
        report = self.root / "manual-report.html"
        render_report(self.state, report)
        self.assertIn("bad: not promoted", report.read_text())
        self.assertIn("good: promoted", report.read_text())

    def test_manual_promotion_and_audit_record_are_atomic(self):
        import sqlite3
        self.fixture()
        with Store(self.state / "state.sqlite3") as store:
            store.db.execute("CREATE TRIGGER reject_manual BEFORE INSERT ON events WHEN NEW.kind='manual_selection' BEGIN SELECT RAISE(ABORT,'injected write error'); END")
            store.db.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                store.record_manual_selection("never-committed", {"candidate": "never-committed"}, promoted=True)
            self.assertEqual(store.get("best"), "baseline")

    def test_unknown_measurement_configuration_fails(self):
        self.fixture()
        p = self.suite / "eval.toml"
        p.write_text(p.read_text().replace('design = "paired_ab_ba"', 'design = "random_guess"'))
        with self.assertRaises(LabError): load_config(self.suite)
