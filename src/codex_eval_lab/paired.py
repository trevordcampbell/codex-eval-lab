"""Opt-in temporal pairing. Source identities and measurement cohorts are distinct."""
from __future__ import annotations

from pathlib import Path
import random
import time
from typing import Any

from .stats import compare_rows
from .store import Store
from .util import LabError, atomic_text, canonical, digest, safe_name, write_json


def enabled(manifest: dict[str, Any]) -> bool:
    return manifest["config"].get("measurement", {}).get("design") == "paired_ab_ba"


def schedule(ids: list[str], repetitions: int, seed: int) -> list[list[Any]]:
    """Adjacent, balanced AB/BA pairs; balance within each case when possible."""
    rng = random.Random(seed)
    cases = sorted(ids)
    rng.shuffle(cases)
    jobs = []
    # With odd repetitions, counterbalance the extra first position across cases.
    extra = rng.randrange(2)
    for index, case_id in enumerate(cases):
        orders = [0, 1] * (repetitions // 2)
        if repetitions % 2:
            orders.append((index + extra) % 2)
        rng.shuffle(orders)
        for rep, first in enumerate(orders):
            arms = ("reference", "candidate") if first == 0 else ("candidate", "reference")
            jobs.append([[role, case_id, rep] for role in arms])
    rng.shuffle(jobs)
    return [job for pair in jobs for job in pair]


def prepare(state: Path, store: Store, manifest: dict[str, Any], cohort: str,
            reference: str, candidate: str, split: str) -> dict[str, Any]:
    from .engine import check_source
    safe_name(cohort)
    if not enabled(manifest):
        raise LabError("Paired measurement must be approved in a new experiment's configuration")
    if split not in ("validation", "test"):
        raise LabError("Paired selection measurements use validation or the sealed final test")
    if split == "test":
        seal = store.get("final_selection")
        if not seal or cohort != "final" or reference != "baseline" or candidate != seal["label"]:
            raise LabError("Only the sealed final cohort may access test measurements")
    ids = manifest["splits"][split]
    if not ids:
        raise LabError(f"No {split} cases; start a new experiment")
    arms = {}
    for role, label in (("reference", reference), ("candidate", candidate)):
        check_source(state, store, label)
        arms[role] = {"label": label, "source_hash": store.variant(label)["source_hash"]}
    if split == "test" and (arms["reference"]["source_hash"] != seal["baseline_source_hash"]
                            or arms["candidate"]["source_hash"] != seal["source_hash"]):
        raise LabError("Final cohort source identities differ from the seal")
    seed = int(digest({"seed": manifest["config"]["seed"], "cohort": cohort})[:16], 16)
    spec = {"schema_version": 1, "design": "paired_ab_ba", "split": split,
            "arms": arms, "schedule_seed": seed,
            "schedule": schedule(ids, manifest["config"]["repetitions"], seed)}
    store.add_cohort(cohort, spec)
    write_json(state / "paired-cohorts" / cohort / "schedule.json", spec)
    return spec


def _check_sources(state, store, spec):
    from .engine import check_source
    for arm in spec["arms"].values():
        check_source(state, store, arm["label"])
        if store.variant(arm["label"])["source_hash"] != arm["source_hash"]:
            raise LabError("Paired cohort source identity changed")


def comparison(state: Path, store: Store, manifest: dict[str, Any], cohort: str) -> dict[str, Any]:
    spec = store.cohort(cohort)
    if not spec:
        raise LabError("Paired cohort has not been measured; use select to measure fresh references")
    _check_sources(state, store, spec)
    split = spec["split"]
    if split == "test":
        seal = store.get("final_selection")
        if (not seal or cohort != "final" or spec["arms"]["candidate"]["label"] != seal["label"]
                or spec["arms"]["candidate"]["source_hash"] != seal["source_hash"]
                or spec["arms"]["reference"]["label"] != "baseline"
                or spec["arms"]["reference"]["source_hash"] != seal["baseline_source_hash"]):
            raise LabError("Final comparison must match the sealed cohort and source identities")
    expected_seed = int(digest({"seed": manifest["config"]["seed"], "cohort": cohort})[:16], 16)
    expected_schedule = schedule(manifest["splits"][split], manifest["config"]["repetitions"], expected_seed)
    if spec["schedule_seed"] != expected_seed or spec["schedule"] != expected_schedule:
        raise LabError("Persisted paired schedule changed")
    indices = {tuple(job): index for index, job in enumerate(expected_schedule)}
    rows = {role: store.results(role, split, cohort=cohort) for role in spec["arms"]}
    for role, values in rows.items():
        for row in values:
            if (row.get("cohort") != cohort or row.get("role") != role
                    or row.get("source_hash") != spec["arms"][role]["source_hash"]
                    or row.get("source_label") != spec["arms"][role]["label"]
                    or row.get("schedule_index") != indices.get((role, row["case_id"], row["rep"]))):
                raise LabError("Trial measurement cohort or source identity mismatch")
    result = compare_rows(rows["reference"], rows["candidate"], cases=manifest["cases"],
                          ids=manifest["splits"][split], cfg=manifest["config"])
    return {"baseline": spec["arms"]["reference"]["label"],
            "candidate": spec["arms"]["candidate"]["label"], "split": split,
            "measurement": {"design": spec["design"], "cohort": cohort,
                            "schedule_digest": digest(spec), "source_hashes": spec["arms"],
                            "limitation": "Temporal pairing reduces slow drift; it does not remove carryover, shared load shocks, or adaptive selection bias."},
            **result}


def execute(state: Path, store: Store, manifest: dict[str, Any], cohort: str,
            reference: str, candidate: str, split: str, *, allow_test: bool = False) -> dict[str, Any]:
    from .engine import manifest_for, perform_trial
    if split == "test":
        seal = store.get("final_selection")
        if not allow_test or not seal or cohort != "final" or seal["label"] != candidate or reference != "baseline":
            raise LabError("Test cases are sealed. Use finalize after selecting a winner.")
    spec = prepare(state, store, manifest, cohort, reference, candidate, split)
    statuses = store.cohort_statuses(cohort)
    jobs = spec["schedule"]
    prefix = 0
    for job in jobs:
        status = statuses.get(tuple(job))
        if status is None:
            break
        if status != "ok":
            raise LabError("Paired cohort has a failed or indeterminate trial; inspect/recover it, never retry it")
        prefix += 1
    if len(statuses) != prefix or prefix % 2:
        raise LabError("Interrupted half-pair is not temporally paired. This cohort is invalid; no trials are retried. Start a new approved experiment.")
    by_id = {case["id"]: case for case in manifest["cases"]}
    budget = manifest["config"]["budget"]
    for index, (role, case_id, rep) in enumerate(jobs[prefix:], start=prefix):
        manifest_for(state, store, check_time=True)
        _check_sources(state, store, spec)
        if index % 2 == 0:
            # Do not knowingly start half a pair with insufficient trial/cost capacity.
            totals = store.budget()
            if totals["trials"] + 2 > budget["max_trials"]:
                raise LabError("Trial budget cannot cover the next complete pair")
            if totals["eval_charged_usd"] + totals["pending_reserved_usd"] + 2 * budget["trial_reserve_usd"] > budget["max_eval_cost_usd"] + 1e-9:
                raise LabError("Evaluation cost reservation cannot cover the next complete pair")
        arm = spec["arms"][role]
        if not store.reserve(role, split, case_id, rep, budget, cohort=cohort):
            raise LabError("Unexpected existing paired trial; cohort execution order is invalid")
        result = perform_trial(state, manifest, state / "candidates" / arm["label"], by_id[case_id], rep,
                               timeout_cap=max(.01, manifest["expires_at"] - time.time()))
        result.update({"cohort": cohort, "role": role, "source_label": arm["label"],
                       "source_hash": arm["source_hash"], "schedule_index": index})
        store.complete(role, split, case_id, rep, result, result["charged_usd"], cohort=cohort)
        if result["status"] != "ok":
            store.event("paired_trial_error", {"cohort": cohort, "role": role, "case_id": case_id, "rep": rep})
            raise LabError(f"Paired trial failed: {cohort}/{role}/{case_id}/{rep}. No automatic retry.")
    manifest_for(state, store)
    _check_sources(state, store, spec)
    # SQLite is authoritative; rebuild exports after any interruption at a pair boundary.
    for role in spec["arms"]:
        rows = store.results(role, split, cohort=cohort)
        atomic_text(state / "paired-cohorts" / cohort / f"{role}.jsonl", "".join(canonical(row) + "\n" for row in rows))
    result = comparison(state, store, manifest, cohort)
    write_json(state / "paired-cohorts" / cohort / "comparison.json", result)
    store.event("paired_comparison_completed", result)
    return result


def selection_plan(state: Path, store: Store, manifest: dict[str, Any], candidate: str,
                   incumbent: str) -> dict[str, Any]:
    from .engine import check_source
    for label in (candidate, incumbent, "baseline"):
        check_source(state, store, label)
    key = f"paired_selection:{candidate}"
    plan = store.get(key)
    if plan is None:
        prefix = "selection-" + digest({"candidate": candidate})[:20]
        same_source = store.variant(incumbent)["source_hash"] == store.variant("baseline")["source_hash"]
        plan = {"candidate": candidate, "incumbent": incumbent,
                "vs_incumbent": prefix + "-incumbent",
                "vs_start": prefix + ("-incumbent" if same_source else "-start")}
        # Persist both schedules before any measurement; never choose design from results.
        prepare(state, store, manifest, plan["vs_incumbent"], incumbent, candidate, "validation")
        if not same_source:
            prepare(state, store, manifest, plan["vs_start"], "baseline", candidate, "validation")
        store.put(key, plan)
    elif plan["incumbent"] != incumbent:
        raise LabError("This candidate was measured against a different incumbent; register a new candidate identity rather than reusing its cohort")
    return plan


def evaluate_selection(state, store, manifest, candidate, incumbent):
    plan = selection_plan(state, store, manifest, candidate, incumbent)
    decision = execute(state, store, manifest, plan["vs_incumbent"], incumbent, candidate, "validation")
    initial = decision if plan["vs_start"] == plan["vs_incumbent"] else execute(
        state, store, manifest, plan["vs_start"], "baseline", candidate, "validation")
    return decision, initial


def selected_comparison(state, store, manifest, baseline, candidate):
    plan = store.get(f"paired_selection:{candidate}")
    if not plan:
        raise LabError("No paired selection cohort exists; use select to measure fresh references")
    if baseline == "baseline":
        cohort = plan["vs_start"]
    elif baseline == plan["incumbent"]:
        cohort = plan["vs_incumbent"]
    else:
        raise LabError("Requested reference is not part of this paired selection")
    return comparison(state, store, manifest, cohort)
