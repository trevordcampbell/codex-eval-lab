"""Paired, group-cluster bootstrap comparisons without repeat pseudo-replication.

Intervals describe the sampled case distribution. They are not a guarantee about
unseen tasks and are not adjusted for repeated adaptive candidate selection.
"""
from __future__ import annotations

from collections import defaultdict
import math
import random
import statistics
from typing import Any

from .util import LabError, finite


def quantile(values: list[float], q: float) -> float:
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def valid_rows(rows: list[dict[str, Any]], ids: list[str], reps: int) -> dict[tuple[str, int], dict[str, Any]]:
    expected = {(id_, rep) for id_ in ids for rep in range(reps)}
    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        key = (row["case_id"], row["rep"])
        if key in indexed:
            raise LabError("Duplicate trial keys in results")
        indexed[key] = row
        if row["status"] != "ok":
            raise LabError("Cannot compare runs with errors or indeterminate attempts; repair the measurement, not the denominator")
    if set(indexed) != expected or not expected:
        raise LabError("Comparison requires a complete, nonempty identical case × repetition matrix")
    return indexed


def case_means(rows: list[dict[str, Any]], metric: str) -> dict[str, float]:
    per_case: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["status"] == "ok" and metric in row.get("metrics", {}):
            per_case[row["case_id"]].append(finite(row["metrics"][metric], metric))
    return {key: statistics.fmean(values) for key, values in per_case.items()}


def paired_interval(deltas: dict[str, float], groups: dict[str, str], *, confidence: float, samples: int, seed: int) -> dict[str, Any]:
    clustered: dict[str, list[float]] = defaultdict(list)
    for id_, delta in deltas.items():
        clustered[groups[id_]].append(delta)
    clusters = [clustered[g] for g in sorted(clustered)]
    mean = statistics.fmean(deltas.values())
    if len(clusters) < 2:
        return {"mean": mean, "low": None, "high": None, "groups": len(clusters), "cases": len(deltas)}
    rng = random.Random(seed)
    sums = [sum(c) for c in clusters]
    sizes = [len(c) for c in clusters]
    bootstrap = []
    for _ in range(samples):
        picks = [rng.randrange(len(clusters)) for _ in clusters]
        bootstrap.append(sum(sums[p] for p in picks) / sum(sizes[p] for p in picks))
    alpha = (1 - confidence) / 2
    return {"mean": mean, "low": quantile(bootstrap, alpha), "high": quantile(bootstrap, 1 - alpha),
            "groups": len(clusters), "cases": len(deltas), "confidence": confidence,
            "method": "paired percentile bootstrap over related-case groups, after averaging repetitions per case"}


def compare_rows(base_rows: list[dict[str, Any]], candidate_rows: list[dict[str, Any]], *, cases: list[dict[str, Any]], ids: list[str], cfg: dict[str, Any]) -> dict[str, Any]:
    reps = cfg["repetitions"]
    base = valid_rows(base_rows, ids, reps)
    candidate = valid_rows(candidate_rows, ids, reps)
    # Verify stochastic seeds match; missing seeds are not accepted as evidence of pairing.
    for key in base:
        if "seed" not in base[key] or base[key]["seed"] != candidate[key].get("seed"):
            raise LabError("Paired trials have missing or mismatched seeds")
    groups = {c["id"]: c["group"] for c in cases}
    objective = cfg["objective"]
    guards = cfg["guardrails"]
    # Familywise adjustment across this candidate's primary + guardrail intervals.
    confidence = 1 - (1 - objective["confidence"]) / (1 + len(guards))
    rules = [objective] + guards
    results: dict[str, Any] = {}
    decisions: list[bool] = []
    for index, rule in enumerate(rules):
        metric = rule["metric"]
        direction = 1 if rule["direction"] == "maximize" else -1
        a, b = case_means(base_rows, metric), case_means(candidate_rows, metric)
        if set(a) != set(ids) or set(b) != set(ids):
            raise LabError(f"Metric is missing from a complete case matrix: {metric}")
        raw = {id_: b[id_] - a[id_] for id_ in ids}
        favorable = {id_: value * direction for id_, value in raw.items()}
        interval = paired_interval(favorable, groups, confidence=confidence,
                                   samples=objective["bootstrap_samples"], seed=cfg["seed"])
        enough = interval["groups"] >= objective["min_validation_groups"]
        if index == 0:
            threshold = objective["min_improvement"]
            passes = enough and interval["low"] is not None and interval["low"] > threshold
        else:
            threshold = -rule["max_regression"]
            passes = enough and interval["low"] is not None and interval["low"] >= threshold - 1e-12
        decisions.append(bool(passes))
        results[metric] = {"baseline": statistics.fmean(a.values()), "candidate": statistics.fmean(b.values()),
                           "raw_delta": statistics.fmean(raw.values()), "direction": rule["direction"],
                           "favorable_delta": interval, "threshold": threshold, "passes": bool(passes)}
    return {"accepted": all(decisions), "metrics": results, "cases": len(ids),
            "groups": len({groups[id_] for id_ in ids}), "repetitions": reps,
            "decision": "keep" if all(decisions) else "do_not_promote",
            "caveats": ["Intervals are exploratory during adaptive validation selection; final-test confirmation remains necessary.",
                        "Repeats do not create independent new tasks. Related groups, not individual repeated trials, are resampled.",
                        "No statistical method repairs unrepresentative cases, contaminated answers, or a miscalibrated grader."]}
