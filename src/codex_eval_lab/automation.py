"""Native, bounded workflow orchestration. No hosted execution or authority service.

A plan records the scope authorized through the host/user's policy. Flags cannot
create that authority or attest human labels. Source/grader changes mean a new run.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

from .artifacts import collect, hashes
from .config import audit, load_cases, load_config, make_splits
from .evidence import evidence_files, public_evidence_summary
from . import oracle, paired, search_policy
from .store import Store
from .util import LabError, digest, file_hash, read_json, utc_now, write_json

NORMAL_STOPS = {"round_limit", "patience_exhausted", "no_more_proposals", "final_budget_reserved", "optimizer_budget_exhausted"}


def make_plan(suite: Path, app: Path) -> dict[str, Any]:
    """Read-only plan. Caller supplies actual authority separately at execution."""
    suite, app = suite.resolve(), app.resolve()
    cfg = load_config(suite)
    result = audit(suite)
    if not cfg.get("oracle") and not result["evidence_gate"]["ready"]:
        raise LabError("Automation requires executable-oracle controls or ready expert calibration; unverified model judgments are not a gate")
    if cfg.get("evidence") and not result["evidence_gate"]["ready"]:
        raise LabError("Configured expert calibration is not ready; an oracle cannot mask it")
    cases = load_cases(suite, cfg)
    splits = make_splits(cases, cfg["seed"])
    counts = {key: len(ids) * cfg["repetitions"] for key, ids in splits.items()}
    if any(n == 0 for n in counts.values()):
        raise LabError("Automation needs nonempty development, validation and final partitions")
    if len({c["group"] for c in cases if c["id"] in splits["validation"]}) < cfg["objective"]["min_validation_groups"]:
        raise LabError("Automation needs enough independent validation groups")
    paths = ["eval.toml", cfg["cases"], *cfg["harness_paths"], *[a for c in cases for a in c["assets"]], *evidence_files(cfg), *oracle.oracle_files(cfg)]
    sources = collect(app, cfg["source_paths"])
    evaluator = collect(suite, paths)
    if set(p.resolve() for p in sources.values()) & set(p.resolve() for p in evaluator.values()):
        raise LabError("Application and evaluator source must not overlap")
    preflight = result["oracle_gate"].get("preflight_calls", 0)
    temporal = cfg.get("measurement", {}).get("design") == "paired_ab_ba"
    baseline = counts["train"] + (0 if temporal else counts["validation"])
    first_round = counts["train"] + (2 if temporal else 1) * counts["validation"]
    final = 2 * counts["test"]
    minimum = preflight + baseline + first_round + final
    if cfg["budget"]["max_trials"] < minimum or minimum * cfg["budget"]["trial_reserve_usd"] > cfg["budget"]["max_eval_cost_usd"] + 1e-9:
        raise LabError("Budget cannot cover preflight, baseline, one full candidate comparison and protected final comparison")
    if cfg["budget"]["max_optimizer_calls"] < 1:
        raise LabError("Automation requires an explicit separate optimizer-call budget")
    return {"schema_version": 1, "kind": "native_automation_plan", "suite": cfg["name"],
            "evaluator_sha256": {k: file_hash(v) for k, v in evaluator.items()},
            "baseline_sha256": {k: file_hash(v) for k, v in sources.items()},
            "objective": cfg["objective"], "guardrails": cfg["guardrails"], "editable": cfg["search"]["editable"],
            "budget": cfg["budget"], "search": cfg["search"], "search_policy": cfg.get("search_policy"), "optimizer": cfg["optimizer"],
            "execution": cfg["execution"], "measurement": cfg.get("measurement", {"design": "variant_blocked"}),
            "stages": ["freeze", "oracle_preflight" if preflight else "expert_evidence_revalidation", "baseline", "bounded_search", "seal", "final_test", "report"],
            "budget_projection": {"oracle_preflight_calls": preflight, "baseline_trials": baseline,
                                  "first_round_trials": first_round, "protected_final_trials": final,
                                  "minimum_trials": minimum, "minimum_reserved_eval_usd": minimum * cfg["budget"]["trial_reserve_usd"]},
            "evidence": {"expert": result["evidence_gate"], "oracle": result["oracle_gate"]},
            "authority": "Record only: host/user policy must authorize this exact scope, data, commands, evaluation limits, separate optimizer usage and final-test opening. This plan grants no permission.",
            "limitations": ["Final trial/dollar capacity is protected, but an expired wall-time window, crash or invalid measurement can still block completion.",
                            "Provider charges rely on conservative reported bounds; optimizer dollars remain separate and potentially unknown.",
                            "No deployment, source overwrite, credential changes, public uploads or outside-scope data access is authorized.",
                            *oracle.LIMITS]}


def initialize_plan(suite: Path, app: Path, state: Path, plan: dict, *, approved: bool, authorization_note: str) -> dict:
    """Freeze the existing exact plan and reserve final capacity without searching.

    Initialization executes configured oracle preflight under the recorded scope.
    It does not dispatch an optimizer or open the final comparison.
    """
    if approved is not True or not isinstance(authorization_note, str) or not authorization_note.strip():
        raise LabError("Record the actual existing scope authorization; --approve-plan is not authority or a human-label attestation")
    current = make_plan(suite, app)
    if digest(current) != digest(plan):
        raise LabError("Plan no longer matches exact evaluator/baseline/scope/budgets; generate a new plan and resolve changed authority")
    from .engine import initialize
    record = {"plan": plan, "plan_sha256": digest(plan), "authorization_note": authorization_note,
              "authorization_recorded_at": utc_now(), "human_labels_attested": False}
    return initialize(suite, app, state, approvals={"cases": True, "grader": True, "execution": True},
               note="Bounded automation execution authorization; no assertion of human case review. " + authorization_note,
               automation_plan=record)


def start_automation(suite: Path, app: Path, state: Path, plan: dict, *, approved: bool, authorization_note: str) -> dict:
    initialize_plan(suite, app, state, plan, approved=approved, authorization_note=authorization_note)
    return resume_automation(state.resolve())


def reserve_for_final(store: Store, manifest: dict) -> int:
    """Use the frozen plan, not a mutable metadata flag, as the final reserve."""
    record = manifest.get("automation_plan")
    if not record:
        return 0
    return record["plan"]["budget_projection"]["protected_final_trials"]


def can_start_round(store: Store, manifest: dict, incumbent: str) -> bool:
    if not manifest.get("automation_plan"):
        return True
    counts = {key: len(ids) * manifest["config"]["repetitions"] for key, ids in manifest["splits"].items()}
    same = store.variant(incumbent)["source_hash"] == store.variant("baseline")["source_hash"]
    need = counts["train"] + counts["validation"] * ((2 if same else 4) if paired.enabled(manifest) else 1)
    budget, spent = manifest["config"]["budget"], store.budget()
    held = reserve_for_final(store, manifest)
    return (spent["trials"] + need + held <= budget["max_trials"]
            and spent["eval_charged_usd"] + spent["pending_reserved_usd"] + (need + held) * budget["trial_reserve_usd"] <= budget["max_eval_cost_usd"] + 1e-9)


def summary(state: Path) -> dict:
    from .engine import manifest_for
    with Store(state / "state.sqlite3") as store:
        manifest = manifest_for(state, store)
        gate = manifest.get("oracle_gate", {})
        expert = manifest.get("evidence_gate", {})
        basis = "expert_calibrated" if expert.get("ready") else "executable_oracle_validated" if gate.get("ready") else "unverified"
        final = store.get("final_result")
        return {"schema_version": 1, "kind": "automation_result", "state": str(state), "best": store.get("best"),
                "status": "completed" if final else "blocked" if store.get("automation_blocker") else "in_progress",
                "readiness": {"evidence_basis": basis, "executable": gate, "expert": public_evidence_summary(expert),
                              "human_reviewed": bool(expert.get("ready")), "local_attestation_not_identity_proof": True},
                "selection": {"history": store.get("search_history", []), "stop_reason": store.get("automation_stop_reason"), **search_policy.outcome_summary(store)},
                "final_result": final, "budget": store.budget(), "blocker": store.get("automation_blocker"),
                "plan_sha256": manifest.get("automation_plan", {}).get("plan_sha256"),
                "source_hashes": {v["label"]: v["source_hash"] for v in store.variants()},
                "report": str(state / "report.html"),
                "warning": "Validation feedback is adaptive; do not supply this summary or full reports to proposal sessions. Final failure consumes the holdout."}


def resume_automation(state: Path) -> dict:
    from .engine import finalize, manifest_for
    from .optimizer import loop
    from .report import render_report
    state = state.resolve()
    with Store(state / "state.sqlite3") as store:
        manifest = manifest_for(state, store)
        if not manifest.get("automation_plan"):
            raise LabError("This experiment has no frozen end-to-end authorization plan; create a new experiment")
        if store.unresolved_optimizers():
            raise LabError("Optimizer execution is unresolved; automatic redispatch and finalization are blocked. Preserve the attempt and inspect its outcome.")
        sealed, completed = store.get("final_selection"), store.get("final_result")
        store.put("automation_blocker", None)
    try:
        if not completed:
            if not sealed:
                search = loop(state, approved=True)
                if search.get("error") or search["stop_reason"] not in NORMAL_STOPS:
                    raise LabError("Automation stopped before finalization: " + str(search.get("error", search["stop_reason"])))
                with Store(state / "state.sqlite3") as store:
                    store.put("automation_stop_reason", search["stop_reason"])
                    store.event("automation_search_finished", {"reason": search["stop_reason"], "best": search["best"]})
            finalize(state, approved=True)
        render_report(state, state / "report.html")
    except LabError as exc:
        with Store(state / "state.sqlite3") as store:
            store.put("automation_blocker", str(exc))
            store.event("automation_blocked", {"error": str(exc)})
        try:
            render_report(state, state / "report.html")
        except LabError:
            pass
        raise
    result = summary(state)
    write_json(state / "automation-result.json", result)
    return result
