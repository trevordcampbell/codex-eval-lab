import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from codex_eval_lab.artifacts import apply_proposal,collect,hashes
from codex_eval_lab.process import ProcessFailure,invoke,minimal_env,docker_argv,substitute
from codex_eval_lab.util import LabError


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def call(self,code,**kwargs):
        return invoke([sys.executable,'-S','-c',code],{'input':'hello'},cwd=self.root,env=minimal_env([]),timeout_s=kwargs.pop('timeout_s',2),**kwargs)
    def test_json_roundtrip(self):self.assertEqual(self.call('import json,sys;print(json.dumps(json.load(sys.stdin)))').value['input'],'hello')
    def test_no_shell_interpolation(self):
        r=invoke([sys.executable,'-S','-c','import json,sys;print(json.dumps(sys.argv[1]))','$(touch OWNED)'],{},cwd=self.root,env=minimal_env([]),timeout_s=2)
        self.assertEqual(r.value,'$(touch OWNED)');self.assertFalse((self.root/'OWNED').exists())
    def test_timeout(self):
        with self.assertRaises(ProcessFailure):self.call('import time;time.sleep(5)',timeout_s=.05)
    def test_nonzero_is_not_a_grade(self):
        with self.assertRaises(ProcessFailure):self.call('raise SystemExit(3)')
    def test_invalid_json_is_error(self):
        with self.assertRaises(ProcessFailure):self.call('print("hello")')
    def test_multiple_json_objects_rejected(self):
        with self.assertRaises(ProcessFailure):self.call('print("{}\\n{}")')
    def test_oversized_stdout(self):
        with self.assertRaises(ProcessFailure):self.call('print("x"*20000)',max_output_bytes=1024)
    def test_oversized_stderr(self):
        with self.assertRaises(ProcessFailure):self.call('import sys;sys.stderr.write("x"*20000);print("{}")',max_output_bytes=1024)
    def test_raw_events_not_json_parsed(self):self.assertIsNone(self.call('print("one\\ntwo")',parse_json=False).value)
    def test_environment_secret_not_inherited(self):
        with patch.dict(os.environ,{'UNRELATED_SECRET':'should-not-pass'}):
            self.assertNotIn('UNRELATED_SECRET',minimal_env([]))
            self.assertEqual(minimal_env(['UNRELATED_SECRET'])['UNRELATED_SECRET'],'should-not-pass')
    def test_missing_explicit_env_rejected(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(LabError):minimal_env(['NO_SUCH_KEY'])
    def test_docker_does_not_mount_evaluator(self):
        cfg={'docker_image':'example@sha256:abc','app_env':[]}
        with patch('shutil.which',return_value='/bin/docker'):
            args=docker_argv(['python3','app.py'],self.root,self.root/'out',cfg)
        self.assertIn('--network=none',args);self.assertIn('--read-only',args)
        self.assertIn('--cap-drop=ALL',args);self.assertNotIn('/evaluator',' '.join(args))
    def test_docker_missing_no_fallback(self):
        with patch('shutil.which',return_value=None),self.assertRaises(LabError):docker_argv([],self.root,self.root,{'app_env':[]})
    def test_substitution_keeps_spaces(self):
        args=substitute(['{python}','{app}/my app.py'],app=Path('/a b'),suite=self.root,artifacts=self.root)
        self.assertEqual(args[1],'/a b/my app.py')


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.base=self.root/'base';self.base.mkdir();(self.base/'app.py').write_text('old')
        self.target=self.root/'new';self.cfg={'search':{'editable':['app.py','src/*.py'],'max_edit_bytes':100}}
    def proposal(self,path='app.py',content='new'):
        return {'hypothesis':'test','edits':[{'path':path,'content':content}]}
    def test_apply_changes_only_new_copy(self):
        self.assertEqual(apply_proposal(self.base,self.target,self.proposal(),self.cfg),['app.py'])
        self.assertEqual((self.base/'app.py').read_text(),'old');self.assertEqual((self.target/'app.py').read_text(),'new')
    def test_offlimits_rejected(self):
        with self.assertRaises(LabError):apply_proposal(self.base,self.target,self.proposal('grader.py'),self.cfg)
        self.assertFalse(self.target.exists())
    def test_traversal_rejected(self):
        with self.assertRaises(LabError):apply_proposal(self.base,self.target,self.proposal('../secret'),self.cfg)
    def test_noop_rejected(self):
        with self.assertRaises(LabError):apply_proposal(self.base,self.target,self.proposal(content='old'),self.cfg)
    def test_empty_edits_rejected(self):
        p=self.proposal();p['edits']=[]
        with self.assertRaises(LabError):apply_proposal(self.base,self.target,p,self.cfg)
    def test_duplicate_edits_rejected(self):
        p=self.proposal();p['edits']*=2
        with self.assertRaises(LabError):apply_proposal(self.base,self.target,p,self.cfg)
    def test_oversized_edit_rejected(self):
        with self.assertRaises(LabError):apply_proposal(self.base,self.target,self.proposal(content='x'*101),self.cfg)
    def test_new_file_allowed_in_scope(self):
        apply_proposal(self.base,self.target,self.proposal('src/new.py'),self.cfg)
        self.assertEqual((self.target/'src/new.py').read_text(),'new')
    def test_missing_hypothesis_rejected(self):
        p=self.proposal();p['hypothesis']=''
        with self.assertRaises(LabError):apply_proposal(self.base,self.target,p,self.cfg)
    def test_secret_source_refused(self):
        (self.base/'.env').write_text('SECRET=1')
        with self.assertRaises(LabError):collect(self.base,['.env'])
    def test_example_env_allowed(self):
        (self.base/'.env.example').write_text('SECRET=')
        self.assertIn('.env.example',collect(self.base,['.env.example']))
    def test_source_symlink_refused(self):
        (self.base/'link').symlink_to(self.base/'app.py')
        with self.assertRaises(LabError):collect(self.base,['link'])
    def test_reserved_asset_dir_refused(self):
        (self.base/'.eval-inputs').mkdir();(self.base/'.eval-inputs/x').write_text('x')
        with self.assertRaises(LabError):collect(self.base,['.eval-inputs'])
