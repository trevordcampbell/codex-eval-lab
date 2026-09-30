import copy
import tempfile
from pathlib import Path
import unittest

from codex_eval_lab.stats import paired_interval,compare_rows,valid_rows
from codex_eval_lab.config import load_config,load_cases,make_splits
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError
from .helpers import make_fixture


class StatsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        suite,_,_=make_fixture(Path(self.tmp.name));self.cfg=load_config(suite)
        self.cases=load_cases(suite,self.cfg);self.ids=make_splits(self.cases,42)['validation']
        self.base=self.rows(.2);self.good=self.rows(.8)
    def rows(self,score,cost=0):
        return [{'case_id':id_,'rep':0,'seed':i,'status':'ok','metrics':{'quality':score,'cost_usd':cost}} for i,id_ in enumerate(self.ids)]
    def compare(self,b=None,c=None):
        return compare_rows(b or self.base,c or self.good,cases=self.cases,ids=self.ids,cfg=self.cfg)
    def test_clear_gain_accepted(self):self.assertTrue(self.compare()['accepted'])
    def test_regression_rejected(self):self.assertFalse(self.compare(c=self.rows(.1))['accepted'])
    def test_noop_not_accepted(self):self.assertFalse(self.compare(c=self.base)['accepted'])
    def test_guardrail_veto(self):self.assertFalse(self.compare(c=self.rows(.8,cost=.1))['accepted'])
    def test_lower_is_better(self):
        self.cfg['objective']['direction']='minimize'
        self.assertTrue(self.compare(b=self.good,c=self.base)['accepted'])
    def test_minimum_effect(self):
        self.cfg['objective']['min_improvement']=.7
        self.assertFalse(self.compare()['accepted'])
    def test_minimum_independent_groups(self):
        for c in self.cases:c['group']='same'
        self.assertFalse(self.compare()['accepted'])
    def test_missing_case_not_dropped(self):
        with self.assertRaises(LabError):self.compare(c=self.good[:-1])
    def test_error_not_dropped(self):
        self.good[0]['status']='error'
        with self.assertRaises(LabError):self.compare()
    def test_duplicate_trial(self):
        self.good.append(self.good[0])
        with self.assertRaises(LabError):self.compare()
    def test_mismatched_seeds(self):
        self.good[0]['seed']=999
        with self.assertRaises(LabError):self.compare()
    def test_missing_seed(self):
        del self.good[0]['seed']
        with self.assertRaises(LabError):self.compare()
    def test_repetitions_not_extra_groups(self):
        d={str(i):float(i%2) for i in range(20)};g={str(i):str(i//5) for i in range(20)}
        r=paired_interval(d,g,confidence=.95,samples=500,seed=1)
        self.assertEqual(r['groups'],4);self.assertEqual(r['cases'],20)
    def test_bootstrap_reproducible(self):
        d={'a':1,'b':0,'c':-.2};g={k:k for k in d}
        self.assertEqual(paired_interval(d,g,confidence=.95,samples=500,seed=1),paired_interval(d,g,confidence=.95,samples=500,seed=1))
    def test_joint_interval_correction(self):
        r=self.compare()['metrics']['quality']['favorable_delta']
        self.assertAlmostEqual(r['confidence'],.975)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'s.sqlite3');self.addCleanup(self.store.db.close)
        self.budget={'max_trials':2,'trial_reserve_usd':.4,'max_eval_cost_usd':.6}
    def reserve(self,id_='a'):return self.store.reserve('base','train',id_,0,self.budget)
    def test_reserve_before_execute(self):
        self.assertTrue(self.reserve());self.assertEqual(self.store.pending(),1)
    def test_pending_reserves_budget(self):
        self.reserve()
        with self.assertRaises(LabError):self.reserve('b')
    def test_pending_attempt_not_retried(self):
        self.reserve()
        with self.assertRaises(LabError):self.reserve()
    def test_completed_not_reexecuted(self):
        self.reserve();self.store.complete('base','train','a',0,{'status':'ok'},.1)
        self.assertFalse(self.reserve())
    def test_released_unused_reservation(self):
        self.reserve();self.store.complete('base','train','a',0,{'status':'ok'},.1)
        self.assertTrue(self.reserve('b'))
    def test_trial_limit(self):
        self.budget['max_trials']=1;self.reserve();self.store.complete('base','train','a',0,{'status':'ok'},0)
        with self.assertRaises(LabError):self.reserve('b')
    def test_recovery_conservative_cost(self):
        self.reserve();self.assertEqual(self.store.recover(),1)
        self.assertAlmostEqual(self.store.budget()['eval_charged_usd'],.4)
        self.assertEqual(self.store.results('base','train')[0]['status'],'indeterminate')
    def test_double_completion_rejected(self):
        self.reserve();self.store.complete('base','train','a',0,{'status':'ok'},0)
        with self.assertRaises(LabError):self.store.complete('base','train','a',0,{'status':'ok'},0)
    def test_unreserved_completion_rejected(self):
        with self.assertRaises(LabError):self.store.complete('base','train','a',0,{'status':'ok'},0)
    def test_negative_charge_rejected(self):
        self.reserve()
        with self.assertRaises(LabError):self.store.complete('base','train','a',0,{'status':'ok'},-1)
    def test_optimizer_call_limit(self):
        self.store.begin_optimizer(1)
        with self.assertRaises(LabError):self.store.begin_optimizer(1)
    def test_metadata_roundtrip(self):
        self.store.put('x',{'a':1});self.assertEqual(self.store.get('x'),{'a':1})
