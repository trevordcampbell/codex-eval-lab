"""Offline, executable controls and native end-to-end automation regressions."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab import automation, oracle
from codex_eval_lab.config import audit, load_config
from codex_eval_lab.engine import initialize, manifest_for, run, register
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError, read_json, write_json
from .helpers import make_fixture

APPROVALS = {"cases": True, "grader": True, "execution": True}


def configure_oracle(root, *, cases_per_split=2, paired=False):
    suite, app, state = make_fixture(root, cases_per_split=cases_per_split)
    cfg = (suite / "eval.toml").read_text().replace('harness_paths = ["grader.py", "demo_optimizer.py"]', 'harness_paths = ["grader.py", "demo_optimizer.py", "reference.py", "spec.txt"]')
    if paired:
        cfg += '\n[measurement]\ndesign = "paired_ab_ba"\n'
    cfg += '\n[oracle]\ncontract = "oracle.json"\n'
    (suite / "eval.toml").write_text(cfg)
    (suite / "spec.txt").write_text("Regression fixture only: return 1 for every request. This is not production data or a human reviewed label set.")
    (suite / "reference.py").write_text('import json,sys\njson.load(sys.stdin)\njson.dump({"output":1,"usage":{"cost_usd":0}},sys.stdout)\n')
    (suite / "grader.py").write_text('import json,sys\nr=json.load(sys.stdin)\nok=r["output"]==r["expected"]\njson.dump({"metrics":{"quality":int(ok)},"usage":{"cost_usd":0},"criterion_results":{"correct":{"status":"pass" if ok else "fail","explanation":"Exact match"}}},sys.stdout)\n')
    contract = {"schema_version": 1, "claim_scope": "Synthetic constant-return protocol test, no model-performance claim",
                "source": {"kind": "synthetic", "reference": "Offline regression fixture"},
                "author": {"kind": "model", "reference": "Codex-authored test fixture; not human labels"},
                "reference_command": ["{python}", "-S", "{suite}/reference.py"],
                "reference_rationale": "Separate trivial implementation checked against the written constant-output specification; not proof of domain truth.",
                "specifications": ["spec.txt"], "criteria": [{"id": "correct", "metric": "quality"}],
                "measurement_metrics": [], "trust_assumptions": ["The fixture specification intentionally defines this toy task."],
                "max_wall_time_s": 30, "anchors": []}
    for i in range(2):
        contract["anchors"].append({"id": f"anchor-{i}", "group": f"anchor-{i}", "role": "development", "basis": "specification_derived", "source_ref": "spec.txt",
                                   "derivation": "The literal constant-output contract gives expected 1 for this boundary input.",
                                   "input": {"boundary": i}, "expected": 1, "output": 1,
                                   "mutations": [{"id": "wrong", "output": 0, "fails": ["correct"]}]})
    optimizer = suite / 'demo_optimizer.py'
    optimizer.write_text(optimizer.read_text().replace('"edits":[{"path":"app.py","content":s}]', '"edits":[] if s==Path("app.py").read_text() else [{"path":"app.py","content":s}]'))
    write_json(suite / "oracle.json", contract)
    return suite, app, state


class OracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.suite, self.app, self.state = configure_oracle(self.root)

    def modify_contract(self, change):
        c = read_json(self.suite / "oracle.json")
        change(c)
        write_json(self.suite / "oracle.json", c)

    def start(self):
        return initialize(self.suite, self.app, self.state, approvals=APPROVALS)

    def test_audit_and_plan_do_not_execute_or_create_receipts(self):
        with patch('codex_eval_lab.oracle.invoke', side_effect=AssertionError("No execution")):
            result = audit(self.suite)
            plan = automation.make_plan(self.suite, self.app)
        self.assertEqual(result['oracle_gate']['status'], 'execution_required')
        self.assertFalse(result['oracle_gate']['ready'])
        self.assertEqual(plan['budget_projection']['oracle_preflight_calls'], 18)
        self.assertFalse(self.state.exists())

    def test_executed_controls_have_truthful_provenance_raw_results_and_accounting(self):
        self.start()
        receipt = read_json(self.state / 'oracle-receipt.json')
        self.assertEqual(receipt['status'], 'completed')
        self.assertEqual(len(receipt['results']), 18)
        self.assertTrue(all(r['stdout'] and r['status'] == 'ok' for r in receipt['results']))
        with Store(self.state / 'state.sqlite3') as s:
            m = manifest_for(self.state, s)
            self.assertEqual(s.budget()['trials'], 18)
            self.assertFalse(m['oracle_gate']['human_reviewed'])
            self.assertEqual(m['oracle_gate']['author_kind'], 'model')
            self.assertEqual(m['oracle_gate']['status'], 'executable_checks_passed')
            self.assertEqual(len(s.results('oracle-preflight', 'oracle')), 18)
        self.assertEqual(run(self.state, 'baseline', 'train')['trials'], 2)

    def test_forged_ready_flags_rejected(self):
        self.modify_contract(lambda c: c.update(ready=True, human_approved=True))
        with self.assertRaises(LabError):
            self.start()
        self.assertFalse(self.state.exists())

    def test_always_pass_grader_fails_and_retains_negative_receipt(self):
        p = self.suite / 'grader.py'
        p.write_text(p.read_text().replace('ok=r["output"]==r["expected"]', 'ok=True'))
        with self.assertRaisesRegex(LabError, 'positive or known-wrong'):
            self.start()
        self.assertTrue((self.state / 'initialization-failed.json').exists())
        self.assertEqual(read_json(self.state / 'oracle-receipt.json')['status'], 'failed')
        with Store(self.state / 'state.sqlite3') as s:
            self.assertEqual(s.budget()['trials'], 3)
            self.assertEqual(s.pending(), 0)
        with self.assertRaisesRegex(LabError, 'already exists'):
            self.start()

    def test_wrong_reference_fails_before_accepting_anchor(self):
        p = self.suite / 'reference.py'
        p.write_text(p.read_text().replace('"output":1', '"output":0'))
        with self.assertRaisesRegex(LabError, 'disagrees'):
            self.start()

    def test_source_mutating_check_rejected_but_original_unchanged(self):
        p = self.suite / 'reference.py'
        p.write_text(p.read_text() + '\nopen("reference.py", "a").write("#mutate")\n')
        before = p.read_bytes()
        with self.assertRaisesRegex(LabError, 'changed its source copy'):
            self.start()
        self.assertEqual(before, p.read_bytes())

    def test_weak_controls_and_model_consensus_cannot_upgrade_readiness(self):
        changes = [lambda c: c['anchors'].pop(),
                   lambda c: c['anchors'][1].update(group='anchor-0'),
                   lambda c: c['anchors'][1].update(mutations=[]),
                   lambda c: c['anchors'][0].update(basis='two_model_agreement'),
                   lambda c: c['anchors'][0]['mutations'][0].update(output=1),
                   lambda c: c['anchors'][0]['mutations'][0].update(id='positive'),
                   lambda c: c.update(reference_command=['{python}', '{suite}/grader.py']),
                   lambda c: c.update(specifications=['unbound.txt'])]
        original = read_json(self.suite / 'oracle.json')
        for change in changes:
            c = copy.deepcopy(original); change(c); write_json(self.suite / 'oracle.json', c)
            with self.subTest(change=change), self.assertRaises(LabError):
                audit(self.suite)

    def test_private_id_group_and_input_overlap_rejected(self):
        original = read_json(self.suite / 'oracle.json')
        for change in ({'id': 'test-0'}, {'group': 'validation-1'}, {'input': {'split_marker': 'SECRET-test-0', 'n': 0}}, {'role': 'final'}):
            c = copy.deepcopy(original); c['anchors'][0].update(change); write_json(self.suite / 'oracle.json', c)
            with self.subTest(change=change), self.assertRaises(LabError):
                audit(self.suite)

    def test_receipt_mutation_invalidates_frozen_experiment(self):
        self.start()
        p = self.state / 'oracle-receipt.json'
        receipt = read_json(p); receipt['results'][0]['response']['output'] = 999; write_json(p, receipt)
        with self.assertRaises(LabError):
            run(self.state, 'baseline', 'train')

    def test_unknown_cost_is_conservatively_charged(self):
        p = self.suite / 'eval.toml'
        p.write_text(p.read_text().replace('max_eval_cost_usd = 0.0', 'max_eval_cost_usd = 100.0').replace('trial_reserve_usd = 0.0', 'trial_reserve_usd = 0.25'))
        (self.suite / 'reference.py').write_text('raise RuntimeError("unknown call outcome")')
        with self.assertRaises(LabError):
            self.start()
        with Store(self.state / 'state.sqlite3') as s:
            self.assertEqual(s.budget()['eval_charged_usd'], .25)
            self.assertEqual(s.budget()['trials'], 1)

    def test_paid_preflight_is_error_with_actual_charge_preserved(self):
        p = self.suite / 'reference.py'; p.write_text(p.read_text().replace('"cost_usd":0', '"cost_usd":3'))
        with self.assertRaisesRegex(LabError, 'nonzero'):
            self.start()
        with Store(self.state / 'state.sqlite3') as s:
            self.assertEqual(s.budget()['eval_charged_usd'], 3)

    def test_preflight_reservation_blocks_before_execution(self):
        p = self.suite / 'eval.toml'; p.write_text(p.read_text().replace('max_trials = 1000', 'max_trials = 1'))
        with self.assertRaisesRegex(LabError, 'Trial budget'):
            self.start()
        with Store(self.state / 'state.sqlite3') as s:
            self.assertEqual(s.budget()['trials'], 1)

    def test_model_or_external_grader_cannot_be_hidden_as_semantic_calibration(self):
        p = self.suite / 'eval.toml'; p.write_text(p.read_text() + '\n[evidence]\nbundle="expert.json"\n')
        with self.assertRaisesRegex(LabError, 'mixed semantic'):
            load_config(self.suite)


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.suite, self.app, self.state = configure_oracle(self.root)

    def plan(self):
        return automation.make_plan(self.suite, self.app)

    def execute(self, plan=None):
        return automation.start_automation(self.suite, self.app, self.state, plan or self.plan(), approved=True,
                                           authorization_note='Explicitly invoked offline regression fixture, scoped local execution through final test, no paid model calls.')

    def test_full_automated_lifecycle_without_human_label_claim(self):
        result = self.execute()
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['final_result']['accepted'])
        self.assertEqual(result['best'], 'round-0001')
        self.assertFalse(result['readiness']['human_reviewed'])
        self.assertEqual(result['readiness']['evidence_basis'], 'executable_oracle_validated')
        self.assertTrue((self.state / 'report.html').exists())
        self.assertTrue((self.state / 'automation-result.json').exists())
        again = automation.resume_automation(self.state)
        self.assertEqual(again['budget']['trials'], result['budget']['trials'])
        self.assertEqual(again['budget']['optimizer_calls'], result['budget']['optimizer_calls'])
        with self.assertRaises(LabError):
            register(self.state, self.app, 'late', 'Cannot reopen winner')

    def test_no_authority_or_empty_note_creates_no_state(self):
        for approved, note in [(False, 'user intent'), (True, '')]:
            with self.assertRaises(LabError):
                automation.start_automation(self.suite, self.app, self.state, self.plan(), approved=approved, authorization_note=note)
            self.assertFalse(self.state.exists())

    def test_mutable_or_edited_plan_rejected_before_execution(self):
        plan = self.plan(); plan['budget']['max_trials'] += 100
        with self.assertRaisesRegex(LabError, 'Plan no longer matches'):
            self.execute(plan)
        self.assertFalse(self.state.exists())

    def test_changed_baseline_after_plan_rejected(self):
        plan = self.plan(); p = self.app / 'app.py'; p.write_text(p.read_text() + '#later\n')
        with self.assertRaisesRegex(LabError, 'Plan no longer matches'):
            self.execute(plan)

    def test_search_reserves_enough_capacity_for_final(self):
        p = self.suite / 'eval.toml'; p.write_text(p.read_text().replace('max_trials = 1000', 'max_trials = 30'))
        result = self.execute()
        self.assertEqual(result['selection']['stop_reason'], 'final_budget_reserved')
        self.assertEqual(result['budget']['trials'], 30)
        self.assertEqual(result['budget']['optimizer_calls'], 1)
        self.assertTrue(result['final_result']['accepted'])

    def test_insufficient_budget_is_rejected_by_readonly_plan(self):
        p = self.suite / 'eval.toml'; p.write_text(p.read_text().replace('max_trials = 1000', 'max_trials = 29'))
        with self.assertRaisesRegex(LabError, 'Budget cannot cover'):
            self.plan()
        self.assertFalse(self.state.exists())

    def test_legacy_ungated_suite_cannot_auto_upgrade(self):
        p = self.suite / 'eval.toml'; p.write_text(p.read_text().split('[oracle]')[0])
        with self.assertRaisesRegex(LabError, 'unverified model'):
            self.plan()
        initialize(self.suite, self.app, self.state, approvals=APPROVALS)
        with self.assertRaisesRegex(LabError, 'no frozen'):
            automation.resume_automation(self.state)

    def test_interrupted_round_resumes_existing_proposal(self):
        from codex_eval_lab.optimizer import run_internal as actual_run
        def interrupt(state, store, manifest, label, split, **kwargs):
            if label == 'round-0001' and split == 'validation':
                raise LabError('interrupted before dispatch')
            return actual_run(state, store, manifest, label, split, **kwargs)
        with patch('codex_eval_lab.optimizer.run_internal', side_effect=interrupt), self.assertRaisesRegex(LabError, 'interrupted'):
            self.execute()
        with Store(self.state / 'state.sqlite3') as s:
            self.assertEqual(s.budget()['optimizer_calls'], 1)
            self.assertIsNone(s.get('final_selection'))
        result = automation.resume_automation(self.state)
        self.assertTrue(result['final_result']['accepted'])
        self.assertEqual(result['budget']['optimizer_calls'], 2)  # second fixture proposal is a no-op; no replay of first

    def test_paired_lifecycle_retains_new_paired_final_and_budget(self):
        p = self.suite / 'eval.toml'; p.write_text(p.read_text() + '\n[measurement]\ndesign="paired_ab_ba"\n')
        result = self.execute()
        self.assertTrue(result['final_result']['accepted'])
        self.assertEqual(result['final_result']['final_selection']['measurement_design'], 'paired_ab_ba')

    def test_bad_proposal_blocks_finalization_without_erasing_history(self):
        (self.suite / 'demo_optimizer.py').write_text('print("not-json")')
        with self.assertRaisesRegex(LabError, 'before finalization'):
            self.execute()
        with Store(self.state / 'state.sqlite3') as s:
            self.assertIsNone(s.get('final_selection'))
            self.assertEqual(s.budget()['optimizer_calls'], 1)
            self.assertIsNotNone(s.get('automation_blocker'))

class OracleAccountingAdversarialTests(unittest.TestCase):
    setUp = OracleTests.setUp
    start = OracleTests.start
    modify_contract = OracleTests.modify_contract
    # Independent-review regressions. Inherits setup and shared oracle invariants.
    def test_existing_ledger_without_receipt_cannot_dispatch_again(self):
        import time
        self.state.mkdir()
        cfg = load_config(self.suite)
        with Store(self.state / 'state.sqlite3') as store:
            row = oracle.requests(oracle.load_contract(self.suite, cfg))[0]
            store.reserve('oracle-preflight', 'oracle', row['id'], 0, cfg['budget'])
            store.complete('oracle-preflight', 'oracle', row['id'], 0, {'status': 'ok'}, 0)
            with patch('codex_eval_lab.oracle.invoke', side_effect=AssertionError('must not dispatch')), self.assertRaisesRegex(LabError, 'fresh execution ledger'):
                oracle.preflight(self.suite, cfg, self.state / 'oracle-receipt.json', store, expires_at=time.time() + 30)
            self.assertEqual(store.budget()['trials'], 1)

    def test_lost_receipt_cannot_delete_durable_reservations(self):
        def reserve_then_fail(suite, cfg, output, store, **kwargs):
            store.reserve('oracle-preflight', 'oracle', 'reserved-control', 0, cfg['budget'])
            raise LabError('Receipt missing after reservation')
        with patch('codex_eval_lab.oracle.preflight', side_effect=reserve_then_fail), self.assertRaises(LabError):
            self.start()
        self.assertTrue((self.state / 'initialization-failed.json').exists())
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.pending(), 1)
            self.assertEqual(store.budget()['trials'], 1)

    def test_failed_process_complete_json_cost_is_not_discarded(self):
        p = self.suite / 'reference.py'
        p.write_text(p.read_text().replace('"cost_usd":0', '"cost_usd":3') + '\nsys.exit(1)\n')
        with self.assertRaises(LabError):
            self.start()
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.budget()['eval_charged_usd'], 3)

    def test_audit_does_not_demand_human_labels_for_exact_controls(self):
        result = audit(self.suite)
        self.assertNotIn('Human-reviewed labels and rubric calibration', result['human_checks'])
        self.assertFalse(any('Evidence gate not configured' in x for x in result['warnings']))

class AutomationInterruptionTests(unittest.TestCase):
    setUp = AutomationTests.setUp
    plan = AutomationTests.plan
    execute = AutomationTests.execute
    def test_response_before_active_commit_cannot_buy_another_call(self):
        from codex_eval_lab.optimizer import generate_proposal
        def interrupt(*a, **kw):
            generate_proposal(*a, **kw)
            raise KeyboardInterrupt('after response, before active commit')
        with patch('codex_eval_lab.optimizer.generate_proposal', side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            self.execute()
        with patch('codex_eval_lab.optimizer.generate_proposal', side_effect=AssertionError('no replay')), self.assertRaisesRegex(LabError, 'unresolved'):
            automation.resume_automation(self.state)
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.budget()['optimizer_calls'], 1)
            self.assertEqual(store.unresolved_optimizers(), 1)
            self.assertIsNone(store.get('final_selection'))
            store.recover()
        with self.assertRaisesRegex(LabError, 'unresolved'):
            automation.resume_automation(self.state)

class OracleProtocolTests(unittest.TestCase):
    setUp = OracleTests.setUp
    start = OracleTests.start
    modify_contract = OracleTests.modify_contract
    def test_boolean_metric_is_not_a_numeric_grade(self):
        p = self.suite / 'grader.py'; p.write_text(p.read_text().replace('int(ok)', 'ok'))
        with self.assertRaisesRegex(LabError, 'finite number'):
            self.start()

    def test_duplicate_input_cannot_supply_two_independent_groups(self):
        self.modify_contract(lambda c: c['anchors'][1].update(input=c['anchors'][0]['input']))
        with self.assertRaisesRegex(LabError, 'Duplicate oracle inputs'):
            self.start()


    def test_grader_environment_mismatch_rejected_before_dispatch(self):
        p = self.suite / 'eval.toml'
        p.write_text(p.read_text().replace('mode = "local"', 'mode = "local"\ngrader_env = ["GRADER_MODE"]'))
        with patch('codex_eval_lab.oracle.invoke', side_effect=AssertionError('must not execute')), self.assertRaisesRegex(LabError, 'empty grader_env'):
            self.start()

    def test_direct_suite_executable_reference_and_grader_supported(self):
        import sys
        c = read_json(self.suite / 'oracle.json')
        c['reference_command'] = ['{suite}/reference.py']
        write_json(self.suite / 'oracle.json', c)
        p = self.suite / 'eval.toml'
        p.write_text(p.read_text().replace('grader_command = ["{python}", "-S", "{suite}/grader.py"]', 'grader_command = ["{suite}/grader.py"]'))
        for name in ['reference.py', 'grader.py']:
            p = self.suite / name
            p.write_text('#!' + sys.executable + '\n' + p.read_text())
            p.chmod(0o755)
        self.start()
        environment = read_json(self.state / 'oracle-receipt.json')['environment']
        self.assertIn('{suite}/reference.py', environment['executables_sha256'])
        self.assertEqual(run(self.state, 'baseline', 'train')['trials'], 2)

    def test_html_report_keeps_basis_scope_and_author_truthful_without_controls(self):
        from codex_eval_lab.report import render_report
        self.start()
        path = self.root / 'report.html'; render_report(self.state, path)
        body = path.read_text()
        self.assertIn('executable_checks_passed', body)
        self.assertIn('Synthetic constant-return protocol test', body)
        self.assertIn('Codex-authored test fixture', body)
        self.assertNotIn('SECRET-validation', body)
        self.assertNotIn('SECRET-test', body)


    def test_wrong_frozen_case_label_blocks_even_when_anchors_pass(self):
        p = self.suite / 'cases.jsonl'
        rows = [json.loads(line) for line in p.read_text().splitlines()]
        rows[-1]['expected'] = 999
        p.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        with self.assertRaisesRegex(LabError, 'Private case-consistency'):
            self.start()
        receipt = read_json(self.state / 'oracle-receipt.json')
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(receipt['results'][-1]['id'], 'case:test-1:consistency')
        self.assertTrue(all(row['status'] == 'ok' for row in receipt['results'][:6]))

    def test_reference_receives_inputs_but_never_expected_labels(self):
        p = self.suite / 'reference.py'
        p.write_text(p.read_text().replace('json.load(sys.stdin)', 'request=json.load(sys.stdin)\nassert "expected" not in request'))
        self.start()
        gate = read_json(self.state / 'manifest.json')['oracle_gate']
        self.assertEqual(gate['case_consistency_cases'], 6)
        self.assertEqual(gate['case_consistency_status'], 'all_frozen_cases_passed')

    def test_artifact_cases_require_a_separate_supported_path(self):
        (self.suite / 'asset.txt').write_text('fixture')
        p = self.suite / 'cases.jsonl'
        rows = [json.loads(line) for line in p.read_text().splitlines()]
        rows[0]['assets'] = ['asset.txt']
        p.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        with self.assertRaisesRegex(LabError, 'JSON-only'):
            self.start()


    def test_case_consistency_preserves_reference_trace_and_runtime_grader_keys(self):
        p = self.suite / 'reference.py'
        p.write_text(p.read_text().replace('"output":1,', '"output":1,"trace":[{"content":"reference trace"}],'))
        p = self.suite / 'grader.py'
        p.write_text(p.read_text().replace('ok=r["output"]', 'assert "assets" not in r\nif r["case_id"].startswith(("train-", "validation-", "test-")): assert r["trace"] == [{"content":"reference trace"}]\nok=r["output"]'))
        self.start()

    def test_reference_artifact_outputs_fail_explicitly(self):
        p = self.suite / 'reference.py'
        p.write_text('import json,sys,pathlib\nr=json.load(sys.stdin)\npathlib.Path(r["artifacts_dir"], "result.txt").write_text("output")\njson.dump({"output":1,"usage":{"cost_usd":0}},sys.stdout)')
        with self.assertRaisesRegex(LabError, 'does not support.*output artifacts'):
            self.start()


    def test_total_oracle_calls_are_capped_including_dataset_checks(self):
        p = self.suite / 'cases.jsonl'
        rows = [json.loads(line) for line in p.read_text().splitlines()]
        for n in range(500):
            rows.append({'id': f'extra-{n}', 'group': f'extra-{n}', 'split': 'train', 'input': {'extra': n}, 'expected': 1, 'tags': ['constant']})
        p.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        with self.assertRaisesRegex(LabError, 'Combined.*1000'):
            audit(self.suite)


class AutomationCliTests(unittest.TestCase):
    setUp = AutomationTests.setUp

    def test_cli_plan_automate_and_resume_emit_durable_results(self):
        from codex_eval_lab.cli import parser, dispatch
        plan_path = self.root / 'plan.json'
        dispatch(parser().parse_args(['automation-plan', str(self.suite), '--app', str(self.app), '--out', str(plan_path)]))
        self.assertFalse(self.state.exists())
        result = dispatch(parser().parse_args(['automate', str(self.suite), '--app', str(self.app), '--state', str(self.state), '--plan', str(plan_path), '--approve-plan', '--authorization-note', 'Offline CLI test with final scope']))
        self.assertEqual(result['status'], 'completed')
        again = dispatch(parser().parse_args(['resume-automation', str(self.state)]))
        self.assertEqual(result['budget'], again['budget'])

    def test_boolean_substitution_does_not_bypass_exact_plan_binding(self):
        plan = automation.make_plan(self.suite, self.app)
        plan['schema_version'] = True
        with self.assertRaisesRegex(LabError, 'Plan no longer matches'):
            automation.start_automation(self.suite, self.app, self.state, plan, approved=True, authorization_note='Offline fixture')
        self.assertFalse(self.state.exists())


class OracleMetricCoverageTests(unittest.TestCase):
    setUp = OracleTests.setUp
    start = OracleTests.start

    def test_grader_cannot_supply_runner_owned_metrics(self):
        p = self.suite / 'grader.py'; p.write_text(p.read_text().replace('"quality":int(ok)', '"quality":int(ok),"cost_usd":0'))
        with self.assertRaisesRegex(LabError, 'runner-owned'):
            self.start()

    def test_grader_must_supply_all_declared_non_runner_metrics(self):
        p = self.suite / 'eval.toml'; p.write_text(p.read_text() + '\n[metrics.diagnostic]\nminimum=0\n')
        with self.assertRaisesRegex(LabError, 'missing or undeclared'):
            self.start()


class PrivatePreflightTests(unittest.TestCase):
    setUp = OracleTests.setUp
    start = OracleTests.start

    def test_private_unknown_fields_stay_in_receipt_not_public_errors(self):
        p = self.suite / 'reference.py'
        p.write_text('import json,sys\nr=json.load(sys.stdin)\nv={"output":1,"usage":{"cost_usd":0}}\nif r["case_id"].startswith("test-"):v["SECRET-final-field"]=True\njson.dump(v,sys.stdout)')
        with self.assertRaises(LabError) as caught:
            self.start()
        self.assertNotIn('SECRET-final-field', str(caught.exception))
        self.assertIn('SECRET-final-field', (self.state / 'oracle-receipt.json').read_text())

    def test_private_duplicate_json_keys_stay_in_receipt_not_public_errors(self):
        p = self.suite / 'reference.py'
        p.write_text('import json,sys\nr=json.load(sys.stdin)\nif r["case_id"].startswith("test-"):print(\'{"PRIVATE-duplicate":1,"PRIVATE-duplicate":2}\')\nelse:json.dump({"output":1,"usage":{"cost_usd":0}},sys.stdout)')
        with self.assertRaises(LabError) as caught:
            self.start()
        self.assertNotIn('PRIVATE-duplicate', str(caught.exception))
        self.assertIn('PRIVATE-duplicate', (self.state / 'oracle-receipt.json').read_text())

    def test_changed_private_receipt_is_rejected_before_interpreting_outputs(self):
        self.start()
        p = self.state / 'oracle-receipt.json'
        receipt = read_json(p)
        row = next(r for r in receipt['results'] if r['id'] == 'case:test-0:reference')
        row['response']['PRIVATE-corruption-marker'] = True
        write_json(p, receipt)
        with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('no execution')), self.assertRaises(LabError) as caught:
            run(self.state, 'baseline', 'train')
        self.assertNotIn('PRIVATE-corruption-marker', str(caught.exception))
        self.assertIn('receipt changed', str(caught.exception))


class GraderProtocolParityTests(unittest.TestCase):
    setUp = OracleTests.setUp

    def test_oracle_and_runtime_share_rejection_rules(self):
        from codex_eval_lab.engine import validate_grader_metrics
        cfg = load_config(self.suite)
        contract = oracle.load_contract(self.suite, cfg)
        row = next(r for r in oracle.requests(contract) if r['kind'] == 'grader')
        good = {'metrics': {'quality': 1}, 'usage': {'cost_usd': 0},
                'criterion_results': {'correct': {'status': 'pass', 'explanation': 'exact'}}}
        changes = [lambda g: g['metrics'].update(extra=1), lambda g: g['metrics'].clear(),
                   lambda g: g['metrics'].update(cost_usd=0), lambda g: g['metrics'].update(latency_s=1),
                   lambda g: g['metrics'].update(quality=True), lambda g: g['metrics'].update(quality=float('nan')),
                   lambda g: g['metrics'].update(quality=float('inf')), lambda g: g['metrics'].update(quality=2),
                   lambda g: g.pop('criterion_results'), lambda g: g['criterion_results']['correct'].update(status='abstain'),
                   lambda g: g['criterion_results']['correct'].update(status='fail'), lambda g: g.update(trace=[])]
        for change in changes:
            value = copy.deepcopy(good); change(value)
            with self.subTest(change=change):
                with self.assertRaises(LabError):
                    validate_grader_metrics(value, cfg, contract=contract['criteria'])
                with self.assertRaises(LabError):
                    oracle.check_response(row, value, contract, cfg)

    def test_reference_trace_shape_is_preserved_without_inventing_semantics(self):
        from codex_eval_lab.engine import response_object
        row = {'request': {'trace': None}, 'source_result_id': 'reference'}
        for trace in (None, [], [{'role': 'tool', 'content': 'x'}], {'opaque': 'trace'}, 'opaque trace'):
            response = {'output': 1, 'usage': {'cost_usd': 0}, 'trace': trace}
            self.assertIs(response_object(response), response)
            self.assertEqual(oracle.actual_request(row, {'reference': response})['trace'], trace)


class InvalidResponseAccountingTests(unittest.TestCase):
    def test_known_cost_survives_invalid_response_or_nonzero_exit(self):
        for stage in ('app', 'grader'):
            for invalid_field in (False, True):
                with self.subTest(stage=stage, invalid_field=invalid_field), tempfile.TemporaryDirectory() as tmp:
                    suite, app, state = make_fixture(Path(tmp), cases_per_split=2)
                    response = {'usage': {'cost_usd': 3}, 'output': 1} if stage == 'app' else {'usage': {'cost_usd': 3}, 'metrics': {'quality': 1}}
                    if invalid_field:
                        response['invalid'] = True
                    code = 'import json,sys\njson.load(sys.stdin)\njson.dump(' + repr(response) + ',sys.stdout)\n'
                    if not invalid_field:
                        code += 'sys.exit(1)\n'
                    (app / 'app.py' if stage == 'app' else suite / 'grader.py').write_text(code)
                    initialize(suite, app, state, approvals=APPROVALS)
                    with self.assertRaises(LabError):
                        run(state, 'baseline', 'train')
                    with Store(state / 'state.sqlite3') as store:
                        self.assertEqual(store.budget()['eval_charged_usd'], 3)
