"""Optional, local-first read-only MCP server for reviewed evaluation artifacts.

No eval execution, writes, approvals, raw file reads, registration tools or HTTP
listener are exposed. Scope is selected by the operator at process startup, never
by model tool arguments. The local OS account remains the trust boundary.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import sys
import stat
from typing import Any

from .review import validate_packet
from .review_ui import render_mcp_review, review_payload
from .util import LabError, digest, strict_json

RESOURCE_URI = "ui://codex-eval-lab/review-v1.html"
RESOURCE_MIME = "text/html;profile=mcp-app"
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ARTIFACTS = 200
RESOURCE_META = {"ui": {"csp": {"connectDomains": [], "resourceDomains": []}}}


def _ordinary_file(path: Path, *, root: Path | None = None) -> Path:
    path = path.expanduser().absolute()
    # Reject symlinks anywhere in the selected path, including ancestors.
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise LabError("Artifact paths must not contain symlinks")
    resolved = path.resolve(strict=True)
    if root is not None and not resolved.is_relative_to(root):
        raise LabError("Artifact is outside the operator-selected review root")
    if not resolved.is_file():
        raise LabError("Artifact must be an ordinary file")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise LabError("Artifact exceeds the 5 MiB limit")
    return resolved


def _load(path: Path, *, root: Path | None = None) -> dict:
    resolved = _ordinary_file(path, root=root)
    # Read once into a snapshot; future tool calls never reopen model-chosen paths.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(resolved, flags)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE_BYTES:
            raise LabError("Artifact must be an ordinary bounded file")
        raw = handle.read(MAX_FILE_BYTES + 1)
    checked = _ordinary_file(path, root=root)
    after = checked.stat()
    if checked != resolved or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
        raise LabError("Artifact changed during registration; restart with stable files")
    if len(raw) > MAX_FILE_BYTES:
        raise LabError("Artifact exceeds the 5 MiB limit")
    try:
        value = strict_json(raw.decode("utf-8"))
    except UnicodeError as exc:
        raise LabError("Artifact must be UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise LabError("Artifact must be a JSON object")
    return value


def _number(value: Any, *, count: bool = False) -> int | float | None:
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise LabError("Invalid numeric calibration aggregate")
    if count and type(value) is not int:
        raise LabError("Calibration counts must be nonnegative integers")
    if not count and value > 1:
        raise LabError("Calibration rates must be in [0,1]")
    return value


def calibration_summary(report: dict) -> dict:
    """Strict allowlist projection, never disagreement rows, rationales or prompts."""
    recomputed = False
    verification = "Recorded report only; not recomputed from its source artifacts"
    if report.get("kind") == "evidence_bundle":
        from .calibration import validate_evidence_bundle
        report = validate_evidence_bundle(report, evaluator_fingerprint=report.get("evaluator_fingerprint"))
        recomputed = True
        verification = "Recomputed from bundled artifacts; current external evaluator identity not verified"
    if report.get("kind") != "calibration_report" or report.get("schema_version") != 1:
        raise LabError("Expected a calibration report or evidence bundle")
    if type(report.get("passed")) is not bool or not isinstance(report.get("criteria"), dict):
        raise LabError("Invalid calibration report")
    criteria = {}
    support_keys = {"groups", "trace_rows", "failure_groups", "pass_groups", "failure_rows", "pass_rows",
                    "uncertain_human_rows", "missing_human_rows", "unresolved_judge_rows", "predicted_failure_groups"}
    confusion_keys = {"true_failures", "missed_failures", "false_alarms", "true_passes"}
    for cid, parts in report["criteria"].items():
        if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", cid) or not isinstance(parts, dict):
            raise LabError("Invalid criterion aggregate")
        criteria[cid] = {}
        for partition in ("tuning", "validation"):
            part = parts.get(partition)
            if not isinstance(part, dict):
                raise LabError("Missing calibration partition aggregate")
            support, confusion = part.get("support"), part.get("confusion_rows")
            if not isinstance(support, dict) or not isinstance(confusion, dict):
                raise LabError("Missing calibration support or confusion aggregate")
            bounds = part.get("bounds", {})
            if not isinstance(bounds, dict):
                raise LabError("Invalid uncertainty bounds")
            projected_bounds = {}
            for metric in ("failure_recall", "failure_precision", "good_output_specificity"):
                if metric not in bounds:
                    continue
                b = bounds[metric]
                if not isinstance(b, dict):
                    raise LabError("Invalid uncertainty bound")
                projected_bounds[metric] = {"lower": _number(b.get("lower")), "upper": _number(b.get("upper")),
                                            "independent_groups": _number(b.get("independent_groups"), count=True)}
            criteria[cid][partition] = {
                "bounds": projected_bounds,
                "support": {k: _number(support[k], count=True) for k in support_keys if k in support},
                "confusion_rows": {k: _number(confusion[k], count=True) for k in confusion_keys if k in confusion},
                **{k: _number(part.get(k)) for k in ("failure_recall", "failure_precision", "good_output_specificity")},
            }
    basis = report.get("threshold_basis")
    if basis not in (None, "lower_bound", "point_estimate"):
        raise LabError("Invalid calibration threshold basis")
    reported_ready = report.get("ready") is True and report.get("readiness_eligible") is True and basis == "lower_bound"
    uncertainty = report.get("uncertainty", {})
    if not isinstance(uncertainty, dict):
        raise LabError("Invalid uncertainty metadata")
    ready = recomputed and reported_ready
    confidence = _number(uncertainty.get("confidence"))
    return {"passed": report["passed"], "ready": ready, "reported_ready": reported_ready, "threshold_basis": basis, "confidence": confidence,
            "criteria": criteria, "verification": verification,
            "positive_class": "failure", "approval": False,
            "note": "Aggregate calibration evidence is not permission to execute or proof of human identity"}


class PacketStore:
    """Immutable startup snapshots within a deliberately narrow operator scope.

    A root discovers only its direct *.packet.json / packet.json and
    *.calibration.json / *.evidence.json children. Other files and subdirectories
    are not scanned. Explicit --packet / --calibration paths are also supported.
    """
    def __init__(self, workspace_root: Path | None = None, *, packets: tuple[Path, ...] = (),
                 calibrations: tuple[Path, ...] = ()) -> None:
        self._packets: dict[str, dict] = {}
        self._calibrations: dict[str, dict] = {}
        root = None
        if workspace_root is not None:
            supplied = Path(workspace_root).expanduser().absolute()
            if any(p.is_symlink() for p in (supplied, *supplied.parents)):
                raise LabError("Review root must not contain symlinks")
            root = supplied.resolve(strict=True)
            if not root.is_dir():
                raise LabError("Review root must be a directory")
            packet_paths = sorted(set(root.glob("*.packet.json")) | ({root / "packet.json"} if (root / "packet.json").exists() else set()))
            calibration_paths = sorted(set(root.glob("*.calibration.json")) | set(root.glob("*.evidence.json")))
        else:
            packet_paths, calibration_paths = [], []
        packet_paths += list(packets)
        calibration_paths += list(calibrations)
        if len(packet_paths) + len(calibration_paths) > MAX_ARTIFACTS:
            raise LabError("Too many review artifacts; narrow the selected scope")
        for path in packet_paths:
            packet = _load(Path(path), root=root)
            validate_packet(packet)
            self._packets[packet["sha256"]] = packet
        for path in calibration_paths:
            report = _load(Path(path), root=root)
            self._calibrations[digest(report)] = calibration_summary(report)

    def list_review_packets(self) -> dict:
        return {"packets": [{"packet_id": key,
                             "tuning_trace_count": sum(t["partition"] == "tuning" for t in packet["traces"])}
                            for key, packet in sorted(self._packets.items())],
                "calibrations": [{"calibration_id": key, "passed": value["passed"], "ready": value["ready"], "threshold_basis": value["threshold_basis"], "confidence": value["confidence"], "verification": value["verification"], "approval": False}
                                 for key, value in sorted(self._calibrations.items())],
                "scope": "Operator-selected startup snapshots; no filesystem path arguments accepted"}

    def open_review(self, packet_id: str) -> tuple[dict, dict]:
        packet = self._packets.get(packet_id)
        if packet is None:
            raise LabError("Unknown registered packet ID; list available packets first")
        payload = review_payload(packet, mode="mcp")
        payload["catalog"] = self.list_review_packets()["packets"]
        summary = {"packet_id": packet_id, "tuning_trace_count": len(payload["packet"]["traces"]),
                   "review_mode": "human draft export", "approval": False,
                   "fallback": "Use eval-lab review render on the operator-selected packet for offline review"}
        return summary, {"codex-eval-lab/review": payload}

    def get_calibration_summary(self, calibration_id: str) -> dict:
        if calibration_id not in self._calibrations:
            raise LabError("Unknown registered calibration ID; list available calibrations first")
        return deepcopy(self._calibrations[calibration_id])


def build_server(store: PacketStore):
    """Construct with official MCP SDK 2.2+; the core has no transport dependency."""
    try:
        from importlib.metadata import version
        installed = version("mcp")
        match = re.match(r"^(\d+)\.(\d+)", installed)
        if not match or int(match[1]) != 2 or int(match[2]) < 2:
            raise LabError('The plugin requires mcp>=2.2.0,<3; upgrade with python -m pip install ".[plugin]"')
        from mcp import types
        from mcp.server import Server
    except ImportError as exc:
        raise LabError('Install optional plugin dependencies with: python -m pip install ".[plugin]"') from exc
    annotations = types.ToolAnnotations(read_only_hint=True, destructive_hint=False,
                                        idempotent_hint=True, open_world_hint=False)
    empty = {"type": "object", "properties": {}, "additionalProperties": False}

    def identifier(field, *, required=True):
        return {"type": "object", "properties": {field: {"type": "string", "pattern": "^[a-f0-9]{64}$"}},
                "required": [field] if required else [], "additionalProperties": False}

    def registered_id(arguments, field):
        # SDK 2 low-level handlers do not automatically validate tool JSON Schema.
        # Enforce the same strict input contract before touching the registry.
        if (not isinstance(arguments, dict) or set(arguments) != {field}
                or not isinstance(arguments[field], str)
                or re.fullmatch(r"[a-f0-9]{64}", arguments[field]) is None):
            raise LabError("Unsupported registered artifact identifier")
        return arguments[field]

    async def list_tools(ctx, params):
        return types.ListToolsResult(tools=[
            types.Tool(name="list_review_packets", description="List registered review packet and calibration IDs. Read-only, no filesystem paths.", input_schema=empty, annotations=annotations),
            types.Tool(name="open_review", title="Trace Review", description="Open the registered-packet chooser, or tuning traces for a selected packet. Exports drafts only; cannot label, approve or run evaluations for the model.", input_schema=identifier("packet_id", required=False), annotations=annotations,
                       _meta={"ui": {"resourceUri": RESOURCE_URI}, "openai/ui": {"entrypoints": [{"type": "thread"}]}}),
            types.Tool(name="get_calibration_summary", description="Read aggregate per-criterion calibration metrics, without private trace rows or rationales. This is not execution approval.", input_schema=identifier("calibration_id"), annotations=annotations),
        ])

    async def call_tool(ctx, params):
        try:
            name, arguments = params.name, params.arguments if params.arguments is not None else {}
            meta = None
            if name == "list_review_packets" and isinstance(arguments, dict) and not arguments:
                summary = store.list_review_packets()
            elif name == "open_review":
                if isinstance(arguments, dict) and not arguments:
                    catalog = store.list_review_packets()["packets"]
                    summary = {"packet_count": len(catalog), "review_mode": "packet chooser", "approval": False,
                               "fallback": "Select registered review artifacts at server startup; use eval-lab review render for offline review"}
                    meta = {"codex-eval-lab/review": {"mode": "mcp", "catalog": catalog, "packet": None, "rubric": None}}
                else:
                    summary, meta = store.open_review(registered_id(arguments, "packet_id"))
            elif name == "get_calibration_summary":
                summary = store.get_calibration_summary(registered_id(arguments, "calibration_id"))
            else:
                raise LabError("Unknown tool or unsupported arguments")
            return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(summary, sort_keys=True))],
                                        structured_content=summary, _meta=meta)
        except (LabError, TypeError):
            # Never echo raw paths, rejected payloads, or private artifact content.
            return types.CallToolResult(content=[types.TextContent(type="text", text="Review request rejected. Use a registered ID and supported arguments.")], is_error=True)

    async def list_resources(ctx, params):
        return types.ListResourcesResult(resources=[
            types.Resource(uri=RESOURCE_URI, name="Trace review", description="Bundled offline-capable review UI; no packet embedded", mime_type=RESOURCE_MIME, _meta=RESOURCE_META),
        ])

    async def read_resource(ctx, params):
        if params.uri != RESOURCE_URI:
            raise ValueError("Unknown review resource")
        return types.ReadResourceResult(contents=[
            types.TextResourceContents(uri=RESOURCE_URI, text=render_mcp_review(), mime_type=RESOURCE_MIME, _meta=RESOURCE_META),
        ])

    server = Server("codex-eval-lab", version="0.2.0", on_list_tools=list_tools,
                    on_call_tool=call_tool, on_list_resources=list_resources,
                    on_read_resource=read_resource)
    # Standard MCP Apps capability declaration; no authentication/write extension.
    server.extensions = {"io.modelcontextprotocol/ui": {}}
    return server


async def serve(store: PacketStore) -> None:
    server = build_server(store)
    from mcp.server.stdio import stdio_server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, help="Explicit review-only directory; no recursive scan")
    parser.add_argument("--packet", type=Path, action="append", default=[], help="Explicit registered packet (repeatable)")
    parser.add_argument("--calibration", type=Path, action="append", default=[], help="Explicit report or evidence bundle (repeatable)")
    parser.add_argument("--check", action="store_true", help="Validate selected artifacts and print safe catalog without starting MCP")
    args = parser.parse_args(argv)
    root = args.workspace_root
    if root is None and os.environ.get("EVAL_LAB_REVIEW_ROOT"):
        root = Path(os.environ["EVAL_LAB_REVIEW_ROOT"])
    try:
        store = PacketStore(root, packets=tuple(args.packet), calibrations=tuple(args.calibration))
        if args.check:
            print(json.dumps(store.list_review_packets(), indent=2))
        else:
            asyncio.run(serve(store))
    except (LabError, OSError) as exc:
        # Operator startup stderr is local, never a model-facing tool error.
        print(f"eval-lab-plugin: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
