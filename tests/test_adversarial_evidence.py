"""Independent adversarial probes of review/evidence trust boundaries.

Fixtures are synthetic, offline tests. A local ``recorded`` assertion in a test
is not a claim of real production evidence or authenticated human participation.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab import review
from codex_eval_lab.config import load_config
from codex_eval_lab.engine import initialize, response_object
from codex_eval_lab.evidence import validate_criterion_results, validate_evidence
from codex_eval_lab.util import LabError, write_json
from .helpers import make_fixture


def reviewed_fixture(*, validation_pairs=4, same_validation_group=False,
                     source_kind="recorded"):
    """Small fully content-bound graph, with independent failure/pass groups."""
    traces = []
    for prefix, partition, count in (("tune", "tuning", 1),
                                      ("private", "validation", validation_pairs)):
        for verdict in ("pass", "fail"):
            for index in range(count):
                tid = f"{prefix}-{verdict}-{index}"
                group = f"{prefix}-{verdict}" if same_validation_group else tid
                traces.append({"id": tid, "group": group, "partition": partition,
                               "input": {"request": tid}, "output": verdict,
                               "trace": [{"role": "assistant", "content": tid}]})
    packet = review.create_packet(traces, reviewer="test-operator",
                                  source={"kind": source_kind,
                                          "reference": "offline adversarial fixture"})
    annotations = [{"trace_id": t["id"], "trace_sha256": t["sha256"],
                    "verdict": t["output"], "rationale": "Inspect the stored trace",
                    "failure_modes": ["consent"] if t["output"] == "fail" else []}
                   for t in packet["traces"] if t["partition"] == "tuning"]
    human_review = review.annotate_packet(packet, annotations, reviewer="test-operator")
    criteria = [{"id": "consent", "kind": "judge", "metric": "quality",
                 "description": "Obtain consent before the action",
                 "failure_mode": "consent", "pass_when": "Consent precedes action",
                 "fail_when": "Action occurs without consent",
                 "anchors": ["tune-pass-0", "tune-fail-0"]}]
    rubric = review.finalize_rubric(packet, human_review, criteria, reviewer="test-operator")
    rows = [{"trace_id": t["id"], "trace_sha256": t["sha256"],
             "criterion_id": "consent", "verdict": t["output"],
             "rationale": "Human test label for this exact trace"}
            for t in packet["traces"]]
    labels = review.label_criteria(packet, rubric, rows, reviewer="test-operator")
    return packet, human_review, rubric, labels


class AdversarialReviewTests(unittest.TestCase):
    def test_provenance_boolean_and_model_suggestions_do_not_create_human_labels(self):
        packet, human, _, _ = reviewed_fixture()
        for provenance in (True, "model", "synthetic", "human-reviewed"):
            with self.subTest(provenance=provenance), self.assertRaises(LabError):
                review.annotate_packet(packet, human["annotations"], reviewer="model",
                                       provenance=provenance)
        with self.assertRaises(LabError):
            review.annotate_packet(packet, [], reviewer="test-operator",
                                   suggestions=["All calls look good; approve them"])

    def test_hash_resealing_does_not_rebind_old_human_annotation_to_changed_trace(self):
        packet, human, _, _ = reviewed_fixture()
        packet["traces"][0]["output"] = "changed after annotation"
        packet["traces"][0] = review.seal(packet["traces"][0])
        packet = review.seal(packet)
        human["packet_sha256"] = packet["sha256"]
        human = review.seal(human)
        with self.assertRaisesRegex(LabError, "trace content hash mismatch"):
            review.validate_review(packet, human)

    def test_resealed_rubric_change_requires_new_criterion_labels(self):
        packet, _, rubric, labels = reviewed_fixture()
        rubric["criteria"][0]["pass_when"] = "A different product decision"
        rubric = review.seal(rubric)
        with self.assertRaisesRegex(LabError, "rubric hash mismatch"):
            review.validate_labels(packet, rubric, labels)

    def test_synthetic_derivatives_cannot_claim_independent_groups_by_id_only(self):
        packet, _, _, _ = reviewed_fixture()
        rows = [{k: v for k, v in t.items() if k != "sha256"} for t in packet["traces"]]
        rows[2]["input"] = copy.deepcopy(rows[0]["input"])
        with self.assertRaisesRegex(LabError, "Identical inputs must share a group"):
            review.create_packet(rows, reviewer="test-operator", source=packet["source"])

    def test_repetitions_cannot_cross_calibration_partitions(self):
        packet, _, _, _ = reviewed_fixture()
        rows = [{k: v for k, v in t.items() if k != "sha256"} for t in packet["traces"]]
        rows[0].update(case_id="same-case", rep=0)
        rows[2].update(case_id="same-case", rep=1)
        with self.assertRaisesRegex(LabError, "Repetitions of a case must share a group"):
            review.create_packet(rows, reviewer="test-operator", source=packet["source"])

    def test_private_examples_cannot_become_open_review_or_rubric_anchors(self):
        packet, human, rubric, _ = reviewed_fixture()
        private = next(t for t in packet["traces"] if t["partition"] == "validation")
        row = copy.deepcopy(human["annotations"][0])
        row.update(trace_id=private["id"], trace_sha256=private["sha256"])
        with self.assertRaisesRegex(LabError, "must not inspect calibration validation"):
            review.annotate_packet(packet, human["annotations"] + [row], reviewer="test-operator")
        criteria = copy.deepcopy(rubric["criteria"])
        criteria[0]["anchors"].append(private["id"])
        with self.assertRaisesRegex(LabError, "never validation"):
            review.finalize_rubric(packet, human, criteria, reviewer="test-operator")
        self.assertNotIn("private-", json.dumps(review.tuning_view(packet)))

    def test_experiment_holdouts_cannot_be_imported_as_calibration_tuning(self):
        packet, _, _, _ = reviewed_fixture()
        for split in ("validation", "test"):
            traces = [{k: v for k, v in t.items() if k != "sha256"} for t in packet["traces"]]
            traces[0]["experiment_split"] = split
            with self.subTest(split=split), self.assertRaises(LabError):
                review.create_packet(traces, reviewer="test-operator", source=packet["source"])

    def test_criteria_cannot_alias_one_composite_metric(self):
        packet, human, rubric, _ = reviewed_fixture()
        criteria = copy.deepcopy(rubric["criteria"])
        duplicate = copy.deepcopy(criteria[0]); duplicate["id"] = "other-check"
        with self.assertRaisesRegex(LabError, "composite metrics cannot mask criteria"):
            review.finalize_rubric(packet, human, criteria + [duplicate], reviewer="test-operator")

    def test_review_artifacts_cannot_overwrite_existing_or_follow_file_symlink(self):
        packet, _, _, _ = reviewed_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / "target.json"
            target.write_text("retained private data")
            for destination in (target, root / "alias.json"):
                if destination != target:
                    destination.symlink_to(target)
                with self.assertRaises(LabError):
                    review.write_artifact(destination, packet)
            self.assertEqual(target.read_text(), "retained private data")


class AdversarialCriterionResultTests(unittest.TestCase):
    contract = [{"id": "consent", "kind": "judge", "metric": "quality"}]

    def test_absent_partial_or_abstaining_atomic_result_cannot_hide_behind_aggregate(self):
        values = [None, {}, {"other": {"status": "pass", "explanation": "Passed"}}]
        values += [{"consent": {"status": s, "explanation": "No decision"}}
                   for s in ("skipped", "error", "abstain", "not_applicable", True, 1)]
        for value in values:
            with self.subTest(value=value), self.assertRaises(LabError):
                validate_criterion_results(value, contract=self.contract)

    def test_component_results_are_not_inferred_from_passing_metric(self):
        value = {"metrics": {"quality": 1}, "usage": {"cost_usd": 0}}
        parsed = response_object(value, grader=True)
        self.assertNotIn("criterion_results", parsed)
        with self.assertRaises(LabError):
            validate_criterion_results(parsed.get("criterion_results"), contract=self.contract)

    def test_atomic_explanation_cannot_be_html_object_or_unbounded_blob(self):
        for explanation in ({"html": "<script>alert(1)</script>"}, "", " \n", "a" * 8193):
            with self.subTest(explanation_type=type(explanation)), self.assertRaises(LabError):
                validate_criterion_results({"consent": {"status": "pass", "explanation": explanation}})


class AdversarialEvidenceIOTests(unittest.TestCase):
    def test_untrusted_bundle_errors_do_not_echo_embedded_private_content(self):
        with tempfile.TemporaryDirectory() as directory:
            suite, _, _ = make_fixture(Path(directory))
            with (suite / "eval.toml").open("a") as output:
                output.write('\n[evidence]\nbundle = "evidence.json"\n')
            secret = "PRIVATE-JUDGE-HOLDOUT-SENTINEL"
            for payload in ({"kind": secret, "human": True, "ready": True},
                            {"labels": [{"output": secret}], "passed": True}):
                write_json(suite / "evidence.json", payload)
                result = validate_evidence(suite)
                self.assertFalse(result["ready"])
                self.assertNotIn(secret, json.dumps(result))
                with self.assertRaises(LabError) as caught:
                    validate_evidence(suite, require_ready=True)
                self.assertNotIn(secret, str(caught.exception))

    def test_bundle_path_traversal_and_symlink_cannot_load_private_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); suite, _, _ = make_fixture(root)
            write_json(root / "private.json", {"private": "SECRET-OUTSIDE-SUITE"})
            (suite / "alias.json").symlink_to(root / "private.json")
            for name in ("../private.json", "alias.json"):
                cfg = load_config(suite); cfg["evidence"] = {"bundle": name}
                result = validate_evidence(suite, cfg)
                self.assertFalse(result["ready"])
                self.assertNotIn("SECRET-OUTSIDE-SUITE", json.dumps(result))

    def test_hash_before_freeze_catches_grader_mutation_between_validation_and_copy(self):
        from codex_eval_lab.artifacts import copy_files
        with tempfile.TemporaryDirectory() as directory:
            suite, app, state = make_fixture(Path(directory))
            def mutate_then_copy(files, target):
                if target == state / "evaluator":
                    (suite / "grader.py").write_text("raise RuntimeError('changed after approval')")
                return copy_files(files, target)
            with patch("codex_eval_lab.engine.copy_files", side_effect=mutate_then_copy):
                with self.assertRaisesRegex(LabError, "changed while it was being frozen"):
                    initialize(suite, app, state,
                               approvals={"cases": True, "grader": True, "execution": True})
            self.assertFalse(state.exists())


def calibration_fixture(*, validation_pairs=4, same_validation_group=False,
                        source_kind="recorded", evaluator_fingerprint="a" * 64):
    from codex_eval_lab.calibration import create_judge_outputs
    packet, human, rubric, labels = reviewed_fixture(
        validation_pairs=validation_pairs, same_validation_group=same_validation_group,
        source_kind=source_kind)
    config = {"schema_version": 1, "model": "judge-test-v1", "model_family": "judge-family",
              "application_model": "application-test-v1", "application_model_family": "app-family",
              "prompt": "Evaluate consent using the frozen rubric", "parameters": {"temperature": 0},
              "evaluator_fingerprint": evaluator_fingerprint}
    policy = {"schema_version": 1, "positive_class": "failure", "min_failure_groups": 2,
              "min_pass_groups": 2, "min_failure_recall": 0.2,
              "min_failure_precision": 0.2, "min_good_specificity": 0.2,
              "confidence": 0.95, "threshold_basis": "lower_bound"}
    rows = [{"trace_id": t["id"], "trace_sha256": t["sha256"], "criterion_id": "consent",
             "status": t["output"], "reason": "Offline test judgment", "model": config["model"]}
            for t in packet["traces"]]
    outputs = create_judge_outputs(packet, rubric, config, rows)
    return packet, human, rubric, labels, config, outputs, policy


class AdversarialCalibrationTests(unittest.TestCase):
    def calibrate(self, fixture):
        from codex_eval_lab.calibration import calibrate
        packet, _, rubric, labels, config, outputs, policy = fixture
        return calibrate(packet, rubric, labels, config, outputs, policy)

    def test_missing_uncertain_or_abstaining_rows_never_shrink_denominator_to_a_pass(self):
        baseline = calibration_fixture()
        self.assertTrue(self.calibrate(baseline)["passed"])
        for mutation in ("missing-human", "uncertain", "missing-judge", "abstain", "skipped", "error"):
            fixture = copy.deepcopy(baseline)
            packet, _, rubric, labels, config, outputs, policy = fixture
            if mutation in ("missing-human", "uncertain"):
                if mutation == "missing-human": labels["labels"].pop()
                else: labels["labels"][-1]["verdict"] = "uncertain"
                labels = review.seal(labels)
            else:
                if mutation == "missing-judge": outputs["rows"].pop()
                else: outputs["rows"][-1]["status"] = mutation
                outputs = review.seal(outputs)
            fixture = (packet, None, rubric, labels, config, outputs, policy)
            with self.subTest(mutation=mutation):
                report = self.calibrate(fixture)
                self.assertFalse(report["passed"])
                self.assertTrue(report["criteria"]["consent"]["validation"]["unresolved"])

    def test_known_confusion_matrix_uses_failure_positive_polarity(self):
        packet, _, rubric, labels, config, outputs, policy = calibration_fixture(validation_pairs=4)
        by_id = {r["trace_id"]: r for r in outputs["rows"]}
        by_id["private-fail-0"]["status"] = "pass"  # FN = 1
        by_id["private-pass-0"]["status"] = "fail"  # FP = 2
        by_id["private-pass-1"]["status"] = "fail"
        report = self.calibrate((packet, None, rubric, labels, config, review.seal(outputs), policy))
        part = report["criteria"]["consent"]["validation"]
        self.assertEqual(part["confusion_rows"], {"true_failures": 3, "missed_failures": 1,
                                                  "false_alarms": 2, "true_passes": 2})
        self.assertEqual(part["failure_recall"], 0.75)
        self.assertEqual(part["failure_precision"], 0.6)
        self.assertEqual(part["good_output_specificity"], 0.5)
        self.assertFalse(report["passed"])

    def test_identical_class_predictions_are_not_perfect_on_imbalanced_support(self):
        for status in ("pass", "fail"):
            fixture = list(calibration_fixture())
            outputs = fixture[5]
            for row in outputs["rows"]: row["status"] = status
            fixture[5] = review.seal(outputs)
            with self.subTest(status=status):
                report = self.calibrate(fixture)
                self.assertFalse(report["passed"])
                val = report["criteria"]["consent"]["validation"]
                if status == "pass":
                    self.assertEqual(val["failure_recall"], 0)
                    self.assertIsNone(val["failure_precision"])
                else:
                    self.assertEqual(val["good_output_specificity"], 0)

    def test_replica_count_cannot_meet_independent_class_support(self):
        fixture = calibration_fixture(validation_pairs=25, same_validation_group=True)
        report = self.calibrate(fixture)
        self.assertFalse(report["passed"])
        val = report["criteria"]["consent"]["validation"]
        self.assertEqual(val["support"]["trace_rows"], 50)
        self.assertEqual(val["support"]["failure_groups"], 1)
        self.assertEqual(val["support"]["pass_groups"], 1)

    def test_composite_perfection_cannot_mask_zero_judge_failure_recall(self):
        from codex_eval_lab.calibration import create_judge_outputs
        packet, human, rubric, labels, config, outputs, policy = calibration_fixture()
        criteria = copy.deepcopy(rubric["criteria"])
        code = copy.deepcopy(criteria[0]); code.update(id="syntax", kind="code", metric="format_valid")
        rubric = review.finalize_rubric(packet, human, criteria + [code], reviewer="test-operator")
        label_rows = []
        output_rows = []
        for trace in packet["traces"]:
            for cid in ("consent", "syntax"):
                label_rows.append({"trace_id": trace["id"], "trace_sha256": trace["sha256"],
                                   "criterion_id": cid, "verdict": trace["output"],
                                   "rationale": "Offline human fixture"})
                output_rows.append({"trace_id": trace["id"], "trace_sha256": trace["sha256"],
                                    "criterion_id": cid,
                                    "status": "pass" if cid == "consent" else trace["output"],
                                    "reason": "Raw component verdict", "model": config["model"]})
        labels = review.label_criteria(packet, rubric, label_rows, reviewer="test-operator")
        outputs = create_judge_outputs(packet, rubric, config, output_rows)
        # AND-composite exactly equals the human outcome, but consent is useless.
        for trace in packet["traces"]:
            component = [r["status"] for r in output_rows if r["trace_id"] == trace["id"]]
            self.assertEqual(all(s == "pass" for s in component), trace["output"] == "pass")
        report = self.calibrate((packet, human, rubric, labels, config, outputs, policy))
        self.assertEqual(report["criteria"]["consent"]["validation"]["failure_recall"], 0)
        self.assertFalse(report["passed"])

    def test_same_model_alias_cannot_claim_independence_by_declared_family_only(self):
        from codex_eval_lab.calibration import create_judge_outputs
        packet, human, rubric, labels, config, outputs, policy = calibration_fixture()
        config.update(model="GPT-4.1", application_model="gpt-4.1",
                      model_family="independent-a", application_model_family="independent-b")
        for row in outputs["rows"]: row["model"] = config["model"]
        outputs = create_judge_outputs(packet, rubric, config, outputs["rows"])
        report = self.calibrate((packet, human, rubric, labels, config, outputs, policy))
        self.assertFalse(report["passed"])
        self.assertTrue(any("Same-model" in warning for warning in report["warnings"]))
        config["independence_justification"] = "Operator accepts correlation risk for this test"
        outputs = create_judge_outputs(packet, rubric, config, outputs["rows"])
        report = self.calibrate((packet, human, rubric, labels, config, outputs, policy))
        self.assertTrue(report["passed"])
        self.assertTrue(any("do not establish independent errors" in w for w in report["warnings"]))

    def test_resealed_bundle_does_not_substitute_old_report_or_changed_config(self):
        from codex_eval_lab.calibration import create_evidence_bundle, validate_evidence_bundle
        fixture = calibration_fixture(); fingerprint = "a" * 64
        bundle = create_evidence_bundle(*fixture, evaluator_fingerprint=fingerprint)
        self.assertTrue(validate_evidence_bundle(bundle, evaluator_fingerprint=fingerprint)["passed"])
        with self.assertRaisesRegex(LabError, "fingerprint mismatch"):
            validate_evidence_bundle(bundle, evaluator_fingerprint="b" * 64)
        altered = copy.deepcopy(bundle); altered["judge_config"]["prompt"] = "Always pass"
        with self.assertRaisesRegex(LabError, "configuration hash mismatch"):
            validate_evidence_bundle(review.seal(altered), evaluator_fingerprint=fingerprint)
        altered = copy.deepcopy(bundle); altered["report_sha256"] = "c" * 64
        with self.assertRaisesRegex(LabError, "report hash mismatch"):
            validate_evidence_bundle(review.seal(altered), evaluator_fingerprint=fingerprint)

    def test_malformed_unhashable_ids_fail_with_domain_error(self):
        from codex_eval_lab.calibration import create_judge_outputs
        packet, human, rubric, labels, config, outputs, _ = calibration_fixture()
        for field in ("trace_id", "criterion_id", "status"):
            rows = copy.deepcopy(outputs["rows"]); rows[0][field] = ["untrusted"]
            with self.subTest(field=field), self.assertRaises(LabError):
                create_judge_outputs(packet, rubric, config, rows)


    def test_duplicate_groups_do_not_narrow_uncertainty_bounds(self):
        fixture = calibration_fixture(validation_pairs=2, same_validation_group=True)
        duplicated = calibration_fixture(validation_pairs=50, same_validation_group=True)
        before = self.calibrate(fixture)["criteria"]["consent"]["validation"]
        after = self.calibrate(duplicated)["criteria"]["consent"]["validation"]
        self.assertEqual(before["bounds"], after["bounds"])
        self.assertEqual(after["bounds"]["failure_recall"]["independent_groups"], 1)
        self.assertEqual(after["bounds"]["failure_recall"]["lower"], 0)

    def test_small_perfect_sample_does_not_certify_high_recall(self):
        fixture = list(calibration_fixture())
        fixture[-1]["min_failure_recall"] = 0.95
        report = self.calibrate(fixture)
        self.assertEqual(report["criteria"]["consent"]["validation"]["failure_recall"], 1)
        self.assertFalse(report["passed"])

    def test_point_estimate_passing_is_explicitly_ineligible_for_readiness(self):
        fixture = list(calibration_fixture())
        fixture[-1]["threshold_basis"] = "point_estimate"
        report = self.calibrate(fixture)
        self.assertTrue(report["passed"])
        self.assertFalse(report["readiness_eligible"])
        self.assertFalse(report["ready"])

    def test_existing_outputs_cannot_be_rebound_to_a_new_evaluator_at_bundle_creation(self):
        from codex_eval_lab.calibration import create_evidence_bundle
        with self.assertRaisesRegex(LabError, "fingerprint mismatch"):
            create_evidence_bundle(*calibration_fixture(), evaluator_fingerprint="b" * 64)


class AdversarialReviewUITests(unittest.TestCase):
    def test_open_review_html_excludes_private_partition_even_from_search_and_page_source(self):
        from codex_eval_lab.review_ui import render_standalone_review
        packet, _, _, _ = reviewed_fixture()
        text = render_standalone_review(packet)
        self.assertIn("tune-pass-0", text)
        self.assertNotIn("private-pass-", text)
        self.assertNotIn("private-fail-", text)
        self.assertNotIn("offline adversarial fixture", text)

    def test_trace_markup_is_inert_json_and_cannot_create_active_elements(self):
        from html.parser import HTMLParser
        from codex_eval_lab.review_ui import render_standalone_review
        payload = '</script><img src="https://attacker.invalid/pixel" onerror="alert(1)"><script>alert(2)</script>'
        packet, _, _, _ = reviewed_fixture()
        traces = [{k: v for k, v in t.items() if k != "sha256"} for t in packet["traces"]]
        traces[0]["output"] = payload
        traces[0]["trace"][0]["content"] = payload
        packet = review.create_packet(traces, reviewer="test-operator", source=packet["source"])
        rendered = render_standalone_review(packet)
        class Tags(HTMLParser):
            def __init__(self): super().__init__(); self.tags = []
            def handle_starttag(self, tag, attrs): self.tags.append((tag, dict(attrs)))
        parser = Tags(); parser.feed(rendered)
        self.assertFalse(any(tag in {"img", "iframe", "object", "embed"} for tag, _ in parser.tags))
        self.assertFalse(any(key.startswith("on") for _, attrs in parser.tags for key in attrs))
        self.assertEqual(sum(tag == "script" for tag, _ in parser.tags), 2)
        self.assertNotIn(payload, rendered)
        self.assertIn("connect-src &#x27;none&#x27;", rendered)
        self.assertIn("\\u003c/script\\u003e", rendered)

    def test_mcp_widget_resource_contains_no_evidence_or_stale_annotation(self):
        from codex_eval_lab.review_ui import render_mcp_review
        rendered = render_mcp_review()
        self.assertNotIn('id="review-data"', rendered)
        self.assertNotIn("private-fail-", rendered)
        self.assertNotIn("tune-fail-", rendered)


class AdversarialReadyGateTests(unittest.TestCase):
    def ready_suite(self, root, *, atomic_status="pass", metric=1):
        from codex_eval_lab.calibration import create_evidence_bundle
        from codex_eval_lab.evidence import evaluator_fingerprint
        suite, app, state = make_fixture(root, cases_per_split=2)
        path = suite / "eval.toml"
        config_text = path.read_text().replace(
            'mode = "local"', 'mode = "local"\nexpected_judge_model = "judge-test-v1"\nexpected_app_model = "application-test-v1"')
        path.write_text(config_text + '\n[evidence]\nbundle = "evidence.json"\n')
        code = app / "app.py"
        code.write_text(code.read_text().replace('"fixture"', '"application-test-v1"'))
        grade = {"metrics": {"quality": metric}, "usage": {"cost_usd": 0}, "model": "judge-test-v1",
                 "criterion_results": {"consent": {"status": atomic_status, "explanation": "Raw decision"}}}
        (suite / "grader.py").write_text("import json\nprint(json.dumps(" + repr(grade) + "))\n")
        fingerprint = evaluator_fingerprint(suite)
        bundle = create_evidence_bundle(*calibration_fixture(evaluator_fingerprint=fingerprint), evaluator_fingerprint=fingerprint)
        write_json(suite / "evidence.json", bundle)
        self.assertTrue(validate_evidence(suite)["ready"])
        return suite, app, state

    def test_stale_live_grader_bytes_block_ready_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            suite, app, state = self.ready_suite(Path(directory))
            with (suite / "grader.py").open("a") as output: output.write("\n# a changed evaluator\n")
            self.assertFalse(validate_evidence(suite)["ready"])
            with self.assertRaises(LabError):
                initialize(suite, app, state, approvals={"cases": True, "grader": True, "execution": True})
            self.assertFalse(state.exists())

    def test_atomic_pass_rate_cannot_be_minimized(self):
        with tempfile.TemporaryDirectory() as directory:
            suite, _, _ = self.ready_suite(Path(directory))
            cfg = load_config(suite); cfg["objective"]["direction"] = "minimize"
            self.assertFalse(validate_evidence(suite, cfg)["ready"])

    def test_metric_and_raw_criterion_disagreement_invalidates_trial(self):
        from codex_eval_lab.engine import run
        from codex_eval_lab.store import Store
        with tempfile.TemporaryDirectory() as directory:
            suite, app, state = self.ready_suite(Path(directory), atomic_status="fail", metric=1)
            initialize(suite, app, state, approvals={"cases": True, "grader": True, "execution": True})
            with self.assertRaises(LabError): run(state, "baseline", "train")
            with Store(state / "state.sqlite3") as store:
                rows = store.results("baseline", "train")
            self.assertEqual(rows[0]["status"], "error")
            self.assertEqual(rows[0]["criterion_results"]["consent"]["status"], "fail")

    def test_bundle_modified_after_read_cannot_pass_pre_copy_verification(self):
        import codex_eval_lab.evidence as evidence
        with tempfile.TemporaryDirectory() as directory:
            suite, _, _ = self.ready_suite(Path(directory))
            real_read = evidence.read_json
            def mutate_after_read(path):
                value = real_read(path)
                if path == suite / "evidence.json":
                    path.write_text('{"forged":true}')
                return value
            with patch.object(evidence, "read_json", side_effect=mutate_after_read):
                result = validate_evidence(suite)
            self.assertFalse(result["ready"])


    def test_application_identity_change_cannot_reuse_independence_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            suite, _, _ = self.ready_suite(Path(directory))
            cfg = load_config(suite)
            cfg["execution"]["expected_app_model"] = cfg["execution"]["expected_judge_model"]
            self.assertFalse(validate_evidence(suite, cfg)["ready"])


class AdversarialPluginScopeTests(unittest.TestCase):
    def test_packet_catalog_and_widget_metadata_do_not_leak_holdouts(self):
        from codex_eval_lab.plugin_server import PacketStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet, _, _, _ = reviewed_fixture()
            path = root / "public.packet.json"; write_json(path, packet)
            # Even valid neighboring files and recursive discoveries need operator scope.
            private = root / "nested"; private.mkdir()
            other = copy.deepcopy(packet); other["source"]["reference"] = "unregistered private source"
            write_json(private / "private.packet.json", review.seal(other))
            write_json(root / "arbitrary.json", review.seal(other))
            store = PacketStore(root)
            catalog = store.list_review_packets()
            self.assertEqual(len(catalog["packets"]), 1)
            summary, meta = store.open_review(packet["sha256"])
            rendered = json.dumps({"catalog": catalog, "summary": summary, "meta": meta})
            self.assertNotIn("private-pass-", rendered)
            self.assertNotIn("private-fail-", rendered)
            self.assertNotIn("unregistered private source", rendered)
            self.assertNotIn(str(root), rendered)
            self.assertIn("tune-pass-0", json.dumps(meta))
            self.assertNotIn("tune-pass-0", json.dumps(summary))
            self.assertFalse(summary["approval"])

    def test_registered_packets_are_snapshots_not_reopened_paths(self):
        from codex_eval_lab.plugin_server import PacketStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); packet, _, _, _ = reviewed_fixture()
            path = root / "packet.json"; write_json(path, packet)
            store = PacketStore(packets=(path,))
            path.write_text('{"output":"PRIVATE-CHANGED-AFTER-REGISTRATION"}')
            summary, meta = store.open_review(packet["sha256"])
            self.assertNotIn("PRIVATE-CHANGED-AFTER-REGISTRATION", json.dumps(meta))
            self.assertEqual(summary["tuning_trace_count"], 2)
            # Returned UI dictionaries do not permit mutation of the registered snapshot.
            meta["codex-eval-lab/review"]["packet"]["traces"][0]["trace"][0]["content"] = "MUTATED-RETURN"
            _, fresh = store.open_review(packet["sha256"])
            self.assertNotIn("MUTATED-RETURN", json.dumps(fresh))

    def test_arbitrary_paths_and_command_strings_are_not_packet_identifiers(self):
        from codex_eval_lab.plugin_server import PacketStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); packet, _, _, _ = reviewed_fixture()
            path = root / "packet.json"; write_json(path, packet)
            store = PacketStore(packets=(path,))
            for identifier in ("../packet.json", str(path), "$(touch /tmp/never)", "python -c 'print(1)'", "f" * 64):
                with self.subTest(identifier=identifier), self.assertRaises(LabError) as caught:
                    store.open_review(identifier)
                self.assertNotIn(identifier, str(caught.exception))

    def test_symlink_file_or_directory_cannot_expand_registered_scope(self):
        from codex_eval_lab.plugin_server import PacketStore
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); packet, _, _, _ = reviewed_fixture()
            target = root / "private"; target.mkdir(); write_json(target / "packet.json", packet)
            link = root / "alias.packet.json"; link.symlink_to(target / "packet.json")
            directory_link = root / "linked"; directory_link.symlink_to(target, target_is_directory=True)
            for kwargs in ({"packets": (link,)}, {"workspace_root": directory_link},
                           {"packets": (directory_link / "packet.json",)}):
                with self.subTest(kwargs=kwargs), self.assertRaises(LabError):
                    PacketStore(**kwargs)


class AdversarialReviewRoundtripTests(unittest.TestCase):
    # Lightweight DOM harness executes the real browser source's handlers. This
    # is deterministic behavior coverage, not a substitute for visual browser QA.
    DOM_HARNESS = r'''
import {pathToFileURL} from 'node:url';
const {mountReview}=await import(pathToFileURL(process.argv[1]));
const payload=JSON.parse(process.argv[2]);
let exported;
function makeDOM(){
 const elements=new Map();
 class Element {
  constructor(tag='div'){this.tag=tag;this.value='';this.checked=false;this.listeners={};this.children=[];}
  addEventListener(name,fn){this.listeners[name]=fn;}
  replaceChildren(){this.children=[];}
  append(child){this.children.push(child);if(this.tag==='select'&&this.children.length===1)this.value=child.value;}
  setAttribute(){} focus(){} click(){this.listeners.click?.();}
 }
 const radios=['pass','fail','uncertain'].map(value=>Object.assign(new Element('input'),{value}));
 globalThis.document={getElementById(id){if(!elements.has(id))elements.set(id,new Element(['criterion','partition','filter'].includes(id)?'select':'div'));return elements.get(id);},
  querySelectorAll(){return radios;},querySelector(){return radios.find(x=>x.checked);},
  createElement(tag){return new Element(tag);},addEventListener(){}};
 globalThis.window={addEventListener(){},confirm(){return true;}};
 globalThis.URL.createObjectURL=(blob)=>{exported=blob;return 'blob:fixture';};
 globalThis.URL.revokeObjectURL=()=>{};globalThis.setTimeout=(fn)=>fn();
 document.getElementById('filter').value='all';
 return {el:id=>document.getElementById(id),radios};
}
let dom=makeDOM();mountReview(payload);
for(const verdict of ['pass','fail']){
 dom.radios.forEach(x=>x.checked=x.value===verdict);
 dom.el('rationale').value='Observed '+verdict+' evidence';
 dom.el('failure-modes').value=verdict==='fail'?'consent':'';
 dom.el('rationale').listeners.input();
 if(verdict==='pass')dom.el('next').listeners.click();
}
dom.el('reviewer').value='test-operator';dom.el('reviewer').listeners.input();
dom.el('export').listeners.click();
const first=JSON.parse(await exported.text());
dom=makeDOM();mountReview(payload);
const serialized=JSON.stringify(first);
await dom.el('import').listeners.change({target:{files:[{size:serialized.length,text:async()=>serialized}],value:'draft.json'}});
dom.el('export').listeners.click();
const second=JSON.parse(await exported.text());
process.stdout.write(JSON.stringify({first,second}));
'''

    def test_actual_js_export_restore_and_cli_import_agree_on_both_draft_schemas(self):
        import shutil
        import subprocess
        from codex_eval_lab.cli import dispatch, parser
        from codex_eval_lab.review_ui import review_payload
        from codex_eval_lab.util import read_json
        node = shutil.which("node")
        if node is None:
            self.skipTest("Optional JavaScript runtime unavailable for UI behavior test")
        source = Path(__file__).resolve().parents[1] / "plugin-ui/src/review.js"
        packet, _, rubric, _ = reviewed_fixture(validation_pairs=1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); write_json(root / "packet.json", packet); write_json(root / "rubric.json", rubric)
            for kind, selected_rubric in (("annotate", None), ("label", rubric)):
                payload = review_payload(packet, selected_rubric)
                result = subprocess.run([node, "--input-type=module", "-e", self.DOM_HARNESS,
                                         str(source), json.dumps(payload)], check=True,
                                        text=True, capture_output=True, timeout=10)
                drafts = json.loads(result.stdout)
                self.assertEqual(drafts["first"], drafts["second"])
                draft = drafts["second"]
                self.assertEqual(draft["kind"], "annotation_draft" if kind == "annotate" else "criterion_labels_draft")
                path = root / (kind + "-draft.json"); write_json(path, draft)
                out = root / (kind + "-sealed.json")
                args = ["review", kind, "--packet", str(root / "packet.json"),
                        "--reviewer", "test-operator", "--confirm-human-review", "--out", str(out)]
                if kind == "annotate": args += ["--annotations", str(path)]
                else: args += ["--rubric", str(root / "rubric.json"), "--labels", str(path)]
                result = dispatch(parser().parse_args(args))
                self.assertEqual(result["artifact"], str(out))
                sealed = read_json(out)
                if kind == "annotate": review.validate_review(packet, sealed)
                else: review.validate_labels(packet, rubric, sealed)

    def test_calibration_review_recomputes_disagreement_and_binds_visible_trace(self):
        from codex_eval_lab.review_ui import render_calibration_review
        packet, _, rubric, labels, config, outputs, policy = calibration_fixture()
        target = next(row for row in outputs["rows"] if row["trace_id"] == "private-fail-0")
        target["status"] = "pass"
        target["reason"] = '</script><img src="https://attacker.invalid/x">PRIVATE-REASON'
        outputs = review.seal(outputs)
        html = render_calibration_review(packet, rubric, labels, config, outputs, policy)
        # Private content is intentional only for this human-only explicit export.
        self.assertIn("private-fail-0", html)
        self.assertIn("missed_failure", html)
        self.assertIn("PRIVATE-REASON", html)
        self.assertNotIn(target["reason"], html)
        self.assertIn("\\u003c/script\\u003e", html)
        stale = copy.deepcopy(config); stale["prompt"] = "Changed after predictions"
        with self.assertRaises(LabError):
            render_calibration_review(packet, rubric, labels, stale, outputs, policy)


    def test_drift_cli_recomputes_from_original_raw_artifacts(self):
        from codex_eval_lab.calibration import create_judge_outputs
        from codex_eval_lab.cli import dispatch, parser
        from codex_eval_lab.util import read_json
        packet, _, rubric, labels, config, outputs, policy = calibration_fixture()
        new_config = copy.deepcopy(config); new_config["prompt"] = "A changed judge prompt"
        rows = copy.deepcopy(outputs["rows"])
        next(row for row in rows if row["trace_id"] == "private-fail-0")["status"] = "pass"
        new_outputs = create_judge_outputs(packet, rubric, new_config, rows)
        data = {"packet": packet, "rubric": rubric, "labels": labels, "old-config": config,
                "old-outputs": outputs, "new-config": new_config, "new-outputs": new_outputs, "policy": policy}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); args = ["calibration-drift"]
            for name, value in data.items():
                path = root / (name + ".json"); write_json(path, value)
                args += ["--" + name, str(path)]
            out = root / "drift.json"; args += ["--out", str(out)]
            result = dispatch(parser().parse_args(args))
            self.assertEqual(result["artifact"], str(out))
            drift = read_json(out)
            self.assertEqual(drift["validation_rate_deltas"]["consent"]["failure_recall"], -0.25)
            self.assertEqual(drift["changed_rows"][0]["trace_id"], "private-fail-0")


class AdversarialPluginStartupRaceTests(unittest.TestCase):
    def test_leaf_symlink_swap_after_scope_validation_is_rejected(self):
        import codex_eval_lab.plugin_server as server
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); allowed = root / "allowed"; allowed.mkdir()
            packet, _, _, _ = reviewed_fixture()
            selected = allowed / "packet.json"; write_json(selected, packet)
            private = root / "private.packet.json"; write_json(private, packet)
            ordinary = server._ordinary_file
            swapped = False
            def swap_after_validation(path, *, root=None):
                nonlocal swapped
                checked = ordinary(path, root=root)
                if not swapped:
                    swapped = True
                    selected.unlink(); selected.symlink_to(private)
                return checked
            with patch.object(server, "_ordinary_file", side_effect=swap_after_validation):
                with self.assertRaises((LabError, OSError)):
                    server.PacketStore(allowed)
