"""Bounded author context, separate from full measurements and statistics."""
from __future__ import annotations

import copy
import statistics

from .stats import case_means
from .util import LabError, canonical, digest, integer


def bounded_feedback(feedback: dict, max_bytes: int = 65_536) -> dict:
    """Deterministic numeric summary plus worst-development-row previews.

    Engine feedback is already sorted worst-first. No heldout data is accepted
    or fetched here. Truncated payloads are explicitly marked JSON text previews,
    never substituted into grading or statistics.
    """
    integer(max_bytes, "max_feedback_bytes", minimum=4096, maximum=2_000_000)
    if len(canonical(feedback).encode("utf-8")) <= max_bytes:
        return feedback
    result = copy.deepcopy({k: v for k, v in feedback.items() if k != "development_results"})
    rows = feedback["development_results"]
    measured = [{**r, "status": "ok"} for r in rows]
    metrics = sorted({k for r in rows for k in r["metrics"]})
    result["development_summary"] = {
        "trials": len(rows), "cases": len({r["case_id"] for r in rows}),
        "case_mean_metrics": {m: statistics.fmean(case_means(measured, m).values()) for m in metrics},
        "interpretation": "Unweighted case means after averaging repetitions; full training rows, not only previews."}
    result["feedback_excerpt"] = {"full_feedback_sha256": digest(feedback), "max_bytes": max_bytes,
                                   "included_rows": 0, "total_rows": len(rows), "omitted_rows": len(rows),
                                   "max_payload_preview_cases": 3, "included_payload_preview_cases": 0, "payload_preview_chars": 512}
    result["warning"] += " This is a bounded development excerpt: all-row numeric aggregates are retained; rows are worst-first. Payload previews are explicitly marked JSON text, not original typed values. Full rows remain in the private controller."
    result["development_results"] = []
    if len(canonical(result).encode("utf-8")) > max_bytes:
        raise LabError("Proposal feedback header exceeds its configured byte budget")
    previewed = set()
    for index, row in enumerate(rows):
        compact = {k: row[k] for k in ("case_id", "rep", "metrics") if k in row}
        if row["case_id"] not in previewed and len(previewed) < 3:
            previewed.add(row["case_id"])
            for field in ("input", "expected", "output", "explanation", "criterion_results"):
                if field in row:
                    text = canonical(row[field])
                    compact[field] = row[field] if len(text) <= 512 else {"_truncated_json_text_preview": text[:512]}
        result["development_results"].append(compact)
        result["feedback_excerpt"]["included_rows"] = index + 1
        result["feedback_excerpt"]["included_payload_preview_cases"] = sum("input" in r for r in result["development_results"])
        result["feedback_excerpt"]["omitted_rows"] = len(rows) - index - 1
        if len(canonical(result).encode("utf-8")) > max_bytes:
            result["development_results"].pop()
            result["feedback_excerpt"]["included_rows"] = index
            result["feedback_excerpt"]["included_payload_preview_cases"] = sum("input" in r for r in result["development_results"])
            result["feedback_excerpt"]["omitted_rows"] = len(rows) - index
            break
    return result
