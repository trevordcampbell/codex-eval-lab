"""Write-once proposal inputs and response evidence for cooperative controllers.

The caller reserves an attempt in its ledger, prepares development-only feedback,
persists this bundle, and pins its returned digest *before* dispatch. Both CLI and
externally orchestrated authors can use the same files. This module neither calls
models nor grants execution authority, authenticates an author, or hides files
from another process running as the same OS user. A writer who controls all files
and the ledger can fabricate evidence; these hashes detect stale or changed data.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Any

from .util import LabError, canonical, digest, safe_name, strict_json, utc_now


_ARTIFACTS = {
    "feedback": "development-feedback.json",
    "prompt": "prompt.txt",
    "response_contract": "response-contract.json",
    "invocation_context": "invocation-context.json",
}
_FEEDBACK_KEYS = {
    "schema_version", "variant", "objective", "guardrails", "editable",
    "warning", "development_results",
}
_ROW_KEYS = {
    "case_id", "rep", "input", "expected", "output", "metrics", "explanation",
    "trace", "criterion_results",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _json_bytes(value: Any) -> bytes:
    try:
        return canonical(value).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise LabError("Proposal evidence must contain finite UTF-8 JSON values") from exc


def _path(path: Path) -> Path:
    """Reject symlinks before resolving, including dangling ancestor links."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise LabError("Proposal evidence paths must not contain symlinks")
    return path.resolve()


def _read(path: Path) -> bytes:
    path = _path(path)
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise LabError("Proposal evidence must be an ordinary file")
        return path.read_bytes()
    except OSError as exc:
        raise LabError("Proposal evidence is missing or unreadable") from exc


def _read_json(data: bytes) -> Any:
    try:
        return strict_json(data.decode("utf-8"))
    except (LabError, UnicodeError):
        # Never put arbitrary artifact content or private JSON keys in public errors.
        raise LabError("Proposal evidence contains invalid UTF-8 JSON") from None


def _sync_directory(path: Path) -> None:
    # File fsync is portable; POSIX also supports syncing the directory entry.
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _write_new(path: Path, data: bytes) -> None:
    """Exclusive creation. Partial writes remain evidence and may not be replaced."""
    path = _path(path)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        _sync_directory(path.parent)
    except FileExistsError as exc:
        raise LabError("Proposal evidence already exists; never overwrite or retry this attempt") from exc
    except OSError as exc:
        raise LabError("Could not persist proposal evidence; preserve this incomplete attempt") from exc


def _source_files(source: Path) -> dict[str, str]:
    source = _path(source)
    if not source.is_dir():
        raise LabError("Proposal source must be an existing directory")
    result = {}
    try:
        for entry in sorted(source.rglob("*")):
            if entry.is_symlink():
                raise LabError("Proposal source must not contain symlinks")
            if entry.is_dir():
                continue
            result[entry.relative_to(source).as_posix()] = _sha(_read(entry))
    except OSError as exc:
        raise LabError("Proposal source could not be hashed") from exc
    if not result:
        raise LabError("Proposal source contains no files")
    return result


def _feedback(value: Any, source_label: str) -> None:
    """Accept the engine.feedback envelope, never an experiment state/manifest.

    The controller must construct this value through its development-only API.
    Its shape cannot prove that arbitrary caller-supplied rows are development
    data, so this is not a sanitizer or an independent privacy boundary.
    """
    if not isinstance(value, dict) or not _FEEDBACK_KEYS.issubset(value) or set(value) - _FEEDBACK_KEYS - {"development_summary", "feedback_excerpt"}:
        raise LabError("Provide prepared development feedback, not experiment state or private results")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise LabError("Unsupported development feedback schema")
    if value["variant"] != source_label:
        raise LabError("Development feedback does not match the proposal source identity")
    if not isinstance(value["objective"], dict) or not isinstance(value["guardrails"], list):
        raise LabError("Invalid prepared development feedback")
    if (not isinstance(value["editable"], list)
            or not all(isinstance(item, str) for item in value["editable"])
            or not isinstance(value["warning"], str)
            or not isinstance(value["development_results"], list)):
        raise LabError("Invalid prepared development feedback")
    if any(not isinstance(row, dict) or set(row) - _ROW_KEYS
           for row in value["development_results"]):
        raise LabError("Development feedback contains unsupported result fields")


def _metadata(receipt: dict[str, Any], dispatch_digest: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "dispatch_digest": dispatch_digest,
        "source_label": receipt["source_label"],
        "source_hash": receipt["source_hash"],
        "source_file_count": len(receipt["source_files"]),
        **{f"{name}_sha256": receipt["artifacts"][name]["sha256"] for name in _ARTIFACTS},
    }


