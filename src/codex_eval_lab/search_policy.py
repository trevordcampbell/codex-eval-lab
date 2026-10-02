"""Explicit exploratory search policies. These decisions are not release evidence.

Only complete development/validation measurements enter the archive. Final-test
data never determine parents, operators, rewards, or capacity decisions.
"""
from __future__ import annotations

import math
import statistics
from typing import Any

from .stats import case_means, valid_rows
from .util import LabError, digest, finite, integer, unknown_keys

OPERATORS = {
    "refine": "Improve the current approach with one targeted algorithmic change. Preserve its strengths and test the stated failure mechanism.",
    "repair": "Use the development failures to diagnose one general failure mechanism. Propose a correction, and state what evidence would falsify it.",
    "rewrite": "Explore a materially different algorithm or representation within the same contract and resource limits. Do not memorize examples.",
}


def validate_policy(cfg: dict) -> None:
    if "search_policy" not in cfg:
        return  # Old configurations and their serialized defaults stay unchanged.
    p = cfg["search_policy"]
    if not isinstance(p, dict):
        raise LabError("search_policy must be a table")
    unknown_keys(p, {"schema_version", "mode", "archive_size", "parent_strategy", "allocation", "operators", "exploration", "diversity_scale", "reward_scale"}, "search_policy")
    if type(p.get("schema_version")) is not int or p["schema_version"] != 1:
        raise LabError("search_policy.schema_version must be 1")
    if p.get("mode") != "archive":
        raise LabError("search_policy.mode must be archive; omit it for conservative legacy selection")
    p.setdefault("archive_size", 8)
    p.setdefault("parent_strategy", "diverse")
    p.setdefault("allocation", "round_robin")
    p.setdefault("operators", ["refine", "repair", "rewrite"])
    p.setdefault("exploration", 1.0)
    p.setdefault("diversity_scale", cfg["objective"]["min_improvement"] or 1.0)
    p.setdefault("reward_scale", cfg["objective"]["min_improvement"] or 1.0)
    integer(p["archive_size"], "archive_size", minimum=2, maximum=100)
    if p["parent_strategy"] not in ("incumbent", "diverse"):
        raise LabError("parent_strategy must be incumbent or diverse")
    if p["allocation"] not in ("round_robin", "ucb"):
        raise LabError("allocation must be round_robin or ucb")
    ops = p["operators"]
    if not isinstance(ops, list) or not ops or any(o not in OPERATORS for o in ops) or len(set(ops)) != len(ops):
        raise LabError("operators must be distinct supported operator names")
    finite(p["exploration"], "exploration", minimum=0, maximum=10)
    finite(p["diversity_scale"], "diversity_scale", minimum=1e-15)
    finite(p["reward_scale"], "reward_scale", minimum=1e-15)


def enabled(manifest: dict) -> bool:
    return manifest["config"].get("search_policy", {}).get("mode") == "archive"


def exploratory_decision(comparison: dict, against_start: dict, cfg: dict) -> dict:
    """Point estimates guide search; the unchanged confidence gate is retained."""
    metric = cfg["objective"]["metric"]
    guards = all(against_start["metrics"][g["metric"]]["favorable_delta"]["mean"] >= -g["max_regression"] - 1e-12
                 for g in cfg["guardrails"])
    improves = comparison["metrics"][metric]["favorable_delta"]["mean"] > 0
    beats_start = against_start["metrics"][metric]["favorable_delta"]["mean"] > 0
    return {"selected_for_search": guards and improves and beats_start,
            "eligible_parent": guards,
            "confidence_gate_passed": comparison["accepted"] and against_start["accepted"],
            "release_qualified": False,
            "reason": "empirical_primary_and_baseline_guardrails" if guards and improves and beats_start else "no_empirical_improvement_or_guardrail_regression",
            "warning": "Adaptive point-estimate search decision; no release claim. Final confirmation is unchanged."}


def candidate_record(store, manifest: dict, label: str, *, eligible: bool = True) -> dict:
    cfg = manifest["config"]
    rows = store.results(label, "train")
    valid_rows(rows, manifest["splits"]["train"], cfg["repetitions"])
    means = case_means(rows, cfg["objective"]["metric"])
    direction = 1 if cfg["objective"]["direction"] == "maximize" else -1
    # A prespecified objective-unit scale makes small timing jitter fall in the
    # same behavioral bucket. This is a descriptive heuristic, not a statistical
    # equivalence test or a proof of semantic novelty.
    base_rows = store.results("baseline", "train")
    valid_rows(base_rows, manifest["splits"]["train"], cfg["repetitions"])
    base = case_means(base_rows, cfg["objective"]["metric"])
    scale = cfg["search_policy"]["diversity_scale"]
    behavior = [[key, round(direction * (means[key] - base[key]) / scale)] for key in sorted(means)]
    return {"label": label, "source_hash": store.variant(label)["source_hash"],
            "development_score": direction * statistics.fmean(means.values()),
            "behavior_hash": digest(behavior), "behavior_descriptor": "rounded per-case training gain / frozen diversity_scale",
            "eligible_parent": eligible,
            "measurement_status": "valid", "release_qualified": False}


