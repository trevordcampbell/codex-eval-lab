import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab.engine import initialize,finalize
from codex_eval_lab.native import prepare_turn,submit_turn
from codex_eval_lab.optimizer import loop
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError
from .helpers import make_fixture
from .test_search_policy import POLICY


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        suite,self.app,self.state=make_fixture(self.root,cases_per_split=2)
        (suite/'eval.toml').write_text((suite/'eval.toml').read_text()+POLICY)
        initialize(suite,self.app,self.state,approvals={'cases':True,'grader':True,'execution':True})

    def prepare(self):
        return prepare_turn(self.state,self.root/'author',approved=True,authorization_note='Authorized free native test')

    def response(self,body=None):
        p=self.root/'response.json'
        code=(self.app/'app.py').read_text().replace('"output":0','"output":1')
        p.write_text(body if body is not None else json.dumps({'hypothesis':'Fix fixture','edits':[{'path':'app.py','content':code}],'notes':'test'}))
        return p

    def test_real_prepare_submit_evaluate_final_and_immutable_capture(self):
        r=self.prepare()
        text='\n'.join(p.read_text() for p in (self.root/'author').rglob('*') if p.is_file())
        self.assertNotIn('SECRET-test',text);self.assertNotIn('SECRET-validation',text)
        with Store(self.state/'state.sqlite3') as s:self.assertEqual(s.budget()['optimizer_calls'],1)
        self.assertEqual(submit_turn(self.state,r['call_id'],self.response(),elapsed_s=1)['status'],'applied')
        out=loop(self.state,approved=True,rounds=1)
        self.assertEqual(out['budget']['optimizer_calls'],1);self.assertEqual(out['best'],'round-0001')
        final=finalize(self.state,approved=True);self.assertTrue(final['release_qualified'])
        with self.assertRaises(LabError):prepare_turn(self.state,self.root/'later',approved=True,authorization_note='same scope')

    def test_pending_blocks_second_prepare_and_loop(self):
        self.prepare()
        with self.assertRaises(LabError):prepare_turn(self.state,self.root/'second',approved=True,authorization_note='same scope')
        with self.assertRaises(LabError):loop(self.state,approved=True,rounds=1)
        with Store(self.state/'state.sqlite3') as s:self.assertEqual(s.budget()['optimizer_calls'],1)

    def test_duplicate_submit_does_not_reapply_or_add_call(self):
        r=self.prepare();response=self.response()
        submit_turn(self.state,r['call_id'],response,elapsed_s=1)
        with self.assertRaises(LabError):submit_turn(self.state,r['call_id'],response,elapsed_s=1)
        with Store(self.state/'state.sqlite3') as s:self.assertEqual(s.budget()['optimizer_calls'],1)

    def test_source_swap_blocks_before_application(self):
        r=self.prepare();(self.root/'author/app/app.py').write_text('print("altered")')
        with self.assertRaises(LabError):submit_turn(self.state,r['call_id'],self.response(),elapsed_s=1)
        with Store(self.state/'state.sqlite3') as s:
            self.assertIsNone(s.variant('round-0001'));self.assertEqual(s.unresolved_optimizers(),1)

    def test_feedback_overwrite_blocks_before_application(self):
        r=self.prepare();(self.root/'author/evidence/development-feedback.json').write_text('{}')
        with self.assertRaises(LabError):submit_turn(self.state,r['call_id'],self.response(),elapsed_s=1)
        with Store(self.state/'state.sqlite3') as s:self.assertIsNone(s.variant('round-0001'))

    def test_malformed_response_is_captured_and_charged(self):
        r=self.prepare()
        with self.assertRaises(LabError):submit_turn(self.state,r['call_id'],self.response('not json'),elapsed_s=1)
        self.assertEqual((self.root/'author/evidence/response.json').read_text(),'not json')
        with Store(self.state/'state.sqlite3') as s:
            self.assertEqual(s.budget()['optimizer_calls'],1);self.assertEqual(s.unresolved_optimizers(),0)

    def test_failed_and_timeout_count_without_source(self):
        r=self.prepare()
        with self.assertRaises(LabError):submit_turn(self.state,r['call_id'],self.response(),elapsed_s=6)
        with Store(self.state/'state.sqlite3') as s:
            self.assertIsNone(s.variant('round-0001'));self.assertEqual(s.budget()['optimizer_calls'],1)

    def test_interrupted_preparation_is_unresolved(self):
        with patch('codex_eval_lab.native.proposal_receipts.prepare_dispatch',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):self.prepare()
        with Store(self.state/'state.sqlite3') as s:self.assertEqual(s.unresolved_optimizers(),1)
        with self.assertRaises(LabError):prepare_turn(self.state,self.root/'retry',approved=True,authorization_note='same scope')

    def test_incomplete_response_cannot_be_retried(self):
        r=self.prepare();(self.root/'author/evidence/response.json').write_text('partial')
        with self.assertRaises(LabError):submit_turn(self.state,r['call_id'],self.response(),elapsed_s=1)
        with Store(self.state/'state.sqlite3') as s:self.assertEqual(s.unresolved_optimizers(),1)

    def test_dangling_response_symlink_never_writes_outside_handoff(self):
        r=self.prepare();outside=self.root/'must-not-create'
        (self.root/'author/evidence/response.json').symlink_to(outside)
        with self.assertRaises(LabError):submit_turn(self.state,r['call_id'],self.response(),elapsed_s=1)
        self.assertFalse(outside.exists())
        with Store(self.state/'state.sqlite3') as s:self.assertEqual(s.unresolved_optimizers(),1)

    def test_response_input_must_be_ordinary_and_bounded(self):
        r=self.prepare();response=self.root/'oversize.json'
        response.write_bytes(b'x'*3_000_001)
        with self.assertRaisesRegex(LabError,'bound'):submit_turn(self.state,r['call_id'],response,elapsed_s=1)
        response.unlink();response.symlink_to(self.response())
        with self.assertRaisesRegex(LabError,'ordinary'):submit_turn(self.state,r['call_id'],response,elapsed_s=1)
        with Store(self.state/'state.sqlite3') as s:self.assertEqual(s.unresolved_optimizers(),1)

    def test_authority_required_before_reservation(self):
        with self.assertRaises(LabError):prepare_turn(self.state,self.root/'author',approved=False,authorization_note='')
        with Store(self.state/'state.sqlite3') as s:self.assertEqual(s.budget()['optimizer_calls'],0)

    def test_pending_blocks_final_test_without_automation_plan(self):
        self.prepare()
        with self.assertRaisesRegex(LabError,'Unresolved'):finalize(self.state,approved=True)
        with Store(self.state/'state.sqlite3') as s:
            self.assertIsNone(s.get('final_selection'));self.assertEqual(s.results('baseline','test'),[])

    def test_no_proposal_is_durable_and_cannot_dispatch_via_loop(self):
        r=self.prepare()
        submit_turn(self.state,r['call_id'],self.response('{"hypothesis":"stop","edits":[],"notes":"done"}'),elapsed_s=1)
        result=loop(self.state,approved=True,rounds=1)
        self.assertEqual(result['stop_reason'],'no_more_proposals');self.assertEqual(result['budget']['optimizer_calls'],1)
        with self.assertRaises(LabError):prepare_turn(self.state,self.root/'another',approved=True,authorization_note='same scope')

    def test_postsubmit_evidence_tamper_blocks_all_consumers(self):
        from codex_eval_lab.report import render_report
        r=self.prepare();submit_turn(self.state,r['call_id'],self.response(),elapsed_s=1)
        p=self.state/'native-runs/call-0001/evidence/prompt.txt';p.write_text(p.read_text()+' altered')
        for fn in (lambda:loop(self.state,approved=True,rounds=1),lambda:finalize(self.state,approved=True),
                   lambda:render_report(self.state,self.root/'report.html')):
            with self.assertRaises(LabError):fn()

    def test_controller_evidence_survives_author_workspace_cleanup(self):
        import shutil
        r=self.prepare();submit_turn(self.state,r['call_id'],self.response(),elapsed_s=1)
        shutil.rmtree(self.root/'author')
        result=loop(self.state,approved=True,rounds=1)
        self.assertEqual(result['best'],'round-0001')
        self.assertTrue(finalize(self.state,approved=True)['accepted'])
