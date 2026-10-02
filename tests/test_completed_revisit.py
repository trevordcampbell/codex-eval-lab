"""Completed revisits keep fresh boundaries and the original fallback semantics."""
import contextlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab import engine, oracle, proposal_receipts
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError, canonical, read_json, write_json
from .helpers import start_fixture
from .test_automation import APPROVALS, configure_oracle


class CompletedRevisitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        _, _, self.state = start_fixture(self.root, cases_per_split=3, repetitions=2)
        self.first = engine.run(self.state, "baseline", "train")

    def test_success_keeps_exact_exports_summary_accounting_and_fresh_checks(self):
        for split in ("train", "validation"):
            with self.subTest(split=split):
                first = self.first if split == "train" else engine.run(self.state, "baseline", split)
                directory = self.state / "runs/baseline"
                exported = (directory / f"{split}.jsonl").read_bytes()
                summary = (directory / f"{split}-summary.json").read_bytes()
                (directory / f"{split}.jsonl").write_text("stale derived export")
                with patch.object(engine, "manifest_for", wraps=engine.manifest_for) as manifest, \
                        patch.object(engine, "check_source", wraps=engine.check_source) as source, \
                        patch.object(Store, "reserve", side_effect=AssertionError("No reservation")), \
                        patch.object(engine, "perform_trial", side_effect=AssertionError("No execution")):
                    second = engine.run(self.state, "baseline", split)
                self.assertEqual(second, first)
                self.assertEqual(manifest.call_count, 3)  # public entry, internal entry, exit
                self.assertEqual([c.kwargs.get("check_time", False) for c in manifest.call_args_list],
                                 [True, True, False])
                self.assertEqual(source.call_count, 3)
                self.assertEqual((directory / f"{split}.jsonl").read_bytes(), exported)
                self.assertEqual((directory / f"{split}-summary.json").read_bytes(), summary)
                with Store(self.state / "state.sqlite3") as store:
                    self.assertEqual(store.budget(), first["budget"])
                    event = store.db.execute("SELECT data FROM events WHERE kind='run_completed' ORDER BY id DESC LIMIT 1").fetchone()
                    self.assertEqual(json.loads(event[0]), first)

    def mutate_ledger(self, state, kind):
        with Store(state / "state.sqlite3") as store:
            key = ("baseline", "train", "train-0", 0)
            where = "label=? AND split=? AND case_id=? AND rep=?"
            raw = store.db.execute(f"SELECT result FROM trials WHERE {where}", key).fetchone()[0]
            result = json.loads(raw)
            if kind == "missing_ledger":
                store.db.execute(f"DELETE FROM trials WHERE {where}", key)
            elif kind in ("pending", "failed_ledger", "indeterminate_ledger"):
                status = {"failed_ledger": "error", "indeterminate_ledger": "indeterminate"}.get(kind, kind)
                store.db.execute(f"UPDATE trials SET status=? WHERE {where}", (status, *key))
            elif kind == "null_result":
                store.db.execute(f"UPDATE trials SET result=NULL WHERE {where}", key)
            elif kind in ("changed_charge", "changed_reserve"):
                column = "charged" if kind == "changed_charge" else "reserved"
                store.db.execute(f"UPDATE trials SET {column}={column}+0.125 WHERE {where}", key)
            elif kind.startswith("extra_"):
                store.db.execute("INSERT INTO trials SELECT label,split,'extra',rep,?,reserved,charged,?,started,finished FROM trials WHERE " + where,
                                 ("pending" if kind == "extra_null_pending" else "ok",
                                  None if "null" in kind else raw, *key))
            elif kind == "swapped_result_keys":
                other = ("baseline", "train", "train-1", 0)
                other_raw = store.db.execute(f"SELECT result FROM trials WHERE {where}", other).fetchone()[0]
                store.db.execute(f"UPDATE trials SET result=? WHERE {where}", (other_raw, *key))
                store.db.execute(f"UPDATE trials SET result=? WHERE {where}", (raw, *other))
            else:
                if kind in ("failed_result", "indeterminate_result"):
                    result["status"] = "error" if kind == "failed_result" else "indeterminate"
                elif kind == "missing_result_key":
                    del result["case_id"]
                elif kind == "duplicate_result_key":
                    result["case_id"] = "train-1"
                elif kind == "extra_result_key":
                    result["case_id"] = "extra"
                elif kind == "wrong_rep":
                    result["rep"] = 99
                elif kind == "missing_seed":
                    del result["seed"]
                elif kind == "wrong_seed":
                    result["seed"] = -1
                elif kind == "boolean_seed":
                    result["seed"] = True
                elif kind == "out_of_range_metric":
                    result["metrics"]["quality"] = 2
                elif kind == "valid_metric":
                    result["metrics"]["quality"] = 0.5
                elif kind == "missing_metric":
                    del result["metrics"]["quality"]
                elif kind == "malformed_metric":
                    result["metrics"]["quality"] = True
                elif kind == "nonobject_result":
                    result = []
                raw = "{" if kind == "invalid_json" else canonical(result)
                if kind == "result_whitespace":
                    raw = " " + raw
                store.db.execute(f"UPDATE trials SET result=? WHERE {where}", (raw, *key))
            store.db.commit()

    def outcome(self, state, *, force_legacy=False):
        qualification = patch.object(engine, "_completed_matrix", return_value=False) if force_legacy else \
            patch.object(engine, "_completed_matrix", wraps=engine._completed_matrix)
        with qualification, patch.object(engine, "manifest_for", wraps=engine.manifest_for) as checked:
            try:
                result = ("returned", engine.run(state, "baseline", "train"))
            except (LabError, ValueError, KeyError, TypeError) as error:
                result = (type(error).__name__, str(error))
        with Store(state / "state.sqlite3") as store:
            ledger = [tuple(r) for r in store.db.execute("SELECT case_id,rep,status,charged FROM trials ORDER BY case_id,rep")]
            budget = store.budget()
        exported = state / "runs/baseline/train.jsonl"
        return result, checked.call_count, ledger, budget, exported.read_bytes()

    def test_nonqualifying_states_match_unchanged_loop_including_legacy_quirks(self):
        kinds = ("missing_ledger", "pending", "failed_ledger", "indeterminate_ledger", "null_result",
                 "extra_result", "extra_null", "extra_null_pending", "swapped_result_keys",
                 "failed_result", "indeterminate_result", "missing_result_key", "duplicate_result_key",
                 "extra_result_key", "wrong_rep", "missing_metric", "malformed_metric",
                 "nonobject_result", "invalid_json")
        for kind in kinds:
            with self.subTest(kind=kind):
                changed, legacy = self.root / kind, self.root / (kind + "-legacy")
                shutil.copytree(self.state, changed)
                self.mutate_ledger(changed, kind)
                shutil.copytree(changed, legacy)
                with Store(changed / "state.sqlite3") as store:
                    manifest = read_json(changed / "manifest.json")
                    jobs = [(id_, rep) for id_ in manifest["splits"]["train"] for rep in range(2)]
                    self.assertFalse(engine._completed_matrix(store, "baseline", "train", jobs, manifest["config"]["metrics"]))
                actual = self.outcome(changed)
                original = self.outcome(legacy, force_legacy=True)
                # Executed missing rows contain fresh timestamps/artifact IDs; all
                # other cases must preserve even the exact derived export bytes.
                self.assertEqual(actual[:4], original[:4])
                if kind != "missing_ledger":
                    self.assertEqual(actual[4], original[4])

    def test_revisit_preserves_existing_seed_and_metric_validation_semantics(self):
        # run_internal historically checks matrix keys/status and finite metric
        # means, not seed correctness or configured bounds on saved rows. Those
        # concerns must not be silently repaired by a revisit optimization.
        for kind in ("missing_seed", "wrong_seed", "boolean_seed", "out_of_range_metric"):
            with self.subTest(kind=kind):
                changed, legacy = self.root / kind, self.root / (kind + "-legacy")
                shutil.copytree(self.state, changed)
                self.mutate_ledger(changed, kind)
                shutil.copytree(changed, legacy)
                actual = self.outcome(changed)
                original = self.outcome(legacy, force_legacy=True)
                self.assertEqual(actual[0][0], "returned")
                self.assertEqual(actual[0], original[0])
                self.assertEqual(actual[2:], original[2:])
                self.assertEqual(actual[1], 3)
                self.assertEqual(original[1], 8)

    def test_eligibility_is_rechecked_after_entry_manifest_and_source_validation(self):
        still_eligible = ("valid_metric", "wrong_seed", "changed_charge", "changed_reserve", "result_whitespace")
        kinds = ("pending", "failed_ledger", "indeterminate_ledger", "null_result", "missing_ledger",
                 "extra_result", "extra_null", "extra_null_pending", "swapped_result_keys",
                 "wrong_rep", "malformed_metric") + still_eligible

        def during_verification(state, kind, hook, *, force_legacy=False):
            with Store(state / "state.sqlite3") as store:
                manifest = engine.manifest_for(state, store)
                original = getattr(engine, hook)
                calls = 0
                def validate_then_mutate(*args, **kwargs):
                    nonlocal calls
                    result = original(*args, **kwargs)
                    calls += 1
                    # check_source also runs once before initial qualification.
                    if calls == (2 if hook == "check_source" else 1):
                        self.mutate_ledger(state, kind)
                    return result
                qualifier = patch.object(engine, "_completed_matrix", return_value=False) if force_legacy else \
                    patch.object(engine, "_completed_matrix", wraps=engine._completed_matrix)
                with patch.object(engine, hook, side_effect=validate_then_mutate), qualifier, \
                        patch.object(store, "reserve", wraps=store.reserve) as reserved:
                    try:
                        result = ("returned", engine.run_internal(state, store, manifest, "baseline", "train"))
                    except (LabError, ValueError, KeyError, TypeError) as error:
                        result = (type(error).__name__, str(error))
                return (result, reserved.call_count, store.budget(),
                        (state / "runs/baseline/train.jsonl").read_bytes())

        for hook in ("manifest_for", "check_source"):
            for kind in kinds:
                with self.subTest(hook=hook, kind=kind):
                    changed = self.root / (hook + "-" + kind)
                    legacy = self.root / (hook + "-" + kind + "-legacy")
                    shutil.copytree(self.state, changed)
                    shutil.copytree(self.state, legacy)
                    actual = during_verification(changed, kind, hook)
                    original = during_verification(legacy, kind, hook, force_legacy=True)
                    if kind in still_eligible:
                        # Accept a freshly qualified entry snapshot, not the
                        # preliminary identity from before verification.
                        self.assertEqual(actual[1], 0)
                        self.assertEqual(actual[0], original[0])
                        self.assertEqual(actual[2], original[2])
                    else:
                        self.assertGreater(actual[1], 0)  # Return to reservation handling.
                        self.assertEqual(actual[:3], original[:3])
                    if kind != "missing_ledger":
                        self.assertEqual(actual[3], original[3])

    def test_accepted_revisit_rejects_any_ledger_change_during_exit_verification(self):
        kinds = ("pending", "failed_ledger", "indeterminate_ledger", "null_result", "missing_ledger",
                 "extra_null", "swapped_result_keys", "wrong_rep", "valid_metric", "wrong_seed",
                 "missing_seed", "changed_charge", "changed_reserve", "result_whitespace")
        for hook in ("manifest_for", "check_source"):
            for kind in kinds:
                with self.subTest(hook=hook, kind=kind):
                    state = self.root / ("exit-" + hook + "-" + kind)
                    shutil.copytree(self.state, state)
                    with Store(state / "state.sqlite3") as store:
                        manifest = engine.manifest_for(state, store)
                        summary = (state / "runs/baseline/train-summary.json").read_bytes()
                        events = store.db.execute("SELECT COUNT(*) FROM events WHERE kind='run_completed'").fetchone()[0]
                        original = getattr(engine, hook)
                        calls = 0
                        def validate_then_mutate(*args, **kwargs):
                            nonlocal calls
                            result = original(*args, **kwargs)
                            calls += 1
                            if calls == (3 if hook == "check_source" else 2):
                                self.mutate_ledger(state, kind)
                            return result
                        with patch.object(engine, hook, side_effect=validate_then_mutate), \
                                patch.object(store, "reserve", side_effect=AssertionError("No reservation")), \
                                patch.object(engine, "perform_trial", side_effect=AssertionError("No execution")):
                            with self.assertRaisesRegex(LabError, "Completed trial ledger changed"):
                                engine.run_internal(state, store, manifest, "baseline", "train")
                        self.assertEqual((state / "runs/baseline/train-summary.json").read_bytes(), summary)
                        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM events WHERE kind='run_completed'").fetchone()[0], events)

    def test_completed_test_matrix_never_uses_shortcut(self):
        with Store(self.state / "state.sqlite3") as store:
            manifest = engine.manifest_for(self.state, store)
            engine.run_internal(self.state, store, manifest, "baseline", "test", allow_test=True)
            with patch.object(engine, "_completed_matrix", side_effect=AssertionError("No final shortcut")), \
                    patch.object(engine, "manifest_for", wraps=engine.manifest_for) as checked, \
                    patch.object(store, "reserve", wraps=store.reserve) as reserved, \
                    patch.object(engine, "perform_trial", side_effect=AssertionError("No replay")):
                engine.run_internal(self.state, store, manifest, "baseline", "test", allow_test=True)
            self.assertEqual(checked.call_count, 7)
            self.assertEqual(reserved.call_count, 6)

    def test_expired_complete_matrix_still_rejected_and_internal_export_rebuilt(self):
        with Store(self.state / "state.sqlite3") as store:
            manifest = engine.manifest_for(self.state, store)
            budget = store.budget()
            path = self.state / "runs/baseline/train.jsonl"
            before = path.read_bytes()
            path.write_text("stale export")
            with patch.object(engine.time, "time", return_value=manifest["expires_at"]), \
                    patch.object(engine, "perform_trial", side_effect=AssertionError("No execution")):
                with self.assertRaisesRegex(LabError, "expired"):
                    engine.run_internal(self.state, store, manifest, "baseline", "train")
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(store.budget(), budget)

    def test_actual_execution_retains_every_reservation_and_validation_boundary(self):
        with Store(self.state / "state.sqlite3") as store:
            manifest = engine.manifest_for(self.state, store)
            with patch.object(engine, "manifest_for", wraps=engine.manifest_for) as checked, \
                    patch.object(engine, "check_source", wraps=engine.check_source) as source, \
                    patch.object(store, "reserve", wraps=store.reserve) as reserved, \
                    patch.object(engine, "perform_trial", wraps=engine.perform_trial) as executed:
                engine.run_internal(self.state, store, manifest, "baseline", "validation")
            self.assertEqual(checked.call_count, 7)
            self.assertEqual(source.call_count, 8)
            self.assertEqual(reserved.call_count, 6)
            self.assertEqual(executed.call_count, 6)

    def test_expiry_during_export_keeps_existing_no_execution_exit_semantics(self):
        with Store(self.state / "state.sqlite3") as store:
            manifest = engine.manifest_for(self.state, store)
            original = engine.atomic_text
            clock = manifest["expires_at"] - 1
            def export_then_expire(path, text):
                nonlocal clock
                original(path, text)
                clock = manifest["expires_at"]
            with patch.object(engine, "atomic_text", side_effect=export_then_expire), \
                    patch.object(engine.time, "time", side_effect=lambda: clock):
                self.assertEqual(engine.run_internal(self.state, store, manifest, "baseline", "train"), self.first)


class RevisitIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self, root, kind):
        root.mkdir()
        if kind in ("oracle_receipt", "dependency"):
            suite, app, state = configure_oracle(root)
            if kind == "dependency":
                launcher = root / "launcher"
                launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n#A\n')
                launcher.chmod(0o755)
                config = suite / "eval.toml"
                config.write_text(config.read_text().replace('grader_command = ["{python}",',
                                                             'grader_command = [' + json.dumps(str(launcher)) + ','))
                contract = read_json(suite / "oracle.json")
                contract["reference_command"][0] = str(launcher)
                write_json(suite / "oracle.json", contract)
            engine.initialize(suite, app, state, approvals=APPROVALS)
        else:
            _, _, state = start_fixture(root, cases_per_split=2)
        engine.run(state, "baseline", "train")
        targets = {"source": state / "candidates/baseline/app.py",
                   "evaluator": state / "evaluator/grader.py", "manifest": state / "manifest.json",
                   "oracle_receipt": state / "oracle-receipt.json", "dependency": root / "launcher"}
        if kind in ("proposal_prompt", "proposal_response", "native_prompt"):
            directory = state / "optimizer-runs/call-0001/evidence"
            with Store(state / "state.sqlite3") as store:
                receipt = proposal_receipts.prepare_dispatch(directory, source=state / "candidates/baseline",
                    source_label="baseline", source_hash=store.variant("baseline")["source_hash"],
                    feedback=engine.feedback(state, "baseline"), prompt="original prompt",
                    response_contract={"type": "object"}, invocation_context={"backend": "native"})
                receipt = proposal_receipts.capture_response(directory, b"original response",
                    expected_digest=receipt["dispatch_digest"], source=state / "candidates/baseline")
                if kind == "native_prompt":
                    store.put("native_turn:1", {"receipt": receipt, "evidence_relative": directory.relative_to(state).as_posix()})
                else:
                    store.put("proposal_receipt:1", receipt)
            targets[kind] = directory / ("response.json" if kind == "proposal_response" else "prompt.txt")
        return state, targets.get(kind)

    def change_same_size_and_restore_mtime(self, path):
        before = path.stat()
        data = path.read_bytes()
        # Change ordinary text while keeping valid JSON for receipts/manifest.
        index = next(i for i, byte in enumerate(data) if 97 <= byte <= 122)
        replacement = b"z" if data[index] != 122 else b"y"
        path.write_bytes(data[:index] + replacement + data[index + 1:])
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(path.stat().st_size, before.st_size)
        self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)

    def test_entry_and_exit_rehash_same_size_restored_mtime_mutations(self):
        kinds = ("source", "evaluator", "manifest", "runtime", "oracle_receipt", "dependency",
                 "proposal_prompt", "proposal_response", "native_prompt")
        for kind in kinds:
            for boundary in ("entry", "exit"):
                with self.subTest(kind=kind, boundary=boundary), contextlib.ExitStack() as stack:
                    root = self.root / (kind + "-" + boundary)
                    if kind == "runtime":
                        runtime = self.root / ("runtime-files-" + boundary)
                        runtime.mkdir()
                        target = runtime / "probe.py"
                        target.write_text("original runtime bytes\n")
                        stack.enter_context(patch.object(engine, "__file__", str(target)))
                    state, path = self.fixture(root, kind)
                    path = target if kind == "runtime" else path
                    with Store(state / "state.sqlite3") as store:
                        manifest = engine.manifest_for(state, store)
                        budget = store.budget()
                        if boundary == "entry":
                            self.change_same_size_and_restore_mtime(path)
                        else:
                            original = engine.atomic_text
                            def export_then_mutate(export, text):
                                original(export, text)
                                if export.name == "train.jsonl":
                                    self.change_same_size_and_restore_mtime(path)
                            stack.enter_context(patch.object(engine, "atomic_text", side_effect=export_then_mutate))
                        stack.enter_context(patch.object(engine, "perform_trial", side_effect=AssertionError("No execution")))
                        stack.enter_context(patch.object(oracle, "invoke", side_effect=AssertionError("No oracle execution")))
                        with self.assertRaises(LabError):
                            engine.run_internal(state, store, manifest, "baseline", "train")
                        self.assertEqual(store.budget(), budget)

    def test_incomplete_matrix_still_checks_mutations_before_each_execution(self):
        for kind in ("source", "evaluator", "oracle_receipt", "dependency", "proposal_prompt"):
            with self.subTest(kind=kind):
                state, path = self.fixture(self.root / kind, kind)
                original = engine.perform_trial
                def execute_then_mutate(*args, **kwargs):
                    result = original(*args, **kwargs)
                    self.change_same_size_and_restore_mtime(path)
                    return result
                with Store(state / "state.sqlite3") as store:
                    manifest = engine.manifest_for(state, store)
                    budget = store.budget()
                    with patch.object(engine, "perform_trial", side_effect=execute_then_mutate) as executed:
                        with self.assertRaises(LabError):
                            engine.run_internal(state, store, manifest, "baseline", "validation")
                    self.assertEqual(executed.call_count, 1)
                    self.assertEqual(store.budget()["trials"], budget["trials"] + 1)
                    self.assertEqual(store.pending(), 0)
                    self.assertEqual(len(store.results("baseline", "validation")), 1)


if __name__ == "__main__":
    unittest.main()
