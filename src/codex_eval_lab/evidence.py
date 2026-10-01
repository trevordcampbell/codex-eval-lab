"""Opt-in, source-recomputed evidence readiness for frozen evaluators.

A recorded human attestation is an assertion, not an authentication boundary.
Hashes and schema checks detect stale/missing evidence in cooperative workflows;
no local file can prove who authored it or whether the labels are true.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import collect
from .util import LabError, canonical, contained, digest, file_hash, read_json, relative_name, safe_name

MAX_BUNDLE_BYTES = 25_000_000
MAX_CRITERIA = 128
MAX_EXPLANATION_BYTES = 8192
CRITERION_STATUSES = {"pass", "fail", "abstain", "skipped", "error"}


def evidence_files(cfg: dict[str, Any]) -> list[str]:
    """All evidence dependencies are embedded in one suite-relative sealed bundle."""
    return [cfg["evidence"]["bundle"]] if cfg.get("evidence") else []


def evaluator_fingerprint(suite: Path, cfg: dict[str, Any] | None = None) -> str:
    """Bind evidence to actual declared grader bytes, argv, model, and metrics.

    Helpers must be declared in harness_paths. External services and undeclared
    dynamic dependencies cannot be made immutable by this local fingerprint.
    """
    if cfg is None:
        from .config import load_config
        cfg = load_config(suite)
    execution = cfg["execution"]
    command = execution["grader_command"]
    if any(marker in arg for marker in ("{app}", "{artifacts}") for arg in command):
        raise LabError("Evidence-bound graders cannot execute from candidate or output paths")
    files = collect(suite, cfg["harness_paths"])
    # A bundle may be inside a declared harness directory. Avoid a circular hash.
    for name in evidence_files(cfg):
        files.pop(name, None)
    if not files:
        raise LabError("Evidence requires declared immutable grader files in harness_paths")
    bound_command = False
    for arg in command:
        if "{suite}" in arg:
            if not arg.startswith("{suite}/"):
                raise LabError("Evidence grader suite paths must be explicit argv entries")
            relative = relative_name(arg[len("{suite}/"):])
            target = contained(suite, relative)
            if target.is_file() and relative in files:
                bound_command = True
            else:
                raise LabError("Evidence grader command references an untracked harness file")
        elif arg in files:
            bound_command = True
    if not bound_command:
        raise LabError("Evidence requires a suite-local grader command covered by harness_paths")
    return digest({"schema_version": 1,
                   "grader_command": command,
                   "expected_judge_model": execution.get("expected_judge_model"),
                   "expected_app_model": execution.get("expected_app_model"),
                   "grader_env": execution["grader_env"],
                   "metrics": cfg["metrics"],
                   "harness_sha256": {name: file_hash(path) for name, path in files.items()}})


def validate_criterion_results(value: Any, *, contract: list[dict[str, str]] | None = None) -> None:
    """Validate raw atomic outcomes. Never reconstruct these from aggregate metrics."""
    if not isinstance(value, dict) or not 1 <= len(value) <= MAX_CRITERIA:
        raise LabError("criterion_results must be an object with 1–128 atomic outcomes")
    for criterion_id, result in value.items():
        safe_name(criterion_id)
        if not isinstance(result, dict) or set(result) != {"status", "explanation"}:
            raise LabError("Each criterion result requires exactly status and explanation")
        if not isinstance(result["status"], str) or result["status"] not in CRITERION_STATUSES:
            raise LabError("Criterion status must be pass, fail, abstain, skipped, or error")
        explanation = result["explanation"]
        if isinstance(explanation, str):
            try:
                encoded = explanation.encode("utf-8")
            except UnicodeError as exc:
                raise LabError("Criterion explanation must be valid UTF-8 text") from exc
        else:
            encoded = b""
        if (not isinstance(explanation, str) or not explanation.strip() or "\x00" in explanation
                or len(encoded) > MAX_EXPLANATION_BYTES):
            raise LabError("Criterion explanation must be nonempty text of at most 8192 UTF-8 bytes")
    if len(canonical(value).encode("utf-8")) > 1_000_000:
        raise LabError("criterion_results exceeds the 1 MB result limit")
    if contract is not None:
        if set(value) != {item["id"] for item in contract}:
            raise LabError("Grader omitted or added an approved atomic criterion")
        if any(result["status"] not in {"pass", "fail"} for result in value.values()):
            raise LabError("An approved atomic criterion was skipped or errored, or abstained; aggregate metrics cannot hide it")


def public_evidence_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Audit-safe metadata only; no examples, labels, rubrics, or disagreement IDs."""
    allowed = {"configured", "status", "ready", "message", "human_assertion_only",
               "evaluator_fingerprint", "bundle_sha256", "source_sha256", "criteria_count",
               "judge_criteria_count", "source_kind"}
    return {key: value for key, value in summary.items() if key in allowed}


