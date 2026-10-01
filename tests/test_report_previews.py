"""Presentation-only bounds; synthetic records are not performance evidence."""
import copy
import io
import json
from contextlib import redirect_stdout
from html import unescape
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab import report
from codex_eval_lab.cli import main
from codex_eval_lab.engine import finalize, initialize, register, run, select
from codex_eval_lab.store import Store
from codex_eval_lab.util import digest
from .helpers import make_fixture


class PreviewTests(unittest.TestCase):
    def test_field_row_and_title_limits_with_large_nested_payloads(self):
        row = {"input": {"lines": ["x" * 100_000] * 100}, "output": "y" * 100_000,
               "trace": ["z" * 100_000], "expected": "e" * 100_000,
               "explanation": "reason" * 100_000, "artifact_dir": "trial-artifacts/example",
               "metrics": {"quality": 0.75}, "case_id": "case-1", "rep": 0, "status": "ok"}
        before = copy.deepcopy(row)
        text, cut = report._json_prefix(row["input"], report.TRACE_FIELD_CHARS)
        self.assertTrue(cut)
        self.assertEqual(len(text), report.TRACE_FIELD_CHARS)
        self.assertIn("truncated", text)
        body, cut = report._row_preview(row)
        self.assertTrue(cut)
        self.assertLessEqual(len(body), report.TRACE_ROW_CHARS)
        self.assertIn("trial-artifacts/example", body)
        self.assertIn('"quality": 0.75', body)
        previews = report._TracePreviews(False)
        previews.add("title" * 10_000, row)
        self.assertIn("Truncated preview", previews.details[0])
        summary = unescape(previews.details[0].split("<summary>")[1].split("<span")[0]).rstrip()
        self.assertLessEqual(len(summary), report.TRACE_TITLE_CHARS)
        self.assertEqual(row, before)

    def test_exact_boundary_is_not_falsely_marked_truncated(self):
        size = report.TRACE_FIELD_CHARS
        for length in (size - 3, size - 2, size - 1):
            value = "x" * length
            text, cut = report._json_prefix(value, size)
            self.assertEqual(cut, length + 2 > size)
            self.assertLessEqual(len(text), size)
        short = {"output": "ok", "metrics": {"quality": 1}}
        self.assertFalse(report._row_preview(short)[1])

    def test_json_preview_stops_before_traversing_long_arrays(self):
        # The object at the end would raise if the encoder traversed the full array.
        text, cut = report._json_prefix(["x" * report.TRACE_FIELD_CHARS, object()], report.TRACE_FIELD_CHARS)
        self.assertTrue(cut)
        self.assertEqual(len(text), report.TRACE_FIELD_CHARS)

    def test_total_budget_counts_escaped_utf8_and_markup(self):
        previews = report._TracePreviews(False)
        row = {"output": '<&"\U0001f9ea\u2028' * 10_000}
        for index in range(500):
            previews.add(f"row {index}", row)
        counts = previews.summary()
        self.assertEqual(counts["eligible_rows"], 500)
        self.assertGreater(counts["shown_rows"], 0)
        self.assertLess(counts["shown_rows"], report.TRACE_MAX_ROWS)
        self.assertGreater(counts["omitted_rows"], 0)
        self.assertLessEqual(counts["html_bytes"], report.TRACE_HTML_BYTES)
        self.assertEqual(counts["html_bytes"], len("".join(previews.details).encode("utf-8")))
        self.assertEqual(counts["truncated_rows"], counts["shown_rows"])
        self.assertEqual(counts["shown_rows"] + counts["omitted_rows"], 500)
        with patch.object(report, "_row_preview", side_effect=AssertionError("must not render omitted rows")):
            previews.add("omitted", row)

    def test_row_count_limit_and_explicit_omission(self):
        previews = report._TracePreviews(False)
        for index in range(report.TRACE_MAX_ROWS + 9):
            previews.add(f"row {index}", {"output": "ok"})
        counts = previews.summary()
        self.assertEqual(counts["shown_rows"], report.TRACE_MAX_ROWS)
        self.assertEqual(counts["omitted_rows"], 9)
        notice = previews.notice(Path("/private/state"))
        self.assertIn("9 rows omitted", notice)
        self.assertIn("not a representative sample", notice)
        self.assertIn("state.sqlite3", notice)
        self.assertIn("Search covers only displayed text", notice)

    def test_hostile_html_unicode_keys_paths_and_full_mode_are_inert(self):
        attack = '</pre></summary><script>alert("x")</script><img src="https://bad.invalid">'
        row = {attack: attack + "\U0001f9ea\ud800", "artifact_dir": attack}
        for full in (False, True):
            previews = report._TracePreviews(full)
            previews.add(attack + "\udfff", row)
            text = "".join(previews.details) + previews.notice(Path(attack))
            text.encode("utf-8")
            self.assertNotIn("<script>", text)
            self.assertNotIn("<img ", text)
            self.assertIn("&lt;script&gt;", text)
            self.assertIn("\\ud800", text)
            self.assertIn("\\udfff", text)

    def test_lone_surrogates_are_normalized_before_character_caps(self):
        value = "\ud800" * 50_000
        field, cut = report._json_prefix(value, report.TRACE_FIELD_CHARS)
        self.assertTrue(cut)
        self.assertEqual(len(field), report.TRACE_FIELD_CHARS)
        field.encode("utf-8")
        previews = report._TracePreviews(False)
        previews.add(value, {str(index): value for index in range(10)})
        detail = previews.details[0]
        title = unescape(detail.split("<summary>")[1].split("<span")[0]).rstrip()
        body = unescape(detail.split("<pre>")[1].split("</pre>")[0])
        self.assertLessEqual(len(title), report.TRACE_TITLE_CHARS)
        self.assertLessEqual(len(body), report.TRACE_ROW_CHARS)
        self.assertLessEqual(len(detail.encode("utf-8")), report.TRACE_HTML_BYTES)

    def test_full_traces_are_explicit_and_unbounded(self):
        row = {"output": "payload" * 10_000 + "TAIL_SENTINEL"}
        bounded, full = report._TracePreviews(False), report._TracePreviews(True)
        for previews in (bounded, full):
            for index in range(report.TRACE_MAX_ROWS + 1):
                previews.add(str(index), row)
        self.assertNotIn("TAIL_SENTINEL", "".join(bounded.details))
        self.assertIn("TAIL_SENTINEL", full.details[0])
        self.assertEqual(full.summary()["shown_rows"], report.TRACE_MAX_ROWS + 1)
        self.assertEqual(full.summary()["omitted_rows"], 0)
        self.assertEqual(full.summary()["truncated_rows"], 0)


