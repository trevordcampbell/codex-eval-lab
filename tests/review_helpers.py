"""Synthetic, offline fixtures: these are not verified human or production data."""
from codex_eval_lab.review import create_packet, annotate_packet, finalize_rubric, label_criteria
from codex_eval_lab.calibration import create_judge_outputs, create_evidence_bundle


def review_fixture(*, criteria_count=2, validation_groups=2):
    traces = []
    for partition, count in (("tuning", 1), ("validation", validation_groups)):
        for verdict in ("pass", "fail"):
            for n in range(count):
                tid = f"{partition}-{verdict}-{n}"
                traces.append({"id": tid, "group": tid, "partition": partition,
                               "input": {"question": tid}, "output": f"{verdict} fixture answer",
                               "trace": [{"role": "assistant", "content": f"{verdict} fixture answer"}],
                               "experiment_split": "train"})
    packet = create_packet(traces, reviewer="Fixture author", source={"kind": "synthetic", "reference": "tests/review_helpers.py"})
    annotations = []
    for t in packet["traces"]:
        if t["partition"] == "tuning":
            failed = "-fail-" in t["id"]
            annotations.append({"trace_id": t["id"], "trace_sha256": t["sha256"],
                                "verdict": "fail" if failed else "pass", "rationale": "Synthetic test anchor",
                                "failure_modes": ["unsupported claim", "invalid format"] if failed else []})
    review = annotate_packet(packet, annotations, reviewer="Fixture reviewer", suggestions=["A model suggestion, not a label"])
    criteria = []
    for cid, kind, mode in (("grounded", "judge", "unsupported claim"), ("format", "code", "invalid format"))[:criteria_count]:
        criteria.append({"id": cid, "kind": kind, "metric": cid, "description": f"Check {mode}",
                         "failure_mode": mode, "pass_when": "The independent criterion is satisfied",
                         "fail_when": "The independent criterion is violated",
                         "anchors": ["tuning-pass-0", "tuning-fail-0"]})
    rubric = finalize_rubric(packet, review, criteria, reviewer="Fixture reviewer")
    label_rows, output_rows = [], []
    config = {"schema_version": 1, "model": "fixture-judge-v1", "model_family": "fixture-judge",
              "application_model": "fixture-app-v1", "application_model_family": "fixture-app",
              "evaluator_fingerprint": "a" * 64, "prompt": "Judge each criterion separately", "parameters": {"temperature": 0}}
    for t in packet["traces"]:
        for c in rubric["criteria"]:
            verdict = "fail" if "-fail-" in t["id"] else "pass"
            base = {"trace_id": t["id"], "trace_sha256": t["sha256"], "criterion_id": c["id"]}
            label_rows.append({**base, "verdict": verdict, "rationale": "Synthetic criterion anchor"})
            output_rows.append({**base, "status": verdict, "reason": "Synthetic judge reason", "model": config["model"]})
    labels = label_criteria(packet, rubric, label_rows, reviewer="Fixture reviewer")
    outputs = create_judge_outputs(packet, rubric, config, output_rows)
    policy = {"schema_version": 1, "positive_class": "failure", "min_failure_groups": 2, "min_pass_groups": 2,
              "confidence": .95, "threshold_basis": "point_estimate", "min_failure_recall": 0.9, "min_failure_precision": 0.9, "min_good_specificity": 0.9}
    return dict(packet=packet, review=review, rubric=rubric, labels=labels, judge_config=config, outputs=outputs, policy=policy)


def calibration_args(fixture):
    return {k: v for k, v in fixture.items() if k != "review"}


def evidence_fixture(**kwargs):
    return create_evidence_bundle(**review_fixture(**kwargs), evaluator_fingerprint="a" * 64)
