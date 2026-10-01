"""Criterion-level calibration with failure-positive, group-balanced evidence.

No provider calls are made here. The operator imports actual criterion judgments;
code checks and composite scores never substitute for a missing judge decision.
Acceptance evidence is recomputed from trace/rubric/config/label/output snapshots.
"""
from __future__ import annotations

from collections import defaultdict
import math
import re
from typing import Any

from .review import (PROVENANCE_LIMITATION, _bound_row, _object, _rows, _sealed,
                     _text, _trace_map, seal, validate_labels, validate_rubric,
                     validate_review)
from .util import LabError, digest, finite, integer

CONFIG_KEYS = {"schema_version", "model", "model_family", "application_model",
               "application_model_family", "prompt", "parameters", "evaluator_fingerprint"}
POLICY_KEYS = {"schema_version", "positive_class", "min_failure_groups", "min_pass_groups",
               "min_failure_recall", "min_failure_precision", "min_good_specificity", "confidence", "threshold_basis"}
OUTPUT_STATUSES = {"pass", "fail", "abstain", "skipped", "error"}


def validate_judge_config(config: dict) -> dict:
    _object(config, CONFIG_KEYS | {"independence_justification"}, "judge configuration", CONFIG_KEYS)
    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise LabError("Unsupported judge configuration schema")
    for key in CONFIG_KEYS - {"schema_version", "parameters"}:
        _text(config[key], f"judge_config.{key}")
    if not re.fullmatch(r"[a-f0-9]{64}", config["evaluator_fingerprint"]):
        raise LabError("judge_config.evaluator_fingerprint must be a SHA-256 digest")
    if not isinstance(config["parameters"], dict):
        raise LabError("judge_config.parameters must be an object")
    if "independence_justification" in config:
        _text(config["independence_justification"], "independence_justification")
    digest(config)  # Reject non-JSON/nonfinite configuration values.
    return config


def validate_policy(policy: dict) -> dict:
    _object(policy, POLICY_KEYS, "calibration policy")
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise LabError("Unsupported calibration policy schema")
    if policy["positive_class"] != "failure":
        raise LabError("Calibration positive_class must be failure (fail is the positive class)")
    finite(policy["confidence"], "confidence", minimum=0.5, maximum=0.999999)
    if policy["threshold_basis"] not in ("lower_bound", "point_estimate"):
        raise LabError("threshold_basis must be lower_bound or point_estimate")
    for key in ("min_failure_groups", "min_pass_groups"):
        integer(policy[key], key, minimum=1)
    for key in ("min_failure_recall", "min_failure_precision", "min_good_specificity"):
        finite(policy[key], key, minimum=0, maximum=1)
    return policy


def validate_judge_outputs(packet: dict, rubric: dict, config: dict, outputs: dict) -> dict:
    traces = _trace_map(packet)
    validate_rubric(packet, rubric)
    validate_judge_config(config)
    _sealed(outputs, "judge_outputs", {"packet_sha256", "rubric_sha256", "judge_config_sha256", "rows"})
    if outputs["packet_sha256"] != packet["sha256"] or outputs["rubric_sha256"] != rubric["sha256"]:
        raise LabError("Judge output packet/rubric hash mismatch")
    if outputs["judge_config_sha256"] != digest(config):
        raise LabError("Judge output configuration hash mismatch; evaluator changes require recalibration")
    criteria = {c["id"]: c for c in rubric["criteria"]}
    seen = set()
    for row in _rows(outputs["rows"], "judge output rows", nonempty=False):
        _bound_row(row, traces, {"criterion_id", "status", "reason", "model"}, "judge output")
        _text(row["criterion_id"], "criterion_id")
        if row["criterion_id"] not in criteria:
            raise LabError("Unknown criterion in judge output; composite-only outputs are not calibration")
        key = (row["trace_id"], row["criterion_id"])
        if key in seen:
            raise LabError("Duplicate (trace, criterion) judge output")
        seen.add(key)
        _text(row["status"], "judge status")
        if row["status"] not in OUTPUT_STATUSES:
            raise LabError("Judge status must be pass, fail, abstain, skipped, or error")
        _text(row["reason"], "judge output reason")
        _text(row["model"], "served model")
        if criteria[row["criterion_id"]]["kind"] == "judge" and row["model"] != config["model"]:
            raise LabError("Actual served judge model differs from calibrated judge configuration")
    return outputs


