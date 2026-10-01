"""Offline Codex exec contracts checked against the 2026-10-01 official docs.

Set EVAL_LAB_CODEX_BINARY to opt into real CLI help/argument checks. Those checks
always use --help, empty isolated HOME/CODEX_HOME, and no provider credentials.
They never start a model turn or establish live provider/sandbox compatibility.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from codex_eval_lab.engine import manifest_for, run
from codex_eval_lab.optimizer import PROPOSAL_SCHEMA, generate_proposal
from codex_eval_lab.process import ProcessResult
from codex_eval_lab.store import Store
from codex_eval_lab.util import LabError, read_json, write_json
from .helpers import ROOT, start_fixture


REQUIRED_FLAGS = (
    "--sandbox", "--json", "--skip-git-repo-check",
    "--output-schema", "--output-last-message",
)


class CodexCurrentEventContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _, _, self.state = start_fixture(self.root, cases_per_split=2)
        run(self.state, "baseline", "train")
        self.proposal = {"hypothesis": "Contract fixture", "edits": [], "notes": "Offline"}
        self.commands = []

    def generate(self, events, *, ignore_config=True, call_id=1, stdout=None):
        def fake(command, request, **kwargs):
            self.commands.append(command)
            if "--help" in command:
                help_text = "\n".join(REQUIRED_FLAGS)
                if ignore_config:
                    help_text += "\n--ignore-user-config"
                return ProcessResult(None, help_text, "", 0, 0)
            self.assertEqual(command[-1], "-")
            self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
            self.assertNotIn("--full-auto", command)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
            self.assertNotIn("SECRET-validation", kwargs["input_text"])
            self.assertNotIn("SECRET-test", kwargs["input_text"])
            schema_path = Path(command[command.index("--output-schema") + 1])
            self.assertEqual(read_json(schema_path), PROPOSAL_SCHEMA)
            result_path = Path(command[command.index("--output-last-message") + 1])
            write_json(result_path, self.proposal)
            output = stdout if stdout is not None else "\n".join(map(json.dumps, events)) + "\n"
            return ProcessResult(None, output, "diagnostic only", 0.01, 0)

        with Store(self.state / "state.sqlite3") as store:
            manifest = manifest_for(self.state, store)
            with patch("codex_eval_lab.optimizer.shutil.which", return_value="/fake/codex"), \
                    patch("codex_eval_lab.optimizer.invoke", side_effect=fake):
                return generate_proposal(
                    self.state, store, manifest, "baseline", call_id,
                    cfg_override={"backend": "codex", "environment": [], "timeout_s": 5},
                )

    def test_current_jsonl_events_and_extended_usage_are_preserved(self):
        # Current docs: https://learn.chatgpt.com/docs/non-interactive-mode
        usage = {"input_tokens": 10, "cached_input_tokens": 6,
                 "output_tokens": 4, "reasoning_output_tokens": 2}
        events = [
            {"type": "thread.started", "thread_id": "offline-fixture"},
            {"type": "turn.started"},
            {"type": "item.started", "item": {"id": "item_1", "type": "command_execution",
                "command": "echo fixture", "status": "in_progress"}},
            {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message",
                "text": "A progress message is not the structured proposal."}},
            {"type": "future.compatible.event", "extra": {"kept": True}},
            {"type": "turn.completed", "usage": usage},
        ]
        self.assertEqual(self.generate(events), self.proposal)
        out = self.state / "optimizer-runs" / "call-0001"
        saved = [json.loads(line) for line in (out / "codex-events.jsonl").read_text().splitlines()]
        self.assertEqual(saved, events)
        metadata = read_json(out / "execution.json")
        self.assertEqual(metadata["usage"], [usage])
        self.assertIsNone(metadata["cost_usd"])
        self.assertTrue(metadata["user_config_ignored"])
        self.assertIn("--ignore-user-config", self.commands[-1])

    def test_optional_ignore_user_config_absence_is_disclosed(self):
        self.generate([{"type": "turn.completed", "usage": {"input_tokens": 0, "output_tokens": 0}}],
                      ignore_config=False)
        self.assertNotIn("--ignore-user-config", self.commands[-1])
        metadata = read_json(self.state / "optimizer-runs" / "call-0001" / "execution.json")
        self.assertFalse(metadata["user_config_ignored"])

    def test_error_event_rejects_a_present_structured_file(self):
        with self.assertRaisesRegex(LabError, "failed turn/error"):
            self.generate([{"type": "error", "message": "Offline failure fixture"}])

    def test_malformed_jsonl_rejects_a_present_structured_file(self):
        with self.assertRaises(LabError):
            self.generate([], stdout="this is not JSON\n")

    def test_nonobject_jsonl_and_missing_event_types_fail_cleanly(self):
        for call_id, event in enumerate(([], None, 7, "message", {}, {"type": 3}, {"type": ""}), 1):
            with self.subTest(event=event), self.assertRaisesRegex(LabError, "events must be objects"):
                self.generate([event], call_id=call_id)

    def test_absent_or_truncated_completion_rejects_a_present_structured_file(self):
        complete = {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}
        streams = [[], [{"type": "thread.started", "thread_id": "fixture"}],
                   [{"type": "turn.started"}],
                   [{"type": "turn.started"}, {"type": "item.completed", "item": {
                       "type": "agent_message", "text": "Looks done but no terminal event"}}],
                   [complete, {"type": "turn.started"}]]
        for call_id, stream in enumerate(streams, 1):
            with self.subTest(stream=stream), self.assertRaisesRegex(LabError, "without a completed turn"):
                self.generate(stream, call_id=call_id)

    def test_conflicting_failure_rejects_a_completed_turn(self):
        complete = {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}
        for call_id, failure in enumerate(("turn.failed", "error"), 1):
            with self.subTest(failure=failure), self.assertRaisesRegex(LabError, "failed turn/error"):
                self.generate([complete, {"type": failure, "error": {"message": "failure"}}], call_id=call_id)

    def test_overlapping_started_turns_are_rejected(self):
        with self.assertRaisesRegex(LabError, "before completing"):
            self.generate([{"type": "turn.started"}, {"type": "turn.started"},
                           {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}])

    def test_new_work_after_completion_is_not_a_terminal_success(self):
        complete = {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}}
        for call_id, event_type in enumerate(("thread.started", "item.started", "item.updated"), 1):
            with self.subTest(event_type=event_type), self.assertRaisesRegex(LabError, "new work after"):
                self.generate([complete, {"type": event_type}], call_id=call_id)

    def test_malformed_completed_usage_is_rejected(self):
        usages = [None, [], {}, {"input_tokens": True, "output_tokens": 1},
                  {"input_tokens": 1, "output_tokens": -1},
                  {"input_tokens": 1, "output_tokens": 1, "cached_input_tokens": "0"},
                  {"input_tokens": 1, "output_tokens": 1, "reasoning_output_tokens": False}]
        for call_id, usage in enumerate(usages, 1):
            with self.subTest(usage=usage), self.assertRaisesRegex(LabError, "turn.completed"):
                self.generate([{"type": "turn.completed", "usage": usage}], call_id=call_id)


@unittest.skipUnless(os.environ.get("EVAL_LAB_CODEX_BINARY"),
                     "Set EVAL_LAB_CODEX_BINARY for a no-model CLI argument check")
class CodexInstalledArgumentContractTests(unittest.TestCase):
    def test_installed_cli_help_and_full_adapter_argument_shape(self):
        binary = str(Path(os.environ["EVAL_LAB_CODEX_BINARY"]).resolve())
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex_home = home / "codex"
            codex_home.mkdir()
            # Do not inherit credentials, user config, or runtime API overrides.
            env = {"PATH": os.environ.get("PATH", os.defpath),
                   "HOME": tmp, "USERPROFILE": tmp, "CODEX_HOME": str(codex_home)}
            for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
                if key in os.environ:
                    env[key] = os.environ[key]
            version = subprocess.run([binary, "--version"], env=env, cwd=home,
                                     capture_output=True, text=True, timeout=15, check=True)
            self.assertIn("codex-cli", version.stdout)
            help_result = subprocess.run([binary, "exec", "--help"], env=env, cwd=home,
                                         capture_output=True, text=True, timeout=15, check=True)
            for flag in REQUIRED_FLAGS:
                self.assertIn(flag, help_result.stdout)
            schema_path = home / "schema.json"
            write_json(schema_path, PROPOSAL_SCHEMA)
            output_path = home / "proposal.json"
            command = [binary, "exec", "--sandbox", "read-only", "--json", "--skip-git-repo-check",
                       "--output-schema", str(schema_path), "--output-last-message", str(output_path)]
            if "--ignore-user-config" in help_result.stdout:
                command.append("--ignore-user-config")
            # --help short-circuits execution; no prompt is supplied over stdin.
            command.extend(["--help", "-"])
            result = subprocess.run(command, input="", env=env, cwd=home,
                                    capture_output=True, text=True, timeout=15, check=True)
            self.assertIn("Run Codex non-interactively", result.stdout)
            self.assertFalse(output_path.exists())


@unittest.skipUnless(importlib.util.find_spec("openai"), "Install the optional judge extra for SDK checks")
class OpenAIInstalledSDKContractTests(unittest.TestCase):
    def test_rubric_grader_real_sdk_with_offline_transport(self):
        # OpenAI 3.22.1 uses httpx2. MockTransport cannot make network requests.
        import httpx2
        from openai import OpenAI

        spec = importlib.util.spec_from_file_location("offline_contract_grader", ROOT / "examples/judges/openai_grader.py")
        grader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(grader)
        requests = []

        def respond(request):
            self.assertEqual(request.url.path, "/v1/responses")
            requests.append(json.loads(request.content))
            body = {
                "id": "resp_offline_fixture", "object": "response", "created_at": 0,
                "status": "completed", "error": None, "incomplete_details": None,
                "instructions": None, "max_output_tokens": 1024, "model": "offline-model-exact",
                "output": [{"id": "msg_fixture", "type": "message", "status": "completed",
                    "role": "assistant", "content": [{"type": "output_text", "annotations": [],
                        "text": json.dumps({"quality": 4, "grounded": True, "reason": "Fixture only"})}]}],
                "parallel_tool_calls": True, "previous_response_id": None,
                "reasoning": {"effort": None, "summary": None}, "store": False,
                "temperature": 1, "text": {"format": {"type": "text"}},
                "tool_choice": "auto", "tools": [], "top_p": 1, "truncation": "disabled",
                "usage": {"input_tokens": 10, "input_tokens_details": {"cached_tokens": 4},
                    "output_tokens": 5, "output_tokens_details": {"reasoning_tokens": 2}, "total_tokens": 15},
                "metadata": {},
            }
            return httpx2.Response(200, json=body, request=request)

        with OpenAI(api_key="offline-placeholder-not-a-credential", base_url="https://offline.invalid/v1",
                    max_retries=0, timeout=45.0,
                    http_client=httpx2.Client(transport=httpx2.MockTransport(respond))) as client:
            result = grader.grade({"input": "fixture task", "expected": "fixture reference", "output": "fixture"},
                client, {"EVAL_JUDGE_MODEL": "offline-model-exact", "EVAL_JUDGE_APPROVED": "1",
                         "EVAL_JUDGE_INPUT_USD_PER_MTOK": "1", "EVAL_JUDGE_CACHED_INPUT_USD_PER_MTOK": "0.5",
                         "EVAL_JUDGE_OUTPUT_USD_PER_MTOK": "2"})
        self.assertEqual(len(requests), 1)
        self.assertIs(requests[0]["store"], False)
        self.assertEqual(requests[0]["text"]["format"],
                         {"type": "json_schema", "name": "evaluation_grade", "schema": grader.SCHEMA, "strict": True})
        self.assertEqual(result["metrics"], {"quality": 1.0, "grounded": 1})
        self.assertEqual(result["model"], "offline-model-exact")
        self.assertEqual(result["usage"]["cached_input_tokens"], 4)
        self.assertEqual(result["usage"]["cost_usd"], 0.000018)


if __name__ == "__main__":
    unittest.main()
