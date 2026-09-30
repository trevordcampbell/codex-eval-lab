import copy
import json
from pathlib import Path
import tempfile
import unittest

from codex_eval_lab.util import LabError, canonical, contained, digest, finite, integer, relative_name, safe_name, strict_json, write_json, read_json, experiment_lock
from codex_eval_lab.config import audit, load_cases, load_config, make_splits, validate_config
from .helpers import make_fixture


class SerializationTests(unittest.TestCase):
    def test_duplicate_json_key(self):
        with self.assertRaises(LabError): strict_json('{"x":1,"x":2}')
    def test_nonfinite_json(self):
        for value in ('NaN','Infinity','-Infinity'):
            with self.subTest(value=value), self.assertRaises(LabError): strict_json(value)
    def test_canonical_order(self):
        self.assertEqual(digest({'a':1,'b':2}),digest({'b':2,'a':1}))
    def test_bool_not_number(self):
        with self.assertRaises(LabError): finite(True,'metric')
    def test_nonfinite_number(self):
        for n in (float('nan'),float('inf'),-float('inf')):
            with self.subTest(n=n), self.assertRaises(LabError): finite(n,'metric')
    def test_number_bounds(self):
        with self.assertRaises(LabError): finite(-1,'cost',minimum=0)
        with self.assertRaises(LabError): finite(2,'rate',maximum=1)
    def test_integer_type(self):
        for n in (True,1.2,'3',0):
            with self.subTest(n=n), self.assertRaises(LabError): integer(n,'n')
    def test_atomic_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a/b.json';write_json(p,{'text':'snow ☃'})
            self.assertEqual(read_json(p),{'text':'snow ☃'})
    def test_invalid_names(self):
        for n in ('','../evil','bad/name','bad\nname','-bad'):
            with self.subTest(n=n),self.assertRaises(LabError):safe_name(n)
    def test_invalid_paths(self):
        for n in ('../evil','/etc/passwd','C:/evil','a\\b','a\x00b','.git/config','.'):
            with self.subTest(n=n),self.assertRaises(LabError):relative_name(n)
    def test_path_controls(self):
        with self.assertRaises(LabError):relative_name('evil\nfile')
    def test_symlink_containment(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'link').symlink_to('/tmp',target_is_directory=True)
            with self.assertRaises(LabError):contained(root,'link/file',exists=False)
    def test_exclusive_lock(self):
        with tempfile.TemporaryDirectory() as d:
            with experiment_lock(Path(d)):
                with self.assertRaises(LabError):
                    with experiment_lock(Path(d)):pass
            self.assertFalse((Path(d)/'.lock').exists())


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.suite,self.app,self.state=make_fixture(Path(self.tmp.name))
        self.cfg=load_config(self.suite)
    def test_valid_suite(self):
        self.assertEqual(audit(self.suite)['cases'],18)
    def test_unknown_config_key(self):
        self.cfg['repititions']=2
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_bool_schema_not_version(self):
        self.cfg['schema_version']=True
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_negative_budget(self):
        self.cfg['budget']['max_eval_cost_usd']=-2
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_bad_primary_metric(self):
        self.cfg['objective']['metric']='invented'
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_bad_direction(self):
        self.cfg['objective']['direction']='up'
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_catchall_scope(self):
        self.cfg['search']['editable']=['**/*']
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_unknown_placeholder(self):
        self.cfg['execution']['app_command']=['{password}']
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_private_suite_not_passed_to_app(self):
        self.cfg['execution']['app_command']=['{python}','{suite}/grader.py']
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_unknown_metric_bound(self):
        self.cfg['metrics']['quality']['minumum']=0
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_inverted_bounds(self):
        self.cfg['metrics']['quality']={'minimum':2,'maximum':1}
        with self.assertRaises(LabError):validate_config(self.cfg)
    def test_duplicate_ids(self):
        p=self.suite/'cases.jsonl';p.write_text(p.read_text()+p.read_text().splitlines()[0]+'\n')
        with self.assertRaises(LabError):load_cases(self.suite,self.cfg)
    def test_duplicate_json_case_keys(self):
        (self.suite/'cases.jsonl').write_text('{"id":"x","id":"y","input":1}\n')
        with self.assertRaises(LabError):load_cases(self.suite,self.cfg)
    def test_missing_input(self):
        (self.suite/'cases.jsonl').write_text('{"id":"x"}\n')
        with self.assertRaises(LabError):load_cases(self.suite,self.cfg)
    def test_asset_escape(self):
        (self.suite/'cases.jsonl').write_text(json.dumps({'id':'a','input':1,'assets':['../secret']})+'\n')
        with self.assertRaises(LabError):load_cases(self.suite,self.cfg)
    def test_identical_inputs_need_same_group(self):
        (self.suite/'cases.jsonl').write_text('\n'.join(json.dumps({'id':i,'input':1}) for i in ('a','b')))
        with self.assertRaises(LabError):load_cases(self.suite,self.cfg)
    def test_local_isolation_warning(self):
        self.assertTrue(any('NOT an isolation boundary' in w for w in audit(self.suite)['warnings']))


class SplitTests(unittest.TestCase):
    def cases(self,n=30):
        return [{'id':str(i),'input':i,'tags':['all'],'group':str(i//2)} for i in range(n)]
    def test_reproducible(self):
        self.assertEqual(make_splits(self.cases(),1),make_splits(self.cases(),1))
    def test_seed_changes_split(self):
        self.assertNotEqual(make_splits(self.cases(),1),make_splits(self.cases(),2))
    def test_related_groups_stay_together(self):
        cases=self.cases();s=make_splits(cases,4);loc={id_:name for name,ids in s.items() for id_ in ids}
        for i in range(0,30,2):self.assertEqual(loc[str(i)],loc[str(i+1)])
    def test_no_loss_or_duplicate(self):
        split=make_splits(self.cases(),2);all_ids=sum(split.values(),[])
        self.assertEqual(len(all_ids),len(set(all_ids)));self.assertEqual(len(all_ids),30)
    def test_cross_split_group_rejected(self):
        c=self.cases(2);c[0]['split']='train';c[1]['split']='test'
        with self.assertRaises(LabError):make_splits(c,2)
    def test_mixed_explicit_splits(self):
        c=self.cases();c[0]['split']='train'
        with self.assertRaises(LabError):make_splits(c,2)
    def test_group_spanning_strata(self):
        c=self.cases();c[0]['tags']=['different']
        with self.assertRaises(LabError):make_splits(c,2)
    def test_small_splits_not_fabricated(self):
        s=make_splits(self.cases(2),2)
        self.assertEqual(s['validation'],[]);self.assertEqual(s['test'],[])