def create_judge_outputs(packet: dict, rubric: dict, judge_config: dict, rows: list[dict]) -> dict:
    """Seal independently recorded criterion results, including non-decisions."""
    validate_rubric(packet, rubric)
    validate_judge_config(judge_config)
    result = seal({"schema_version": 1, "kind": "judge_outputs", "packet_sha256": packet["sha256"],
                   "rubric_sha256": rubric["sha256"], "judge_config_sha256": digest(judge_config), "rows": rows})
    return validate_judge_outputs(packet, rubric, judge_config, result)


def _inferred_family(model: str) -> str | None:
    name = model.casefold().split("/")[-1]
    # Deliberately conservative: different versions/names do not prove independence.
    for family in ("gpt", "claude", "gemini", "llama", "qwen", "deepseek", "mistral"):
        if family in name:
            return family
    if re.match(r"o[1-9](?:\D|$)", name):
        return "openai-reasoning"
    return None


def family_warnings(config: dict) -> list[str]:
    validate_judge_config(config)
    same_name = config["model"].casefold() == config["application_model"].casefold()
    same_declared = config["model_family"].casefold() == config["application_model_family"].casefold()
    inferred = _inferred_family(config["model"])
    same_inferred = inferred is not None and inferred == _inferred_family(config["application_model"])
    warnings = ["Different model names or families do not establish independent errors; inspect human anchors."]
    if same_name or same_declared or same_inferred:
        warnings.append("Same-model or same-family judge/application overlap: correlated errors are possible.")
    if "unknown" in (config["model_family"].casefold(), config["application_model_family"].casefold()):
        warnings.append("Model family is unknown; independence cannot be assessed from the supplied identity.")
    return warnings


def _group_rate(rows: list[dict], denominator, numerator) -> float | None:
    buckets = defaultdict(list)
    for row in rows:
        if denominator(row):
            buckets[row["group"]].append(float(numerator(row)))
    if not buckets:
        return None
    return sum(sum(v) / len(v) for v in buckets.values()) / len(buckets)


