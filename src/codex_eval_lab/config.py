"""Configuration and case validation. No executable code is imported here."""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import random
import tomllib
from typing import Any

from .util import LabError, canonical, contained, digest, finite, integer, relative_name, safe_name, strict_json, unknown_keys

TOP = {"schema_version", "name", "cases", "repetitions", "seed", "source_paths", "harness_paths", "execution", "metrics", "objective", "guardrails", "budget", "search", "optimizer", "evidence", "measurement", "oracle", "search_policy"}


def strings(value: Any, name: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value) or any(not isinstance(v, str) or not v or "\x00" in v for v in value):
        raise LabError(f"{name} must be a {'nonempty ' if nonempty else ''}list of nonempty strings")
    return value


def load_config(suite: Path) -> dict[str, Any]:
    try:
        cfg = tomllib.loads((suite / "eval.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise LabError(f"Cannot read eval.toml: {exc}") from exc
    return validate_config(cfg)


def validate_config(cfg: dict[str, Any]) -> dict[str, Any]:
    unknown_keys(cfg, TOP, "configuration")
    if type(cfg.get("schema_version")) is not int or cfg["schema_version"] != 1:
        raise LabError("schema_version must be 1")
    safe_name(cfg.get("name", ""))
    relative_name(cfg.get("cases", ""))
    cfg.setdefault("repetitions", 1)
    cfg.setdefault("seed", 42)
    integer(cfg["repetitions"], "repetitions", maximum=10000)
    integer(cfg["seed"], "seed", minimum=0)
    for field in ("source_paths", "harness_paths"):
        for path in strings(cfg.get(field), field, nonempty=(field == "source_paths")):
            relative_name(path)
    for field in ("execution", "metrics", "objective", "budget", "search"):
        if not isinstance(cfg.get(field), dict):
            raise LabError(f"[{field}] is required")
    ex = cfg["execution"]
    unknown_keys(ex, {"mode", "app_command", "grader_command", "timeout_s", "grader_timeout_s", "max_output_bytes", "app_env", "grader_env", "docker_image", "docker_memory", "docker_cpus", "expected_app_model", "expected_judge_model"}, "execution")
    ex.setdefault("mode", "local")
    if ex["mode"] not in ("local", "docker"):
        raise LabError("execution.mode must be local or docker")
    for field in ("app_command", "grader_command"):
        strings(ex.get(field), f"execution.{field}")
        for arg in ex[field]:
            # Only these substitutions are supported; never eval, shell-expand, or format arbitrary fields.
            rest = arg
            for marker in ("{python}", "{app}", "{suite}", "{artifacts}"):
                rest = rest.replace(marker, "")
            if "{" in rest or "}" in rest:
                raise LabError(f"Unknown command placeholder in {arg!r}")
        if field == "app_command" and any("{suite}" in arg for arg in ex[field]):
            raise LabError("The app must not receive the private evaluator directory ({suite})")
    for field, default in (("timeout_s", 60), ("grader_timeout_s", 60)):
        ex.setdefault(field, default)
        finite(ex[field], field, minimum=0.01, maximum=86400)
    ex.setdefault("max_output_bytes", 2_000_000)
    integer(ex["max_output_bytes"], "max_output_bytes", minimum=1024, maximum=100_000_000)
    for field in ("app_env", "grader_env"):
        ex.setdefault(field, [])
        strings(ex[field], field, nonempty=False)
        for name in ex[field]:
            if not name.replace("_", "A").isalnum() or name[0].isdigit():
                raise LabError(f"Invalid environment variable name: {name}")
    for field in ("expected_app_model", "expected_judge_model", "docker_image", "docker_memory"):
        if field in ex and (not isinstance(ex[field], str) or not ex[field] or "\x00" in ex[field]):
            raise LabError(f"execution.{field} must be a nonempty string")
    if "docker_cpus" in ex:
        finite(ex["docker_cpus"], "docker_cpus", minimum=0.01)
    if ex["mode"] == "docker" and not isinstance(ex.get("docker_image"), str):
        raise LabError("Docker execution requires docker_image (prefer a digest-pinned image)")
    if not cfg["metrics"]:
        raise LabError("Declare at least one metric")
    for metric, bounds in cfg["metrics"].items():
        safe_name(metric)
        if not isinstance(bounds, dict):
            raise LabError(f"Metric {metric} must be a table")
        unknown_keys(bounds, {"minimum", "maximum", "description"}, f"metric {metric}")
        for field in ("minimum", "maximum"):
            if field in bounds:
                finite(bounds[field], f"{metric}.{field}")
        if bounds.get("minimum", float("-inf")) > bounds.get("maximum", float("inf")):
            raise LabError(f"Inverted bounds for {metric}")
    obj = cfg["objective"]
    unknown_keys(obj, {"metric", "direction", "min_improvement", "confidence", "min_validation_groups", "bootstrap_samples"}, "objective")
    obj.setdefault("min_improvement", 0.0)
    obj.setdefault("confidence", 0.95)
    obj.setdefault("min_validation_groups", 8)
    obj.setdefault("bootstrap_samples", 4000)
    check_direction(obj, cfg, "objective")
    finite(obj["min_improvement"], "min_improvement", minimum=0)
    finite(obj["confidence"], "confidence", minimum=0.8, maximum=0.999)
    integer(obj["min_validation_groups"], "min_validation_groups", minimum=2)
    integer(obj["bootstrap_samples"], "bootstrap_samples", minimum=500, maximum=100000)
    guards = cfg.setdefault("guardrails", [])
    if not isinstance(guards, list):
        raise LabError("guardrails must be an array of tables")
    seen = {obj["metric"]}
    for g in guards:
        if not isinstance(g, dict):
            raise LabError("Each guardrail must be a table")
        unknown_keys(g, {"metric", "direction", "max_regression"}, "guardrail")
        check_direction(g, cfg, "guardrail")
        if g["metric"] in seen:
            raise LabError("Objective and guardrail metrics must be distinct")
        seen.add(g["metric"])
        finite(g.get("max_regression"), "max_regression", minimum=0)
    budget = cfg["budget"]
    unknown_keys(budget, {"max_eval_cost_usd", "trial_reserve_usd", "max_trials", "max_wall_time_s", "max_optimizer_calls"}, "budget")
    for field in ("max_eval_cost_usd", "trial_reserve_usd"):
        finite(budget.get(field), field, minimum=0)
    if budget["trial_reserve_usd"] > budget["max_eval_cost_usd"]:
        raise LabError("trial_reserve_usd exceeds max_eval_cost_usd")
    integer(budget.get("max_trials"), "max_trials")
    finite(budget.get("max_wall_time_s"), "max_wall_time_s", minimum=1)
    budget.setdefault("max_optimizer_calls", 0)
    integer(budget["max_optimizer_calls"], "max_optimizer_calls", minimum=0, maximum=1000)
    search = cfg["search"]
    unknown_keys(search, {"editable", "max_rounds", "patience", "max_edit_bytes", "max_feedback_bytes"}, "search")
    for pattern in strings(search.get("editable"), "search.editable"):
        relative_name(pattern)
        if pattern in ("*", "**", "**/*"):
            raise LabError("Use specific editable files/directories, not a catch-all")
    search.setdefault("max_rounds", 5)
    search.setdefault("patience", 3)
    search.setdefault("max_edit_bytes", 1_000_000)
    integer(search["max_rounds"], "max_rounds", maximum=1000)
    integer(search["patience"], "patience", maximum=1000)
    integer(search["max_edit_bytes"], "max_edit_bytes", maximum=100_000_000)
    if "max_feedback_bytes" in search:
        integer(search["max_feedback_bytes"], "max_feedback_bytes", minimum=4096, maximum=2_000_000)
    opt = cfg.setdefault("optimizer", {"backend": "codex"})
    if not isinstance(opt, dict):
        raise LabError("optimizer must be a table")
    unknown_keys(opt, {"backend", "command", "model", "timeout_s", "environment"}, "optimizer")
    opt.setdefault("backend", "codex")
    opt.setdefault("timeout_s", 600)
    opt.setdefault("environment", [])
    finite(opt["timeout_s"], "optimizer.timeout_s", minimum=1, maximum=86400)
    strings(opt["environment"], "optimizer.environment", nonempty=False)
    if "model" in opt and (not isinstance(opt["model"], str) or not opt["model"] or "\x00" in opt["model"]):
        raise LabError("optimizer.model must be a nonempty string")
    for name in opt["environment"]:
        if not name.replace("_", "A").isalnum() or name[0].isdigit():
            raise LabError(f"Invalid optimizer environment variable name: {name}")
    if opt["backend"] not in ("codex", "command"):
        raise LabError("optimizer.backend must be codex or command")
    if opt["backend"] == "command":
        strings(opt.get("command"), "optimizer.command")
    if "evidence" in cfg:
        evidence = cfg["evidence"]
        if not isinstance(evidence, dict):
            raise LabError("evidence must be a table")
        unknown_keys(evidence, {"bundle"}, "evidence")
        evidence["bundle"] = relative_name(evidence.get("bundle", ""))
    if "oracle" in cfg:
        if "evidence" in cfg:
            raise LabError("Use the expert-calibration path for mixed semantic/deterministic criteria; oracle and evidence cannot be combined")
        oracle = cfg["oracle"]
        if not isinstance(oracle, dict):
            raise LabError("oracle must be a table")
        unknown_keys(oracle, {"contract"}, "oracle")
        oracle["contract"] = relative_name(oracle.get("contract", ""))
    if "measurement" in cfg:
        measurement = cfg["measurement"]
        if not isinstance(measurement, dict):
            raise LabError("measurement must be a table")
        unknown_keys(measurement, {"design"}, "measurement")
        if measurement.get("design") != "paired_ab_ba":
            raise LabError('measurement.design must be "paired_ab_ba" when configured')
    from .search_policy import validate_policy
    validate_policy(cfg)
    return cfg


def check_direction(obj: dict[str, Any], cfg: dict[str, Any], name: str) -> None:
    if obj.get("metric") not in cfg["metrics"]:
        raise LabError(f"{name} references an undeclared metric")
    if obj.get("direction") not in ("maximize", "minimize"):
        raise LabError(f"{name}.direction must be maximize or minimize")


def load_cases(suite: Path, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    path = contained(suite, cfg["cases"])
    cases: list[dict[str, Any]] = []
    ids: set[str] = set()
    inputs: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        case = strict_json(line)
        if not isinstance(case, dict):
            raise LabError(f"Case line {line_number} must be an object")
        unknown_keys(case, {"id", "input", "expected", "tags", "group", "assets", "split", "metadata"}, "case")
        safe_name(case.get("id", ""))
        if case["id"] in ids:
            raise LabError(f"Duplicate case id: {case['id']}")
        ids.add(case["id"])
        if "input" not in case:
            raise LabError(f"Missing input: {case['id']}")
        case.setdefault("expected", None)
        case.setdefault("tags", ["default"])
        strings(case["tags"], "tags")
        case.setdefault("group", case["id"])
        safe_name(case["group"])
        case.setdefault("assets", [])
        strings(case["assets"], "assets", nonempty=False)
        for asset in case["assets"]:
            if not contained(suite, asset).is_file():
                raise LabError(f"Asset must be a file: {asset}")
        fingerprint = digest({"input": case["input"], "assets": case["assets"]})
        if fingerprint in inputs and inputs[fingerprint] != case["group"]:
            raise LabError("Duplicate inputs must share a group to avoid cross-split leakage")
        inputs[fingerprint] = case["group"]
        if "split" in case and case["split"] not in ("train", "validation", "test"):
            raise LabError(f"Invalid split on {case['id']}")
        cases.append(case)
    if not cases:
        raise LabError("No evaluation cases")
    return cases


def make_splits(cases: list[dict[str, Any]], seed: int) -> dict[str, list[str]]:
    """Stratified 60/20/20 group split. Explicit splits are supported and checked."""
    split: dict[str, list[str]] = {"train": [], "validation": [], "test": []}
    explicit = ["split" in c for c in cases]
    if any(explicit) and not all(explicit):
        raise LabError("Either all cases have explicit splits or none do")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        groups[case["group"]].append(case)
    if all(explicit):
        for group in groups.values():
            if len({c["split"] for c in group}) != 1:
                raise LabError("A related case group crosses explicit splits")
        for case in cases:
            split[case["split"]].append(case["id"])
        return split
    strata: dict[str, list[str]] = defaultdict(list)
    for gid, members in groups.items():
        labels = {c["tags"][0] for c in members}
        if len(labels) != 1:
            raise LabError("A group spans primary tags; use a common stratum or explicit splits")
        strata[next(iter(labels))].append(gid)
    rng = random.Random(seed)
    for stratum in sorted(strata):
        gids = sorted(strata[stratum])
        rng.shuffle(gids)
        n = len(gids)
        n_val = max(1, round(n * .2)) if n >= 3 else 0
        n_test = max(1, round(n * .2)) if n >= 3 else 0
        for index, gid in enumerate(gids):
            target = "validation" if index < n_val else "test" if index < n_val + n_test else "train"
            split[target].extend(c["id"] for c in groups[gid])
    return {key: sorted(value) for key, value in split.items()}


def audit(suite: Path) -> dict[str, Any]:
    cfg = load_config(suite)
    cases = load_cases(suite, cfg)
    splits = make_splits(cases, cfg["seed"])
    warnings: list[str] = []
    if cfg.get("measurement", {}).get("design") == "paired_ab_ba":
        warnings.append("Paired mode measures fresh references for each candidate and final test. Budget all calls; interruption within a pair invalidates its cohort.")
    else:
        warnings.append("Default measurements are variant-blocked and reuse cached validation references. Case/seed pairing is not temporal pairing; use a new approved paired_ab_ba experiment for timing-sensitive selection.")
    if cfg["execution"]["mode"] == "local":
        warnings.append("Local processes are NOT an isolation boundary. Use only trusted code; holdouts remain accessible to the same OS user.")
    if cfg["execution"]["mode"] == "docker" and "@sha256:" not in cfg["execution"]["docker_image"]:
        warnings.append("Docker image is not digest-pinned; mutable tags undermine reproducibility.")
    for name in ("train", "validation", "test"):
        if not splits[name]:
            warnings.append(f"{name} split is empty; automatic selection/final testing may be unavailable.")
    by_id = {c["id"]: c for c in cases}
    n_groups = len({by_id[i]["group"] for i in splits["validation"]})
    if n_groups < cfg["objective"]["min_validation_groups"]:
        warnings.append("Too few independent validation groups for automatic acceptance; add groups, not merely repeats.")
    for path in cfg["harness_paths"]:
        contained(suite, path)
    from .evidence import public_evidence_summary, validate_evidence
    evidence_gate = validate_evidence(suite, cfg)
    if evidence_gate["status"] == "not_configured" and not cfg.get("oracle"):
        warnings.append("Evidence gate not configured; structural checks do not establish evaluation readiness or grader trust.")
    elif evidence_gate["configured"] and not evidence_gate["ready"]:
        warnings.append("Evidence gate is not ready; initialization and optimization are blocked until the recorded evidence passes.")
    if evidence_gate.get("source_kind") == "synthetic":
        warnings.append("Synthetic calibration evidence exercises the workflow; it does not establish production performance.")
    oracle_gate = {"configured": False, "ready": False, "status": "not_configured"}
    if cfg.get("oracle"):
        from .oracle import load_contract, binding, all_requests, LIMITS
        contract = load_contract(suite, cfg)
        from .oracle_controls import coverage_summary
        oracle_gate = {"configured": True, "ready": False, "status": "execution_required",
                       "control_coverage": coverage_summary(contract), "binding": binding(suite, cfg, contract), "preflight_calls": len(all_requests(suite, cfg, contract)),
                       "author_kind": contract["author"]["kind"], "source_kind": contract["source"]["kind"],
                       "human_reviewed": False, "limitations": LIMITS}
        warnings.append("Oracle schema checked only; authorized start must execute the bound reference and mutation controls.")
    full_trials = len(cases) * cfg["repetitions"]
    return {"suite": cfg["name"], "cases": len(cases), "groups": len({c["group"] for c in cases}),
            "splits": {s: len(v) for s, v in splits.items()}, "repetitions": cfg["repetitions"],
            "full_pass_trials": full_trials,
            "full_pass_reserved_eval_usd": full_trials * cfg["budget"]["trial_reserve_usd"],
            "optimizer_cost": "separate; tokens/calls recorded, dollar cost may be unknown",
            "evidence_gate": public_evidence_summary(evidence_gate), "oracle_gate": oracle_gate,
            "warnings": warnings,
            "human_checks": ["Representative cases and realistic difficulty", ("Specification validity and declared anchor/reference independence; no human labeling requirement for exact controls" if cfg.get("oracle") else "Human-reviewed labels and rubric calibration"), "No training contamination or production side effects", "Meaningful minimum effect and sufficient measurement resolution", "Source, dependencies, fixture and model identity reproducible"]}
