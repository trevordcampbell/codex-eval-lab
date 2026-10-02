"""Offline regressions for additive native initialization and active-only evaluation.

These tests exercise product hardening, never the frozen comparative benchmark.
"""
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab import automation, native, paired
from codex_eval_lab.cli import dispatch, parser
from codex_eval_lab.engine import finalize, initialize, manifest_for
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError, digest, read_json, write_json
from .helpers import make_fixture
from .test_automation import configure_oracle
from .test_search_policy import POLICY


class NativeEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.suite, self.app, self.state = make_fixture(self.root, cases_per_split=2)
        (self.suite / 'eval.toml').write_text((self.suite / 'eval.toml').read_text() + POLICY)
        initialize(self.suite, self.app, self.state, approvals={'cases': True, 'grader': True, 'execution': True})

    def prepare(self, name='author'):
        return native.prepare_turn(self.state, self.root / name, approved=True,
                                   authorization_note='Authorized synthetic offline regression')

    def submit(self):
        call = self.prepare()
        response = self.root / 'proposal.json'
        code = (self.app / 'app.py').read_text().replace('"output":0', '"output":1')
        write_json(response, {'hypothesis': 'Correct constant fixture',
                             'edits': [{'path': 'app.py', 'content': code}], 'notes': 'Offline test'})
        native.submit_turn(self.state, call['call_id'], response, elapsed_s=1)
        return call['call_id']

    def evaluate(self, call_id=1):
        # Any fallback to generic loop, a reservation, or an optimizer fails.
        with ExitStack() as stack:
            for target in ('codex_eval_lab.optimizer.loop', 'codex_eval_lab.optimizer.generate_proposal',
                           'codex_eval_lab.optimizer.invoke', 'codex_eval_lab.store.Store.begin_optimizer'):
                stack.enter_context(patch(target, side_effect=AssertionError('Native evaluation must not dispatch')))
            return native.evaluate_turn(self.state, call_id)

    def budget(self):
        with Store(self.state / 'state.sqlite3') as store:
            return store.budget()

    def test_evaluate_and_duplicate_return_exact_bound_receipt_without_more_work(self):
        call_id = self.submit()
        result = self.evaluate(call_id)
        self.assertEqual(result['best'], 'round-0001')
        self.assertEqual(result['budget']['optimizer_calls'], 1)
        self.assertFalse(result['release_qualified'])
        before = self.budget()
        with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('Duplicate must not execute')):
            self.assertEqual(self.evaluate(call_id), result)
        self.assertEqual(self.budget(), before)
        with Store(self.state / 'state.sqlite3') as store:
            record = store.get('native_turn:1')
            self.assertEqual(record['status'], 'evaluated')
            self.assertEqual(record['evaluation_receipt_sha256'], digest(result))
            self.assertEqual(result['binding']['manifest_sha256'], store.get('manifest_digest'))
            self.assertEqual(result['binding']['source_hash'], store.variant('round-0001')['source_hash'])
            self.assertIsNone(store.get('active_round'))
            self.assertIsNone(store.get('final_selection'))
            self.assertEqual(store.results('baseline', 'test'), [])

    def test_missing_and_wrong_calls_never_reserve_or_dispatch(self):
        for call_id in (1, 99, 0, -1, True):
            with self.subTest(call_id=call_id), self.assertRaises(LabError):
                self.evaluate(call_id)
        self.assertEqual(self.budget()['optimizer_calls'], 0)
        self.submit()
        before = self.budget()
        with self.assertRaises(LabError):
            self.evaluate(2)
        self.assertEqual(self.budget(), before)

    def test_pending_and_indeterminate_author_block_evaluation_and_final(self):
        self.prepare()
        for recovered in (False, True):
            if recovered:
                with Store(self.state / 'state.sqlite3') as store:
                    store.recover()
            with self.assertRaisesRegex(LabError, 'Unresolved'):
                self.evaluate()
            with self.assertRaisesRegex(LabError, 'Unresolved'):
                finalize(self.state, approved=True)
            with Store(self.state / 'state.sqlite3') as store:
                self.assertIsNone(store.get('final_selection'))
                self.assertEqual(store.results('baseline', 'test'), [])
                self.assertEqual(store.budget()['optimizer_calls'], 1)

    def test_no_more_proposals_is_not_an_active_candidate(self):
        call = self.prepare()
        response = self.root / 'empty.json'
        write_json(response, {'hypothesis': 'Stop', 'edits': [], 'notes': 'No proposal'})
        native.submit_turn(self.state, call['call_id'], response, elapsed_s=1)
        before = self.budget()
        with self.assertRaises(LabError):
            self.evaluate()
        self.assertEqual(self.budget(), before)
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.get('search_terminal_stop'), 'no_more_proposals')

    def test_changed_active_binding_is_rejected_before_evaluation(self):
        self.submit()
        with Store(self.state / 'state.sqlite3') as store:
            active = store.get('active_round')
            active['native_binding']['call_id'] = 2
            store.put('active_round', active)
        before = self.budget()
        with self.assertRaisesRegex(LabError, 'changed active'):
            self.evaluate()
        self.assertEqual(self.budget(), before)

    def test_duplicate_does_not_hide_a_later_pending_author(self):
        self.submit()
        self.evaluate()
        self.prepare('second-author')
        before = self.budget()
        with self.assertRaisesRegex(LabError, 'Unresolved'):
            self.evaluate(1)
        self.assertEqual(self.budget(), before)

    def test_duplicate_does_not_hide_a_different_active_round(self):
        self.submit()
        self.evaluate()
        second = self.prepare('second-author')
        response = self.root / 'second.json'
        code = (self.state / 'candidates/round-0001/app.py').read_text() + '# Another source identity\n'
        write_json(response, {'hypothesis': 'Equivalent fixture', 'edits': [{'path': 'app.py', 'content': code}], 'notes': 'Test'})
        native.submit_turn(self.state, second['call_id'], response, elapsed_s=1)
        before = self.budget()
        with self.assertRaisesRegex(LabError, 'different or changed active'):
            self.evaluate(1)
        self.assertEqual(self.budget(), before)

    def test_candidate_source_tampering_blocks_first_and_duplicate_evaluation(self):
        self.submit()
        path = self.state / 'candidates/round-0001/app.py'
        original = path.read_text()
        path.write_text(original + '# changed\n')
        with self.assertRaisesRegex(LabError, 'Frozen candidate changed'):
            self.evaluate()
        path.write_text(original)
        self.evaluate()
        path.write_text(original + '# changed again\n')
        with self.assertRaisesRegex(LabError, 'Frozen candidate changed'):
            self.evaluate()

    def test_duplicate_rechecks_evaluator_and_response_receipts(self):
        self.submit()
        self.evaluate()
        for path in (self.state / 'evaluator/grader.py', self.state / 'native-runs/call-0001/evidence/response.json'):
            original = path.read_bytes()
            path.write_bytes(original + b' altered')
            with self.subTest(path=path), self.assertRaises(LabError):
                self.evaluate()
            path.write_bytes(original)

    def test_duplicate_rechecks_optimizer_result_and_decision_and_saved_receipt(self):
        self.submit()
        self.evaluate()
        with Store(self.state / 'state.sqlite3') as store:
            original_result = store.db.execute('SELECT result FROM optimizers WHERE id=1').fetchone()[0]
            store.db.execute("UPDATE optimizers SET result='{}' WHERE id=1")
            store.db.commit()
        with self.assertRaisesRegex(LabError, 'completion no longer matches'):
            self.evaluate()
        with Store(self.state / 'state.sqlite3') as store:
            store.db.execute('UPDATE optimizers SET result=? WHERE id=1', (original_result,))
            store.db.commit()
        path = self.state / 'decisions/round-0001.json'
        original = path.read_bytes()
        write_json(path, {})
        with self.assertRaisesRegex(LabError, 'decision export changed'):
            self.evaluate()
        path.write_bytes(original)
        with Store(self.state / 'state.sqlite3') as store:
            record = store.get('native_turn:1')
            record['evaluation_receipt']['best'] = 'baseline'
            store.put('native_turn:1', record)
        with self.assertRaisesRegex(LabError, 'receipt changed'):
            self.evaluate()

    def test_pending_and_recovered_trial_never_reexecute(self):
        self.submit()
        with Store(self.state / 'state.sqlite3') as store:
            manifest = manifest_for(self.state, store)
            store.reserve('round-0001', 'train', manifest['splits']['train'][0], 0, manifest['config']['budget'])
        before = self.budget()['trials']
        for recovered in (False, True):
            if recovered:
                with Store(self.state / 'state.sqlite3') as store:
                    store.recover()
            with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('No replay')):
                with self.assertRaisesRegex(LabError, 'Pending or indeterminate'):
                    self.evaluate()
            self.assertEqual(self.budget()['trials'], before)

    def test_completed_trial_boundary_resumes_without_duplicate_trial(self):
        self.submit()
        from codex_eval_lab import engine
        # Interrupt between whole matrix invocations, after development commits.
        with patch('codex_eval_lab.optimizer.run_internal', wraps=engine.run_internal) as run:
            def after_development(*args, **kwargs):
                result = engine.run_internal(*args, **kwargs)
                if args[-1] == 'train':
                    raise KeyboardInterrupt
                return result
            run.side_effect = after_development
            with self.assertRaises(KeyboardInterrupt):
                self.evaluate()
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(len(store.results('round-0001', 'train')), 2)
            self.assertEqual(store.pending(), 0)
        result = self.evaluate()
        self.assertEqual(result['budget']['trials'], 8)
        self.assertEqual(result['budget']['optimizer_calls'], 1)

    def test_history_commit_interruption_reconciles_without_more_trials(self):
        self.submit()
        original = Store.put
        interrupted = []
        def stop_after_history(store, key, value):
            original(store, key, value)
            if key == 'search_history' and not interrupted:
                interrupted.append(True)
                raise KeyboardInterrupt
        with patch.object(Store, 'put', stop_after_history), self.assertRaises(KeyboardInterrupt):
            self.evaluate()
        before = self.budget()
        with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('Committed trials must not replay')):
            result = self.evaluate()
        self.assertEqual(result['budget'], before)
        self.assertTrue((self.state / 'decisions/round-0001.json').is_file())

    def test_receipt_transaction_interruption_rolls_back_retirement_and_resumes(self):
        self.submit()
        original = Store.transaction
        @contextmanager
        def interrupt_receipt_commit(store):
            with original(store):
                yield
                record = store.get('native_turn:1')
                if record and record.get('status') == 'evaluated':
                    raise KeyboardInterrupt
        with patch.object(Store, 'transaction', interrupt_receipt_commit), self.assertRaises(KeyboardInterrupt):
            self.evaluate()
        before = self.budget()
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.get('native_turn:1')['status'], 'applied')
            self.assertIsNotNone(store.get('active_round'))
        with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('No repeated trials')):
            result = self.evaluate()
        self.assertEqual(result['budget'], before)
        self.assertEqual(result, self.evaluate())

    def test_report_interruption_after_completion_keeps_idempotent_receipt(self):
        self.submit()
        with patch('codex_eval_lab.report.render_report', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.evaluate()
        before = self.budget()
        with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('Completed calls must not replay')):
            result = self.evaluate()
        self.assertEqual(result['budget'], before)
        self.assertEqual(result['status'], 'evaluated')

    def test_expiry_blocks_new_evaluation_but_not_verified_completed_receipt(self):
        self.submit()
        expiry = read_json(self.state / 'manifest.json')['expires_at']
        with patch('codex_eval_lab.engine.time.time', return_value=expiry + 1), self.assertRaisesRegex(LabError, 'expired'):
            self.evaluate()
        receipt = self.evaluate()
        with patch('codex_eval_lab.engine.time.time', return_value=expiry + 1):
            self.assertEqual(self.evaluate(), receipt)

    def test_applied_round_blocks_final_seal_until_evaluated(self):
        self.submit()
        before = self.budget()
        with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('No final reveal')):
            with self.assertRaisesRegex(LabError, 'active evaluation round'):
                finalize(self.state, approved=True)
        self.assertEqual(self.budget(), before)
        with Store(self.state / 'state.sqlite3') as store:
            self.assertIsNone(store.get('final_selection'))
            self.assertEqual(store.results('baseline', 'test'), [])
            self.assertIsNone(store.cohort('final'))
        self.evaluate()
        self.assertTrue(finalize(self.state, approved=True)['release_qualified'])

    def test_nonfinal_pending_and_indeterminate_trials_block_new_seal(self):
        with Store(self.state / 'state.sqlite3') as store:
            manifest = manifest_for(self.state, store)
            store.reserve('baseline', 'train', manifest['splits']['train'][0], 0, manifest['config']['budget'])
        for recover in (False, True):
            if recover:
                with Store(self.state / 'state.sqlite3') as store:
                    store.recover()
            with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('No final reveal')):
                with self.assertRaisesRegex(LabError, 'Pending or indeterminate evaluation'):
                    finalize(self.state, approved=True)
            with Store(self.state / 'state.sqlite3') as store:
                self.assertIsNone(store.get('final_selection'))
                self.assertIsNone(store.cohort('final'))
                self.assertEqual(store.results('baseline', 'test'), [])
                self.assertEqual(store.budget()['trials'], 1)

    def test_interrupted_final_pending_and_recovery_never_reopen_or_reveal_more(self):
        with patch('codex_eval_lab.engine.perform_trial', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                finalize(self.state, approved=True)
        with Store(self.state / 'state.sqlite3') as store:
            seal = store.get('final_selection')
            self.assertIsNotNone(seal)
            self.assertEqual(store.pending(), 1)
        before = self.budget()['trials']
        for recover in (False, True):
            if recover:
                with Store(self.state / 'state.sqlite3') as store:
                    store.recover()
            with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('No extra final calls')):
                with self.assertRaisesRegex(LabError, 'Pending or indeterminate evaluation'):
                    finalize(self.state, approved=True)
            with Store(self.state / 'state.sqlite3') as store:
                self.assertEqual(store.get('final_selection'), seal)
                self.assertIsNone(store.get('final_result'))
                self.assertEqual(store.budget()['trials'], before)
            with self.assertRaises(LabError):
                self.prepare('cannot-reopen')

    def test_sealed_final_complete_boundary_resumes_same_selection(self):
        self.submit()
        self.evaluate()
        original = Store.reserve
        completed = []
        def stop_before_third(store, label, split, case_id, rep, budget, **kwargs):
            if split == 'test':
                if len(completed) == 2:
                    raise KeyboardInterrupt
                completed.append((label, case_id, rep))
            return original(store, label, split, case_id, rep, budget, **kwargs)
        with patch.object(Store, 'reserve', stop_before_third), self.assertRaises(KeyboardInterrupt):
            finalize(self.state, approved=True)
        with Store(self.state / 'state.sqlite3') as store:
            seal = store.get('final_selection')
            self.assertEqual(seal['label'], 'round-0001')
            self.assertEqual(store.pending(), 0)
            before = store.budget()['trials']
        result = finalize(self.state, approved=True)
        self.assertTrue(result['release_qualified'])
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.get('final_selection'), seal)
            self.assertEqual(store.budget()['trials'], before + 2)
        with patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('Final repeat must be read-only')):
            self.assertEqual(finalize(self.state, approved=True), result)

    def test_completed_final_is_read_only_after_expiry_but_not_unresolved_work(self):
        self.submit()
        self.evaluate()
        result = finalize(self.state, approved=True)
        expiry = read_json(self.state / 'manifest.json')['expires_at']
        with (patch('codex_eval_lab.engine.time.time', return_value=expiry + 1),
              patch('codex_eval_lab.engine.invoke', side_effect=AssertionError('No new execution'))):
            self.assertEqual(finalize(self.state, approved=True), result)
        # A saved result must not bypass a later inconsistent/unresolved ledger.
        with Store(self.state / 'state.sqlite3') as store:
            store.begin_optimizer(100)
        with self.assertRaisesRegex(LabError, 'Unresolved'):
            finalize(self.state, approved=True)
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.get('final_result'), result)
            self.assertEqual(store.get('final_selection'), result['final_selection'])

    def test_cli_requires_explicit_call_id_and_has_no_optimizer_approval(self):
        args = parser().parse_args(['evaluate-turn', str(self.state), '--call-id', '1'])
        self.assertFalse(hasattr(args, 'approve_optimizer'))
        with patch('codex_eval_lab.native.evaluate_turn', return_value={'called': 1}) as evaluate:
            self.assertEqual(dispatch(args), {'called': 1})
        evaluate.assert_called_once_with(self.state.resolve(), 1)


