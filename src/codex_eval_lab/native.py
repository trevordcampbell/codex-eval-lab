"""Counted external proposal handoff for native Codex orchestration.

This is a local file protocol, not a model dispatcher or authorization service.
The host enforces its tool/model permissions and reports unknown usage honestly.
"""
from __future__ import annotations

from pathlib import Path
import os
import stat
import shutil
import time

from . import proposal_receipts, search_policy, paired
from .artifacts import apply_proposal, hashes
from .engine import check_source, feedback, manifest_for, run_internal
from .optimizer import PROMPT, PROPOSAL_SCHEMA, evaluate_active_round
from .store import Store
from .proposal_feedback import bounded_feedback
from .util import LabError, canonical, digest, experiment_lock, safe_name, strict_json, read_json, utc_now, write_json


def start_native(suite: Path, app: Path, state: Path, plan: dict, *, approved: bool,
                 authorization_note: str) -> dict:
    """Initialize the existing protected plan; never dispatch or finalize.

    Configured oracle preflight executes now, and its actual ledger charges are
    disclosed. Approval records existing host/user authority, not a new grant.
    """
    from .automation import initialize_plan, reserve_for_final
    initialize_plan(suite, app, state, plan, approved=approved, authorization_note=authorization_note)
    state = state.resolve()
    with experiment_lock(state), Store(state / "state.sqlite3") as store:
        manifest = manifest_for(state, store)
        final_trials = reserve_for_final(store, manifest)
        result = {"schema_version": 1, "kind": "native_initialization", "status": "initialized",
                  "state": str(state), "plan_sha256": manifest["automation_plan"]["plan_sha256"],
                  "protected_final_trials": final_trials,
                  "protected_final_reserved_eval_usd": final_trials * manifest["config"]["budget"]["trial_reserve_usd"],
                  "oracle_preflight": {"status": manifest["oracle_gate"]["status"],
                                       "trials": len(store.results("oracle-preflight", "oracle")),
                                       "receipt": str(state / "oracle-receipt.json") if manifest["config"].get("oracle") else None},
                  "budget": store.budget(),
                  "next_action": "prepare-turn",
                  "warning": "Configured oracle preflight has executed. No author or final comparison has run. Final capacity does not extend the wall-time window; flags record existing authority only."}
        store.put("native_initialization", result)
        store.event("native_initialized", result)
        return result


def _evaluation_binding(store: Store, manifest: dict, record: dict) -> dict:
    receipt = record["receipt"]
    return {"call_id": record["call_id"], "label": record["label"],
            "parent": record["parent"], "incumbent": record["incumbent"],
            "source_hash": record["source_hash"], "parent_source_hash": receipt["source_hash"],
            "incumbent_source_hash": store.variant(record["incumbent"])["source_hash"],
            "baseline_source_hash": store.variant("baseline")["source_hash"],
            "manifest_sha256": digest(manifest), "evaluator_sha256": digest(manifest["evaluator_hashes"]),
            "dispatch_digest": receipt["dispatch_digest"], "response_digest": receipt["response_digest"]}