def validate_evidence(suite: Path, cfg: dict[str, Any] | None = None, *,
                      require_ready: bool = False) -> dict[str, Any]:
    """Recompute readiness from embedded source artifacts, ignoring supplied verdicts.

    All public failures are deliberately content-free. Detailed source reviews stay
    private with the evaluator, never in audit/optimizer output.
    """
    if cfg is None:
        from .config import load_config
        cfg = load_config(suite)
    if not cfg.get("evidence"):
        if require_ready:
            raise LabError("Evidence gate not configured; readiness cannot be established")
        return {"configured": False, "status": "not_configured", "ready": False,
                "message": "Evidence gate not configured", "human_assertion_only": True}
    result: dict[str, Any] = {"configured": True, "status": "invalid", "ready": False,
                              "message": "Evidence artifacts could not be verified",
                              "human_assertion_only": True}
    try:
        from .calibration import validate_evidence_bundle
        path = contained(suite, cfg["evidence"]["bundle"])
        if not path.is_file() or path.stat().st_size > MAX_BUNDLE_BYTES:
            raise LabError("Evidence bundle must be an ordinary JSON file of at most 25 MB")
        fingerprint = evaluator_fingerprint(suite, cfg)
        bundle_hash = file_hash(path)
        bundle = read_json(path)
        report = validate_evidence_bundle(bundle, evaluator_fingerprint=fingerprint)
        if file_hash(path) != bundle_hash or evaluator_fingerprint(suite, cfg) != fingerprint:
            raise LabError("Evidence or grader changed during verification")
        # Human rubric development must not consume this experiment's private
        # selection/final examples, even if an import omitted its split marker.
        from .config import load_cases, make_splits
        cases = load_cases(suite, cfg)
        splits = make_splits(cases, cfg["seed"])
        private_ids = set(splits["validation"] + splits["test"])
        private = [case for case in cases if case["id"] in private_ids]
        private_groups = {case["group"] for case in private}
        private_inputs = {digest(case["input"]) for case in private}
        for trace in bundle["packet"]["traces"]:
            if (trace["id"] in private_ids or trace.get("case_id") in private_ids
                    or trace["group"] in private_groups or digest(trace["input"]) in private_inputs):
                raise LabError("Calibration traces overlap private experiment groups or inputs")
        contract = report["criteria_contract"]
        if not isinstance(contract, list) or not 1 <= len(contract) <= MAX_CRITERIA:
            raise LabError("Invalid atomic criterion contract")
        directions = {gate["metric"]: gate["direction"] for gate in [cfg["objective"], *cfg["guardrails"]]}
        for item in contract:
            if item["metric"] not in cfg["metrics"] or item["metric"] in {"cost_usd", "latency_s"}:
                raise LabError("Evidence criterion does not match an execution grader metric")
            if directions.get(item["metric"]) != "maximize":
                raise LabError("Every atomic success metric must be a maximize objective or guardrail")
            bounds = cfg["metrics"][item["metric"]]
            if bounds.get("minimum", 0) > 0 or bounds.get("maximum", 1) < 1:
                raise LabError("Atomic criterion metrics must permit binary 0/1 outcomes")
        expected = cfg["execution"].get("expected_judge_model")
        if any(item["kind"] == "judge" for item in contract):
            if bundle["policy"]["threshold_basis"] != "lower_bound":
                raise LabError("LLM readiness requires uncertainty-aware lower-bound calibration thresholds")
            if not expected:
                raise LabError("LLM evidence requires execution.expected_judge_model")
            expected_app = cfg["execution"].get("expected_app_model")
            if not expected_app or bundle["judge_config"]["application_model"] != expected_app:
                raise LabError("LLM evidence must match execution.expected_app_model")
        if expected is not None and report["judge_model"] != expected:
            raise LabError("Evidence model differs from the execution model")
        ready = report.get("passed") is True
        result.update(status="ready" if ready else "not_ready", ready=ready,
                      message="Evidence readiness checks passed" if ready else "Evidence support or calibration checks failed",
                      evaluator_fingerprint=fingerprint, bundle_sha256=bundle_hash,
                      source_sha256=report["source_sha256"],
                      criteria_count=len(contract), judge_criteria_count=sum(c["kind"] == "judge" for c in contract),
                      criteria_contract=contract, judge_model=report["judge_model"],
                      source_kind=bundle["packet"]["source"]["kind"])
    except (LabError, OSError, UnicodeError, ValueError, TypeError, KeyError, RecursionError):
        # Never echo arbitrary labels/outputs supplied by an invalid bundle.
        pass
    if require_ready and not result["ready"]:
        raise LabError("Evidence gate is not ready: verify human review, anchors, calibration, source hashes, and grader identity")
    return result
