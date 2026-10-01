"""Offline review/calibration CLI; imports record explicit human attestations.

The CLI cannot authenticate a human against code running as the same OS user.
It never runs a model, spends tokens, or launches an optimizer.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .util import LabError, read_json, strict_json

COMMANDS = {"review", "calibrate", "calibration-drift", "judge-results", "calibration-review", "evidence"}


def _output(p):
    p.add_argument("--out", type=Path, required=True, help="New output file; never overwrite an existing artifact")


def _human(p):
    p.add_argument("--reviewer", required=True, help="Actual human reviewer; a recorded assertion, not authentication")
    p.add_argument("--confirm-human-review", action="store_true", help="Record actual human review; never let an agent manufacture consent")


def _calibration_inputs(p, *, include_review=False):
    for name in ("packet", "rubric", "labels", "judge-config", "outputs", "policy"):
        p.add_argument("--" + name, type=Path, required=True)
    if include_review:
        p.add_argument("--review", type=Path, required=True)


def add_parsers(sub) -> None:
    p = sub.add_parser("review", help="Inspect development traces, import human judgments, and freeze criteria before optimization")
    actions = p.add_subparsers(dest="review_action", required=True)
    c = actions.add_parser("create", help="Create a sealed packet; does not create labels or approve it")
    c.add_argument("--traces", type=Path, required=True)
    c.add_argument("--reviewer", required=True)
    c.add_argument("--source", required=True, help="Provenance/sampling reference, not trace contents")
    c.add_argument("--source-kind", choices=("recorded", "synthetic"), default="recorded")
    _output(c)
    for name in ("annotate", "rubric", "label"):
        c = actions.add_parser(name)
        c.add_argument("--packet", type=Path, required=True)
        _human(c)
        _output(c)
        if name == "annotate":
            c.add_argument("--annotations", type=Path, required=True)
        elif name == "rubric":
            c.add_argument("--review", type=Path, required=True)
            c.add_argument("--criteria", type=Path, required=True)
        else:
            c.add_argument("--rubric", type=Path, required=True)
            c.add_argument("--labels", type=Path, required=True)
    c = actions.add_parser("render", help="Write an offline human review UI; annotations export separately")
    c.add_argument("--packet", type=Path, required=True)
    c.add_argument("--rubric", type=Path)
    _output(c)
    c = sub.add_parser("calibrate", help="Measure independent judge criteria against frozen human labels; no model calls")
    _calibration_inputs(c)
    _output(c)
    c = sub.add_parser("calibration-review", help="Render actual human/judge disagreements beside traces; offline human-only artifact")
    _calibration_inputs(c)
    _output(c)
    c = sub.add_parser("judge-results", help="Bind imported actual per-criterion predictions to their trace/rubric/config versions")
    for name in ("packet", "rubric", "judge-config", "rows"):
        c.add_argument("--" + name, type=Path, required=True)
    _output(c)
    c = sub.add_parser("calibration-drift", help="Recompute old/new judges on the same human anchors; no reapproval")
    for name in ("packet", "rubric", "labels", "old-config", "old-outputs", "new-config", "new-outputs", "policy"):
        c.add_argument("--" + name, type=Path, required=True)
    _output(c)
    p = sub.add_parser("evidence", help="Build or recompute a suite-bound measurement-readiness gate")
    actions = p.add_subparsers(dest="evidence_action", required=True)
    c = actions.add_parser("build")
    _calibration_inputs(c, include_review=True)
    c.add_argument("--suite", type=Path, required=True)
    _output(c)
    for name in ("check", "fingerprint"):
        c = actions.add_parser(name)
        c.add_argument("--suite", type=Path, required=True)


def read_rows(path: Path) -> list:
    if path.stat().st_size > 32 * 1024 * 1024:
        raise LabError("Review input exceeds 32 MiB; create smaller, explicit review batches")
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        data = strict_json(text)
    else:
        data = [strict_json(line) for line in text.splitlines() if line.strip()]
    if not isinstance(data, list):
        raise LabError("Expected a JSON array or JSONL records")
    return data


def _draft(path: Path, field: str, packet: dict, reviewer: str, rubric: dict | None = None) -> list:
    value = read_json(path)
    if isinstance(value, list):
        return value
    expected = {"schema_version", "kind", "packet_sha256", "reviewer", field}
    if rubric is not None:
        expected.add("rubric_sha256")
    if not isinstance(value, dict) or set(value) != expected:
        raise LabError("Invalid review draft fields; export the matching review form or use a raw array")
    kind = "annotation_draft" if field == "annotations" else "criterion_labels_draft"
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["kind"] != kind:
        raise LabError("Unsupported review draft format")
    if value["packet_sha256"] != packet["sha256"] or value["reviewer"] != reviewer:
        raise LabError("Review draft does not match this packet and reviewer")
    if rubric is not None and value["rubric_sha256"] != rubric["sha256"]:
        raise LabError("Review draft rubric changed; start a fresh labeling pass")
    if not isinstance(value[field], list):
        raise LabError("Review draft records must be a list")
    return value[field]


def _save(path: Path, obj: dict) -> dict:
    from .review import write_artifact
    write_artifact(path, obj)
    result = {"artifact": str(path), "kind": obj.get("kind"), "sha256": obj.get("sha256")}
    # Do not echo trace contents or human/private labels into a command log.
    if "ready" in obj or "passed" in obj:
        result["ready"] = obj.get("ready", obj.get("passed"))
        if result["ready"] is not True:
            result["error"] = "Calibration is not ready; inspect the saved report and its evidence"

    return result


def dispatch(a: argparse.Namespace) -> dict[str, Any]:
    from . import review
    if a.command == "review":
        if a.review_action == "create":
            packet = review.create_packet(read_rows(a.traces), reviewer=a.reviewer,
                                          source={"kind": a.source_kind, "reference": a.source})
            return _save(a.out, packet)
        packet = review.validate_packet(read_json(a.packet))
        if a.review_action == "render":
            from .review_ui import write_standalone_review
            rubric = read_json(a.rubric) if a.rubric else None
            out = write_standalone_review(packet, a.out, rubric=rubric)
            return {"review_ui": str(out), "network": "none", "approval": "not granted"}
        if not a.confirm_human_review:
            raise LabError("Actual human review is required; import only after --confirm-human-review records it")
        if a.review_action == "annotate":
            rows = _draft(a.annotations, "annotations", packet, a.reviewer)
            obj = review.annotate_packet(packet, rows, reviewer=a.reviewer, provenance="human")
        elif a.review_action == "rubric":
            obj = review.finalize_rubric(packet, read_json(a.review), read_rows(a.criteria), reviewer=a.reviewer)
        else:
            rubric = read_json(a.rubric)
            rows = _draft(a.labels, "labels", packet, a.reviewer, rubric=rubric)
            obj = review.label_criteria(packet, rubric, rows, reviewer=a.reviewer)
        return _save(a.out, obj)
    from . import calibration
    if a.command == "calibration-review":
        from .review_ui import render_calibration_review
        data = {k: read_json(getattr(a, k)) for k in ("packet", "rubric", "labels", "judge_config", "outputs", "policy")}
        html = render_calibration_review(**data)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        try:
            with a.out.open("x", encoding="utf-8") as stream:
                stream.write(html)
        except FileExistsError as exc:
            raise LabError("Review output exists; choose a new artifact path") from exc
        return {"calibration_review": str(a.out), "scope": "human-only; do not share with optimizer"}
    if a.command == "judge-results":
        return _save(a.out, calibration.create_judge_outputs(read_json(a.packet), read_json(a.rubric),
                                                            read_json(a.judge_config), read_rows(a.rows)))
    if a.command == "calibration-drift":
        data = {k: read_json(getattr(a, k)) for k in
                ("packet", "rubric", "labels", "old_config", "old_outputs", "new_config", "new_outputs", "policy")}
        return _save(a.out, calibration.drift(**data))
    if a.command == "evidence" and a.evidence_action == "fingerprint":
        from .evidence import evaluator_fingerprint
        return {"evaluator_fingerprint": evaluator_fingerprint(a.suite.resolve()),
                "instruction": "Record this in judge_config before collecting/sealing actual judge outputs"}
    if a.command == "evidence" and a.evidence_action == "check":
        from .evidence import validate_evidence
        result = validate_evidence(a.suite.resolve(), require_ready=True)
        return {"evidence": result, "scope": "recorded cooperative-local evidence; not authentication"}
    data = {k: read_json(getattr(a, k)) for k in ("packet", "rubric", "labels", "judge_config", "outputs", "policy")}
    if a.command == "calibrate":
        return _save(a.out, calibration.calibrate(**data))
    from .evidence import evaluator_fingerprint
    data["review"] = read_json(a.review)
    data["evaluator_fingerprint"] = evaluator_fingerprint(a.suite.resolve())
    return _save(a.out, calibration.create_evidence_bundle(**data))