def _partition_summary(rows: list[dict], *, confidence: float, comparisons: int) -> dict:
    binary = [r for r in rows if r["human_verdict"] in ("pass", "fail")]
    confusion = {
        "true_failures": sum(r["human_verdict"] == "fail" and r["judge_status"] == "fail" for r in rows),
        "missed_failures": sum(r["human_verdict"] == "fail" and r["judge_status"] == "pass" for r in rows),
        "false_alarms": sum(r["human_verdict"] == "pass" and r["judge_status"] == "fail" for r in rows),
        "true_passes": sum(r["human_verdict"] == "pass" and r["judge_status"] == "pass" for r in rows),
    }
    support = {
        "groups": len({r["group"] for r in rows}), "trace_rows": len(rows),
        "failure_groups": len({r["group"] for r in binary if r["human_verdict"] == "fail"}),
        "pass_groups": len({r["group"] for r in binary if r["human_verdict"] == "pass"}),
        "failure_rows": sum(r["human_verdict"] == "fail" for r in rows),
        "pass_rows": sum(r["human_verdict"] == "pass" for r in rows),
        "uncertain_human_rows": sum(r["human_verdict"] == "uncertain" for r in rows),
        "missing_human_rows": sum(r["human_verdict"] == "missing" for r in rows),
        "unresolved_judge_rows": sum(r["judge_status"] not in ("pass", "fail") for r in rows),
        "predicted_failure_groups": len({r["group"] for r in binary if r["judge_status"] == "fail"}),
    }
    failure_recall = _group_rate(binary, lambda r: r["human_verdict"] == "fail",
                                lambda r: r["judge_status"] == "fail")
    failure_precision = _group_rate(binary, lambda r: r["judge_status"] == "fail",
                                   lambda r: r["human_verdict"] == "fail")
    good_specificity = _group_rate(binary, lambda r: r["human_verdict"] == "pass",
                                  lambda r: r["judge_status"] == "pass")
    disagreements, unresolved = [], []
    for row in rows:
        if row["human_verdict"] not in ("pass", "fail") or row["judge_status"] not in ("pass", "fail"):
            unresolved.append(row)
        elif row["human_verdict"] != row["judge_status"]:
            disagreements.append({**row, "error_type": "missed_failure" if row["human_verdict"] == "fail" else "false_alarm"})
    intervals = {}
    for metric, estimate, n in (
            ("failure_recall", failure_recall, support["failure_groups"]),
            ("failure_precision", failure_precision, support["predicted_failure_groups"]),
            ("good_output_specificity", good_specificity, support["pass_groups"])):
        # Union bound across two tails and all prespecified criterion/metric pairs.
        radius = math.sqrt(math.log(2 * comparisons / (1 - confidence)) / (2 * n)) if n else None
        intervals[metric] = {
            "lower": max(0.0, estimate - radius) if estimate is not None else None,
            "upper": min(1.0, estimate + radius) if estimate is not None else None,
            "independent_groups": n,
        }
    return {"support": support, "confusion_rows": confusion, "bounds": intervals,
            "failure_recall": failure_recall, "failure_precision": failure_precision,
            "good_output_specificity": good_specificity,
            "disagreements": disagreements, "unresolved": unresolved}


