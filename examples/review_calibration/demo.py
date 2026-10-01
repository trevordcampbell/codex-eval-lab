#!/usr/bin/env python3
"""Run a free, synthetic workflow demonstration, never a model benchmark.

The adapter is actually executed as a Python function; all annotation identities
and labels below are scripted fixture data, not real human-reviewed evidence.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from codex_eval_lab.calibration import (calibrate, create_evidence_bundle,
                                      create_judge_outputs, drift)
from codex_eval_lab.review import (annotate_packet, create_packet, finalize_rubric,
                                  label_criteria, write_artifact)
from codex_eval_lab.util import canonical, digest, file_hash


def app(request):
    """Actual deterministic application execution on synthetic input."""
    if request["fixture_bug"]:
        return f"Stock is {request['stock'] + 999}; invented an unsupported number"
    return {"answer": f"Stock is {request['stock']}"}


def run(out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    traces = []
    for partition, count in (("tuning", 1), ("validation", 8)):
        for bad in (False, True):
            for n in range(count):
                tid = f"{partition}-{'bad' if bad else 'good'}-{n}"
                request = {"case": tid, "stock": n, "fixture_bug": bad}
                output = app(request)
                traces.append({"id": tid, "group": tid, "partition": partition,
                               "input": request, "output": output,
                               "trace": [{"role": "user", "content": canonical(request)},
                                         {"role": "assistant", "content": canonical(output)}]})
    packet = create_packet(traces, reviewer="Scripted fixture author; no real human review",
                           source={"kind": "synthetic", "reference": "Actual deterministic app calls on synthetic template inputs in examples/review_calibration/demo.py. Group independence and human provenance are NOT established by this fixture."})
    review_rows = [{"trace_id": t["id"], "trace_sha256": t["sha256"],
                    "verdict": "fail" if t["input"]["fixture_bug"] else "pass",
                    "rationale": "SCRIPTED FIXTURE: inspect the unsupported number and output shape",
                    "failure_modes": ["unsupported stock number", "unstructured answer"] if t["input"]["fixture_bug"] else []}
                   for t in packet["traces"] if t["partition"] == "tuning"]
    human = annotate_packet(packet, review_rows, reviewer="SCRIPTED FIXTURE; not an actual human")
    criteria = [
        {"id": "grounded", "kind": "judge", "metric": "grounded",
         "description": "The answer's stock number matches the supplied stock count",
         "failure_mode": "unsupported stock number", "pass_when": "Stock number matches the supplied input",
         "fail_when": "Answer asserts an unsupported stock number", "anchors": ["tuning-good-0", "tuning-bad-0"]},
        {"id": "format", "kind": "code", "metric": "format",
         "description": "Output is an object with one string answer field",
         "failure_mode": "unstructured answer", "pass_when": "Output is an object with a string answer",
         "fail_when": "Output is not the required object", "anchors": ["tuning-good-0", "tuning-bad-0"]},
    ]
    rubric = finalize_rubric(packet, human, criteria, reviewer="SCRIPTED FIXTURE; not an actual human")
    labels = label_criteria(packet, rubric, [
        {"trace_id": t["id"], "trace_sha256": t["sha256"], "criterion_id": c["id"],
         "verdict": "fail" if t["input"]["fixture_bug"] else "pass",
         "rationale": "SCRIPTED FIXTURE annotation for this exact captured output"}
        for t in packet["traces"] for c in criteria], reviewer="SCRIPTED FIXTURE; not an actual human")
    fingerprint = digest({"demo_source_sha256": file_hash(Path(__file__)), "purpose": "offline fixture only"})
    config = {"schema_version": 1, "model": "scripted-judge-v1", "model_family": "scripted-judge",
              "application_model": "scripted-app-v1", "application_model_family": "scripted-app",
              "prompt": "Offline scripted criterion checker; no provider is called", "parameters": {},
              "evaluator_fingerprint": fingerprint}
    rows = [{"trace_id": row["trace_id"], "trace_sha256": row["trace_sha256"], "criterion_id": row["criterion_id"],
             "status": row["verdict"], "reason": "SCRIPTED FIXTURE correct criterion result", "model": config["model"]}
            for row in labels["labels"]]
    outputs = create_judge_outputs(packet, rubric, config, rows)
    policy = {"schema_version": 1, "positive_class": "failure", "min_failure_groups": 8, "min_pass_groups": 8,
              "min_failure_recall": .3, "min_failure_precision": .3, "min_good_specificity": .3,
              "confidence": .95, "threshold_basis": "lower_bound"}
    report = calibrate(packet, rubric, labels, config, outputs, policy)
    bundle = create_evidence_bundle(packet, human, rubric, labels, config, outputs, policy,
                                    evaluator_fingerprint=fingerprint)
    broken_config = deepcopy(config)
    broken_config["prompt"] = "A deliberately broken judge that passes everything for grounding"
    bad_rows = deepcopy(rows)
    for row in bad_rows:
        if row["criterion_id"] == "grounded":
            row["status"] = "pass"
            row["reason"] = "Incorrectly trusts confident text; code check cannot mask this missed failure"
    broken_outputs = create_judge_outputs(packet, rubric, broken_config, bad_rows)
    broken_report = calibrate(packet, rubric, labels, broken_config, broken_outputs, policy)
    comparison = drift(packet, rubric, labels, config, outputs, broken_config, broken_outputs, policy)
    artifacts = {"packet": packet, "human-review": human, "rubric": rubric, "labels": labels,
                 "judge-config": config, "judge-outputs": outputs, "policy": policy,
                 "calibration": report, "evidence": bundle, "broken-judge-config": broken_config,
                 "broken-judge-outputs": broken_outputs, "broken-calibration": broken_report, "drift": comparison}
    for name, artifact in artifacts.items():
        write_artifact(out / f"{name}.json", artifact)
    result = {"synthetic_fixture_only": True, "cost_usd": 0, "recorded_traces": len(traces),
              "scripted_human_labels_not_real_review": True, "good_judge_ready_under_demo_policy": report["ready"],
              "broken_judge_ready": broken_report["ready"], "broken_judge_issues": broken_report["issues"],
              "evaluator_fingerprint": fingerprint}
    write_artifact(out / "result.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="New output directory")
    args = parser.parse_args()
    print(json.dumps(run(args.out), indent=2))
