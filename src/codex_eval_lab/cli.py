"""Command line entry point. Commands print machine-readable JSON."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys

from . import __version__
from . import review_cli, automation, native, search_policy
from .config import audit
from .engine import compare, export_best, feedback, finalize, initialize, manifest_for, register, run, select
from .optimizer import export_workspace, import_proposal, loop
from .report import render_report
from .store import Store
from .util import LabError, experiment_lock, read_json, write_json


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eval-lab", description="Design, measure, and hillclimb applications without changing the measurement contract.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check local prerequisites without spending tokens or running app code")
    s = sub.add_parser("audit", help="Validate a suite and disclose measurement risks; executes no adapters")
    s.add_argument("suite", type=Path)
    s = sub.add_parser("start", help="Approve and freeze a new experiment; executes configured oracle preflight")
    s.add_argument("suite", type=Path)
    s.add_argument("--app", type=Path, required=True)
    s.add_argument("--state", type=Path, required=True)
    for key in ("cases", "grader", "execution"):
        s.add_argument(f"--approve-{key}", action="store_true")
    s.add_argument("--note", default="")
    for cmd in ("status", "recover", "unlock"):
        s = sub.add_parser(cmd)
        s.add_argument("state", type=Path)
        if cmd in ("recover", "unlock"):
            s.add_argument("--confirm-no-running-process", action="store_true")
    s = sub.add_parser("register", help="Snapshot a manually edited candidate or unchanged control")
    s.add_argument("state", type=Path)
    s.add_argument("--app", type=Path, required=True)
    s.add_argument("--label", required=True)
    s.add_argument("--hypothesis", required=True)
    s = sub.add_parser("run", help="Execute/resume a development or validation matrix")
    s.add_argument("state", type=Path)
    s.add_argument("--label", default="baseline")
    s.add_argument("--split", choices=("train", "validation"), default="train")
    s = sub.add_parser("compare")
    s.add_argument("state", type=Path)
    s.add_argument("--baseline", default="baseline")
    s.add_argument("--candidate", required=True)
    s.add_argument("--split", choices=("train", "validation", "test"), default="validation")
    s = sub.add_parser("select", help="Select a candidate; paired mode executes fresh validation reference/candidate cohorts first")
    s.add_argument("state", type=Path)
    s.add_argument("--candidate", required=True)
    s = sub.add_parser("loop", help="Run a bounded automatic proposal/evaluation loop; optimizer billing is separate")
    s.add_argument("state", type=Path)
    s.add_argument("--rounds", type=int)
    s.add_argument("--approve-optimizer", action="store_true")
    s = sub.add_parser("finalize", help="Seal the selected candidate before opening the final test; resumable")
    s.add_argument("state", type=Path)
    s.add_argument("--approve-final", action="store_true")
    s = sub.add_parser("report")
    s.add_argument("state", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--full-traces", action="store_true", help="Opt in to unbounded inline traces; can produce very large HTML. Does not include held-out details by itself")
    s.add_argument("--include-private", action="store_true", help="Explicitly include held-out details; never send this to the optimizer")
    s = sub.add_parser("feedback", help="Export ONLY development evidence")
    s.add_argument("state", type=Path)
    s.add_argument("--label", default="baseline")
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("export-workspace", help="Export app + development evidence for a separate optimizer trust domain")
    s.add_argument("state", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--label")
    s = sub.add_parser("import-proposal", help="Validate scope and apply a proposal returned by an external optimizer")
    s.add_argument("state", type=Path)
    s.add_argument("--proposal", type=Path, required=True)
    s.add_argument("--label", required=True)
    s.add_argument("--base")
    s = sub.add_parser("export-best", help="Copy selected source to a NEW directory; never overwrite the working tree")
    s.add_argument("state", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s = sub.add_parser("automation-plan", help="Generate a content-bound end-to-end plan without executing code")
    s.add_argument("suite", type=Path)
    s.add_argument("--app", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    for command, help_text in (
        ("automate", "Execute a scope-authorized plan through final test and report"),
        ("start-native", "Freeze an authorized plan and protect final capacity; executes oracle preflight, never an author or final comparison"),
    ):
        s = sub.add_parser(command, help=help_text)
        s.add_argument("suite", type=Path)
        s.add_argument("--app", type=Path, required=True)
        s.add_argument("--state", type=Path, required=True)
        s.add_argument("--plan", type=Path, required=True)
        s.add_argument("--approve-plan", action="store_true")
        s.add_argument("--authorization-note", required=True)
    s = sub.add_parser("resume-automation", help="Resume the frozen authorized workflow without creating a second proposal or reopening a sealed winner")
    s.add_argument("state", type=Path)
    s = sub.add_parser("prepare-turn", help="Reserve one native author opportunity and capture immutable source/feedback/prompt")
    s.add_argument("state", type=Path)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--approve-optimizer", action="store_true")
    s.add_argument("--authorization-note", required=True)
    s.add_argument("--instruction-file", type=Path)
    s = sub.add_parser("submit-turn", help="Capture one counted native response and apply scoped edits; then evaluate-turn --call-id to evaluate")
    s.add_argument("state", type=Path)
    s.add_argument("--call-id", type=int, required=True)
    s.add_argument("--response", type=Path, required=True)
    s.add_argument("--elapsed-s", type=float, required=True)
    s.add_argument("--outcome", choices=("completed", "failed", "timeout"), default="completed")
    s = sub.add_parser("evaluate-turn", help="Evaluate/resume only the identified applied native turn; never dispatch an optimizer")
    s.add_argument("state", type=Path)
    s.add_argument("--call-id", type=int, required=True)
    review_cli.add_parsers(sub)
    return p


def dispatch(a: argparse.Namespace):
    if a.command in review_cli.COMMANDS:
        return review_cli.dispatch(a)
    if a.command == "doctor":
        return {"version": __version__, "python": platform.python_version(), "platform": platform.platform(),
                "codex_cli": shutil.which("codex"), "docker": shutil.which("docker"), "git": shutil.which("git"),
                "core_dependencies": "Python 3.11+ standard library only",
                "warnings": ["Codex login/provider access is not checked or used by doctor.",
                             "Local execution and local optimizer processes are not private-data isolation boundaries.",
                             "Windows native process-tree termination is limited; WSL is recommended for agent workloads."]}
    if a.command == "audit":
        return audit(a.suite.resolve())
    if a.command == "automation-plan":
        if a.out.exists():
            raise LabError("Plan output already exists; do not overwrite a recorded plan")
        result = automation.make_plan(a.suite, a.app)
        write_json(a.out, result)
        return {"plan": str(a.out), **result}
    if a.command == "automate":
        return automation.start_automation(a.suite, a.app, a.state, read_json(a.plan), approved=a.approve_plan, authorization_note=a.authorization_note)
    if a.command == "start-native":
        return native.start_native(a.suite, a.app, a.state, read_json(a.plan), approved=a.approve_plan,
                                   authorization_note=a.authorization_note)
    if a.command == "start":
        return initialize(a.suite, a.app, a.state, approvals={key:getattr(a, f"approve_{key}") for key in ("cases", "grader", "execution")}, note=a.note)
    state = a.state.resolve()
    if not (state / "manifest.json").is_file() or not (state / "state.sqlite3").is_file():
        raise LabError("Not an initialized experiment directory")
    if a.command == "resume-automation":
        return automation.resume_automation(state)
    if a.command == "prepare-turn":
        instruction = a.instruction_file.read_text(encoding="utf-8") if a.instruction_file else ""
        return native.prepare_turn(state, a.out, approved=a.approve_optimizer,
                    authorization_note=a.authorization_note, instruction=instruction)
    if a.command == "submit-turn":
        return native.submit_turn(state, a.call_id, a.response, elapsed_s=a.elapsed_s, outcome=a.outcome)
    if a.command == "evaluate-turn":
        return native.evaluate_turn(state, a.call_id)
    if a.command == "status":
        with Store(state / "state.sqlite3") as store:
            manifest = manifest_for(state, store)
            return {"name": manifest["config"]["name"], "best": store.get("best"), "variants": store.variants(), "search_outcome": search_policy.outcome_summary(store),
                    "budget": store.budget(), "pending_trials": store.pending(), "unresolved_optimizer_calls": store.unresolved_optimizers(), "final_selection": store.get("final_selection"),
                    "final_completed": store.get("final_result") is not None, "expires_at": manifest["expires_at"],
                    "oracle_gate": manifest.get("oracle_gate"), "automation_blocker": store.get("automation_blocker"),
                    "automation_plan_sha256": manifest.get("automation_plan", {}).get("plan_sha256")}
    if a.command == "register":
        register(state, a.app, a.label, a.hypothesis)
        return {"registered": a.label}
    if a.command == "run":
        return run(state, a.label, a.split)
    if a.command == "compare":
        return compare(state, a.baseline, a.candidate, a.split)
    if a.command == "select":
        return select(state, a.candidate)
    if a.command == "loop":
        return loop(state, approved=a.approve_optimizer, rounds=a.rounds)
    if a.command == "finalize":
        return finalize(state, approved=a.approve_final)
    if a.command == "report":
        return render_report(state, a.out.resolve(), include_private=a.include_private, full_traces=a.full_traces)
    if a.command == "feedback":
        write_json(a.out, feedback(state, a.label))
        return {"feedback": str(a.out), "split": "train"}
    if a.command == "export-workspace":
        return export_workspace(state, a.out.resolve(), label=a.label)
    if a.command == "import-proposal":
        return import_proposal(state, read_json(a.proposal), a.label, base=a.base)
    if a.command == "export-best":
        return export_best(state, a.out.resolve())
    if a.command == "recover":
        if not a.confirm_no_running_process:
            raise LabError("Confirm no process is active before marking interrupted work indeterminate")
        with experiment_lock(state), Store(state / "state.sqlite3") as store:
            manifest_for(state, store)
            return {"recovered": store.recover()}
    if a.command == "unlock":
        if not a.confirm_no_running_process:
            raise LabError("Confirm no process is active; removing an active lock can corrupt concurrent work")
        lock = state / ".lock"
        if not lock.exists():
            return {"unlocked": False, "note": "No lock present"}
        owner_path = lock / "owner.json"
        owner = read_json(owner_path) if owner_path.exists() else {}
        if os.name == "posix" and isinstance(owner.get("pid"), int):
            try:
                os.kill(owner["pid"], 0)
            except ProcessLookupError:
                pass
            except PermissionError as exc:
                raise LabError("Lock owner still exists (different user); not removing lock") from exc
            else:
                raise LabError("Lock owner PID is still running; not removing lock")
        if owner_path.exists():
            owner_path.unlink()
        lock.rmdir()
        with Store(state / "state.sqlite3") as store:
            store.event("manual_unlock", {"previous_owner": owner})
        return {"unlocked": True}
    raise LabError("Unknown command")


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        # A failed proposal is a real automation failure, not a successful shell exit.
        return 2 if isinstance(result, dict) and result.get("error") else 0
    except (LabError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc), "command": args.command}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print(json.dumps({"error": "Interrupted. Completed work is retained. Check status/recover before resuming."}), file=sys.stderr)
        return 130
