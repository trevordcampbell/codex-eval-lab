"""SQLite remains authoritative; derived JSONL is not rewritten every trial."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from codex_eval_lab import engine
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError
from .helpers import start_fixture

class MatrixMaterializationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.suite, self.app, self.state = start_fixture(Path(self.tmp.name), cases_per_split=5)

    def test_completed_matrix_materializes_once_and_resume_rebuilds_from_sqlite(self):
        original = engine.atomic_text
        writes = []
        def recording(path, text):
            if str(path).endswith('train.jsonl'):
                writes.append(path)
            return original(path, text)
        with patch('codex_eval_lab.engine.atomic_text', side_effect=recording):
            engine.run(self.state, 'baseline', 'train')
        self.assertEqual(len(writes), 1)
        path = self.state / 'runs/baseline/train.jsonl'
        expected = path.read_bytes(); path.write_text('broken export')
        engine.run(self.state, 'baseline', 'train')
        self.assertEqual(path.read_bytes(), expected)
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.budget()['trials'], 5)

    def test_ordinary_failure_flushes_successful_rows_without_retry(self):
        original = engine.perform_trial
        n = 0
        def interrupted(*args, **kwargs):
            nonlocal n
            n += 1
            if n == 3:
                raise KeyboardInterrupt()
            return original(*args, **kwargs)
        with patch('codex_eval_lab.engine.perform_trial', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            engine.run(self.state, 'baseline', 'train')
        path = self.state / 'runs/baseline/train.jsonl'
        self.assertEqual(len(path.read_text().splitlines()), 2)
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.pending(), 1)
            store.recover()
        with self.assertRaises(LabError):
            engine.run(self.state, 'baseline', 'train')
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertTrue(any(r['status'] == 'indeterminate' for r in rows))
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.budget()['trials'], 5)