class NativePairedEvaluationTests(NativeEvaluationTests):
    # Inherited happy/failure paths also exercise paired schedules and final guards.
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.suite, self.app, self.state = make_fixture(self.root, cases_per_split=2)
        path = self.suite / 'eval.toml'
        path.write_text(path.read_text() + POLICY + '\n[measurement]\ndesign="paired_ab_ba"\n')
        initialize(self.suite, self.app, self.state, approvals={'cases': True, 'grader': True, 'execution': True})

    def test_completed_half_pair_is_not_resumed_as_adjacent(self):
        self.submit()
        with Store(self.state / 'state.sqlite3') as store:
            manifest = manifest_for(self.state, store)
            plan = paired.selection_plan(self.state, store, manifest, 'round-0001', 'baseline')
            cohort = plan['vs_incumbent']
            role, case_id, rep = store.cohort(cohort)['schedule'][0]
            store.reserve(role, 'validation', case_id, rep, manifest['config']['budget'], cohort=cohort)
            store.complete(role, 'validation', case_id, rep,
                           {'status': 'ok', 'case_id': case_id, 'rep': rep, 'metrics': {'quality': 1}}, 0, cohort=cohort)
        with self.assertRaisesRegex(LabError, 'half-pair'):
            self.evaluate()
        # Candidate development may run once; the second half is never executed.
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(len(store.cohort_statuses(cohort)), 1)
            self.assertIsNone(store.get('final_selection'))


class NativeInitializationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.suite, self.app, self.state = configure_oracle(self.root)

    def start(self, plan=None, approved=True, note='Explicit offline local scope including preflight and final'):
        return native.start_native(self.suite, self.app, self.state,
                                   plan or automation.make_plan(self.suite, self.app),
                                   approved=approved, authorization_note=note)

    def test_initialization_records_actual_preflight_and_protects_final_without_dispatch(self):
        with (patch('codex_eval_lab.optimizer.loop', side_effect=AssertionError('No search')),
              patch('codex_eval_lab.store.Store.begin_optimizer', side_effect=AssertionError('No author'))):
            result = self.start()
        self.assertEqual(result['kind'], 'native_initialization')
        self.assertEqual(result['oracle_preflight']['trials'], 18)
        self.assertEqual(result['budget']['trials'], 18)
        self.assertEqual(result['budget']['optimizer_calls'], 0)
        self.assertEqual(result['protected_final_trials'], 4)
        with Store(self.state / 'state.sqlite3') as store:
            manifest = manifest_for(self.state, store)
            self.assertEqual(store.get('protected_final_trials'), 4)
            self.assertEqual(store.get('native_initialization'), result)
            self.assertFalse(manifest['automation_plan']['human_labels_attested'])
            self.assertIsNone(store.get('final_selection'))
            self.assertEqual(store.results('baseline', 'train'), [])
            self.assertEqual(store.results('baseline', 'test'), [])

    def test_native_lifecycle_preserves_existing_protected_final_budget(self):
        path = self.suite / 'eval.toml'
        path.write_text(path.read_text().replace('max_trials = 1000', 'max_trials = 30'))
        self.start()
        turn = native.prepare_turn(self.state, self.root / 'author', approved=True, authorization_note='Same scope')
        with self.assertRaisesRegex(LabError, 'Unresolved'):
            finalize(self.state, approved=True)
        response = self.root / 'response.json'
        write_json(response, {'hypothesis': 'Correct fixture', 'edits': [{'path': 'app.py', 'content':
                    (self.app / 'app.py').read_text().replace('"output":0', '"output":1')}], 'notes': 'Offline'})
        native.submit_turn(self.state, turn['call_id'], response, elapsed_s=1)
        native.evaluate_turn(self.state, turn['call_id'])
        with self.assertRaisesRegex(LabError, 'Protected final budget'):
            native.prepare_turn(self.state, self.root / 'second', approved=True, authorization_note='Same scope')
        final = finalize(self.state, approved=True)
        self.assertTrue(final['release_qualified'])
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.budget()['trials'], 30)
            self.assertEqual(store.budget()['optimizer_calls'], 1)

    def test_missing_authority_stale_plan_and_insufficient_budget_fail_before_execution(self):
        with patch('codex_eval_lab.oracle.invoke', side_effect=AssertionError('Must not execute')):
            for approved, note in ((False, 'scope'), (True, '')):
                with self.assertRaises(LabError):
                    self.start(approved=approved, note=note)
            plan = automation.make_plan(self.suite, self.app)
            plan['budget']['max_trials'] += 1
            with self.assertRaisesRegex(LabError, 'Plan no longer matches'):
                self.start(plan)
            path = self.suite / 'eval.toml'
            path.write_text(path.read_text().replace('max_trials = 1000', 'max_trials = 29'))
            with self.assertRaisesRegex(LabError, 'Budget cannot cover'):
                self.start()
        self.assertFalse(self.state.exists())

    def test_final_reserve_tamper_fails_before_prepare(self):
        self.start()
        with Store(self.state / 'state.sqlite3') as store:
            store.put('protected_final_trials', 0)
        with self.assertRaisesRegex(LabError, 'final reserve changed'):
            native.prepare_turn(self.state, self.root / 'author', approved=True, authorization_note='Same scope')
        with Store(self.state / 'state.sqlite3') as store:
            self.assertEqual(store.budget()['optimizer_calls'], 0)

    def test_cli_start_native_binds_plan_arguments(self):
        plan_path = self.root / 'plan.json'
        plan = automation.make_plan(self.suite, self.app)
        write_json(plan_path, plan)
        args = parser().parse_args(['start-native', str(self.suite), '--app', str(self.app),
                 '--state', str(self.state), '--plan', str(plan_path), '--approve-plan', '--authorization-note', 'Existing scope'])
        with patch('codex_eval_lab.native.start_native', return_value={'initialized': True}) as start:
            self.assertEqual(dispatch(args), {'initialized': True})
        start.assert_called_once_with(self.suite, self.app, self.state, plan, approved=True, authorization_note='Existing scope')
