import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab.config import load_config
from codex_eval_lab.engine import initialize,run,register,compare,select,finalize,feedback,export_best,manifest_for,response_object
from codex_eval_lab.optimizer import loop,import_proposal,export_workspace,generate_proposal
from codex_eval_lab.report import render_report
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError,read_json,write_json,digest
from .helpers import make_fixture,start_fixture


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.suite,self.app,self.state=start_fixture(self.root)
    def good_variant(self,label='good'):
        p=self.app/'app.py';p.write_text(p.read_text().replace('"output":0','"output":1'))
        register(self.state,self.app,label,'Return the correct fixture output')
    def baseline(self):
        run(self.state,'baseline','train');run(self.state,'baseline','validation')
    def test_original_suite_can_change_without_redefining_frozen_eval(self):
        (self.suite/'grader.py').write_text('raise RuntimeError("changed external suite")')
        self.assertEqual(run(self.state,'baseline','train')['trials'],6)
    def test_frozen_evaluator_tamper_stops_execution(self):
        (self.state/'evaluator/grader.py').write_text('print("changed")')
        with self.assertRaises(LabError):run(self.state,'baseline','train')
    def test_frozen_candidate_tamper_stops_execution(self):
        (self.state/'candidates/baseline/app.py').write_text('changed')
        with self.assertRaises(LabError):run(self.state,'baseline','train')
    def test_manifest_tamper_stops_execution(self):
        p=self.state/'manifest.json';m=read_json(p);m['config']['budget']['max_trials']=999999;write_json(p,m)
        with self.assertRaises(LabError):run(self.state,'baseline','train')
    def test_resume_does_not_repeat_completed_cases(self):
        first=run(self.state,'baseline','train');second=run(self.state,'baseline','train')
        self.assertEqual(first['budget']['trials'],second['budget']['trials'])
    def test_test_split_blocked_before_final(self):
        with self.assertRaises(LabError):run(self.state,'baseline','test')
    def test_feedback_contains_no_heldout_inputs(self):
        run(self.state,'baseline','train');text=json.dumps(feedback(self.state,'baseline'))
        self.assertIn('SECRET-train',text);self.assertNotIn('SECRET-validation',text);self.assertNotIn('SECRET-test',text)
    def test_incomplete_comparison_blocked(self):
        self.good_variant()
        with self.assertRaises(LabError):compare(self.state,'baseline','good')
    def test_complete_pipeline_and_final_seal(self):
        self.baseline();self.good_variant();run(self.state,'good','train');run(self.state,'good','validation')
        self.assertTrue(select(self.state,'good')['accepted'])
        result=finalize(self.state,approved=True);self.assertTrue(result['accepted'])
        with Store(self.state/'state.sqlite3') as s:count=s.budget()['trials']
        self.assertEqual(finalize(self.state,approved=True),result)
        with Store(self.state/'state.sqlite3') as s:self.assertEqual(count,s.budget()['trials'])
        with self.assertRaises(LabError):select(self.state,'baseline')
        with self.assertRaises(LabError):register(self.state,self.app,'later','try again')
        with self.assertRaises(LabError):loop(self.state,approved=True)
    def test_final_requires_approval(self):
        with self.assertRaises(LabError):finalize(self.state,approved=False)
    def test_import_offlimits_proposal(self):
        with self.assertRaises(LabError):import_proposal(self.state,{'hypothesis':'hack','edits':[{'path':'../evaluator/grader.py','content':'pass'}]},'bad')
    def test_scoped_import(self):
        out=import_proposal(self.state,{'hypothesis':'fix','edits':[{'path':'app.py','content':'print("new")'}]},'new')
        self.assertEqual(out['changes'],['app.py'])
    def test_export_no_working_tree_overwrite(self):
        with self.assertRaises(LabError):export_best(self.state,self.app)
    def test_export_best(self):
        dest=self.root/'export';export_best(self.state,dest)
        self.assertEqual((dest/'app.py').read_text(),(self.app/'app.py').read_text())
    def test_external_workspace_excludes_evaluator(self):
        run(self.state,'baseline','train');dest=self.root/'handoff';export_workspace(self.state,dest)
        all_text='\n'.join(p.read_text() for p in dest.rglob('*') if p.is_file())
        self.assertNotIn('SECRET-validation',all_text);self.assertNotIn('SECRET-test',all_text)
        self.assertFalse((dest/'evaluator').exists());self.assertFalse((dest/'state.sqlite3').exists())
    def test_automatic_loop_works(self):
        result=loop(self.state,approved=True,rounds=1)
        self.assertEqual(result['best'],'round-0001');self.assertTrue(result['history'][0]['accepted'])
    def test_optimizer_requires_explicit_approval(self):
        with self.assertRaises(LabError):loop(self.state,approved=False)
    def test_round_budget_cannot_be_expanded(self):
        with self.assertRaises(LabError):loop(self.state,approved=True,rounds=999)
    def test_report_default_does_not_embed_holdout_details(self):
        self.baseline();out=self.root/'report.html';render_report(self.state,out)
        text=out.read_text();self.assertIn('SECRET-train',text);self.assertNotIn('SECRET-validation',text);self.assertNotIn('SECRET-test',text)
    def test_private_report_still_respects_unopened_test(self):
        self.baseline();out=self.root/'report.html';render_report(self.state,out,include_private=True)
        text=out.read_text();self.assertIn('SECRET-validation',text);self.assertNotIn('SECRET-test',text)
    def test_cost_required_even_for_free_adapter(self):
        with self.assertRaises(LabError):response_object({'output':'x'})
    def test_nonfinite_cost_rejected(self):
        with self.assertRaises(LabError):response_object({'output':'x','usage':{'cost_usd':float('nan')}})
    def test_unknown_response_field_rejected(self):
        with self.assertRaises(LabError):response_object({'output':1,'usage':{'cost_usd':0},'socre':1})
    def test_baseline_not_changed_by_candidate(self):
        before=(self.state/'candidates/baseline/app.py').read_text();self.good_variant()
        self.assertEqual(before,(self.state/'candidates/baseline/app.py').read_text())