def calibrate(packet: dict, rubric: dict, labels: dict, judge_config: dict,
              outputs: dict, policy: dict) -> dict:
    """Evaluate every criterion separately against frozen human labels.

    Failure is positive. Rates first average class-conditional decisions within
    each related group, then equally across groups. Raw row counts are descriptive,
    never independent support. Missing/uncertain/abstained rows block acceptance.
    """
    validate_labels(packet, rubric, labels)
    validate_judge_outputs(packet, rubric, judge_config, outputs)
    validate_policy(policy)
    human = {(r["trace_id"], r["criterion_id"]): r for r in labels["labels"]}
    judged = {(r["trace_id"], r["criterion_id"]): r for r in outputs["rows"]}
    issues, results = [], {}
    for criterion in rubric["criteria"]:
        cid = criterion["id"]
        partition_rows = {"tuning": [], "validation": []}
        for trace in packet["traces"]:
            key = (trace["id"], cid)
            h, j = human.get(key, {}), judged.get(key, {})
            partition_rows[trace["partition"]].append({
                "trace_id": trace["id"], "trace_sha256": trace["sha256"], "group": trace["group"],
                "criterion_id": cid, "human_verdict": h.get("verdict", "missing"),
                "human_rationale": h.get("rationale"), "judge_status": j.get("status", "missing"),
                "judge_reason": j.get("reason"),
            })
        parts = {name: _partition_summary(rows, confidence=policy["confidence"],
                                              comparisons=3 * len(rubric["criteria"]))
                 for name, rows in partition_rows.items()}
        for name, part in parts.items():
            if part["unresolved"]:
                issues.append(f"{cid}:{name}:unresolved_rows")
        validation = parts["validation"]
        for field, threshold in (("failure_groups", "min_failure_groups"), ("pass_groups", "min_pass_groups")):
            if validation["support"][field] < policy[threshold]:
                issues.append(f"{cid}:validation:insufficient_{field}")
        for metric, threshold in (("failure_recall", "min_failure_recall"),
                                  ("failure_precision", "min_failure_precision"),
                                  ("good_output_specificity", "min_good_specificity")):
            value = (validation["bounds"][metric]["lower"] if policy["threshold_basis"] == "lower_bound"
                     else validation[metric])
            if value is None:
                issues.append(f"{cid}:validation:undefined_{metric}")
            elif value < policy[threshold]:
                issues.append(f"{cid}:validation:below_{metric}")
        results[cid] = parts
    warnings = family_warnings(judge_config)
    if any(c["kind"] == "judge" for c in rubric["criteria"]):
        if any(w.startswith(("Same-model", "Model family is unknown")) for w in warnings) and not judge_config.get("independence_justification"):
            issues.append("judge:family_overlap_or_unknown_requires_justification")
    if packet["source"]["kind"] == "synthetic":
        warnings.append("Synthetic review data exercise the workflow; they do not establish production performance.")
    if policy["threshold_basis"] == "point_estimate":
        warnings.append("Exploratory point-estimate policy: passing is not statistically supported acceptance; use lower_bound for acceptance.")
    warnings.append("Failure precision depends on labeled-sample prevalence; curated/oversampled failures do not estimate deployment precision or production error rate.")
    warnings.append(PROVENANCE_LIMITATION)
    return seal({"schema_version": 1, "kind": "calibration_report", "positive_class": "failure",
            "rate_unit": "equal-weight related groups, class-conditional within each group",
            "undefined_rates": "null; never substituted with zero or one",
            "uncertainty": {
                "method": "two-sided Hoeffding bounds, Bonferroni/union bound over all criterion-metric pairs",
                "confidence": policy["confidence"], "comparisons": 3 * len(rubric["criteria"]),
                "scope": "simultaneous validation bounds; tuning intervals are descriptive and not acceptance evidence",
                "assumptions": "Declared groups are independent bounded sampling units representative of the target group-conditional estimand. Group declarations, label truth and representativeness are not verified.",
            },
            "threshold_basis": policy["threshold_basis"],
            "source_sha256": {"packet": packet["sha256"], "review": rubric["review_sha256"], "rubric": rubric["sha256"],
                              "labels": labels["sha256"], "judge_config": digest(judge_config),
                              "outputs": outputs["sha256"], "policy": digest(policy)},
            "criteria_contract": [{k: c[k] for k in ("id", "kind", "metric")} for c in rubric["criteria"]],
            "judge_model": judge_config["model"], "criteria": results,
            "passed": not issues, "readiness_eligible": policy["threshold_basis"] == "lower_bound",
            "ready": not issues and policy["threshold_basis"] == "lower_bound", "issues": issues, "warnings": warnings,
            "independence_justification": judge_config.get("independence_justification"),
            "policy": dict(policy)})


def _validate_anchor_labels(packet: dict, review: dict, rubric: dict, labels: dict) -> None:
    """A later label import cannot silently reverse the rubric's human anchors."""
    validate_labels(packet, rubric, labels)
    reviewed = {r["trace_id"]: r for r in review["annotations"]}
    labeled = {(r["trace_id"], r["criterion_id"]): r for r in labels["labels"]}
    for criterion in rubric["criteria"]:
        for tid in criterion["anchors"]:
            observed = reviewed[tid]
            expected = ("pass" if observed["verdict"] == "pass" else
                        "fail" if observed["verdict"] == "fail" and criterion["failure_mode"] in observed["failure_modes"]
                        else None)
            actual = labeled.get((tid, criterion["id"]))
            if expected is not None and actual is not None and actual["verdict"] not in (expected, "uncertain"):
                raise LabError("Criterion label contradicts reviewed rubric anchor; revise human review/rubric explicitly")


