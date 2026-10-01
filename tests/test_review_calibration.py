from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from codex_eval_lab.review import (annotate_packet, create_packet, finalize_rubric,
    label_criteria, seal, tuning_view, validate_packet, write_artifact)
from codex_eval_lab.calibration import (calibrate, create_evidence_bundle, create_judge_outputs,
    drift, validate_evidence_bundle, validate_judge_config, validate_policy, _partition_summary)
from codex_eval_lab.util import LabError, digest
from tests.review_helpers import review_fixture, calibration_args, evidence_fixture


class TraceReviewTests(unittest.TestCase):
    def setUp(self):
        self.f = review_fixture()

    def raw_traces(self):
        return [{k: v for k, v in t.items() if k != "sha256"} for t in self.f["packet"]["traces"]]

    def packet(self, traces):
        return create_packet(traces, reviewer="Reviewer", source={"kind": "recorded", "reference": "Local recorded trial capture"})

    def test_packet_binds_real_output_and_trace_snapshot(self):
        packet = self.f["packet"]
        changed = deepcopy(packet)
        changed["traces"][0]["output"] = "Different answer"
        with self.assertRaisesRegex(LabError, "hash mismatch"):
            validate_packet(changed)
        changed = seal(changed)
        with self.assertRaisesRegex(LabError, "Trace content hash mismatch"):
            validate_packet(changed)

    def test_input_object_not_mutated_by_snapshot(self):
        traces = self.raw_traces()
        packet = self.packet(traces)
        traces[0]["output"] = "Mutation"
        self.assertNotEqual(packet["traces"][0]["output"], traces[0]["output"])

    def test_model_suggestions_cannot_be_imported_as_human_labels(self):
        with self.assertRaisesRegex(LabError, "human provenance"):
            annotate_packet(self.f["packet"], self.f["review"]["annotations"], reviewer="model", provenance="model")
        with self.assertRaisesRegex(LabError, "nonempty"):
            annotate_packet(self.f["packet"], self.f["review"]["annotations"], reviewer="")

    def test_unknown_keys_rejected_at_trace_boundary(self):
        traces = self.raw_traces()
        traces[0]["grade"] = 1
        with self.assertRaisesRegex(LabError, "Unknown trace"):
            self.packet(traces)

    def test_experiment_heldouts_never_imported_as_calibration_tuning(self):
        for split in ("validation", "test"):
            traces = self.raw_traces()
            traces[0]["experiment_split"] = split
            with self.assertRaisesRegex(LabError, "experiment validation/test"):
                self.packet(traces)

    def test_group_partition_leakage_rejected(self):
        traces = self.raw_traces()
        traces[2]["group"] = traces[0]["group"]
        with self.assertRaisesRegex(LabError, "groups cannot cross"):
            self.packet(traces)

    def test_duplicate_input_and_case_repetitions_not_independent(self):
        for field in ("input", "case_id"):
            traces = self.raw_traces()
            if field == "input":
                traces[1]["input"] = traces[0]["input"]
            else:
                traces[0][field] = traces[1][field] = "same-case"
            with self.assertRaisesRegex(LabError, "share a group"):
                self.packet(traces)

    def test_open_ended_review_cannot_use_validation(self):
        rows = deepcopy(self.f["review"]["annotations"])
        validation = self.f["packet"]["traces"][2]
        rows.append({**rows[0], "trace_id": validation["id"], "trace_sha256": validation["sha256"]})
        with self.assertRaisesRegex(LabError, "validation"):
            annotate_packet(self.f["packet"], rows, reviewer="Reviewer")

    def test_incomplete_review_rejected_but_uncertain_allowed(self):
        rows = deepcopy(self.f["review"]["annotations"])
        with self.assertRaisesRegex(LabError, "Complete all tuning"):
            annotate_packet(self.f["packet"], rows[:1], reviewer="Reviewer")
        rows[0]["verdict"] = "uncertain"
        result = annotate_packet(self.f["packet"], rows, reviewer="Reviewer")
        self.assertEqual(result["annotations"][0]["verdict"], "uncertain")

    def test_criteria_require_observed_failure_mode_and_both_anchors(self):
        for replacement in ({"failure_mode": "invented"}, {"anchors": ["tuning-fail-0"]},
                            {"anchors": ["tuning-pass-0", "validation-fail-0"]}):
            criteria = deepcopy(self.f["rubric"]["criteria"])
            criteria[0].update(replacement)
            with self.assertRaises(LabError):
                finalize_rubric(self.f["packet"], self.f["review"], criteria, reviewer="Reviewer")

    def test_duplicate_criterion_metric_cannot_hide_composite(self):
        criteria = deepcopy(self.f["rubric"]["criteria"])
        criteria[1]["metric"] = criteria[0]["metric"]
        with self.assertRaisesRegex(LabError, "composite"):
            finalize_rubric(self.f["packet"], self.f["review"], criteria, reviewer="Reviewer")

    def test_create_only_files_and_model_safe_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "packet.json"
            write_artifact(path, self.f["packet"])
            with self.assertRaisesRegex(LabError, "already exists"):
                write_artifact(path, self.f["packet"])
        view = tuning_view(self.f["packet"])
        self.assertTrue(all(t["partition"] == "tuning" for t in view["traces"]))
        self.assertNotIn("validation-pass", str(view))


class CriterionCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.f = review_fixture()

    def run_calibration(self):
        return calibrate(**calibration_args(self.f))

    def replace_outputs(self, rows):
        self.f["outputs"] = create_judge_outputs(self.f["packet"], self.f["rubric"], self.f["judge_config"], rows)

    def test_perfect_criterion_evidence_is_recomputable(self):
        report = self.run_calibration()
        self.assertTrue(report["passed"])
        self.assertFalse(report["ready"])  # Point estimates are exploratory, never engine readiness.
        self.assertEqual(report["positive_class"], "failure")
        for parts in report["criteria"].values():
            self.assertEqual(parts["validation"]["failure_recall"], 1)
            self.assertEqual(parts["validation"]["good_output_specificity"], 1)
        bundle = create_evidence_bundle(**self.f, evaluator_fingerprint="a" * 64)
        self.assertEqual(validate_evidence_bundle(bundle, evaluator_fingerprint="a" * 64), report)
        self.assertTrue(any("not cryptographic proof" in w for w in report["warnings"]))

    def test_missed_failure_and_false_alarm_preserve_reasons(self):
        rows = deepcopy(self.f["outputs"]["rows"])
        for row in rows:
            if row["criterion_id"] == "grounded" and row["trace_id"].startswith("validation"):
                row["status"] = "pass" if row["status"] == "fail" else "fail"
                row["reason"] = "Incorrect judge rationale to inspect"
        self.replace_outputs(rows)
        report = self.run_calibration()
        result = report["criteria"]["grounded"]["validation"]
        self.assertFalse(report["passed"])
        self.assertEqual(result["failure_recall"], 0)
        self.assertEqual(result["failure_precision"], 0)
        self.assertEqual(result["good_output_specificity"], 0)
        self.assertEqual({r["error_type"] for r in result["disagreements"]}, {"missed_failure", "false_alarm"})
        self.assertTrue(all(r["human_rationale"] and r["judge_reason"] for r in result["disagreements"]))
        self.assertEqual(report["criteria"]["format"]["validation"]["failure_recall"], 1)

    def test_composite_and_other_checks_do_not_mask_missing_criterion(self):
        self.replace_outputs([r for r in self.f["outputs"]["rows"] if r["criterion_id"] == "format"])
        report = self.run_calibration()
        self.assertFalse(report["passed"])
        self.assertIn("grounded:validation:unresolved_rows", report["issues"])
        self.assertEqual(report["criteria"]["format"]["validation"]["failure_recall"], 1)

    def test_abstention_skip_error_and_missing_are_never_pass(self):
        for status in ("abstain", "skipped", "error", "missing"):
            with self.subTest(status=status):
                self.f = review_fixture()
                rows = deepcopy(self.f["outputs"]["rows"])
                selected = next(r for r in rows if r["trace_id"] == "validation-fail-0")
                if status == "missing":
                    rows.remove(selected)
                else:
                    selected["status"] = status
                self.replace_outputs(rows)
                report = self.run_calibration()
                self.assertFalse(report["passed"])
                part = report["criteria"]["grounded"]["validation"]
                self.assertEqual(part["support"]["unresolved_judge_rows"], 1)
                self.assertEqual(part["failure_recall"], .5)

    def test_uncertain_and_missing_human_rows_block_acceptance(self):
        for missing in (False, True):
            rows = deepcopy(self.f["labels"]["labels"])
            if missing:
                rows.pop()
            else:
                rows[-1]["verdict"] = "uncertain"
            self.f["labels"] = label_criteria(self.f["packet"], self.f["rubric"], rows, reviewer="Reviewer")
            self.assertFalse(self.run_calibration()["passed"])

    def test_undefined_precision_is_null_even_threshold_zero(self):
        rows = deepcopy(self.f["outputs"]["rows"])
        for row in rows:
            row["status"] = "pass"
        self.replace_outputs(rows)
        for key in ("min_failure_recall", "min_failure_precision", "min_good_specificity"):
            self.f["policy"][key] = 0
        report = self.run_calibration()
        self.assertIsNone(report["criteria"]["grounded"]["validation"]["failure_precision"])
        self.assertFalse(report["passed"])

    def test_per_class_support_counts_groups_not_repetitions(self):
        self.f = review_fixture(validation_groups=1)
        report = self.run_calibration()
        self.assertFalse(report["passed"])
        self.assertEqual(report["criteria"]["grounded"]["validation"]["support"]["failure_groups"], 1)

    def test_same_family_alias_warning_requires_justification(self):
        self.f["judge_config"].update(model="gpt-4.1-judge", model_family="claimed-family-a",
                                      application_model="gpt-4o-app", application_model_family="claimed-family-b")
        rows = deepcopy(self.f["outputs"]["rows"])
        for row in rows:
            row["model"] = self.f["judge_config"]["model"]
        self.replace_outputs(rows)
        self.assertFalse(self.run_calibration()["passed"])
        self.f["judge_config"]["independence_justification"] = "Same family; judged independently against these explicit human anchors"
        self.replace_outputs(rows)
        report = self.run_calibration()
        self.assertTrue(report["passed"])
        self.assertTrue(any(w.startswith("Same-model") for w in report["warnings"]))

    def test_policy_unknown_polarity_nonfinite_and_implicit_support_rejected(self):
        for patch in ({"positive_class": "pass"}, {"min_failure_groups": 0},
                      {"min_failure_recall": float("nan")}, {"min_failure_recall": True}, {"typo": 1}):
            with self.assertRaises(LabError):
                validate_policy({**self.f["policy"], **patch})

    def test_duplicate_label_output_and_wrong_trace_digest_rejected(self):
        rows = deepcopy(self.f["labels"]["labels"])
        with self.assertRaisesRegex(LabError, "Duplicate"):
            label_criteria(self.f["packet"], self.f["rubric"], rows + [rows[0]], reviewer="Reviewer")
        rows = deepcopy(self.f["outputs"]["rows"])
        with self.assertRaisesRegex(LabError, "Duplicate"):
            self.replace_outputs(rows + [rows[0]])
        rows[0]["trace_sha256"] = "0" * 64
        with self.assertRaisesRegex(LabError, "hash mismatch"):
            self.replace_outputs(rows)

    def test_stale_judge_configuration_requires_new_outputs(self):
        self.f["judge_config"]["prompt"] += " Changed rule"
        with self.assertRaisesRegex(LabError, "configuration hash mismatch"):
            self.run_calibration()

    def test_served_model_mismatch_rejected(self):
        rows = deepcopy(self.f["outputs"]["rows"])
        rows[0]["model"] = "unexpected-model"
        with self.assertRaisesRegex(LabError, "served judge model"):
            self.replace_outputs(rows)

    def test_bundle_recomputes_and_rejects_stale_evaluator_or_report(self):
        bundle = evidence_fixture()
        with self.assertRaisesRegex(LabError, "evaluator fingerprint"):
            validate_evidence_bundle(bundle, evaluator_fingerprint="b" * 64)
        bundle["report_sha256"] = digest({"passed": True})
        bundle = seal(bundle)
        with self.assertRaisesRegex(LabError, "report hash mismatch"):
            validate_evidence_bundle(bundle, evaluator_fingerprint="a" * 64)
        bundle = evidence_fixture()
        bundle["passed"] = True
        with self.assertRaisesRegex(LabError, "Unknown"):
            validate_evidence_bundle(seal(bundle), evaluator_fingerprint="a" * 64)

    def test_lower_bounds_stay_honest_for_tiny_perfect_sample(self):
        self.f["policy"]["threshold_basis"] = "lower_bound"
        report = self.run_calibration()
        part = report["criteria"]["grounded"]["validation"]
        self.assertEqual(part["failure_recall"], 1)
        self.assertLess(part["bounds"]["failure_recall"]["lower"], 1)
        self.assertFalse(report["ready"])
        self.assertFalse(report["passed"])
        self.assertEqual(report["uncertainty"]["comparisons"], 6)
        self.assertEqual(part["bounds"]["failure_recall"]["independent_groups"], 2)
        self.assertTrue(any("prevalence" in w for w in report["warnings"]))

    def test_explicit_permissive_bound_policy_is_not_silently_tightened(self):
        self.f["policy"].update(threshold_basis="lower_bound", min_failure_recall=0,
                                min_failure_precision=0, min_good_specificity=0)
        report = self.run_calibration()
        self.assertTrue(report["ready"])
        self.assertEqual(report["policy"]["min_failure_recall"], 0)

    def test_old_outputs_cannot_be_rebound_to_new_evaluator(self):
        with self.assertRaisesRegex(LabError, "do not rebind"):
            create_evidence_bundle(**self.f, evaluator_fingerprint="b" * 64)
        self.f["judge_config"]["evaluator_fingerprint"] = "b" * 64
        with self.assertRaisesRegex(LabError, "configuration hash mismatch"):
            create_evidence_bundle(**self.f, evaluator_fingerprint="b" * 64)

    def test_replica_rows_never_narrow_group_uncertainty(self):
        rows = [{"group": "bad-task", "human_verdict": "fail", "judge_status": "fail"},
                {"group": "good-task", "human_verdict": "pass", "judge_status": "pass"}]
        original = _partition_summary(rows, confidence=.95, comparisons=3)
        replicated = _partition_summary(rows * 100, confidence=.95, comparisons=3)
        self.assertEqual(original["bounds"], replicated["bounds"])
        self.assertEqual(replicated["support"]["failure_groups"], 1)
        self.assertEqual(replicated["support"]["failure_rows"], 100)

    def test_bundle_rejects_reversal_of_observed_human_anchors(self):
        rows = deepcopy(self.f["labels"]["labels"])
        rows[0]["verdict"] = "fail"
        self.f["labels"] = label_criteria(self.f["packet"], self.f["rubric"], rows, reviewer="Reviewer")
        with self.assertRaisesRegex(LabError, "contradicts reviewed rubric anchor"):
            create_evidence_bundle(**self.f, evaluator_fingerprint="a" * 64)

    def test_offline_demo_exposes_judge_failure_despite_good_code_criterion(self):
        import json
        import runpy
        demo = Path(__file__).resolve().parents[1] / "examples/review_calibration/demo.py"
        run = runpy.run_path(str(demo))["run"]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "demo"
            result = run(out)
            self.assertEqual(result["cost_usd"], 0)
            self.assertTrue(result["good_judge_ready_under_demo_policy"])
            self.assertFalse(result["broken_judge_ready"])
            bad = json.loads((out / "broken-calibration.json").read_text())
            self.assertEqual(bad["criteria"]["format"]["validation"]["failure_recall"], 1)
            self.assertEqual(len(bad["criteria"]["grounded"]["validation"]["disagreements"]), 8)

    def test_drift_checks_same_anchors_and_exposes_regressions(self):
        old_config, old_outputs = deepcopy(self.f["judge_config"]), deepcopy(self.f["outputs"])
        self.f["judge_config"]["prompt"] = "New prompt"
        rows = deepcopy(self.f["outputs"]["rows"])
        selected = next(r for r in rows if r["trace_id"] == "validation-fail-0")
        selected["status"], selected["reason"] = "pass", "Missed the failure"
        self.replace_outputs(rows)
        result = drift(self.f["packet"], self.f["rubric"], self.f["labels"], old_config, old_outputs,
                       self.f["judge_config"], self.f["outputs"], self.f["policy"])
        self.assertEqual(result["validation_rate_deltas"]["grounded"]["failure_recall"], -.5)
        self.assertEqual(result["changed_rows"][0]["human_verdict"], "fail")
        self.assertTrue(result["old"]["passed"])
        self.assertFalse(result["new"]["passed"])


if __name__ == "__main__":
    unittest.main()