def archive_records(store, manifest: dict, label: str, *, eligible: bool = True, selected: str | None = None) -> list[dict]:
    records = store.get("search_archive", [])
    if not any(r["label"] == "baseline" for r in records):
        records.insert(0, candidate_record(store, manifest, "baseline"))
    if not any(r["label"] == label for r in records):
        records.append(candidate_record(store, manifest, label, eligible=eligible))
    p = manifest["config"]["search_policy"]
    # Preserve the selected incumbent and original source. Fill with the best
    # representative of each training behavior, deterministic earliest ties.
    protected = {"baseline", selected or store.get("best")}
    retained = [r for r in records if r["label"] in protected]
    seen = {r["behavior_hash"] for r in retained}
    ranked = sorted(enumerate(records), key=lambda item: (-item[1]["development_score"], item[0]))
    for _, r in ranked:
        if len(retained) >= p["archive_size"]:
            break
        if r["label"] not in protected and r["eligible_parent"] and r["behavior_hash"] not in seen:
            retained.append(r)
            seen.add(r["behavior_hash"])
    return retained


def update_archive(store, manifest: dict, label: str, *, eligible: bool = True) -> list[dict]:
    retained = archive_records(store, manifest, label, eligible=eligible)
    store.put("search_archive", retained)
    store.event("search_archive_updated", {"candidate": label, "retained_labels": [r["label"] for r in retained], "eligible_parent": eligible})
    return retained


def next_context(store, manifest: dict, round_number: int) -> dict:
    """Deterministic choice from durable completed history; no new random state."""
    p = manifest["config"]["search_policy"]
    history = store.get("search_history", [])
    ops = p["operators"]
    counts = {o: 0 for o in ops}
    rewards = {o: 0.0 for o in ops}
    completed = {h["label"]: h for h in history}
    for attempt in store.get("search_dispatches", history):
        h = completed.get(attempt["label"], {})
        operator = (attempt.get("search_context") or {}).get("operator")
        if operator in counts:
            counts[operator] += 1
            # Bounded material gain per measured trial. Failed calls have zero
            # reward but count toward allocation. Inference cost remains unknown.
            metric = manifest["config"]["objective"]["metric"]
            gain = h.get("vs_incumbent", {}).get("metrics", {}).get(metric, {}).get("favorable_delta", {}).get("mean", 0)
            reward = min(1.0, max(0.0, gain) / p["reward_scale"]) if h.get("search_selected") else 0.0
            rewards[operator] += reward / max(1, h.get("evaluation_trials", 1))
    untried = [o for o in ops if not counts[o]]
    if p["allocation"] == "round_robin":
        operator = ops[(round_number - 1) % len(ops)]
    elif untried:
        operator = untried[0]
    else:
        total = sum(counts.values())
        operator = max(ops, key=lambda o: rewards[o] / counts[o] + p["exploration"] * math.sqrt(math.log(total + 1) / counts[o]))
    incumbent = store.get("best")
    parent = incumbent
    candidates = [r for r in store.get("search_archive", []) if r["eligible_parent"] and r["label"] != incumbent]
    if p["parent_strategy"] == "diverse" and operator != "refine" and candidates:
        # Ordered, bounded archive rotation; no randomly changing resume choice.
        parent = candidates[(round_number - 1) % len(candidates)]["label"]
    return {"schema_version": 1, "policy_sha256": digest(p), "round": round_number,
            "parent": parent, "incumbent": incumbent, "operator": operator,
            "operator_instruction": OPERATORS[operator], "allocation": p["allocation"],
            "operator_counts": counts, "operator_reward_sums": rewards,
            "reward_definition": "min(1, positive selected primary gain / frozen reward_scale) / complete candidate evaluation trials; model costs excluded and unknown",
            "release_qualified": False}


def outcome_summary(store) -> dict[str, Any]:
    final = store.get("final_result")
    return {"best_found": store.get("best"), "search_selected": store.get("best"),
            "best_found_definition": "sequential search-selected incumbent; not a global retrospective archive ranking",
            "validation_champion": store.get("validation_champion", "baseline"),
            "release_champion": final["final_selection"]["label"] if final and final["accepted"] else "baseline",
            "release_status": "passed" if final and final["accepted"] else "failed" if final else "not_evaluated",
            "archive": store.get("search_archive", []),
            "warning": "Best found and validation champion are adaptively selected. Only the sealed final comparison supplies separate release evidence."}


def record_dispatch(store, label: str, context: dict | None, call_id: int) -> None:
    if context is None:
        return
    attempts = store.get("search_dispatches", [])
    if any(a["call_id"] == call_id for a in attempts):
        raise LabError("Search dispatch already recorded; do not create another opportunity")
    attempts.append({"call_id": call_id, "label": label, "search_context": context})
    store.put("search_dispatches", attempts)


def author_context(context: dict | None) -> dict | None:
    """Only the chosen strategy/source crosses the proposer boundary.

    Allocation rewards/counts remain private controller diagnostics. Parent/source
    choices are adaptive selection feedback, not new independent evidence.
    """
    if context is None:
        return None
    return {k: context[k] for k in ("schema_version", "policy_sha256", "round", "parent", "incumbent",
                                    "operator", "operator_instruction", "release_qualified")}
