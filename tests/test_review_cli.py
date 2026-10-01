from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

from codex_eval_lab.cli import main
from codex_eval_lab.util import read_json

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('review_cli_demo', ROOT / 'examples/review_calibration/demo.py')
DEMO = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEMO)


class ReviewCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / 'fixture'
        DEMO.run(self.data)

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def inputs(self, *, broken=False):
        return ['--packet', self.data/'packet.json', '--rubric', self.data/'rubric.json',
                '--labels', self.data/'labels.json', '--judge-config', self.data/('broken-judge-config.json' if broken else 'judge-config.json'),
                '--outputs', self.data/('broken-judge-outputs.json' if broken else 'judge-outputs.json'),
                '--policy', self.data/'policy.json']

    def test_calibrate_roundtrip_creates_report_without_echoing_traces(self):
        dest = self.root/'report.json'
        code, out, err = self.invoke('calibrate', *self.inputs(), '--out', dest)
        self.assertEqual(code, 0, err)
        self.assertTrue(read_json(dest)['ready'])
        summary = json.loads(out)
        self.assertTrue(summary['ready'])
        self.assertNotIn('traces', summary)
        self.assertNotIn('criteria', summary)

    def test_failed_calibration_saves_evidence_and_returns_nonzero(self):
        dest = self.root/'failed.json'
        code, out, err = self.invoke('calibrate', *self.inputs(broken=True), '--out', dest)
        self.assertEqual(code, 2, err)
        self.assertFalse(read_json(dest)['ready'])
        self.assertIn('error', json.loads(out))

    def test_point_estimate_never_returns_cli_ready(self):
        p = read_json(self.data/'policy.json'); p['threshold_basis'] = 'point_estimate'
        path = self.root/'point.json'; path.write_text(json.dumps(p))
        args = self.inputs(); args[args.index('--policy')+1] = path
        code, out, err = self.invoke('calibrate', *args, '--out', self.root/'point-report.json')
        self.assertEqual(code, 2, err)
        self.assertFalse(json.loads(out)['ready'])

    def test_drift_recomputes_bound_source_artifacts(self):
        args = ['calibration-drift', '--packet', self.data/'packet.json', '--rubric', self.data/'rubric.json',
                '--labels', self.data/'labels.json', '--old-config', self.data/'judge-config.json',
                '--old-outputs', self.data/'judge-outputs.json', '--new-config', self.data/'broken-judge-config.json',
                '--new-outputs', self.data/'broken-judge-outputs.json', '--policy', self.data/'policy.json',
                '--out', self.root/'drift.json']
        code, out, err = self.invoke(*args)
        self.assertEqual(code, 0, err)
        self.assertTrue(read_json(self.root/'drift.json')['changed_rows'])

    def test_annotation_requires_explicit_confirmation(self):
        review = read_json(self.data/'human-review.json')
        raw = self.root/'annotations.json'; raw.write_text(json.dumps(review['annotations']))
        dest = self.root/'reviewed.json'
        code, out, err = self.invoke('review', 'annotate', '--packet', self.data/'packet.json',
                '--annotations', raw, '--reviewer', review['reviewer'], '--out', dest)
        self.assertEqual(code, 2)
        self.assertIn('Actual human review', err)
        self.assertFalse(dest.exists())

    def test_valid_ui_draft_import_and_reviewer_binding(self):
        review = read_json(self.data/'human-review.json')
        packet = read_json(self.data/'packet.json')
        draft = {'schema_version':1,'kind':'annotation_draft','packet_sha256':packet['sha256'],
                 'reviewer':review['reviewer'],'annotations':review['annotations']}
        raw = self.root/'draft.json'; raw.write_text(json.dumps(draft))
        args = ['review','annotate','--packet',self.data/'packet.json','--annotations',raw,
                '--confirm-human-review','--reviewer',review['reviewer'],'--out',self.root/'reviewed.json']
        code, out, err = self.invoke(*args)
        self.assertEqual(code, 0, err)
        self.assertEqual(read_json(self.root/'reviewed.json')['annotations'],review['annotations'])
        args[args.index('--reviewer')+1] = 'different'; args[-1] = self.root/'bad.json'
        self.assertEqual(self.invoke(*args)[0],2)
        self.assertFalse((self.root/'bad.json').exists())

    def test_artifacts_never_overwrite(self):
        dest = self.root/'report.json'; dest.write_text('keep')
        code, out, err = self.invoke('calibrate',*self.inputs(),'--out',dest)
        self.assertEqual(code,2)
        self.assertEqual(dest.read_text(),'keep')

    def test_calibration_review_contains_actual_wrong_call_and_is_no_network(self):
        path=self.root/'disagreements.html'
        code,out,err=self.invoke('calibration-review',*self.inputs(broken=True),'--out',path)
        self.assertEqual(code,0,err)
        html=path.read_text()
        self.assertIn('missed_failure',html)
        self.assertIn("connect-src",html)
        self.assertIn('human-only',out)

    def test_unconfigured_gate_returns_nonzero(self):
        code,out,err=self.invoke('evidence','check','--suite',ROOT/'examples/routing')
        self.assertEqual(code,2)
        self.assertIn('Evidence gate',err)

    def test_fingerprint_has_no_source_data(self):
        code,out,err=self.invoke('evidence','fingerprint','--suite',ROOT/'examples/routing')
        self.assertEqual(code,0,err)
        obj=json.loads(out)
        self.assertEqual(len(obj['evaluator_fingerprint']),64)
        self.assertNotIn('cases',obj)

if __name__ == '__main__':
    unittest.main()
