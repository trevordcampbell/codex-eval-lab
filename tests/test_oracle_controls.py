"""Exact-JSON grader challenge regressions; all fixtures are synthetic and local."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab import automation, oracle, oracle_controls as controls
from codex_eval_lab.config import audit, load_config
from codex_eval_lab.engine import initialize
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError, read_json, write_json
from .test_automation import APPROVALS, configure_oracle

POLICY = {"kind": "exact_json", "criterion": "correct", "numeric_equality": "mathematical", "max_per_anchor": 64}
EXPECTED = {"answer": 1, "items": [1, 2], "ok": True}

# Fixture-specific, independently written expected-output predicate. This does not
# import the probe generator or its equality helper to manufacture passing labels.
GOOD_PREDICATE = '''def valid(value):
    return (type(value) is dict and set(value) == {"answer", "items", "ok"}
            and type(value["answer"]) in (int, float) and value["answer"] == 1
            and type(value["ok"]) is bool and value["ok"] is True
            and type(value["items"]) is list and len(value["items"]) == 2
            and all(type(item) in (int, float) for item in value["items"])
            and value["items"][0] == 1 and value["items"][1] == 2)
ok=valid(r["output"])
'''


def grader_source(predicate):
    return ('import json,sys\nr=json.load(sys.stdin)\n' + predicate +
            '\njson.dump({"metrics":{"quality":int(ok)},"usage":{"cost_usd":0},'
            '"criterion_results":{"correct":{"status":"pass" if ok else "fail","explanation":"Fixture contract"}}},sys.stdout)\n')


def configure_exact(root, predicate=GOOD_PREDICATE, *, enabled=True):
    suite, app, state = configure_oracle(root)
    contract = read_json(suite / 'oracle.json')
    for anchor in contract['anchors']:
        anchor.update(output=EXPECTED, expected=EXPECTED,
                      derivation='The synthetic specification explicitly fixes answer=1, items=[1,2], and ok=true.',
                      mutations=[{'id': 'wrong', 'output': None, 'fails': ['correct']}])
    if enabled:
        contract['generated_controls'] = dict(POLICY)
    write_json(suite / 'oracle.json', contract)
    (suite / 'spec.txt').write_text('Synthetic fixture: output the object with exactly answer=1, items=[1,2], ok=true. Numbers have mathematical equality; booleans are distinct. Object order is irrelevant; array order is significant.')
    (suite / 'reference.py').write_text('import json,sys\njson.load(sys.stdin)\njson.dump({"output":'+repr(EXPECTED)+',"usage":{"cost_usd":0}},sys.stdout)\n')
    cases = [json.loads(line) for line in (suite / 'cases.jsonl').read_text().splitlines()]
    for case in cases:
        case['expected'] = EXPECTED
    (suite / 'cases.jsonl').write_text(''.join(json.dumps(case) + '\n' for case in cases))
    (suite / 'grader.py').write_text(grader_source(predicate))
    return suite, app, state


class GeneratedControlUnitTests(unittest.TestCase):
    def anchor(self, output):
        return {'id': 'a', 'group': 'g', 'output': output, 'mutations': []}

    def test_equality_distinguishes_boolean_numbers_and_keeps_number_and_key_equivalence(self):
        for left, right in [(1, 1.0), ({'b': [1, False], 'a': 2}, {'a': 2.0, 'b': [1.0, False]})]:
            self.assertTrue(controls.equivalent(left, right))
        for left, right in [(1, True), (0, False), ({'n': 1}, {'n': True}), ([1, 2], [2, 1]), (None, False), ('1', 1)]:
            self.assertFalse(controls.equivalent(left, right))

    def test_nonfinite_numbers_and_unsupported_values_rejected(self):
        for value in [float('nan'), float('inf'), -float('inf'), {'deep': [float('inf')]}, (1,), {1: 'key'}]:
            with self.subTest(value=value), self.assertRaises(LabError):
                controls.generate(self.anchor(value), POLICY)

    def test_deterministic_unique_probes_do_not_modify_the_source(self):
        anchor = self.anchor(EXPECTED)
        before = copy.deepcopy(anchor)
        rows, details = controls.generate(anchor, POLICY)
        self.assertEqual((rows, details), controls.generate(anchor, POLICY))
        self.assertEqual(anchor, before)
        self.assertEqual(len({controls.encoded(row['output']) for row in rows}), len(rows))
        self.assertNotIn(controls.encoded(EXPECTED), {controls.encoded(row['output']) for row in rows})
        self.assertEqual({row['family'] for row in rows}, set(controls.FAMILIES))
        # Explicit witnesses exercise both valid alternatives and plausible wrong
        # outputs independently of whatever the generator marks pass/fail.
        witnesses = {row['family']: [] for row in rows}
        for row in rows:
            witnesses[row['family']].append(row)
        reordered = witnesses['object_key_order'][0]
        self.assertEqual(list(reordered['output']), ['ok', 'items', 'answer'])
        self.assertEqual(reordered['fails'], [])
        self.assertTrue(any(type(row['output']['answer']) is float and row['fails'] == [] for row in witnesses['number_representation']))
        self.assertTrue(any(type(row['output']) is dict and row['output'].get('answer') is True and row['fails'] == ['correct'] for row in witnesses['type_mismatch']))
        self.assertTrue(any(row['output']['items'] == [2, 1] and row['fails'] == ['correct'] for row in witnesses['array_order']))
        self.assertTrue(any('answer' not in row['output'] for row in witnesses['missing_field']))

    def test_cap_preserves_diversity_and_discloses_missing_coverage(self):
        contract = {'criteria': [{'id': 'correct'}], 'generated_controls': {**POLICY, 'max_per_anchor': 2}, 'anchors': [self.anchor(EXPECTED)]}
        summary = controls.coverage_summary(contract)
        self.assertEqual(summary['generated_controls'], 2)
        self.assertEqual(summary['positive_controls'], 2)
        self.assertGreater(summary['omitted_by_cap'], 0)
        self.assertIn('type_mismatch', summary['applicable_but_unselected_families'])
        contract['anchors'] = [self.anchor(None)]
        summary = controls.coverage_summary(contract)
        self.assertIn('object_key_order', summary['no_applicable_unique_probe'])
        self.assertIn('array_order', summary['no_applicable_unique_probe'])
        self.assertEqual(summary['positive_controls'], 0)
        self.assertEqual(summary['families']['type_mismatch']['declared_groups'], 1)

    def test_declared_duplicates_are_not_new_generated_controls(self):
        anchor = self.anchor(1)
        anchor['mutations'] = [{'output': None}, {'output': False}]
        rows, _ = controls.generate(anchor, POLICY)
        self.assertNotIn('null', {controls.encoded(row['output']) for row in rows})
        self.assertNotIn('false', {controls.encoded(row['output']) for row in rows})
        self.assertIn('true', {controls.encoded(row['output']) for row in rows})

    def test_large_or_deep_anchors_fail_closed(self):
        for value in [list(range(128)), 'x' * 65537]:
            with self.assertRaises(LabError):
                controls.generate(self.anchor(value), POLICY)
        value = None
        for _ in range(17):
            value = [value]
        with self.assertRaises(LabError):
            controls.generate(self.anchor(value), POLICY)


class GeneratedControlIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def start(self, predicate=GOOD_PREDICATE, *, enabled=True):
        self.suite, self.app, self.state = configure_exact(self.root, predicate, enabled=enabled)
        return initialize(self.suite, self.app, self.state, approvals=APPROVALS)

    def test_good_fixture_passes_all_controls_with_accounting_and_bound_coverage(self):
        self.suite, self.app, self.state = configure_exact(self.root)
        with patch('codex_eval_lab.oracle.invoke', side_effect=AssertionError('read only')):
            plan = automation.make_plan(self.suite, self.app)
        cfg = load_config(self.suite)
        contract = oracle.load_contract(self.suite, cfg)
        requests = oracle.all_requests(self.suite, cfg, contract)
        self.assertEqual(plan['budget_projection']['oracle_preflight_calls'], len(requests))
        initialize(self.suite, self.app, self.state, approvals=APPROVALS)
        receipt = read_json(self.state / 'oracle-receipt.json')
        gate = oracle.validate_receipt(self.suite, cfg, receipt)
        self.assertEqual(len(receipt['results']), len(requests))
        self.assertEqual(gate['control_coverage'], controls.coverage_summary(contract))
        self.assertEqual(gate['case_consistency_cases'], 6)
        self.assertGreater(gate['control_coverage']['positive_controls'], 0)
        self.assertGreater(gate['control_coverage']['negative_controls'], 0)
        self.assertFalse(gate['human_reviewed'])
        self.assertNotIn('SECRET-', json.dumps(gate['control_coverage']))
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.budget()['trials'], len(requests))
        with patch('codex_eval_lab.oracle.invoke', side_effect=AssertionError('no replay')):
            self.assertEqual(oracle.validate_receipt(self.suite, cfg, receipt), gate)

    def test_weak_python_equality_passes_old_controls_but_generated_controls_detect_boolean_coercion(self):
        with tempfile.TemporaryDirectory() as tmp:
            suite, app, state = configure_exact(Path(tmp), 'ok=r["output"]==r["expected"]', enabled=False)
            initialize(suite, app, state, approvals=APPROVALS)
        with self.assertRaisesRegex(LabError, 'positive or known-wrong'):
            self.start('ok=r["output"]==r["expected"]')
        receipt = read_json(self.state / 'oracle-receipt.json')
        self.assertEqual(receipt['status'], 'failed')
        contract = oracle.load_contract(self.suite, load_config(self.suite))
        row = next(row for row in oracle.requests(contract) if row['id'] == receipt['results'][-1]['id'])
        self.assertEqual(row['generated_family'], 'type_mismatch')
        self.assertEqual(row['request']['output']['answer'], True)
        self.assertIs(type(row['request']['output']['answer']), bool)
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.pending(), 0)
            self.assertEqual(store.budget()['trials'], len(receipt['results']))
        self.assertTrue((self.state / 'initialization-failed.json').exists())

    def test_object_order_probe_reaches_grader_without_canonicalization(self):
        with self.assertRaisesRegex(LabError, 'positive or known-wrong'):
            self.start(GOOD_PREDICATE + '\nok=ok and list(r["output"])==["answer","items","ok"] if type(r["output"]) is dict else False\n')
        receipt = read_json(self.state / 'oracle-receipt.json')
        self.assertEqual(receipt['results'][-1]['id'], 'anchor-0:generated:000')
        self.assertEqual(receipt['results'][-1]['response']['metrics']['quality'], 0)

    def test_numeric_spelling_probe_detects_rejection_of_correct_float(self):
        with self.assertRaisesRegex(LabError, 'positive or known-wrong'):
            self.start('ok=json.dumps(r["output"],sort_keys=True)==json.dumps(r["expected"],sort_keys=True)')
        receipt = read_json(self.state / 'oracle-receipt.json')
        contract = oracle.load_contract(self.suite, load_config(self.suite))
        row = next(row for row in oracle.requests(contract) if row['id'] == receipt['results'][-1]['id'])
        self.assertEqual(row['generated_family'], 'number_representation')
        self.assertEqual(row['fails'], [])

    def test_wrong_field_and_order_semantics_cannot_hide_behind_trivial_negatives(self):
        predicates = {
            'ignores_field': 'ok=type(r["output"]) is dict and r["output"].get("answer")==1',
            'ignores_extra_field': 'ok=type(r["output"]) is dict and all(r["output"].get(k)==v for k,v in r["expected"].items())',
            'unordered_array': GOOD_PREDICATE.replace('value["items"][0] == 1 and value["items"][1] == 2', 'sorted(value["items"]) == [1, 2]'),
        }
        for name, predicate in predicates.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                old = root / 'old'; old.mkdir()
                suite, app, state = configure_exact(old, predicate, enabled=False)
                initialize(suite, app, state, approvals=APPROVALS)
                new = root / 'new'; new.mkdir()
                suite, app, state = configure_exact(new, predicate)
                with self.assertRaisesRegex(LabError, 'positive or known-wrong'):
                    initialize(suite, app, state, approvals=APPROVALS)
                self.assertEqual(read_json(state / 'oracle-receipt.json')['status'], 'failed')

    def test_reference_accepts_equivalent_number_spelling_but_rejects_boolean(self):
        suite, app, state = configure_oracle(self.root)
        cfg = load_config(suite)
        contract = oracle.load_contract(suite, cfg)
        contract['generated_controls'] = POLICY
        row = oracle.requests(contract)[0]
        oracle.check_response(row, {'output': 1.0, 'usage': {'cost_usd': 0}}, contract, cfg)
        with self.assertRaisesRegex(LabError, 'disagrees'):
            oracle.check_response(row, {'output': True, 'usage': {'cost_usd': 0}}, contract, cfg)

    def test_opt_in_policy_is_strict_and_old_contract_counts_unchanged(self):
        suite, app, state = configure_oracle(self.root)
        cfg = load_config(suite)
        old = oracle.load_contract(suite, cfg)
        self.assertEqual(len(oracle.all_requests(suite, cfg, old)), 18)
        self.assertEqual(controls.coverage_summary(old)['mode'], 'declared_only')
        invalid = [None, {}, {**POLICY, 'kind': 'semantic'}, {**POLICY, 'numeric_equality': 'strict_types'},
                   {**POLICY, 'criterion': 'missing'}, {**POLICY, 'max_per_anchor': True},
                   {**POLICY, 'max_per_anchor': 65}, {**POLICY, 'unknown': True}]
        for policy in invalid:
            contract = copy.deepcopy(old)
            contract['generated_controls'] = policy
            write_json(suite / 'oracle.json', contract)
            with self.subTest(policy=policy), self.assertRaises(LabError):
                audit(suite)
        contract = copy.deepcopy(old)
        contract['generated_controls'] = POLICY
        contract['anchors'][0]['mutations'][0]['output'] = 1.0
        write_json(suite / 'oracle.json', contract)
        with self.assertRaisesRegex(LabError, 'distinct from correct'):
            audit(suite)

    def test_budget_exhaustion_cannot_dispatch_unreserved_generated_probe(self):
        suite, app, state = configure_exact(self.root)
        p = suite / 'eval.toml'
        p.write_text(p.read_text().replace('max_trials = 1000', 'max_trials = 3'))
        with self.assertRaisesRegex(LabError, 'Trial budget'):
            initialize(suite, app, state, approvals=APPROVALS)
        receipt = read_json(state / 'oracle-receipt.json')
        self.assertEqual(len(receipt['results']), 3)
        self.assertTrue(all(':generated:' not in row['id'] for row in receipt['results']))
        with Store(state / 'state.sqlite3') as store:
            self.assertEqual(store.budget()['trials'], 3)

    def test_generated_receipt_tampering_rejected_without_reexecution(self):
        self.start()
        cfg = load_config(self.suite)
        receipt = read_json(self.state / 'oracle-receipt.json')
        row = next(row for row in receipt['results'] if ':generated:' in row['id'])
        row['request_sha256'] = 'changed-wire-order-binding'
        with patch('codex_eval_lab.oracle.invoke', side_effect=AssertionError('no replay')), self.assertRaisesRegex(LabError, 'missing, changed or failed'):
            oracle.validate_receipt(self.suite, cfg, receipt)

    def test_generated_calls_are_included_in_the_preflight_cap(self):
        suite, _, _ = configure_exact(self.root)
        contract = read_json(suite / 'oracle.json')
        template = contract['anchors'][0]
        contract['anchors'] = [{**copy.deepcopy(template), 'id': f'anchor-{i}', 'group': f'anchor-{i}',
                                'input': {'boundary': i}} for i in range(32)]
        write_json(suite / 'oracle.json', contract)
        with self.assertRaisesRegex(LabError, 'preflight exceeds 1000'):
            audit(suite)


if __name__ == '__main__':
    unittest.main()