class ReportIntegrationTests(unittest.TestCase):
    def fixture(self, paired=False):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        suite, self.app, self.state = make_fixture(self.root, cases_per_split=2, repetitions=2)
        if paired:
            config = suite / "eval.toml"
            config.write_text(config.read_text() + '\n[measurement]\ndesign = "paired_ab_ba"\n')
        initialize(suite, self.app, self.state, approvals={"cases": True, "grader": True, "execution": True})
        (self.app / "app.py").write_text("candidate fixture")
        register(self.state, self.app, "candidate", "Synthetic better candidate")
        self.payload = "large & payload \U0001f9ea" * 7_000 + "TAIL_SENTINEL"
        self.trials = patch("codex_eval_lab.engine.perform_trial", side_effect=self.trial)
        self.trials.start()
        self.addCleanup(self.trials.stop)

    def trial(self, state, manifest, source, case, rep, **kwargs):
        return {"case_id": case["id"], "group": case["group"], "rep": rep,
                "seed": int(digest({"seed": manifest["config"]["seed"], "id": case["id"], "rep": rep})[:8], 16),
                "status": "ok", "metrics": {"quality": float(source.name == "candidate"), "cost_usd": 0},
                "charged_usd": 0, "input": case["input"], "expected": case["expected"],
                "artifact_dir": "trial-artifacts/synthetic", "output": self.payload,
                "trace": [{"content": self.payload}]}

    def render(self, **kwargs):
        output = self.root / "report.html"
        result = report.render_report(self.state, output, **kwargs)
        return result, output.read_text()

    def test_legacy_scores_counts_and_state_are_unchanged(self):
        self.fixture()
        for label in ("baseline", "candidate"):
            for split in ("train", "validation"):
                run(self.state, label, split)
        select(self.state, "candidate")
        finalize(self.state, approved=True)
        with Store(self.state / "state.sqlite3") as store:
            before = list(store.db.iterdump())
        bounded, text = self.render()
        full, full_text = self.render(full_traces=True)
        self.assertEqual(text.split('<section id="cases">')[0], full_text.split('<section id="cases">')[0])
        self.assertIn("2 cases · 2 repeats", text)
        self.assertEqual(bounded["trace_preview"]["eligible_rows"], 8)
        self.assertEqual(full["trace_preview"]["eligible_rows"], 8)
        self.assertNotIn("TAIL_SENTINEL", text)
        self.assertIn("TAIL_SENTINEL", full_text)
        self.assertLess(len(text.encode("utf-8")), 250_000)
        for rendered in (text, full_text):
            self.assertNotIn("SECRET-validation", rendered)
            self.assertNotIn("SECRET-test", rendered)
            self.assertIn("default-src 'none'", rendered)
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(list(store.db.iterdump()), before)
            self.assertEqual(store.results("baseline", "train")[0]["output"], self.payload)
        _, private_text = self.render(include_private=True)
        self.assertIn("SECRET-validation", private_text)
        self.assertIn("SECRET-test", private_text)

    def test_paired_reports_share_bounds_and_keep_holdouts_sealed(self):
        self.fixture(paired=True)
        run(self.state, "baseline", "train")
        select(self.state, "candidate")
        for full in (False, True):
            result, text = self.render(full_traces=full)
            self.assertEqual(result["trace_preview"]["eligible_rows"], 4)
            self.assertNotIn("SECRET-validation", text)
            self.assertNotIn("SECRET-test", text)
            result, text = self.render(include_private=True, full_traces=full)
            self.assertEqual(result["trace_preview"]["eligible_rows"], 12)
            self.assertIn("SECRET-validation", text)
            self.assertNotIn("SECRET-test", text)
        finalize(self.state, approved=True)
        result, text = self.render(include_private=True)
        _, full_text = self.render(include_private=True, full_traces=True)
        self.assertEqual(text.split('<section id="cases">')[0], full_text.split('<section id="cases">')[0])
        self.assertEqual(result["trace_preview"]["eligible_rows"], 20)
        self.assertIn("SECRET-test", text)
        self.assertIn("Paired measurement cohorts", text)
        with patch.object(report, "TRACE_MAX_ROWS", 6):
            result, _ = self.render(include_private=True)
        self.assertEqual(result["trace_preview"]["shown_rows"], 6)
        self.assertEqual(result["trace_preview"]["omitted_rows"], 14)
        with Store(self.state / "state.sqlite3") as store:
            self.assertEqual(store.results("candidate", "test", cohort="final")[0]["output"], self.payload)

    def assert_interrupted_final_is_sealed(self, paired):
        self.fixture(paired=paired)
        run(self.state, "baseline", "train")
        calls = 0

        def interrupted(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("synthetic interruption after one private test row")
            return self.trial(*args, **kwargs)

        with patch("codex_eval_lab.engine.perform_trial", side_effect=interrupted):
            with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
                finalize(self.state, approved=True)
        with Store(self.state / "state.sqlite3") as store:
            table = "paired_trials" if paired else "trials"
            saved = store.db.execute(f"SELECT result FROM {table} WHERE split='test' AND result IS NOT NULL").fetchall()
            self.assertEqual(len(saved), 1)
            self.assertIn("SECRET-test", saved[0][0])
            self.assertIsNone(store.get("final_result"))
        results = Store.results

        def no_test_reads(store, label, split, **kwargs):
            self.assertNotEqual(split, "test", "an unfinished test row must not even be loaded")
            return results(store, label, split, **kwargs)

        with patch.object(Store, "results", new=no_test_reads):
            for full in (False, True):
                for private in (False, True):
                    result, text = self.render(full_traces=full, include_private=private)
                    self.assertNotIn("SECRET-test", text)
                    self.assertFalse(result["final_test_complete"])
                    self.assertEqual(result["trace_preview"]["eligible_rows"], 4)

    def test_existing_legacy_test_rows_stay_sealed_after_interruption(self):
        self.assert_interrupted_final_is_sealed(paired=False)

    def test_existing_paired_test_rows_stay_sealed_after_interruption(self):
        self.assert_interrupted_final_is_sealed(paired=True)

    def test_cli_full_trace_flag_is_separate_from_private_flag(self):
        self.fixture()
        run(self.state, "baseline", "train")
        for args, full in (([], False), (["--full-traces"], True)):
            captured = io.StringIO()
            with redirect_stdout(captured):
                code = main(["report", str(self.state), "--out", str(self.root / "cli.html"), *args])
            self.assertEqual(code, 0)
            result = json.loads(captured.getvalue())
            self.assertEqual(result["trace_preview"]["full_traces"], full)
            self.assertFalse(result["private_details_included"])