def evaluate_turn(state: Path, call_id: int) -> dict:
    """Evaluate only an applied native turn, or return its verified saved receipt.

    This path cannot reserve an optimizer opportunity or dispatch a backend.
    Pending/indeterminate execution and mismatched identities fail closed, even
    when returning a prior result. It never opens final-test data.
    """
    if type(call_id) is not int or call_id < 1:
        raise LabError("Native call ID must be a positive integer")
    state = state.resolve()
    with experiment_lock(state), Store(state / "state.sqlite3") as store:
        # A completed receipt can be inspected after expiry; new execution cannot.
        manifest = manifest_for(state, store)
        if store.unresolved_optimizers():
            raise LabError("Unresolved optimizer execution blocks native evaluation")
        for table in ("trials", "paired_trials"):
            if store.db.execute(f"SELECT 1 FROM {table} WHERE status IN ('pending','indeterminate') LIMIT 1").fetchone():
                raise LabError("Pending or indeterminate trials block native evaluation; preserve their evidence, never replay them")
        record = store.get(f"native_turn:{call_id}")
        row = store.db.execute("SELECT status,result FROM optimizers WHERE id=?", (call_id,)).fetchone()
        if not record or record.get("status") not in ("applied", "evaluated") or not row or row["status"] != "ok":
            raise LabError("Native turn is not an applied completed-author opportunity")
        if type(record.get("call_id")) is not int or record["call_id"] != call_id:
            raise LabError("Native call identity changed")
        result = strict_json(row["result"])
        expected = {"native_turn": call_id, "label": record["label"], "receipt": record["receipt"]}
        if digest(result) != digest(expected):
            raise LabError("Native optimizer completion no longer matches its call and response")
        for label in {record["label"], record["parent"], record["incumbent"], "baseline"}:
            check_source(state, store, label)
        if store.variant(record["label"])["source_hash"] != record["source_hash"]:
            raise LabError("Native candidate source no longer matches the submitted call")
        dispatch = proposal_receipts.verify_dispatch(state / record["evidence_relative"],
                    expected_digest=record["receipt"]["dispatch_digest"],
                    source=state / "candidates" / record["parent"])
        context = dispatch["invocation_context"]
        if (type(context.get("call_id")) is not int or context["call_id"] != call_id
                or context.get("backend") != "native_external" or dispatch["source_label"] != record["parent"]):
            raise LabError("Native dispatch does not bind this call and parent")
        binding = _evaluation_binding(store, manifest, record)
        original = record.get("active_round")
        if not original or digest(original.get("native_binding")) != digest(binding):
            raise LabError("Native applied-round identity changed or lacks its binding")
        active = store.get("active_round")
        if active is not None and digest(active) != digest(original):
            raise LabError("A different or changed active round blocks this native evaluation")
        history = store.get("search_history", [])
        entries = [entry for entry in history if entry["label"] == record["label"]]
        if len(entries) > 1:
            raise LabError("Native evaluation has duplicate decision records")
        entry = entries[0] if entries else None
        if entry is not None and (any(key not in entry for key in original)
                or digest({key: entry[key] for key in original}) != digest(original)):
            raise LabError("Native decision no longer binds the submitted round")
        if active is not None:
            allowed_best = {record["incumbent"]}
            if entry is not None and entry["accepted"]:
                allowed_best.add(record["label"])
            if store.get("best") not in allowed_best or store.get("rounds_started") != record["round"]:
                raise LabError("Search state changed outside the bound native round")
        decision_path = state / "decisions" / f"{record['label']}.json"
        if decision_path.is_symlink() or (decision_path.exists() and not decision_path.is_file()):
            raise LabError("Native decision export must be an ordinary file")
        if entry is not None and decision_path.exists() and digest(read_json(decision_path)) != digest(entry):
            raise LabError("Native decision export changed")
        saved = record.get("evaluation_receipt")
        if saved is not None:
            if (record["status"] != "evaluated" or active is not None or entry is None
                    or not decision_path.is_file()
                    or digest(saved) != record.get("evaluation_receipt_sha256")
                    or digest(saved.get("binding")) != digest(binding)
                    or saved.get("decision_sha256") != digest(entry)):
                raise LabError("Native evaluation receipt changed or completion is inconsistent")
            return saved
        if record["status"] != "applied" or active is None:
            raise LabError("No matching active native round; this command cannot create one")
        if store.get("final_selection"):
            raise LabError("Final test sealed this experiment; no native evaluation permitted")
        manifest_for(state, store, check_time=True)
        cfg = manifest["config"]
        val_ids = set(manifest["splits"]["validation"])
        val_groups = {case["group"] for case in manifest["cases"] if case["id"] in val_ids}
        if len(val_groups) < cfg["objective"]["min_validation_groups"]:
            raise LabError("Not enough independent validation groups for automatic selection; add groups in a new approved experiment")
        # Same baseline readiness and archive reconciliation as loop. Completed
        # rows are reused; no new candidate or author can be created here.
        best = store.get("best")
        run_internal(state, store, manifest, best, "train")
        if not paired.enabled(manifest):
            run_internal(state, store, manifest, best, "validation")
        if search_policy.enabled(manifest):
            search_policy.update_archive(store, manifest, best)
        entry, best, _ = evaluate_active_round(state, store, manifest, active, history,
                                              store.get("stalled_rounds", 0))
        # A crash after the history commit may precede its derived JSON export.
        if not decision_path.exists():
            write_json(decision_path, entry)
        if digest(read_json(decision_path)) != digest(entry):
            raise LabError("Native decision export changed")
        receipt = {"schema_version": 1, "kind": "native_evaluation_receipt", "status": "evaluated",
                   "call_id": call_id, "label": record["label"], "binding": binding,
                   "decision_sha256": digest(entry), "best": best,
                   "search_selected": entry["search_selected"],
                   "confidence_gate_passed": entry["confidence_gate_passed"],
                   "release_qualified": False, "budget": store.budget(),
                   "warning": "Private adaptive selection receipt; do not send it to a proposal author. Final confirmation is separate."}
        record.update(status="evaluated", evaluation_receipt=receipt, evaluation_receipt_sha256=digest(receipt))
        # Receipt and active-round retirement commit together. A crash before
        # this boundary resumes the same decision; after it, retries are read-only.
        with store.transaction():
            store.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (f"native_turn:{call_id}", canonical(record)))
            store.db.execute("INSERT OR REPLACE INTO meta VALUES('active_round','null')")
            store.db.execute("INSERT INTO events(at,kind,data) VALUES(?,?,?)",
                             (utc_now(), "native_turn_evaluated", canonical(receipt)))
        from .report import render_report
        render_report(state, state / "report.html")
        return receipt


