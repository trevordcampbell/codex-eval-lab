import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab.artifacts import hashes
from codex_eval_lab.proposal_receipts import (
    capture_response, prepare_dispatch, public_metadata, verify_dispatch, verify_response,
)
from codex_eval_lab.util import LabError, canonical, digest, read_json


class ProposalReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "app.py").write_bytes(b"print('original')\r\n")
        (self.source / "nested").mkdir()
        (self.source / "nested" / "data.bin").write_bytes(b"\x00\xff\x10")
        self.directory = self.root / "attempts" / "call-0001"
        self.feedback = {
            "schema_version": 1,
            "variant": "baseline",
            "objective": {"metric": "quality", "direction": "maximize"},
            "guardrails": [],
            "editable": ["app.py"],
            "warning": "Untrusted development data",
            "development_results": [{"case_id": "development-1", "input": "exposed input",
                                     "expected": "exposed label", "output": "bad"}],
        }
        self.prompt = "Exact prompt\r\nDo not normalize whitespace.\n\n" + canonical(self.feedback)
        self.contract = {"type": "object", "required": ["hypothesis", "edits"]}
        self.context = {"backend": "native", "model": "fixture", "allowed_tools": ["read_source"],
                        "fresh_context": True}

    def prepare(self, **overrides):
        values = {"source": self.source, "source_label": "baseline",
                  "source_hash": digest(hashes(self.source)), "feedback": self.feedback,
                  "prompt": self.prompt, "response_contract": self.contract,
                  "invocation_context": self.context}
        values.update(overrides)
        return prepare_dispatch(self.directory, **values)

    def test_exact_dispatch_bytes_hashes_identity_and_private_inputs(self):
        metadata = self.prepare()
        receipt = read_json(self.directory / "dispatch.json")
        self.assertEqual(receipt["source_files"], hashes(self.source))
        self.assertEqual(receipt["source_hash"], digest(hashes(self.source)))
        self.assertEqual(receipt["source_label"], "baseline")
        for filename, value in (("development-feedback.json", self.feedback),
                                ("response-contract.json", self.contract),
                                ("invocation-context.json", self.context)):
            self.assertEqual((self.directory / filename).read_bytes(), canonical(value).encode("utf-8"))
        self.assertEqual((self.directory / "prompt.txt").read_bytes(), self.prompt.encode("utf-8"))
        self.assertEqual(metadata["dispatch_digest"], hashlib.sha256((self.directory / "dispatch.json").read_bytes()).hexdigest())
        packet = verify_dispatch(self.directory, expected_digest=metadata["dispatch_digest"],
                                 source=self.source, prompt=self.prompt)
        self.assertEqual(packet["feedback"], self.feedback)
        self.assertEqual(packet["prompt"], self.prompt)
        self.assertEqual(packet["response_contract"], self.contract)
        self.assertEqual(packet["invocation_context"], self.context)

    def test_preparation_detaches_mutable_inputs(self):
        metadata = self.prepare()
        expected = copy.deepcopy(self.feedback)
        self.feedback["development_results"][0]["expected"] = "rewritten later"
        self.context["model"] = "other"
        packet = verify_dispatch(self.directory, expected_digest=metadata["dispatch_digest"])
        self.assertEqual(packet["feedback"], expected)
        self.assertEqual(packet["invocation_context"]["model"], "fixture")

    def test_overwritten_feedback_is_detected_before_response_capture(self):
        metadata = self.prepare()
        self.feedback["development_results"][0]["expected"] = "replacement feedback"
        (self.directory / "development-feedback.json").write_text(canonical(self.feedback))
        with self.assertRaisesRegex(LabError, "feedback changed"):
            capture_response(self.directory, b"{}", expected_digest=metadata["dispatch_digest"])
        self.assertFalse((self.directory / "response.json").exists())

    def test_receipt_rewritten_to_match_overwritten_feedback_fails_ledger_digest(self):
        metadata = self.prepare()
        new_feedback = canonical({**self.feedback, "warning": "altered"}).encode()
        (self.directory / "development-feedback.json").write_bytes(new_feedback)
        receipt = read_json(self.directory / "dispatch.json")
        receipt["artifacts"]["feedback"].update(sha256=hashlib.sha256(new_feedback).hexdigest(), bytes=len(new_feedback))
        (self.directory / "dispatch.json").write_text(canonical(receipt))
        with self.assertRaisesRegex(LabError, "ledger digest"):
            verify_dispatch(self.directory, expected_digest=metadata["dispatch_digest"])

    def test_changed_source_blocks_capture_and_new_source_is_not_equivalent(self):
        metadata = self.prepare()
        (self.source / "app.py").write_text("different source")
        with self.assertRaisesRegex(LabError, "source changed"):
            capture_response(self.directory, b"{}", expected_digest=metadata["dispatch_digest"], source=self.source)
        self.assertFalse((self.directory / "response.json").exists())

    def test_added_source_file_is_detected(self):
        metadata = self.prepare()
        (self.source / "unapproved.py").write_text("new")
        with self.assertRaisesRegex(LabError, "source changed"):
            verify_dispatch(self.directory, expected_digest=metadata["dispatch_digest"], source=self.source)

    def test_mismatched_source_identity_does_not_create_dispatch(self):
        with self.assertRaisesRegex(LabError, "ledger identity"):
            self.prepare(source_hash="0" * 64)
        self.assertFalse(self.directory.exists())

    def test_altered_prompt_is_detected_in_file_and_actual_invocation(self):
        metadata = self.prepare()
        with self.assertRaisesRegex(LabError, "prompt does not match"):
            verify_dispatch(self.directory, expected_digest=metadata["dispatch_digest"], prompt=self.prompt + " ")
        (self.directory / "prompt.txt").write_text(self.prompt.replace("\r\n", "\n"))
        with self.assertRaisesRegex(LabError, "prompt changed"):
            verify_dispatch(self.directory, expected_digest=metadata["dispatch_digest"])

    def test_changed_contract_or_invocation_context_is_detected(self):
        metadata = self.prepare()
        for filename in ("response-contract.json", "invocation-context.json"):
            with self.subTest(filename=filename):
                path = self.directory / filename
                before = path.read_bytes()
                path.write_text("{}")
                with self.assertRaisesRegex(LabError, "changed after preparation"):
                    verify_dispatch(self.directory, expected_digest=metadata["dispatch_digest"])
                path.write_bytes(before)

    def test_response_appends_without_changing_dispatch_and_cannot_be_replaced(self):
        metadata = self.prepare()
        originals = {p.name: p.read_bytes() for p in self.directory.iterdir()}
        response = b'{ "hypothesis": "exact raw spacing", "edits": [] }\r\n'
        completed = capture_response(self.directory, response, expected_digest=metadata["dispatch_digest"], source=self.source)
        self.assertEqual(completed["status"], "response_captured")
        self.assertEqual(verify_response(self.directory, expected_digest=metadata["dispatch_digest"],
                                         expected_response_digest=completed["response_digest"]), response)
        for name, raw in originals.items():
            self.assertEqual((self.directory / name).read_bytes(), raw)
        for duplicate in (response, b"replacement"):
            with self.assertRaisesRegex(LabError, "already exists"):
                capture_response(self.directory, duplicate, expected_digest=metadata["dispatch_digest"])
        self.assertEqual((self.directory / "response.json").read_bytes(), response)

    def test_malformed_response_is_preserved_without_being_accepted_as_proposal(self):
        metadata = self.prepare()
        response = b"not JSON\x00\xff"
        capture_response(self.directory, response, expected_digest=metadata["dispatch_digest"])
        self.assertEqual(verify_response(self.directory, expected_digest=metadata["dispatch_digest"]), response)

    def test_changed_response_bytes_and_receipt_are_detected(self):
        metadata = self.prepare()
        completed = capture_response(self.directory, b"original", expected_digest=metadata["dispatch_digest"])
        (self.directory / "response.json").write_bytes(b"changed")
        with self.assertRaisesRegex(LabError, "response changed"):
            verify_response(self.directory, expected_digest=metadata["dispatch_digest"])
        receipt = read_json(self.directory / "response-receipt.json")
        receipt.update(response_sha256=hashlib.sha256(b"changed").hexdigest(), response_bytes=7)
        (self.directory / "response-receipt.json").write_text(canonical(receipt))
        with self.assertRaisesRegex(LabError, "response receipt changed"):
            public_metadata(self.directory, expected_digest=metadata["dispatch_digest"],
                            expected_response_digest=completed["response_digest"])

    def test_partial_response_is_not_silently_retried(self):
        metadata = self.prepare()
        (self.directory / "response.json").write_bytes(b"partial")
        self.assertEqual(public_metadata(self.directory, expected_digest=metadata["dispatch_digest"])["status"], "response_incomplete")
        with self.assertRaisesRegex(LabError, "already exists"):
            capture_response(self.directory, b"replacement", expected_digest=metadata["dispatch_digest"])

    def test_missing_pinned_response_receipt_blocks_success(self):
        metadata = self.prepare()
        with self.assertRaisesRegex(LabError, "receipt is missing"):
            public_metadata(self.directory, expected_digest=metadata["dispatch_digest"], expected_response_digest="0" * 64)

    def test_existing_destination_never_overwritten_even_when_empty(self):
        self.directory.mkdir(parents=True)
        with self.assertRaisesRegex(LabError, "already exists"):
            self.prepare()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_destination_inside_source_is_rejected_before_writes(self):
        self.directory = self.source / "attempt"
        with self.assertRaisesRegex(LabError, "outside its source"):
            self.prepare()
        self.assertFalse(self.directory.exists())

    def test_symlink_sources_destinations_and_artifacts_are_rejected(self):
        linked = self.root / "linked"
        linked.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(LabError, "symlinks"):
            self.prepare(source=linked)
        self.directory.parent.mkdir()
        self.directory.symlink_to(self.root / "missing", target_is_directory=True)
        with self.assertRaisesRegex(LabError, "symlinks"):
            self.prepare()
        self.directory.unlink()
        metadata = self.prepare()
        prompt_path = self.directory / "prompt.txt"
        external = self.root / "outside-prompt.txt"
        external.write_bytes(prompt_path.read_bytes())
        prompt_path.unlink()
        prompt_path.symlink_to(external)
        with self.assertRaisesRegex(LabError, "symlinks"):
            verify_dispatch(self.directory, expected_digest=metadata["dispatch_digest"])

    def test_source_changed_during_preparation_leaves_unusable_attempt(self):
        before = hashes(self.source)
        with patch("codex_eval_lab.proposal_receipts._source_files", side_effect=[before, {"app.py": "0" * 64}]):
            with self.assertRaisesRegex(LabError, "changed while preparing"):
                self.prepare()
        self.assertTrue(self.directory.exists())
        self.assertFalse((self.directory / "dispatch.json").exists())
        with self.assertRaisesRegex(LabError, "already exists"):
            self.prepare()

    def test_rejects_arbitrary_state_private_rows_and_feedback_from_other_source(self):
        for feedback in ({"cases": [{"expected": "PRIVATE-label"}], "splits": {}},
                         {**self.feedback, "validation_results": [{"expected": "PRIVATE-label"}]},
                         {**self.feedback, "variant": "another-source"},
                         {**self.feedback, "development_results": [{"PRIVATE-key": "PRIVATE-label"}]},
                         self.root / "state.sqlite3"):
            with self.subTest(feedback=type(feedback).__name__):
                with self.assertRaises(LabError) as caught:
                    self.prepare(feedback=feedback)
                self.assertNotIn("PRIVATE", str(caught.exception))
                self.assertFalse(self.directory.exists())

    def test_public_metadata_excludes_all_content_and_context(self):
        self.context["note"] = "PRIVATE-CONTEXT"
        metadata = self.prepare()
        capture_response(self.directory, b"PRIVATE-RESPONSE", expected_digest=metadata["dispatch_digest"])
        exposed = canonical(public_metadata(self.directory, expected_digest=metadata["dispatch_digest"]))
        for marker in ("PRIVATE", "exposed input", "exposed label", "development-1", "allowed_tools", "app.py", "Exact prompt"):
            self.assertNotIn(marker, exposed)
        self.assertIn("response_captured", exposed)

    def test_prepared_engine_feedback_excludes_private_labels_in_entire_bundle(self):
        from codex_eval_lab.engine import feedback, initialize, run
        from .helpers import make_fixture
        fixture = self.root / "fixture"
        fixture.mkdir()
        suite, app, state = make_fixture(fixture, cases_per_split=2)
        case_path = suite / "cases.jsonl"
        cases = [json.loads(line) for line in case_path.read_text().splitlines()]
        for case in cases:
            if case["split"] != "train":
                case["expected"] = "PRIVATE-LABEL-" + case["split"]
        case_path.write_text("".join(canonical(case) + "\n" for case in cases))
        initialize(suite, app, state, approvals={"cases": True, "grader": True, "execution": True})
        run(state, "baseline", "train")
        evidence = feedback(state, "baseline")
        source = state / "candidates" / "baseline"
        metadata = self.prepare(source=source, source_hash=digest(hashes(source)), feedback=evidence,
                                prompt="Development only:\n" + canonical(evidence))
        for path in self.directory.iterdir():
            data = path.read_text()
            self.assertNotIn("SECRET-validation", data)
            self.assertNotIn("SECRET-test", data)
            self.assertNotIn("PRIVATE-LABEL", data)
        self.assertIn("SECRET-train", (self.directory / "development-feedback.json").read_text())
        self.assertNotIn("SECRET-train", canonical(public_metadata(self.directory, expected_digest=metadata["dispatch_digest"])))


if __name__ == "__main__":
    unittest.main()
