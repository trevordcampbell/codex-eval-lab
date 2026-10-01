"""Self-contained, no-network human review UI; optional MCP Apps asset rendering.

The viewer records only judgments entered by its operator. JSON downloads are
unsealed drafts, not authenticated human attestations and never run approvals.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import html
import json
from importlib.resources import files
from pathlib import Path

from .review import validate_packet, validate_rubric
from .util import LabError


def review_payload(packet: dict, rubric: dict | None = None, *, mode: str = "standalone") -> dict:
    """Validated UI projection. Open-ended review never includes validation rows."""
    validate_packet(packet)
    if rubric is not None:
        validate_rubric(packet, rubric)
    rows = [dict(deepcopy(row), trace_sha256=row["sha256"]) for row in packet["traces"]
            if rubric is not None or row["partition"] == "tuning"]
    # Omit packet source/reference and reviewer; neither is needed to review traces.
    return {"mode": mode, "packet": {"packet_sha256": packet["sha256"], "traces": rows},
            "rubric": dict(deepcopy(rubric), rubric_sha256=rubric["sha256"]) if rubric else None}


def _asset(name: str) -> str:
    return files("codex_eval_lab").joinpath("ui", name).read_text(encoding="utf-8")


def _hash_source(text: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode()).digest()).decode() + "'"


def _render(*, data: dict | None = None, app: bool = False, calibration: bool = False) -> str:
    script = _asset("calibration.js" if calibration else "app.js" if app else "standalone.js")
    style = _asset("review.css")
    if "</script" in script.lower() or "</style" in style.lower():
        raise LabError("Unsafe delimiter in bundled review assets")
    csp = ("default-src 'none'; base-uri 'none'; form-action 'none'; object-src 'none'; "
           "connect-src 'none'; img-src 'none'; media-src 'none'; frame-src 'none'; "
           f"script-src {_hash_source(script)}; style-src {_hash_source(style)}")
    # Inert JSON is escaped against HTML parser termination, not just JSON quoting.
    payload = json.dumps(data, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    data_tag = f'<script id="review-data" type="application/json">{payload}</script>' if data else ""
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta http-equiv="Content-Security-Policy" content="{html.escape(csp, quote=True)}">'
            f"<title>Codex Eval Lab · Trace review</title><style>{style}</style></head><body>"
            f"{_asset('calibration.html' if calibration else 'review.html')}{data_tag}<script>{script}</script></body></html>\n")


def render_standalone_review(packet: dict, rubric: dict | None = None) -> str:
    """Return offline HTML. A frozen rubric is required for calibration validation."""
    return _render(data=review_payload(packet, rubric))


def write_standalone_review(packet: dict, out: Path, rubric: dict | None = None) -> Path:
    """Create a new export, never overwrite an existing viewer or evidence file."""
    rendered = render_standalone_review(packet, rubric)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with out.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    except FileExistsError as exc:
        raise LabError(f"Review export already exists; choose a new path: {out}") from exc
    return out


def render_mcp_review() -> str:
    """Packet-free resource; tuning traces arrive only in a tool result's _meta."""
    return _render(app=True)


def render_calibration_review(packet: dict, rubric: dict, labels: dict, judge_config: dict,
                              outputs: dict, policy: dict) -> str:
    """Offline-only disagreement viewer with real calls and independent decisions.

    Includes calibration-validation content for human inspection after rubric
    freeze. Never serve this via model tools or use it as optimizer context.
    """
    from .calibration import calibrate
    report = calibrate(packet, rubric, labels, judge_config, outputs, policy)
    data = {"packet": packet, "rubric": rubric, "labels": labels, "outputs": outputs, "report": report}
    return _render(data=data, calibration=True)
