import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

path=Path(__file__).resolve().parents[1]/'examples/judges/openai_grader.py'
spec=importlib.util.spec_from_file_location('example_judge',path)
judge=importlib.util.module_from_spec(spec);spec.loader.exec_module(judge)

class OptionalJudgeTests(unittest.TestCase):
    def setUp(self):
        self.env={'EVAL_JUDGE_MODEL':'approved-model','EVAL_JUDGE_APPROVED':'1','EVAL_JUDGE_INPUT_USD_PER_MTOK':'2','EVAL_JUDGE_CACHED_INPUT_USD_PER_MTOK':'0.5','EVAL_JUDGE_OUTPUT_USD_PER_MTOK':'8'}
        self.response=SimpleNamespace(model='approved-model',status='completed',output_text=json.dumps({'quality':4,'grounded':True,'reason':'Matches evidence.'}),usage=SimpleNamespace(input_tokens=1000,output_tokens=100,input_tokens_details=SimpleNamespace(cached_tokens=400)))
        self.kwargs=None
        def create(**kwargs):self.kwargs=kwargs;return self.response
        self.client=SimpleNamespace(responses=SimpleNamespace(create=create))
    def call(self):return judge.grade({'input':'task','expected':'rubric','output':'answer'},self.client,self.env)
    def test_structured_output_contract(self):
        result=self.call();self.assertEqual(result['metrics'],{'quality':1,'grounded':1})
        self.assertTrue(self.kwargs['text']['format']['strict']);self.assertFalse(self.kwargs['store'])
    def test_cached_cost_accounting(self):
        self.assertAlmostEqual(self.call()['usage']['cost_usd'],.0022)
    def test_missing_rates_refuse_before_call(self):
        del self.env['EVAL_JUDGE_INPUT_USD_PER_MTOK']
        with self.assertRaises(KeyError):self.call()
        self.assertIsNone(self.kwargs)
    def test_no_approval_refuses_before_call(self):
        self.env['EVAL_JUDGE_APPROVED']='0'
        with self.assertRaises(ValueError):self.call()
        self.assertIsNone(self.kwargs)
    def test_nonfinite_rates_rejected(self):
        self.env['EVAL_JUDGE_OUTPUT_USD_PER_MTOK']='nan'
        with self.assertRaises(ValueError):self.call()
    def test_served_model_mismatch(self):
        self.response.model='unapproved'
        with self.assertRaises(ValueError):self.call()
    def test_incomplete_judgment(self):
        self.response.status='incomplete'
        with self.assertRaises(ValueError):self.call()
    def test_invalid_cached_tokens(self):
        self.response.usage.input_tokens_details.cached_tokens=1001
        with self.assertRaises(ValueError):self.call()
    def test_grade_boolean_not_integer(self):
        self.response.output_text=json.dumps({'quality':True,'grounded':True,'reason':'invalid'})
        with self.assertRaises(ValueError):self.call()
    def test_unknown_fields_rejected(self):
        self.response.output_text=json.dumps({'quality':4,'grounded':True,'reason':'x','extra':1})
        with self.assertRaises(ValueError):self.call()