def create_evidence_bundle(packet: dict, review: dict, rubric: dict, labels: dict,
                           judge_config: dict, outputs: dict, policy: dict, *,
                           evaluator_fingerprint: str) -> dict:
    """Bind recomputable acceptance evidence to current evaluator source/config."""
    validate_review(packet, review)
    validate_rubric(packet, rubric, review)
    _validate_anchor_labels(packet, review, rubric, labels)
    validate_judge_config(judge_config)
    if not isinstance(evaluator_fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", evaluator_fingerprint):
        raise LabError("evaluator_fingerprint must be a SHA-256 digest")
    if judge_config.get("evaluator_fingerprint") != evaluator_fingerprint:
        raise LabError("Judge output configuration evaluator fingerprint mismatch; do not rebind old outputs to a changed evaluator")
    report = calibrate(packet, rubric, labels, judge_config, outputs, policy)
    return seal({"schema_version": 1, "kind": "evidence_bundle", "packet": packet, "review": review,
                 "rubric": rubric, "labels": labels, "judge_config": judge_config,
                 "outputs": outputs, "policy": policy, "evaluator_fingerprint": evaluator_fingerprint,
                 "report_sha256": report["sha256"]})


def validate_evidence_bundle(bundle: dict, *, evaluator_fingerprint: str) -> dict:
    """Return recomputed report; reject stale/tampered artifacts before trusting it."""
    _sealed(bundle, "evidence_bundle", {"packet", "review", "rubric", "labels", "judge_config", "outputs", "policy",
                                        "evaluator_fingerprint", "report_sha256"})
    if bundle["evaluator_fingerprint"] != evaluator_fingerprint:
        raise LabError("Calibration evaluator fingerprint mismatch; changed evaluator needs fresh calibration")
    validate_judge_config(bundle["judge_config"])
    if bundle["judge_config"].get("evaluator_fingerprint") != evaluator_fingerprint:
        raise LabError("Judge output configuration evaluator fingerprint mismatch; changed evaluator needs fresh outputs")
    validate_review(bundle["packet"], bundle["review"])
    validate_rubric(bundle["packet"], bundle["rubric"], bundle["review"])
    _validate_anchor_labels(bundle["packet"], bundle["review"], bundle["rubric"], bundle["labels"])
    report = calibrate(bundle["packet"], bundle["rubric"], bundle["labels"], bundle["judge_config"], bundle["outputs"], bundle["policy"])
    if bundle["report_sha256"] != report["sha256"]:
        raise LabError("Calibration report hash mismatch; acceptance evidence must be recomputed")
    return report


def drift(packet: dict, rubric: dict, labels: dict, old_config: dict, old_outputs: dict,
          new_config: dict, new_outputs: dict, policy: dict) -> dict:
    """Compare two judge versions against the exact same frozen human anchors."""
    old = calibrate(packet, rubric, labels, old_config, old_outputs, policy)
    new = calibrate(packet, rubric, labels, new_config, new_outputs, policy)
    old_rows = {(r["trace_id"], r["criterion_id"]): r for r in old_outputs["rows"]}
    new_rows = {(r["trace_id"], r["criterion_id"]): r for r in new_outputs["rows"]}
    human = {(r["trace_id"], r["criterion_id"]): r for r in labels["labels"]}
    changes = []
    for trace in packet["traces"]:
        for c in rubric["criteria"]:
            key = (trace["id"], c["id"])
            before, after = old_rows.get(key, {}), new_rows.get(key, {})
            if (before.get("status", "missing"), before.get("reason")) != (after.get("status", "missing"), after.get("reason")):
                label = human.get(key, {})
                changes.append({"trace_id": key[0], "trace_sha256": trace["sha256"], "criterion_id": key[1],
                                "partition": trace["partition"], "human_verdict": label.get("verdict", "missing"),
                                "human_rationale": label.get("rationale"), "old_status": before.get("status", "missing"),
                                "new_status": after.get("status", "missing"), "old_reason": before.get("reason"),
                                "new_reason": after.get("reason")})
    deltas = {}
    for cid in old["criteria"]:
        deltas[cid] = {}
        for metric in ("failure_recall", "failure_precision", "good_output_specificity"):
            a, b = old["criteria"][cid]["validation"][metric], new["criteria"][cid]["validation"][metric]
            deltas[cid][metric] = None if a is None or b is None else b - a
    return seal({"schema_version": 1, "kind": "judge_drift", "anchors_sha256": labels["sha256"],
            "old": old, "new": new, "validation_rate_deltas": deltas, "changed_rows": changes,
            "warning": "Reusing these anchors for judge tuning makes subsequent validation adaptive; collect new held-out groups for confirmation."})