def prepare_turn(state: Path, destination: Path, *, approved: bool, authorization_note: str,
                 instruction: str = "") -> dict:
    """Reserve one opportunity and freeze inputs before any external author call."""
    if not approved or not isinstance(authorization_note, str) or not authorization_note.strip():
        raise LabError("Record existing optimizer scope authority before a native handoff; flags do not grant permission")
    state, destination = state.resolve(), destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise LabError("Native author workspace must be a fresh directory")
    if destination.resolve().is_relative_to(state):
        raise LabError("Native author workspace must be outside private experiment state")
    with experiment_lock(state), Store(state / "state.sqlite3") as store:
        manifest = manifest_for(state, store, check_time=True)
        cfg = manifest["config"]
        if store.get("final_selection") or store.get("active_round") or store.unresolved_optimizers():
            raise LabError("A sealed, active, or unresolved experiment cannot dispatch another author")
        if store.get("search_terminal_stop"):
            raise LabError("Search has a terminal stop; no new author opportunity is allowed")
        number = store.get("rounds_started", 0) + 1
        if number > cfg["search"]["max_rounds"]:
            raise LabError("Search round limit reached")
        if store.get("stalled_rounds", 0) >= cfg["search"]["patience"]:
            raise LabError("Search patience exhausted")
        best = store.get("best")
        run_internal(state, store, manifest, best, "train")
        if not paired.enabled(manifest):
            run_internal(state, store, manifest, best, "validation")
        from .automation import can_start_round
        if not can_start_round(store, manifest, best):
            raise LabError("Protected final budget prevents another complete candidate round")
        if search_policy.enabled(manifest):
            search_policy.update_archive(store, manifest, best)
            context = search_policy.next_context(store, manifest, number)
        else:
            context = None
        parent = context["parent"] if context else best
        source = check_source(state, store, parent)
        evidence = bounded_feedback(feedback(state, parent), cfg["search"].get("max_feedback_bytes", 65_536))
        prompt = PROMPT + canonical(evidence)
        if context:
            prompt += "\nSEARCH INSTRUCTION (exploratory, no release claim):\n" + canonical(search_policy.author_context(context))
        if instruction:
            prompt += "\nAUTHORIZED TASK CONTEXT:\n" + instruction
        call_id = store.begin_optimizer(cfg["budget"]["max_optimizer_calls"])
        store.put("rounds_started", number)
        record = {"call_id": call_id, "round": number, "label": f"round-{number:04d}",
                  "parent": parent, "incumbent": best, "search_context": context,
                  "workspace": str(destination), "authorization_note": authorization_note,
                  "status": "preparing", "prepared_epoch": time.time(),
                  "evidence_relative": f"native-runs/call-{call_id:04d}/evidence",
                  "usage": {"cost_usd": None, "tokens": None, "served_model": None}}
        store.put(f"native_turn:{call_id}", record)
        search_policy.record_dispatch(store, record["label"], context, call_id)
        # Any interruption after reservation remains unresolved and blocks redispatch.
        destination.mkdir(parents=True)
        shutil.copytree(source, destination / "app")
        if hashes(destination / "app") != hashes(source):
            raise LabError("Native source copy differs from its frozen parent")
        receipt = proposal_receipts.prepare_dispatch(state / record["evidence_relative"], source=destination / "app",
                    source_label=parent, source_hash=store.variant(parent)["source_hash"],
                    feedback=evidence, prompt=prompt, response_contract=PROPOSAL_SCHEMA,
                    invocation_context={"backend": "native_external", "timeout_s": cfg["optimizer"]["timeout_s"],
                                        "configured_model": cfg["optimizer"].get("model"), "search_context": search_policy.author_context(context),
                                        "call_id": call_id, "tools": "Host-authorized tools only; do not inspect evaluator/ancestor files or call nested models"})
        shutil.copytree(state / record["evidence_relative"], destination / "evidence")
        record.update(status="prepared", receipt=receipt)
        store.put(f"native_turn:{call_id}", record)
        store.event("native_turn_prepared", {"call_id": call_id, "parent": parent,
                    "source_hash": receipt["source_hash"], "dispatch_digest": receipt["dispatch_digest"]})
        return {"call_id": call_id, "label": record["label"], "parent": parent,
                "workspace": str(destination), "prompt": str(destination / "evidence/prompt.txt"),
                "dispatch_digest": receipt["dispatch_digest"], "usage": record["usage"],
                "warning": "Reservation is not proof of dispatch. The host must enforce scope/time and preserve actual admission/usage evidence."}


