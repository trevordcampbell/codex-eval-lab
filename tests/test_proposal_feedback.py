import copy
import unittest

from codex_eval_lab.proposal_feedback import bounded_feedback
from codex_eval_lab.util import canonical,digest,LabError


class ProposalFeedbackTests(unittest.TestCase):
    def feedback(self,n=10):
        return {'schema_version':1,'variant':'baseline','objective':{'metric':'quality','direction':'maximize'},
                'guardrails':[],'editable':['app.py'],'warning':'Training data only.',
                'development_results':[{'case_id':f'case-{i//2:02d}','rep':i%2,
                    'input':{'text':'abcdefgh😀'*3000},'output':[i]*5000,'expected':[i]*5000,
                    'metrics':{'quality':float(i)},'explanation':'bounded test'} for i in range(n)]}

    def test_bounded_deterministic_and_all_row_statistics(self):
        f=self.feedback();before=copy.deepcopy(f)
        x=bounded_feedback(f,4096)
        self.assertLessEqual(len(canonical(x).encode()),4096)
        self.assertEqual(x,bounded_feedback(f,4096));self.assertEqual(f,before)
        self.assertEqual(x['development_summary']['trials'],10)
        self.assertEqual(x['development_summary']['cases'],5)
        self.assertEqual(x['development_summary']['case_mean_metrics']['quality'],4.5)
        self.assertEqual(x['feedback_excerpt']['full_feedback_sha256'],digest(f))
        self.assertEqual(x['feedback_excerpt']['included_rows'],len(x['development_results']))
        self.assertEqual(x['feedback_excerpt']['included_payload_preview_cases'],sum('input' in r for r in x['development_results']))
        self.assertIn('bounded development excerpt',x['warning'])

    def test_small_feedback_unchanged(self):
        f=self.feedback(0)
        self.assertEqual(bounded_feedback(f),f)

    def test_payload_previews_are_marked_not_partial_json(self):
        x=bounded_feedback(self.feedback(),20000)
        self.assertIn('_truncated_json_text_preview',x['development_results'][0]['input'])
        self.assertIn('_truncated_json_text_preview',x['development_results'][0]['output'])
        self.assertNotIn('input',x['development_results'][1])
        self.assertNotIn('input',x['development_results'][6])

    def test_budget_bounds(self):
        for bad in (True,1,3_000_000):
            with self.assertRaises(LabError):bounded_feedback(self.feedback(),bad)