def prepare_dispatch(destination: Path, *, source: Path, source_label: str,
                     source_hash: str, feedback: dict[str, Any], prompt: str,
                     response_contract: dict[str, Any], invocation_context: dict[str, Any]) -> dict[str, Any]:
    """Persist exact dispatch inputs at a fresh path and return public metadata.

    ``source_hash`` is the variant's ledger hash (digest of its per-file hashes).
    ``feedback`` must already be prepared by engine.feedback. The context records
    the allowed invocation settings, such as backend/model/tool scope; pass no
    credentials or unrestricted process environment. Preserve the returned
    dispatch_digest in the attempt ledger before calling an author. No record
    here is an approval, nor evidence that dispatch actually happened.
    """
    safe_name(source_label)
    _feedback(feedback, source_label)
    if not isinstance(prompt, str) or not isinstance(response_contract, dict) or not isinstance(invocation_context, dict):
        raise LabError("A proposal dispatch needs prompt text, a response contract, and invocation context")
    if not _valid_digest(source_hash):
        raise LabError("Proposal source identity needs its ledger SHA-256 digest")
    source = _path(source)
    destination = _path(destination)
    if destination.is_relative_to(source):
        raise LabError("Proposal evidence must be outside its source directory")
    before = _source_files(source)
    if digest(before) != source_hash:
        raise LabError("Proposal source does not match its ledger identity")
    try:
        prompt_bytes = prompt.encode("utf-8")
    except UnicodeError as exc:
        raise LabError("Proposal prompt must be valid UTF-8 text") from exc
    payloads = {
        "feedback": _json_bytes(feedback),
        "prompt": prompt_bytes,
        "response_contract": _json_bytes(response_contract),
        "invocation_context": _json_bytes(invocation_context),
    }
    receipt = {
        "schema_version": 1,
        "kind": "proposal_dispatch",
        "prepared_at": utc_now(),
        "source_label": source_label,
        "source_hash": source_hash,
        "source_files": before,
        "artifacts": {name: {"path": _ARTIFACTS[name], "sha256": _sha(data), "bytes": len(data)}
                      for name, data in payloads.items()},
    }
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        _path(destination.parent)
        destination.mkdir(mode=0o700)
        _sync_directory(destination.parent)
    except FileExistsError as exc:
        raise LabError("Proposal dispatch destination already exists; use a fresh attempt path") from exc
    except OSError as exc:
        raise LabError("Could not create proposal dispatch destination") from exc
    for name, data in payloads.items():
        _write_new(destination / _ARTIFACTS[name], data)
    if _source_files(source) != before:
        raise LabError("Proposal source changed while preparing dispatch; preserve this incomplete attempt")
    # Written last: a partial input bundle cannot masquerade as a prepared dispatch.
    receipt_bytes = _json_bytes(receipt)
    _write_new(destination / "dispatch.json", receipt_bytes)
    return _metadata(receipt, _sha(receipt_bytes))


def verify_dispatch(directory: Path, *, expected_digest: str, source: Path | None = None,
                    prompt: str | None = None) -> dict[str, Any]:
    """Revalidate a pinned dispatch and return its exact, private author inputs.

    Pass the workspace as ``source`` immediately before/after dispatch. Supplying
    ``prompt`` additionally checks the actual text about to be sent. Reading this
    result is for the trusted controller; use public_metadata for report output.
    """
    directory = _path(directory)
    raw = _read(directory / "dispatch.json")
    if not _valid_digest(expected_digest) or _sha(raw) != expected_digest:
        raise LabError("Proposal dispatch receipt changed or does not match its ledger digest")
    receipt = _read_json(raw)
    required = {"schema_version", "kind", "prepared_at", "source_label", "source_hash", "source_files", "artifacts"}
    if (not isinstance(receipt, dict) or set(receipt) != required
            or receipt["schema_version"] != 1 or receipt["kind"] != "proposal_dispatch"
            or not isinstance(receipt["source_files"], dict)
            or not isinstance(receipt["artifacts"], dict) or set(receipt["artifacts"]) != set(_ARTIFACTS)):
        raise LabError("Invalid proposal dispatch receipt")
    safe_name(receipt["source_label"])
    if digest(receipt["source_files"]) != receipt["source_hash"]:
        raise LabError("Proposal dispatch source identity is inconsistent")
    payloads = {}
    for name, filename in _ARTIFACTS.items():
        spec = receipt["artifacts"][name]
        if not isinstance(spec, dict) or set(spec) != {"path", "sha256", "bytes"} or spec["path"] != filename:
            raise LabError("Invalid proposal dispatch artifact reference")
        data = _read(directory / filename)
        if _sha(data) != spec["sha256"] or len(data) != spec["bytes"]:
            raise LabError(f"Proposal dispatch {name} changed after preparation")
        try:
            payloads[name] = data.decode("utf-8") if name == "prompt" else _read_json(data)
        except UnicodeError:
            raise LabError("Proposal prompt contains invalid UTF-8") from None
    _feedback(payloads["feedback"], receipt["source_label"])
    if not isinstance(payloads["response_contract"], dict) or not isinstance(payloads["invocation_context"], dict):
        raise LabError("Invalid proposal dispatch contract or invocation context")
    if source is not None and _source_files(source) != receipt["source_files"]:
        raise LabError("Proposal source changed or does not match the prepared dispatch")
    if prompt is not None and prompt != payloads["prompt"]:
        raise LabError("Proposal prompt does not match the prepared dispatch")
    return {**_metadata(receipt, expected_digest), **payloads, "source_files": receipt["source_files"]}


