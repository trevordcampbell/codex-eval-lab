import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab import search_policy
from codex_eval_lab.config import load_config, validate_config
from codex_eval_lab.engine import initialize, register, run, select, finalize
from codex_eval_lab.optimizer import loop
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError
from .helpers import make_fixture


POLICY = '\n[search_policy]\nschema_version=1\nmode="archive"\narchive_size=3\nallocation="ucb"\n'


class SearchPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def fixture(self, paired=False):
        suite, app, state = make_fixture(self.root, cases_per_split=3)
        cfg = (suite/'eval.toml').read_text().replace('min_improvement = 0.01', 'min_improvement = 0.5')
        (suite/'eval.toml').write_text(cfg + POLICY + ('\n[measurement]\ndesign="paired_ab_ba"\n' if paired else ''))
        initialize(suite, app, state, approvals={'cases':True,'grader':True,'execution':True})
        return suite, app, state

    def test_mean_improvement_is_search_only_until_final(self):
        _, app, state = self.fixture()
        run(state,'baseline','train'); run(state,'baseline','validation')
        p=app/'app.py';p.write_text(p.read_text().replace('"output":0','"output":int(r["input"]["n"]==0)'))
        register(state,app,'partial','Improve one regime')
        run(state,'partial','train');run(state,'partial','validation')
        result=select(state,'partial')
        self.assertFalse(result['accepted']);self.assertTrue(result['selected_for_search'])
        with Store(state/'state.sqlite3') as s:
            out=search_policy.outcome_summary(s)
            self.assertEqual(out['best_found'],'partial');self.assertEqual(out['release_champion'],'baseline')
            self.assertEqual(out['validation_champion'],'baseline');self.assertEqual(out['release_status'],'not_evaluated')
        final=finalize(state,approved=True)
        self.assertFalse(final['accepted']);self.assertEqual(final['release_champion'],'baseline')
        with self.assertRaises(LabError):select(state,'baseline')

    def test_fresh_pairing_used_for_exploratory_selection(self):
        _,app,state=self.fixture(paired=True)
        run(state,'baseline','train')
        p=app/'app.py';p.write_text(p.read_text().replace('"output":0','"output":int(r["input"]["n"]==0)'))
        register(state,app,'partial','Partial improvement');run(state,'partial','train')
        self.assertTrue(select(state,'partial')['selected_for_search'])
        with Store(state/'state.sqlite3') as s:
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM paired_cohorts').fetchone()[0],1)
            self.assertEqual(s.db.execute('SELECT COUNT(*) FROM paired_trials').fetchone()[0],6)
            self.assertEqual(s.results('partial','validation'),[])
        final=finalize(state,approved=True)
        self.assertFalse(final['accepted']);self.assertEqual(final['measurement']['design'],'paired_ab_ba')

    def test_guardrail_regressions_exclude_search_parent(self):
        cfg={'objective':{'metric':'quality'},'guardrails':[{'metric':'safe','max_regression':0}]}
        result={'accepted':False,'metrics':{'quality':{'favorable_delta':{'mean':1}},'safe':{'favorable_delta':{'mean':-0.01}}}}
        d=search_policy.exploratory_decision(result,result,cfg)
        self.assertFalse(d['selected_for_search']);self.assertFalse(d['eligible_parent'])
        self.assertFalse(d['release_qualified'])

    def test_missing_development_rows_cannot_mutate_incumbent(self):
        _,app,state=self.fixture()
        run(state,'baseline','validation')
        p=app/'app.py';p.write_text(p.read_text().replace('"output":0','"output":1'))
        register(state,app,'no-train','Validation only');run(state,'no-train','validation')
        with self.assertRaises(LabError):select(state,'no-train')
        with Store(state/'state.sqlite3') as s:
            self.assertEqual(s.get('best'),'baseline');self.assertEqual(s.get('validation_champion'),'baseline')
            self.assertIsNone(s.get('search_archive'))

    def test_configuration_rejects_invalid_and_unknown_policies(self):
        suite,_,_=make_fixture(self.root)
        original=load_config(suite)
        for bad in ({'schema_version':True,'mode':'archive'}, {'schema_version':1,'mode':'archive','operators':['repair','repair']},
                    {'schema_version':1,'mode':'archive','archive_size':1}, {'schema_version':1,'mode':'archive','exploration':float('inf')},
                    {'schema_version':1,'mode':'archive','lower_release_gate':True}):
            cfg=copy.deepcopy(original);cfg['search_policy']=bad
            with self.assertRaises(LabError):validate_config(cfg)
        self.assertNotIn('search_policy',validate_config(copy.deepcopy(original)))

    def test_native_and_automatic_use_persisted_portfolio_context(self):
        _,_,state=self.fixture()
        out=loop(state,approved=True,rounds=1)
        self.assertEqual(out['best'],'round-0001')
        with Store(state/'state.sqlite3') as s:
            history=s.get('search_history');ctx=history[0]['search_context']
            self.assertEqual(ctx['operator'],'refine');self.assertEqual(ctx['parent'],'baseline')
            self.assertEqual(history[0]['evaluation_trials'],6)
            self.assertEqual(s.get('search_dispatches')[0]['search_context'],ctx)
            from codex_eval_lab.engine import manifest_for
            m=manifest_for(state,s)
            self.assertEqual(search_policy.next_context(s,m,2),search_policy.next_context(s,m,2))
            self.assertEqual(search_policy.next_context(s,m,2)['operator'],'repair')
            self.assertLessEqual(len(s.get('search_archive')),3)
        captured=json.loads((state/'optimizer-runs/call-0001/evidence/invocation-context.json').read_text())
        self.assertEqual(captured['search_context'],search_policy.author_context(ctx))
        self.assertNotIn('operator_reward_sums',captured['search_context'])

    def test_automatic_archive_resume_preserves_parent_and_pairing(self):
        _,_,state=self.fixture(paired=True)
        from codex_eval_lab.optimizer import run_internal as original
        def interrupt(state,store,manifest,label,split,**kwargs):
            if label=='round-0001':raise LabError('before candidate execution')
            return original(state,store,manifest,label,split,**kwargs)
        with patch('codex_eval_lab.optimizer.run_internal',side_effect=interrupt),self.assertRaises(LabError):loop(state,approved=True,rounds=1)
        with Store(state/'state.sqlite3') as s:active=s.get('active_round')
        result=loop(state,approved=True,rounds=1)
        self.assertEqual(result['budget']['optimizer_calls'],1)
        self.assertEqual(result['history'][0]['search_context'],active['search_context'])
        self.assertEqual(result['history'][0]['parent'],active['parent'])
        self.assertEqual(result['history'][0]['evaluation_trials'],9)

    def test_invalid_utf8_command_cannot_be_normalized_into_a_proposal(self):
        suite,app,state=make_fixture(self.root,cases_per_split=2)
        (suite/'demo_optimizer.py').write_text("import sys\nsys.stdout.buffer.write(b'{\"hypothesis\":\"\\xff\",\"edits\":[],\"notes\":\"\"}')\n")
        initialize(suite,app,state,approvals={'cases':True,'grader':True,'execution':True})
        result=loop(state,approved=True,rounds=1)
        self.assertIn('not valid UTF-8',result['error'])
        self.assertIn(b'\xff',(state/'optimizer-runs/call-0001/failed-stdout.bin').read_bytes())
        with Store(state/'state.sqlite3') as s:
            self.assertEqual(s.budget()['optimizer_calls'],1);self.assertIsNone(s.variant('round-0001'))
