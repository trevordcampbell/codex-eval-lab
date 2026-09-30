from __future__ import annotations
from contextlib import redirect_stdout,redirect_stderr
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from codex_eval_lab.cli import main
from codex_eval_lab.util import write_json
from .helpers import make_fixture

class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.suite,self.app,self.state=make_fixture(self.root)
    def call(self,*argv):
        out,err=io.StringIO(),io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):code=main([str(x) for x in argv])
        payload=json.loads(out.getvalue() if code==0 else err.getvalue())
        return code,payload
    def start(self):
        code,r=self.call('start',self.suite,'--app',self.app,'--state',self.state,'--approve-cases','--approve-grader','--approve-execution')
        self.assertEqual(code,0);return r
    def test_doctor(self):
        code,r=self.call('doctor');self.assertEqual(code,0);self.assertIn('core_dependencies',r)
    def test_audit_no_state_creation(self):
        code,r=self.call('audit',self.suite);self.assertEqual(code,0);self.assertEqual(r['cases'],18);self.assertFalse(self.state.exists())
    def test_start_records_approvals(self):
        self.start();code,r=self.call('status',self.state);self.assertEqual(code,0);self.assertEqual(r['best'],'baseline')
    def test_start_missing_approval_exit_two(self):
        code,r=self.call('start',self.suite,'--app',self.app,'--state',self.state);self.assertEqual(code,2);self.assertIn('approval',r['error'])
    def test_invalid_state_read(self):
        code,r=self.call('status',self.root/'missing');self.assertEqual(code,2)
    def test_resume_run_from_cli(self):
        self.start();self.call('run',self.state);code,r=self.call('run',self.state);self.assertEqual(code,0);self.assertEqual(r['trials'],6)
    def test_loop_and_final_cli(self):
        self.start();code,r=self.call('loop',self.state,'--approve-optimizer','--rounds','1');self.assertEqual(code,0);self.assertEqual(r['best'],'round-0001')
        code,r=self.call('finalize',self.state,'--approve-final');self.assertEqual(code,0);self.assertTrue(r['accepted'])
        code,r=self.call('report',self.state,'--out',self.root/'report.html');self.assertEqual(code,0);self.assertTrue(r['final_test_complete'])
        code,r=self.call('export-best',self.state,'--out',self.root/'best');self.assertEqual(code,0);self.assertTrue((self.root/'best/app.py').exists())
    def test_feedback_cli(self):
        self.start();self.call('run',self.state);out=self.root/'feedback.json'
        code,r=self.call('feedback',self.state,'--out',out);self.assertEqual(code,0);self.assertNotIn('SECRET-test',out.read_text())
    def test_workspace_and_import_cli(self):
        self.start();self.call('run',self.state);out=self.root/'workspace'
        code,r=self.call('export-workspace',self.state,'--out',out);self.assertEqual(code,0);self.assertTrue((out/'development-feedback.json').exists())
        proposal=self.root/'proposal.json';write_json(proposal,{'hypothesis':'fix','edits':[{'path':'app.py','content':(self.app/'app.py').read_text().replace('"output":0','"output":1')}]})
        code,r=self.call('import-proposal',self.state,'--proposal',proposal,'--label','new');self.assertEqual(code,0);self.assertEqual(r['label'],'new')
    def test_manual_register_compare_select_cli(self):
        self.start();self.call('run',self.state,'--split','validation')
        p=self.app/'app.py';p.write_text(p.read_text().replace('"output":0','"output":1'))
        code,r=self.call('register',self.state,'--app',self.app,'--label','manual','--hypothesis','fix');self.assertEqual(code,0)
        self.call('run',self.state,'--label','manual','--split','validation')
        code,r=self.call('compare',self.state,'--candidate','manual');self.assertEqual(code,0);self.assertTrue(r['accepted'])
        code,r=self.call('select',self.state,'--candidate','manual');self.assertEqual(code,0)
    def test_no_optimizer_permission(self):
        self.start();code,r=self.call('loop',self.state);self.assertEqual(code,2)
    def test_recover_requires_confirmation(self):
        self.start();code,r=self.call('recover',self.state);self.assertEqual(code,2)
    def test_recover_empty(self):
        self.start();code,r=self.call('recover',self.state,'--confirm-no-running-process');self.assertEqual(code,0)
    def test_unlock_requires_confirmation(self):
        self.start();code,r=self.call('unlock',self.state);self.assertEqual(code,2)
    def test_unlock_absent(self):
        self.start();code,r=self.call('unlock',self.state,'--confirm-no-running-process');self.assertEqual(code,0);self.assertFalse(r['unlocked'])
    def test_unlock_active_pid_refused(self):
        if os.name!='posix':self.skipTest('POSIX PID check')
        self.start();(self.state/'.lock').mkdir();write_json(self.state/'.lock/owner.json',{'pid':os.getpid()})
        code,r=self.call('unlock',self.state,'--confirm-no-running-process');self.assertEqual(code,2);self.assertIn('still running',r['error'])
    def test_unlock_stale(self):
        self.start();(self.state/'.lock').mkdir();write_json(self.state/'.lock/owner.json',{})
        code,r=self.call('unlock',self.state,'--confirm-no-running-process');self.assertEqual(code,0);self.assertTrue(r['unlocked'])
    def test_keyboard_interrupt_has_actionable_error(self):
        with patch('codex_eval_lab.cli.dispatch',side_effect=KeyboardInterrupt):
            code,r=self.call('doctor')
        self.assertEqual(code,130);self.assertIn('recover',r['error'])