class ErrorBoundaryTests(unittest.TestCase):
    def setup_custom(self,app_code=None,grader_code=None,config_edit=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);suite,app,state=make_fixture(root,cases_per_split=2)
        if app_code:(app/'app.py').write_text(app_code)
        if grader_code:(suite/'grader.py').write_text(grader_code)
        if config_edit:
            p=suite/'eval.toml';p.write_text(config_edit(p.read_text()))
        initialize(suite,app,state,approvals={'cases':True,'grader':True,'execution':True})
        return root,suite,app,state
    def test_missing_cost_fails_not_zero(self):
        _,_,_,state=self.setup_custom(app_code='print(\'{"output":1}\')')
        with self.assertRaises(LabError):run(state,'baseline','train')
        with Store(state/'state.sqlite3') as s:self.assertEqual(s.results('baseline','train')[0]['status'],'error')
    def test_metrics_cannot_be_nan(self):
        _,_,_,state=self.setup_custom(grader_code='print(\'{"metrics":{"quality":NaN},"usage":{"cost_usd":0}}\')')
        with self.assertRaises(LabError):run(state,'baseline','train')
    def test_metric_out_of_bounds(self):
        _,_,_,state=self.setup_custom(grader_code='print(\'{"metrics":{"quality":2},"usage":{"cost_usd":0}}\')')
        with self.assertRaises(LabError):run(state,'baseline','train')
    def test_model_mismatch(self):
        _,_,_,state=self.setup_custom(config_edit=lambda s:s.replace('mode = "local"','mode = "local"\nexpected_app_model = "wrong"'))
        with self.assertRaises(LabError):run(state,'baseline','train')
    def test_actual_cost_over_bound_aborts(self):
        _,_,_,state=self.setup_custom(app_code='print(\'{"output":1,"usage":{"cost_usd":1.5}}\')',config_edit=lambda s:s.replace('max_eval_cost_usd = 0.0','max_eval_cost_usd = 2.0').replace('trial_reserve_usd = 0.0','trial_reserve_usd = 1.0'))
        with self.assertRaises(LabError):run(state,'baseline','train')
        with Store(state/'state.sqlite3') as s:
            self.assertEqual(s.results('baseline','train')[0]['status'],'cost_bound_violation')
            self.assertAlmostEqual(s.budget()['eval_charged_usd'],1.5)
    def test_secrets_not_passed_as_input(self):
        code='import json,sys\nr=json.load(sys.stdin)\nassert "expected" not in r\nassert "split" not in r\njson.dump({"output":1,"usage":{"cost_usd":0}},sys.stdout)'
        _,_,_,state=self.setup_custom(app_code=code)
        self.assertEqual(run(state,'baseline','train')['metrics']['quality'],1)
    def test_html_injection_is_escaped(self):
        payload='</script><script>alert("INJECTED")</script>'
        code='import json\nprint(json.dumps({"output":'+repr(payload)+',"usage":{"cost_usd":0}}))'
        root,_,_,state=self.setup_custom(app_code=code);run(state,'baseline','train')
        report=root/'report.html';render_report(state,report)
        text=report.read_text();self.assertNotIn(payload,text);self.assertIn('&lt;/script&gt;',text);self.assertIn("default-src 'none'",text)
    def test_start_requires_all_approvals(self):
        with tempfile.TemporaryDirectory() as d:
            suite,app,state=make_fixture(Path(d))
            with self.assertRaises(LabError):initialize(suite,app,state,approvals={'cases':True,'execution':True})
            self.assertFalse(state.exists())
    def test_start_never_overwrites_existing_directory(self):
        with tempfile.TemporaryDirectory() as d:
            suite,app,state=make_fixture(Path(d));state.mkdir()
            with self.assertRaises(LabError):initialize(suite,app,state,approvals={'cases':True,'grader':True,'execution':True})
    def test_expired_experiment_blocks_execution(self):
        _,_,_,state=self.setup_custom()
        with patch('codex_eval_lab.engine.time.time',return_value=10**15),self.assertRaises(LabError):run(state,'baseline','train')


class ResumeAndCodexTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.suite,self.app,self.state=start_fixture(self.root,cases_per_split=3)
    def test_interrupted_round_reuses_proposal(self):
        from codex_eval_lab.optimizer import run_internal as real_run
        def interrupt(state,store,manifest,label,split,**kwargs):
            if label=='round-0001' and split=='validation':raise LabError('simulated interruption before dispatch')
            return real_run(state,store,manifest,label,split,**kwargs)
        with patch('codex_eval_lab.optimizer.run_internal',side_effect=interrupt),self.assertRaises(LabError):loop(self.state,approved=True,rounds=1)
        with Store(self.state/'state.sqlite3') as s:
            self.assertIsNotNone(s.get('active_round'));self.assertEqual(s.budget()['optimizer_calls'],1)
        result=loop(self.state,approved=True,rounds=1)
        self.assertEqual(result['best'],'round-0001');self.assertEqual(result['budget']['optimizer_calls'],1)
    def test_codex_adapter_contract_with_stubbed_process(self):
        from codex_eval_lab.process import ProcessResult
        run(self.state,'baseline','train')
        expected={'hypothesis':'test','edits':[{'path':'app.py','content':'new'}],'notes':'stub test'}
        def fake(command,request,**kwargs):
            if command[-1]=='--help':
                return ProcessResult(None,'--output-schema --output-last-message --json --sandbox --skip-git-repo-check --ignore-user-config','',0,0)
            self.assertIn('read-only',command);self.assertNotIn('danger-full-access',command)
            self.assertNotIn('SECRET-test',kwargs['input_text']);self.assertNotIn('SECRET-validation',kwargs['input_text'])
            result=Path(command[command.index('--output-last-message')+1]);write_json(result,expected)
            return ProcessResult(None,'{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":4}}\n','',.1,0)
        with Store(self.state/'state.sqlite3') as store:
            m=manifest_for(self.state,store)
            with patch('codex_eval_lab.optimizer.shutil.which',return_value='/bin/codex'),patch('codex_eval_lab.optimizer.invoke',side_effect=fake):
                result=generate_proposal(self.state,store,m,'baseline',1,cfg_override={'backend':'codex','environment':[],'timeout_s':5})
        self.assertEqual(result,expected)
    def test_missing_codex_flags_no_unsafe_fallback(self):
        from codex_eval_lab.process import ProcessResult
        run(self.state,'baseline','train')
        with Store(self.state/'state.sqlite3') as store:
            m=manifest_for(self.state,store)
            with patch('codex_eval_lab.optimizer.shutil.which',return_value='/bin/codex'),patch('codex_eval_lab.optimizer.invoke',return_value=ProcessResult(None,'old CLI','',0,0)),self.assertRaises(LabError):
                generate_proposal(self.state,store,m,'baseline',2,cfg_override={'backend':'codex','environment':[],'timeout_s':5})

class AdditionalIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.suite,self.app,self.state=start_fixture(self.root)
    def test_runtime_fingerprint_change_refuses_execution(self):
        with patch('codex_eval_lab.engine.runtime_fingerprint',return_value={'different':'runtime'}),self.assertRaises(LabError):run(self.state,'baseline','train')
    def test_manual_scope_is_enforced(self):
        # A new experiment deliberately freezes a second, non-editable source file.
        (self.root/'another').mkdir()
        suite,app,state=make_fixture(self.root/'another')
        (app/'protected.txt').write_text('protected')
        p=suite/'eval.toml';p.write_text(p.read_text().replace('source_paths = ["app.py"]','source_paths = ["app.py", "protected.txt"]'))
        initialize(suite,app,state,approvals={'cases':True,'grader':True,'execution':True})
        (app/'protected.txt').write_text('modified')
        with self.assertRaises(LabError):register(state,app,'bad','offlimits change')
        self.assertFalse((state/'candidates/bad').exists())
    def test_optimizer_deadline_prevents_process_start(self):
        run(self.state,'baseline','train')
        with Store(self.state/'state.sqlite3') as store:
            m=manifest_for(self.state,store);m['expires_at']=0
            with patch('codex_eval_lab.optimizer.invoke',side_effect=AssertionError('no process allowed')),self.assertRaises(LabError):
                generate_proposal(self.state,store,m,'baseline',1,cfg_override={'backend':'command','command':['echo'],'environment':[],'timeout_s':5})
    def test_codex_error_event_rejects_structured_proposal(self):
        from codex_eval_lab.process import ProcessResult
        run(self.state,'baseline','train')
        def fake(command,request,**kwargs):
            if command[-1]=='--help':return ProcessResult(None,'--output-schema --output-last-message --json --sandbox --skip-git-repo-check','',0,0)
            write_json(Path(command[command.index('--output-last-message')+1]),{'hypothesis':'false success','edits':[],'notes':''})
            return ProcessResult(None,'{"type":"turn.failed","error":{"message":"failure"}}\n','',0,0)
        with Store(self.state/'state.sqlite3') as store:
            m=manifest_for(self.state,store)
            with patch('codex_eval_lab.optimizer.shutil.which',return_value='/bin/codex'),patch('codex_eval_lab.optimizer.invoke',side_effect=fake),self.assertRaises(LabError):
                generate_proposal(self.state,store,m,'baseline',1,cfg_override={'backend':'codex','environment':[],'timeout_s':5})
