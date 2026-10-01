"""Regression coverage for frozen, opt-in readiness and atomic result retention."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab.config import audit, load_config, validate_config
from codex_eval_lab.engine import initialize, response_object, run, feedback, manifest_for
from codex_eval_lab.evidence import evaluator_fingerprint, validate_evidence, validate_criterion_results
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError, read_json, write_json
from .helpers import make_fixture

APPROVALS = {"cases": True, "grader": True, "execution": True}


def make_evidence_bundle(suite, *, policy_changes=None, trace_changes=None, output_status=None):
    from codex_eval_lab.review import create_packet, annotate_packet, finalize_rubric, label_criteria
    from codex_eval_lab.calibration import create_judge_outputs, create_evidence_bundle
    traces = []
    for partition, count in (("tuning", 1), ("validation", 4)):
        for verdict in ("pass", "fail"):
            for i in range(count):
                tid = "anchor-" + partition + "-" + verdict + "-" + str(i)
                traces.append({"id": tid, "group": tid, "partition": partition,
                               "input": {"anchor": tid}, "output": verdict,
                               "trace": [{"role": "assistant", "content": verdict}]})
    if trace_changes:
        trace_changes(traces)
    packet = create_packet(traces, reviewer="Human reviewer", source={"kind": "synthetic", "reference": "Offline regression fixture"})
    annotations = [{"trace_id": t["id"], "trace_sha256": t["sha256"], "verdict": t["output"],
                    "rationale": "PRIVATE-HUMAN-ANCHOR", "failure_modes": ["wrong answer"] if t["output"] == "fail" else []}
                   for t in packet["traces"] if t["partition"] == "tuning"]
    review = annotate_packet(packet, annotations, reviewer="Human reviewer")
    rubric = finalize_rubric(packet, review, [{"id": "correctness", "kind": "judge", "metric": "quality",
                            "description": "Correct answer", "failure_mode": "wrong answer",
                            "pass_when": "The answer is correct", "fail_when": "The answer is incorrect",
                            "anchors": [t["id"] for t in packet["traces"] if t["partition"] == "tuning"]}], reviewer="Human reviewer")
    labels = label_criteria(packet, rubric, [{"trace_id": t["id"], "trace_sha256": t["sha256"],
                           "criterion_id": "correctness", "verdict": t["output"], "rationale": "PRIVATE-HELDOUT-LABEL"}
                          for t in packet["traces"]], reviewer="Human reviewer")
    judge_config = {"schema_version": 1, "model": "judge-v1", "model_family": "judge-family",
                    "application_model": "fixture", "application_model_family": "fixture-family",
                    "prompt": "Review each answer independently", "parameters": {"temperature": 0},
                    "evaluator_fingerprint": evaluator_fingerprint(suite)}
    outputs = create_judge_outputs(packet, rubric, judge_config,
                 [{"trace_id": t["id"], "trace_sha256": t["sha256"], "criterion_id": "correctness",
                   "status": output_status if output_status else t["output"], "reason": "PRIVATE-JUDGE-REASON", "model": "judge-v1"}
                  for t in packet["traces"]])
    policy = {"schema_version": 1, "positive_class": "failure", "min_failure_groups": 1, "min_pass_groups": 1,
              "min_failure_recall": .2, "min_failure_precision": .2, "min_good_specificity": .2,
              "confidence": .95, "threshold_basis": "lower_bound"}
    policy.update(policy_changes or {})
    return create_evidence_bundle(packet, review, rubric, labels, judge_config, outputs, policy,
                                  evaluator_fingerprint=evaluator_fingerprint(suite))


class AtomicResultTests(unittest.TestCase):
    def grade(self, results):
        return {"metrics": {"quality": 1}, "usage": {"cost_usd": 0}, "criterion_results": results}

    def test_atomic_components_preserved_independently_from_aggregate(self):
        results = {"format": {"status": "pass", "explanation": "Valid JSON"},
                   "grounded": {"status": "skipped", "explanation": "Provider unavailable"}}
        value = self.grade(results)
        self.assertIs(response_object(value, grader=True)["criterion_results"], results)
        with self.assertRaisesRegex(LabError, "skipped or errored"):
            validate_criterion_results(results, contract=[{"id": key} for key in results])

    def test_legacy_aggregate_grade_remains_valid(self):
        self.assertEqual(response_object({"metrics": {"quality": 1}, "usage": {"cost_usd": 0}}, grader=True)["metrics"], {"quality": 1})

    def test_raw_results_require_exact_fields_status_and_bounded_text(self):
        invalid = [None, [], {}, {"q": 1},
                   {"q": {"status": True, "explanation": "x"}},
                   {"q": {"status": "uncertain", "explanation": "x"}},
                   {"q": {"status": "pass", "explanation": ""}},
                   {"q": {"status": "pass", "explanation": "x" * 8193}},
                   {"q": {"status": "pass", "explanation": "\ud800"}},
                   {"q": {"status": "pass", "explanation": "x", "passed": True}},
                   {str(i): {"status": "pass", "explanation": "x"} for i in range(129)}]
        for result in invalid:
            with self.subTest(result=repr(result)[:100]), self.assertRaises(LabError):
                response_object(self.grade(result), grader=True)

    def test_missing_or_extra_approved_criteria_rejected(self):
        results = {"one": {"status": "pass", "explanation": "Independent judgment"}}
        for contract in ([{"id": "one"}, {"id": "two"}], [{"id": "different"}]):
            with self.assertRaises(LabError):
                validate_criterion_results(results, contract=contract)

    def test_app_cannot_return_grader_criterion_results(self):
        with self.assertRaises(LabError):
            response_object({"output": 1, "usage": {"cost_usd": 0}, "criterion_results": {}})


class EvidenceConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.suite, self.app, self.state = make_fixture(Path(self.tmp.name), cases_per_split=2)

    def configure(self, path="review/evidence.json"):
        with (self.suite / "eval.toml").open("a") as f:
            f.write('\n[evidence]\nbundle = ' + json.dumps(path) + '\n')

    def test_old_suites_explicitly_not_evidence_ready(self):
        result = audit(self.suite)
        self.assertEqual(result["evidence_gate"]["status"], "not_configured")
        self.assertFalse(result["evidence_gate"]["ready"])
        self.assertTrue(any("Evidence gate not configured" in w for w in result["warnings"]))
        with self.assertRaisesRegex(LabError, "not configured"):
            validate_evidence(self.suite, require_ready=True)
        initialize(self.suite, self.app, self.state, approvals=APPROVALS)

    def test_evidence_config_strict_unknown_types_paths(self):
        for value in (True, [], {}, {"bundle": "../escape"}, {"bundle": "/tmp/x"},
                      {"bundle": "a.json", "passed": True}, {"bundle": ["x"]}):
            cfg = load_config(self.suite)
            cfg["evidence"] = value
            with self.subTest(value=value), self.assertRaises(LabError):
                validate_config(cfg)

    def test_bundle_path_normalized(self):
        cfg = load_config(self.suite)
        cfg["evidence"] = {"bundle": "review/./evidence.json"}
        self.assertEqual(validate_config(cfg)["evidence"]["bundle"], "review/evidence.json")

    def test_missing_bundle_fails_closed_without_create(self):
        self.configure()
        self.assertFalse(validate_evidence(self.suite)["ready"])
        with self.assertRaises(LabError):
            initialize(self.suite, self.app, self.state, approvals=APPROVALS)
        self.assertFalse(self.state.exists())

    def test_crafted_passed_flag_is_never_evidence(self):
        self.configure()
        write_json(self.suite / "review/evidence.json", {"passed": True, "human_approved": True})
        self.assertEqual(validate_evidence(self.suite)["status"], "invalid")
        with self.assertRaisesRegex(LabError, "Evidence gate"):
            initialize(self.suite, self.app, self.state, approvals=APPROVALS)

    def test_symlink_bundle_rejected(self):
        self.configure("evidence.json")
        outside = Path(self.tmp.name) / "external.json"
        write_json(outside, {"passed": True})
        (self.suite / "evidence.json").symlink_to(outside)
        self.assertFalse(validate_evidence(self.suite)["ready"])
        with self.assertRaises(LabError):
            initialize(self.suite, self.app, self.state, approvals=APPROVALS)

    def test_fingerprint_binds_grader_bytes_argv_model_metrics(self):
        cfg = load_config(self.suite)
        original = evaluator_fingerprint(self.suite, cfg)
        for field, value in (("expected_judge_model", "judge-v2"), ("grader_command", ["{python}", "{suite}/grader.py", "--new"])):
            changed = copy.deepcopy(cfg)
            changed["execution"][field] = value
            self.assertNotEqual(original, evaluator_fingerprint(self.suite, changed))
        changed = copy.deepcopy(cfg)
        changed["metrics"]["quality"]["maximum"] = 2
        self.assertNotEqual(original, evaluator_fingerprint(self.suite, changed))
        with (self.suite / "grader.py").open("a") as f:
            f.write("\n# New implementation\n")
        self.assertNotEqual(original, evaluator_fingerprint(self.suite, cfg))

    def test_candidate_controlled_or_untracked_grader_not_bound(self):
        for command in (["{python}", "{app}/grader.py"], ["{python}", "{artifacts}/grader.py"], ["external-grader"]):
            cfg = load_config(self.suite)
            cfg["execution"]["grader_command"] = command
            with self.subTest(command=command), self.assertRaises(LabError):
                evaluator_fingerprint(self.suite, cfg)

    def test_snapshot_changed_during_copy_rejected(self):
        import codex_eval_lab.engine as engine
        original = engine.copy_files
        def changing_copy(files, target):
            (self.suite / "grader.py").write_text("# changed after approval\n")
            return original(files, target)
        with patch.object(engine, "copy_files", side_effect=changing_copy), self.assertRaisesRegex(LabError, "changed while"):
            initialize(self.suite, self.app, self.state, approvals=APPROVALS)
        self.assertFalse(self.state.exists())

    def test_atomic_evidence_in_feedback_is_train_only(self):
        grader = self.suite / "grader.py"
        grader.write_text('import json,sys\nr=json.load(sys.stdin)\njson.dump({"metrics":{"quality":1},"usage":{"cost_usd":0},"criterion_results":{"q":{"status":"pass","explanation":"Evidence-"+r["case_id"]}}},sys.stdout)\n')
        initialize(self.suite, self.app, self.state, approvals=APPROVALS)
        run(self.state, "baseline", "train")
        run(self.state, "baseline", "validation")
        result = feedback(self.state, "baseline")
        self.assertTrue(all(row["criterion_results"]["q"]["status"] == "pass" for row in result["development_results"]))
        rendered = json.dumps(result)
        self.assertNotIn("Evidence-validation", rendered)
        self.assertNotIn("Evidence-test", rendered)


class EvidenceExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.suite, self.app, self.state = make_fixture(Path(self.tmp.name), cases_per_split=2)
        config = self.suite / "eval.toml"
        config.write_text(config.read_text().replace('mode = "local"', 'mode = "local"\nexpected_judge_model = "judge-v1"\nexpected_app_model = "fixture"') +
                          '\n[evidence]\nbundle = "review/evidence.json"\n')
        self.grader_response = {"metrics": {"quality": 1}, "model": "judge-v1", "usage": {"cost_usd": 0},
                               "criterion_results": {"correctness": {"status": "pass", "explanation": "Per-criterion actual result"}}}
        self.write_grader()
        self.write_bundle()

    def write_grader(self):
        (self.suite / "grader.py").write_text('import json,sys\nr=json.load(sys.stdin)\njson.dump(' +
                                             repr(self.grader_response) + ',sys.stdout)\n')

    def write_bundle(self, **kwargs):
        bundle = make_evidence_bundle(self.suite, **kwargs)
        write_json(self.suite / "review/evidence.json", bundle)
        return bundle

    def start(self):
        return initialize(self.suite, self.app, self.state, approvals=APPROVALS)

    def test_ready_frozen_snapshot_and_runtime_grade(self):
        self.assertTrue(validate_evidence(self.suite)["ready"])
        self.start()
        manifest = read_json(self.state / "manifest.json")
        self.assertTrue(manifest["evidence_gate"]["ready"])
        self.assertIn("review/evidence.json", manifest["evaluator_hashes"])
        run(self.state, "baseline", "train")
        with Store(self.state / "state.sqlite3") as store:
            rows = store.results("baseline", "train")
        self.assertEqual(rows[0]["criterion_results"], self.grader_response["criterion_results"])

    def test_audit_is_content_free(self):
        result = audit(self.suite)
        serialized = json.dumps(result)
        for private in ("PRIVATE-HUMAN-ANCHOR", "PRIVATE-HELDOUT-LABEL", "PRIVATE-JUDGE-REASON", "anchor-validation", "Correct answer"):
            self.assertNotIn(private, serialized)
        self.assertNotIn("criteria_contract", result["evidence_gate"])

    def test_missing_failure_support_and_undefined_rates_block(self):
        self.write_bundle(output_status="pass")
        self.assertEqual(validate_evidence(self.suite)["status"], "not_ready")
        with self.assertRaises(LabError):
            self.start()

    def test_point_estimate_calibration_does_not_unlock_judge_gate(self):
        self.write_bundle(policy_changes={"threshold_basis": "point_estimate"})
        self.assertFalse(validate_evidence(self.suite)["ready"])
        with self.assertRaises(LabError):
            self.start()

    def test_tiny_perfect_sample_cannot_meet_confidence_threshold(self):
        self.write_bundle(policy_changes={"min_failure_recall": .9, "min_failure_precision": .9, "min_good_specificity": .9})
        self.assertFalse(validate_evidence(self.suite)["ready"])

    def test_sample_cannot_meet_support_threshold(self):
        self.write_bundle(policy_changes={"min_failure_groups": 5})
        self.assertFalse(validate_evidence(self.suite)["ready"])
        with self.assertRaises(LabError):
            self.start()

    def test_stale_grader_blocks_reusing_evidence(self):
        with (self.suite / "grader.py").open("a") as f:
            f.write("# New grader implementation\n")
        self.assertFalse(validate_evidence(self.suite)["ready"])
        with self.assertRaises(LabError):
            self.start()

    def test_model_binding_requires_expected_served_judge(self):
        config = self.suite / "eval.toml"
        config.write_text(config.read_text().replace('expected_judge_model = "judge-v1"\n', ''))
        self.write_bundle()
        self.assertFalse(validate_evidence(self.suite)["ready"])

    def test_application_identity_mismatch_cannot_fake_independence(self):
        config = self.suite / "eval.toml"
        config.write_text(config.read_text().replace('expected_app_model = "fixture"', 'expected_app_model = "judge-v1"'))
        self.write_bundle()
        self.assertFalse(validate_evidence(self.suite)["ready"])

    def test_atomic_quality_cannot_be_minimized_or_unconstrained(self):
        config = self.suite / "eval.toml"
        config.write_text(config.read_text().replace('direction = "maximize"', 'direction = "minimize"'))
        self.write_bundle()
        self.assertFalse(validate_evidence(self.suite)["ready"])

    def test_suite_holdout_cannot_be_relabeled_as_calibration(self):
        for change in (lambda rows: rows[2].update(group="validation-0"),
                       lambda rows: rows[2].update(case_id="test-0"),
                       lambda rows: rows[2].update(input={"split_marker": "SECRET-test-0", "n": 0})):
            self.write_bundle(trace_changes=change)
            self.assertFalse(validate_evidence(self.suite)["ready"])

    def test_frozen_evidence_mutation_blocks_before_execution(self):
        self.start()
        write_json(self.state / "evaluator/review/evidence.json", {"passed": True})
        with self.assertRaisesRegex(LabError, "Frozen evaluator changed"):
            run(self.state, "baseline", "train")
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(store.results("baseline", "train"), [])

    def test_skipped_criterion_cannot_hide_behind_passing_metric(self):
        self.grader_response["criterion_results"]["correctness"]["status"] = "skipped"
        self.write_grader()
        self.write_bundle()
        self.start()
        with self.assertRaisesRegex(LabError, "skipped or errored"):
            run(self.state, "baseline", "train")
        with Store(self.state / "state.sqlite3") as store:
            failed = store.results("baseline", "train")[0]
        self.assertEqual(failed["criterion_results"]["correctness"]["status"], "skipped")
        self.assertEqual(failed["status"], "error")

    def test_aggregate_cannot_contradict_raw_fail(self):
        self.grader_response["criterion_results"]["correctness"]["status"] = "fail"
        self.write_grader()
        self.write_bundle()
        self.start()
        with self.assertRaisesRegex(LabError, "metric disagrees"):
            run(self.state, "baseline", "train")
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(store.results("baseline", "train")[0]["criterion_results"]["correctness"]["status"], "fail")

    def test_missing_raw_criterion_cannot_be_reconstructed_from_metric(self):
        del self.grader_response["criterion_results"]
        self.write_grader()
        self.write_bundle()
        self.start()
        with self.assertRaisesRegex(LabError, "criterion_results"):
            run(self.state, "baseline", "train")

    def test_provider_model_drift_rejected_with_raw_evidence_retained(self):
        self.grader_response["model"] = "judge-v2"
        self.write_grader()
        self.write_bundle()
        self.start()
        with self.assertRaisesRegex(LabError, "Served judge model"):
            run(self.state, "baseline", "train")
        with Store(self.state / "state.sqlite3") as store:
            self.assertIn("criterion_results", store.results("baseline", "train")[0])


if __name__ == "__main__":
    unittest.main()
