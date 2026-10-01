"""Trace-first, content-bound human review artifacts (standard library only).

These digests detect accidental/stale edits in a cooperative local workflow. They
are not signatures, identity verification, or proof that an annotation is human.
Never give calibration-validation contents to the optimizer or rubric author.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .util import LabError, canonical, digest, integer, safe_name, unknown_keys

PROVENANCE_LIMITATION = (
    "Cooperative-local attestations and hashes are not cryptographic proof of human "
    "review, real-world provenance, chronology, or unobserved holdouts."
)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise LabError(f"{name} must be a nonempty string")
    return value


def _object(value: Any, keys: set[str], name: str, required: set[str] | None = None) -> dict:
    if not isinstance(value, dict):
        raise LabError(f"{name} must be an object")
    unknown_keys(value, keys, name)
    missing = (required if required is not None else keys) - set(value)
    if missing:
        raise LabError(f"Missing {name} keys: {', '.join(sorted(missing))}")
    return value


def _rows(value: Any, name: str, *, nonempty: bool = True) -> list:
    if not isinstance(value, list) or (nonempty and not value):
        raise LabError(f"{name} must be a {'nonempty ' if nonempty else ''}list")
    return value


def _strings(value: Any, name: str, *, nonempty: bool = True) -> list[str]:
    values = _rows(value, name, nonempty=nonempty)
    for v in values:
        _text(v, name)
    if len(set(values)) != len(values):
        raise LabError(f"Duplicate {name}")
    return values


def seal(value: dict) -> dict:
    """Return an independent canonical-content snapshot, never mutate the input."""
    result = deepcopy(value)
    result.pop("sha256", None)
    result["sha256"] = digest(result)
    return result


def _sealed(value: Any, kind: str, fields: set[str]) -> dict:
    _object(value, fields | {"schema_version", "kind", "sha256"}, kind)
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["kind"] != kind:
        raise LabError(f"Unsupported {kind} schema")
    if value["sha256"] != digest({k: v for k, v in value.items() if k != "sha256"}):
        raise LabError(f"{kind} content hash mismatch")
    return value


def write_artifact(path: Path, artifact: dict) -> None:
    """Atomically create once; never overwrite an existing artifact version."""
    import os
    import tempfile
    path = Path(path)
    # Serialize before touching the destination; invalid input creates no file.
    content = canonical(artifact) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        try:
            # Hard-link publication is atomic and refuses even a concurrent writer.
            os.link(temporary, path)
        except FileExistsError as exc:
            raise LabError(f"Artifact already exists; create a new version: {path}") from exc
    finally:
        os.unlink(temporary)


def validate_packet(packet: dict) -> dict:
    _sealed(packet, "review_packet", {"reviewer", "source", "traces"})
    _text(packet["reviewer"], "packet reviewer")
    source = _object(packet["source"], {"kind", "reference"}, "trace source")
    if source["kind"] not in ("recorded", "synthetic"):
        raise LabError("source.kind must be recorded or synthetic")
    _text(source["reference"], "source.reference")
    seen, groups, inputs, case_groups = set(), {}, {}, {}
    for row in _rows(packet["traces"], "traces"):
        fields = {"id", "group", "partition", "input", "output", "trace", "sha256"}
        _object(row, fields | {"experiment_split", "case_id", "rep"}, "trace", fields)
        safe_name(row["id"])
        _text(row["group"], "trace.group")
        if row["id"] in seen:
            raise LabError(f"Duplicate trace id: {row['id']}")
        seen.add(row["id"])
        if row["partition"] not in ("tuning", "validation"):
            raise LabError("Calibration partition must be tuning or validation")
        if "experiment_split" in row and row["experiment_split"] != "train":
            raise LabError("Review import forbids experiment validation/test; only train traces may be imported")
        _rows(row["trace"], "trace events")
        if row["sha256"] != digest({k: v for k, v in row.items() if k != "sha256"}):
            raise LabError(f"Trace content hash mismatch: {row['id']}")
        if groups.setdefault(row["group"], row["partition"]) != row["partition"]:
            raise LabError("Related groups cannot cross calibration tuning/validation partitions")
        input_hash = digest(row["input"])
        if inputs.setdefault(input_hash, row["group"]) != row["group"]:
            raise LabError("Identical inputs must share a group; repetitions are not independent cases")
        if "rep" in row:
            integer(row["rep"], "trace.rep", minimum=0)
            _text(row.get("case_id"), "trace.case_id required with rep")
        if "case_id" in row:
            _text(row["case_id"], "trace.case_id")
            if case_groups.setdefault(row["case_id"], row["group"]) != row["group"]:
                raise LabError("Repetitions of a case must share a group")
    return packet


def create_packet(traces: list[dict], *, reviewer: str, source: dict) -> dict:
    """Freeze actual input/output/event traces before defining any rubric.

    `source={kind:'recorded'|'synthetic', reference:'...'}; recorded means the
    operator attests these are captured runs, not automatically verified traffic.
    Calibration partitions are unrelated to the engine's experiment splits.
    """
    rows = []
    for row in _rows(traces, "traces"):
        if not isinstance(row, dict) or "sha256" in row:
            raise LabError("Provide raw trace objects without sha256")
        rows.append(seal(row))
    result = seal({"schema_version": 1, "kind": "review_packet", "reviewer": reviewer,
                   "source": source, "traces": rows})
    return validate_packet(result)


def _trace_map(packet: dict) -> dict:
    validate_packet(packet)
    return {t["id"]: t for t in packet["traces"]}


def _bound_row(row: dict, traces: dict, fields: set[str], name: str) -> dict:
    _object(row, fields | {"trace_id", "trace_sha256"}, name)
    _text(row["trace_id"], f"{name} trace_id")
    _text(row["trace_sha256"], f"{name} trace_sha256")
    trace = traces.get(row["trace_id"])
    if trace is None:
        raise LabError(f"Unknown {name} trace: {row['trace_id']}")
    if row["trace_sha256"] != trace["sha256"]:
        raise LabError(f"{name} trace content hash mismatch: {row['trace_id']}")
    return trace


def validate_review(packet: dict, review: dict) -> dict:
    traces = _trace_map(packet)
    _sealed(review, "human_review", {"packet_sha256", "reviewer", "provenance", "annotations", "suggestions"})
    if review["packet_sha256"] != packet["sha256"]:
        raise LabError("Review packet hash mismatch")
    _text(review["reviewer"], "reviewer")
    if review["provenance"] != "human":
        raise LabError("Review requires explicit human provenance; model suggestions are not human labels")
    seen = set()
    for row in _rows(review["annotations"], "annotations"):
        trace = _bound_row(row, traces, {"verdict", "rationale", "failure_modes"}, "annotation")
        if trace["partition"] != "tuning":
            raise LabError("Open-ended review must not inspect calibration validation traces")
        if row["trace_id"] in seen:
            raise LabError("Duplicate human annotation")
        seen.add(row["trace_id"])
        if row["verdict"] not in ("pass", "fail", "uncertain"):
            raise LabError("Human verdict must be pass, fail, or uncertain")
        _text(row["rationale"], "annotation rationale")
        _strings(row["failure_modes"], "failure_modes", nonempty=row["verdict"] == "fail")
        if row["verdict"] == "pass" and row["failure_modes"]:
            raise LabError("Passing review cannot list observed failure modes")
    if seen != {t["id"] for t in traces.values() if t["partition"] == "tuning"}:
        raise LabError("Complete all tuning trace annotations, including uncertain judgments")
    for suggestion in _rows(review["suggestions"], "suggestions", nonempty=False):
        _text(suggestion, "model suggestion")
    return review


def annotate_packet(packet: dict, annotations: list[dict], *, reviewer: str,
                    provenance: str = "human", suggestions: list[str] | None = None) -> dict:
    """Import explicit human annotations. Optional suggestions never affect labels."""
    validate_packet(packet)
    result = seal({"schema_version": 1, "kind": "human_review", "packet_sha256": packet["sha256"],
                   "reviewer": reviewer, "provenance": provenance, "annotations": annotations,
                   "suggestions": suggestions or []})
    return validate_review(packet, result)


def validate_rubric(packet: dict, rubric: dict, review: dict | None = None) -> dict:
    traces = _trace_map(packet)
    _sealed(rubric, "reviewed_rubric", {"packet_sha256", "review_sha256", "reviewer", "criteria"})
    if rubric["packet_sha256"] != packet["sha256"]:
        raise LabError("Rubric packet hash mismatch")
    _text(rubric["reviewer"], "rubric reviewer")
    _text(rubric["review_sha256"], "review_sha256")
    reviewed = None
    if review is not None:
        validate_review(packet, review)
        if rubric["review_sha256"] != review["sha256"]:
            raise LabError("Rubric human-review hash mismatch")
        reviewed = {row["trace_id"]: row for row in review["annotations"]}
    ids, metrics = set(), set()
    for c in _rows(rubric["criteria"], "criteria"):
        _object(c, {"id", "kind", "metric", "description", "failure_mode", "pass_when", "fail_when", "anchors"}, "criterion")
        safe_name(c["id"])
        safe_name(c["metric"])
        if c["id"] in ids or c["metric"] in metrics:
            raise LabError("Criterion ids and metrics must each be unique; composite metrics cannot mask criteria")
        ids.add(c["id"])
        metrics.add(c["metric"])
        if c["kind"] not in ("judge", "code"):
            raise LabError("Criterion kind must be judge or code")
        for key in ("description", "failure_mode", "pass_when", "fail_when"):
            _text(c[key], f"criterion {key}")
        anchors = _strings(c["anchors"], "criterion anchors")
        for tid in anchors:
            if tid not in traces or traces[tid]["partition"] != "tuning":
                raise LabError("Rubric anchors must reference existing tuning traces, never validation")
        if reviewed is not None:
            failures = [reviewed[tid] for tid in anchors if reviewed[tid]["verdict"] == "fail"
                        and c["failure_mode"] in reviewed[tid]["failure_modes"]]
            passes = [reviewed[tid] for tid in anchors if reviewed[tid]["verdict"] == "pass"]
            if not failures or not passes:
                raise LabError("Each atomic criterion needs observed human failure-mode and passing tuning anchors")
    return rubric


def finalize_rubric(packet: dict, review: dict, criteria: list[dict], *, reviewer: str) -> dict:
    """Freeze one binary decision per observed failure mode, with inspectable anchors."""
    validate_review(packet, review)
    result = seal({"schema_version": 1, "kind": "reviewed_rubric", "packet_sha256": packet["sha256"],
                   "review_sha256": review["sha256"], "reviewer": reviewer, "criteria": criteria})
    return validate_rubric(packet, result, review)


def validate_labels(packet: dict, rubric: dict, labels: dict) -> dict:
    traces = _trace_map(packet)
    validate_rubric(packet, rubric)
    _sealed(labels, "criterion_labels", {"packet_sha256", "rubric_sha256", "reviewer", "provenance", "labels"})
    if labels["packet_sha256"] != packet["sha256"] or labels["rubric_sha256"] != rubric["sha256"]:
        raise LabError("Criterion labels packet/rubric hash mismatch")
    _text(labels["reviewer"], "label reviewer")
    if labels["provenance"] != "human":
        raise LabError("Criterion labels require explicit human provenance")
    criteria = {c["id"] for c in rubric["criteria"]}
    seen = set()
    for row in _rows(labels["labels"], "criterion labels"):
        _bound_row(row, traces, {"criterion_id", "verdict", "rationale"}, "criterion label")
        _text(row["criterion_id"], "criterion_id")
        if row["criterion_id"] not in criteria:
            raise LabError("Unknown criterion in human labels")
        key = (row["trace_id"], row["criterion_id"])
        if key in seen:
            raise LabError("Duplicate (trace, criterion) human label")
        seen.add(key)
        if row["verdict"] not in ("pass", "fail", "uncertain"):
            raise LabError("Human criterion verdict must be pass, fail, or uncertain")
        _text(row["rationale"], "criterion label rationale")
    return labels


def label_criteria(packet: dict, rubric: dict, labels: list[dict], *, reviewer: str,
                   provenance: str = "human") -> dict:
    """Import human criterion judgments after rubric freeze; missing stays missing."""
    validate_rubric(packet, rubric)
    result = seal({"schema_version": 1, "kind": "criterion_labels", "packet_sha256": packet["sha256"],
                   "rubric_sha256": rubric["sha256"], "reviewer": reviewer,
                   "provenance": provenance, "labels": labels})
    return validate_labels(packet, rubric, result)


def tuning_view(packet: dict) -> dict:
    """Explicit safe model-facing view; exclude calibration validation contents."""
    validate_packet(packet)
    return {"packet_sha256": packet["sha256"], "source": deepcopy(packet["source"]),
            "traces": deepcopy([t for t in packet["traces"] if t["partition"] == "tuning"])}