def submit_turn(state: Path, call_id: int, response: Path, *, elapsed_s: float,
                outcome: str = "completed") -> dict:
    """Capture one author result, import scoped edits, and prepare evaluation.

    Failed/malformed/no-op calls remain counted. An interrupted import is never
    automatically replayed. Use evaluate_turn with this exact call ID to evaluate.
    """
    from .util import finite
    finite(elapsed_s, "author elapsed_s", minimum=0)
    if outcome not in ("completed", "failed", "timeout"):
        raise LabError("Native outcome must be completed, failed, or timeout")
    with experiment_lock(state), Store(state / "state.sqlite3") as store:
        manifest = manifest_for(state, store, check_time=True)
        record = store.get(f"native_turn:{call_id}")
        row = store.db.execute("SELECT status FROM optimizers WHERE id=?", (call_id,)).fetchone()
        if not record or record["status"] != "prepared" or not row or row[0] != "pending":
            raise LabError("Native turn is not a pending prepared opportunity; never replay a result")
        if store.get("final_selection") or store.get("active_round") or store.get("best") != record["incumbent"]:
            raise LabError("Search state changed after native dispatch; preserve and inspect the attempt")
        work = Path(record["workspace"])
        limit = manifest["config"]["search"]["max_edit_bytes"] + 2_000_000
        try:
            if response.is_symlink():
                raise LabError("Native response must be an ordinary file, not a symlink")
            fd = os.open(response, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise LabError("Native response must be an ordinary file")
                raw = stream.read(limit + 1)
        except OSError:
            raise LabError("Native response is missing or unreadable; preserve the pending attempt") from None
        if len(raw) > limit:
            raise LabError("Native response exceeds the retained response bound")
        proposal_receipts.verify_dispatch(work / "evidence", expected_digest=record["receipt"]["dispatch_digest"], source=work / "app")
        if any((work / "evidence" / name).exists() or (work / "evidence" / name).is_symlink() for name in ("response.json", "response-receipt.json")):
            raise LabError("Public handoff already contains a response; preserve this ambiguous attempt")
        receipt = proposal_receipts.capture_response(state / record["evidence_relative"], raw,
                    expected_digest=record["receipt"]["dispatch_digest"], source=work / "app")
        # Public copies are convenient handoff artifacts; controller copies are
        # authoritative after submission and survive author-workspace cleanup.
        for name in ("response.json", "response-receipt.json"):
            try:
                with (work / "evidence" / name).open("xb") as target:
                    target.write((state / record["evidence_relative"] / name).read_bytes())
            except OSError:
                raise LabError("Public response path changed; preserve the unresolved attempt") from None
        record.update(receipt=receipt, elapsed_s=elapsed_s, reported_outcome=outcome, status="response_captured")
        store.put(f"native_turn:{call_id}", record)
        try:
            if outcome != "completed" or elapsed_s > manifest["config"]["optimizer"]["timeout_s"]:
                raise LabError("Native author failed or exceeded its configured time opportunity")
            proposal = strict_json(raw.decode("utf-8"))
            if not isinstance(proposal, dict):
                raise LabError("Native proposal must be a JSON object")
            if proposal.get("edits") == []:
                store.put("search_terminal_stop", "no_more_proposals")
                record.update(status="no_more_proposals")
                store.put(f"native_turn:{call_id}", record)
                store.finish_optimizer(call_id, "ok", {"native_turn": call_id, "no_more_proposals": True, "receipt": receipt})
                store.event("search_stopped", {"reason": "no_more_proposals", "call_id": call_id})
                return {"call_id": call_id, "status": "no_more_proposals"}
            label = record["label"]
            safe_name(label)
            source = check_source(state, store, record["parent"])
            target = state / "candidates" / label
            changes = apply_proposal(source, target, proposal, manifest["config"])
            store.add_variant(label, digest(hashes(target)), proposal["hypothesis"])
            active = {key: record[key] for key in ("round", "label", "incumbent", "parent", "search_context")}
            active.update(hypothesis=proposal["hypothesis"], evaluation_start_trials=store.budget()["trials"])
            record.update(source_hash=store.variant(label)["source_hash"])
            active["native_binding"] = _evaluation_binding(store, manifest, record)
            store.put("active_round", active)
            write_json(state / "proposals" / f"{label}.json", proposal)
            record.update(status="applied", active_round=active)
            store.put(f"native_turn:{call_id}", record)
            store.finish_optimizer(call_id, "ok", {"native_turn": call_id, "label": label, "receipt": receipt})
            store.event("native_proposal_applied", {"call_id": call_id, "label": label, "parent": record["parent"], "changes": changes})
            return {"call_id": call_id, "status": "applied", "label": label, "source_hash": record["source_hash"]}
        except (LabError, UnicodeError) as exc:
            record.update(status="failed", error=str(exc))
            store.put(f"native_turn:{call_id}", record)
            store.finish_optimizer(call_id, "failed", {"native_turn": call_id, "error": str(exc), "receipt": receipt})
            store.event("native_proposal_failed", {"call_id": call_id, "error": str(exc)})
            raise LabError("Native proposal failed; response and counted opportunity retained") from exc