def capture_response(directory: Path, response_bytes: bytes, *, expected_digest: str,
                     source: Path | None = None) -> dict[str, Any]:
    """Append one exact response and its receipt, without parsing or approving it.

    Invalid/malformed responses are still evidence. Once either response file
    exists, a retry is refused, including after a partial write or interruption.
    Store the returned response_digest in the ledger for later revalidation.
    """
    verified = verify_dispatch(directory, expected_digest=expected_digest, source=source)
    if not isinstance(response_bytes, bytes):
        raise LabError("Capture exact response bytes before parsing the proposal")
    directory = _path(directory)
    if (directory / "response.json").exists() or (directory / "response-receipt.json").exists():
        raise LabError("Proposal response already exists; never overwrite or retry this attempt")
    receipt = {
        "schema_version": 1,
        "kind": "proposal_response",
        "captured_at": utc_now(),
        "dispatch_digest": expected_digest,
        "response_sha256": _sha(response_bytes),
        "response_bytes": len(response_bytes),
    }
    _write_new(directory / "response.json", response_bytes)
    raw = _json_bytes(receipt)
    _write_new(directory / "response-receipt.json", raw)
    return {key: value for key, value in verified.items() if key not in {*_ARTIFACTS, "source_files"}} | {
        "status": "response_captured", "response_digest": _sha(raw),
        "response_sha256": receipt["response_sha256"], "response_bytes": len(response_bytes),
    }


def verify_response(directory: Path, *, expected_digest: str,
                    expected_response_digest: str | None = None,
                    source: Path | None = None) -> bytes:
    """Return retained raw response bytes after digest and dispatch-link checks."""
    verify_dispatch(directory, expected_digest=expected_digest, source=source)
    raw = _read(Path(directory) / "response-receipt.json")
    if expected_response_digest is not None and (
            not _valid_digest(expected_response_digest) or _sha(raw) != expected_response_digest):
        raise LabError("Proposal response receipt changed or does not match its ledger digest")
    receipt = _read_json(raw)
    required = {"schema_version", "kind", "captured_at", "dispatch_digest", "response_sha256", "response_bytes"}
    if (not isinstance(receipt, dict) or set(receipt) != required
            or receipt["schema_version"] != 1 or receipt["kind"] != "proposal_response"
            or receipt["dispatch_digest"] != expected_digest):
        raise LabError("Proposal response receipt does not match the prepared dispatch")
    data = _read(Path(directory) / "response.json")
    if _sha(data) != receipt["response_sha256"] or len(data) != receipt["response_bytes"]:
        raise LabError("Proposal response changed after capture")
    return data


def public_metadata(directory: Path, *, expected_digest: str,
                    expected_response_digest: str | None = None) -> dict[str, Any]:
    """Expose identity, digests, counts and status, never feedback/prompt/context.

    This deliberately omits source filenames, model text, environment/context
    values, response content, and private case IDs/labels or aggregates.
    """
    verified = verify_dispatch(directory, expected_digest=expected_digest)
    result = {key: value for key, value in verified.items() if key not in {*_ARTIFACTS, "source_files"}}
    directory = _path(directory)
    response_path = directory / "response.json"
    receipt_path = directory / "response-receipt.json"
    has_response = response_path.exists() or response_path.is_symlink()
    has_receipt = receipt_path.exists() or receipt_path.is_symlink()
    if expected_response_digest is not None and not has_receipt:
        raise LabError("Pinned proposal response receipt is missing")
    if has_response and has_receipt:
        data = verify_response(directory, expected_digest=expected_digest,
                               expected_response_digest=expected_response_digest)
        result.update(status="response_captured", response_sha256=_sha(data),
                      response_digest=_sha(_read(receipt_path)), response_bytes=len(data))
    elif has_response or has_receipt:
        result["status"] = "response_incomplete"
    else:
        result["status"] = "prepared"
    return result
