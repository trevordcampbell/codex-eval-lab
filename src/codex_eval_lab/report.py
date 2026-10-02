"""Offline, escaped HTML reports. No model-supplied markup is executed."""
from __future__ import annotations

import base64
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from . import paired, search_policy
from .engine import manifest_for
from .evidence import public_evidence_summary
from .stats import case_means
from .store import Store
from .util import LabError, atomic_text, utc_now

CSS = """
:root{color-scheme:light;--ink:#182432;--muted:#526476;--line:#d9e1e8;--accent:#17626e}
*{box-sizing:border-box}body{margin:0;background:#f6f8fa;color:var(--ink);font:15px/1.6 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
main{max-width:1220px;margin:auto;padding:44px 28px 80px}h1{font-size:40px;letter-spacing:-1.4px;line-height:1.12;margin:14px 0}h2{font-size:23px;margin:32px 0 12px}.eyebrow{font-size:12px;letter-spacing:2px;font-weight:750;color:var(--accent)}
.subtitle,.muted{color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:28px 0}.card,section{background:white;border:1px solid var(--line);border-radius:12px;padding:20px}.card strong{display:block;font-size:25px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.card span{font-size:12px;color:var(--muted)}section{margin:18px 0}.notice{border-left:4px solid var(--accent);padding:13px 18px;background:#edf5f6;border-radius:6px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:11px 13px;border-bottom:1px solid var(--line);vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted)}.scroll{overflow-x:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;border:1px solid var(--line);padding:14px;border-radius:7px;font-size:12px;line-height:1.5}details{border-top:1px solid var(--line);padding:12px 0}summary{cursor:pointer;font-weight:650}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.9em}.pill{display:inline-block;padding:3px 9px;border-radius:20px;background:#e9f3ed;font-size:12px;font-weight:650}.warn{background:#fff3d8}input{width:100%;font:inherit;padding:11px;border:1px solid var(--line);border-radius:7px}nav a{margin-right:16px;color:var(--accent)}.bar{height:8px;background:#e9eef2;border-radius:8px;margin-top:8px;max-width:150px}.bar i{display:block;height:8px;background:var(--accent);border-radius:8px}footer{margin-top:28px;font-size:12px;color:var(--muted)}
@media(max-width:700px){main{padding:24px 16px}h1{font-size:31px}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}section{padding:14px}th,td{padding:8px;font-size:13px}}
"""
JS = """document.getElementById('filter').addEventListener('input',function(){const q=this.value.toLowerCase();for(const el of document.querySelectorAll('[data-case]'))el.hidden=!el.textContent.toLowerCase().includes(q);});"""


def esc(value: Any) -> str:
    # JSON permits lone surrogates; keep them inert and UTF-8 writable too.
    return html.escape(str(value).encode("utf-8", errors="backslashreplace").decode("utf-8"), quote=True)


def pretty(value: Any) -> str:
    return esc(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


# Presentation limits only. Never feed preview data to statistics or write it to state.
TRACE_FIELD_CHARS = 4_096
TRACE_ROW_CHARS = 16_384
TRACE_TITLE_CHARS = 512
TRACE_MAX_ROWS = 200
TRACE_HTML_BYTES = 1_048_576
TRUNCATED = "\n[truncated; full value remains in raw state]"


def _text_prefix(value: str, limit: int) -> tuple[str, bool]:
    # Normalize invalid Unicode before counting; later escaping must not expand
    # lone surrogates beyond the promised text limits.
    value = value.encode("utf-8", errors="backslashreplace").decode("utf-8")
    if len(value) <= limit:
        return value, False
    return value[:limit - len(TRUNCATED)] + TRUNCATED, True


def _json_prefix(value: Any, limit: int) -> tuple[str, bool]:
    """Stop traversing large arrays/maps once a text preview is full.

    A truncated preview is explicitly a text fragment, not parseable JSON.
    The encoder can still allocate one full string token; raw row loading and
    analysis memory are outside the HTML presentation bounds.
    """
    pieces = []
    size = 0
    for chunk in json.JSONEncoder(ensure_ascii=False, indent=2, allow_nan=False).iterencode(value):
        pieces.append(chunk[:limit + 1 - size])
        size += len(pieces[-1])
        if size > limit:
            break
    return _text_prefix("".join(pieces), limit)


def _row_preview(row: dict[str, Any]) -> tuple[str, bool]:
    # Keep trial identity, numeric evidence and the artifact locator ahead of payloads.
    first = ("case_id", "rep", "status", "metrics", "artifact_dir", "cohort", "label", "split")
    keys = dict.fromkeys((*first, *row))
    pieces = []
    size = 0
    truncated = False
    for key in keys:
        if key not in row:
            continue
        name, name_cut = _json_prefix(key, TRACE_FIELD_CHARS)
        value, value_cut = _json_prefix(row[key], TRACE_FIELD_CHARS)
        field = f"{name}: {value}\n"
        pieces.append(field[:TRACE_ROW_CHARS + 1 - size])
        size += len(pieces[-1])
        truncated |= name_cut or value_cut
        if size > TRACE_ROW_CHARS:
            break
    text, row_cut = _text_prefix("".join(pieces), TRACE_ROW_CHARS)
    return text, truncated or row_cut


class _TracePreviews:
    """One shared budget across legacy and paired rows, after privacy filtering."""

    def __init__(self, full: bool):
        self.full = full
        self.details: list[str] = []
        self.eligible = self.truncated = self.html_bytes = 0
        self.exhausted = False

    def add(self, title: str, row: dict[str, Any]) -> None:
        self.eligible += 1
        if not self.full and (self.exhausted or len(self.details) >= TRACE_MAX_ROWS):
            return
        if self.full:
            body, cut = json.dumps(row, ensure_ascii=False, indent=2, allow_nan=False), False
        else:
            title, title_cut = _text_prefix(title, TRACE_TITLE_CHARS)
            body, cut = _row_preview(row)
            cut |= title_cut
        badge = " <span class='pill warn'>Truncated preview</span>" if cut else ""
        detail = f"<details data-case><summary>{esc(title)}{badge}</summary><pre>{esc(body)}</pre></details>"
        size = len(detail.encode("utf-8"))
        if not self.full and self.html_bytes + size > TRACE_HTML_BYTES:
            self.exhausted = True
            return
        self.details.append(detail)
        self.html_bytes += size
        self.truncated += int(cut)

    def summary(self) -> dict[str, Any]:
        return {"eligible_rows": self.eligible, "shown_rows": len(self.details),
                "omitted_rows": self.eligible - len(self.details), "truncated_rows": self.truncated,
                "html_bytes": self.html_bytes, "full_traces": self.full}

    def notice(self, state: Path) -> str:
        counts = self.summary()
        limits = ("Unbounded full-trace export explicitly requested; this file can be very large."
                  if self.full else
                  f"Bounded text previews: at most {TRACE_FIELD_CHARS:,} serialized characters per top-level field value/key, "
                  f"{TRACE_ROW_CHARS:,} per row, {TRACE_TITLE_CHARS:,} per title, {TRACE_MAX_ROWS:,} rows and "
                  f"{TRACE_HTML_BYTES:,} UTF-8 bytes of trace HTML in total (including escaped text and row markup). "
                  "Truncation markers count toward character caps; preview fragments may not be valid JSON.")
        return (f"<p class='notice'>{limits} Shown: {counts['shown_rows']:,} of {counts['eligible_rows']:,} eligible rows; "
                f"{counts['truncated_rows']:,} shown rows truncated; {counts['omitted_rows']:,} rows omitted from this HTML. "
                "Rows are a deterministic prefix of report order, not a representative sample. "
                "All scores, comparisons and sample counts use full records. Search covers only displayed text.</p>"
                f"<p class='muted'>Full raw evidence remains in <code>{esc(state / 'state.sqlite3')}</code>, "
                "table <code>trials</code> keyed by label/split/case_id/rep, or <code>paired_trials</code> "
                "also keyed by cohort (label is the measurement role). Each record's <code>artifact_dir</code> "
                "is relative to the experiment state directory. Nothing is removed from state. "
                "The database and raw artifacts may contain private held-out data; do not send them to the optimizer. "
                "Use <code>report --full-traces</code> only when a large inline export is needed; "
                "held-out details still require <code>--include-private</code> and unfinished test details remain sealed.</p>")


def render_report(state: Path, output: Path, *, include_private: bool = False, full_traces: bool = False) -> dict[str, Any]:
    with Store(state / "state.sqlite3") as store:
        manifest = manifest_for(state, store)
        cfg, splits = manifest["config"], manifest["splits"]
        best, final = store.get("best"), store.get("final_result")
        budget = store.budget()
        variants = store.variants()
        metric = cfg["objective"]["metric"]
        rows_html = []
        previews = _TracePreviews(full_traces)
        for variant in variants:
            label = variant["label"]
            cells = []
            for split in ("train", "validation", "test"):
                allowed = split != "test" or final is not None
                rows = store.results(label, split) if allowed and not (paired.enabled(manifest) and split != "train") else []
                expected = len(splits[split]) * cfg["repetitions"]
                complete = len(rows) == expected and expected > 0 and all(r["status"] == "ok" for r in rows)
                if complete:
                    means = case_means(rows, metric)
                    score = sum(means.values()) / len(means)
                    cells.append(f"<td><strong>{score:.5g}</strong><br><span class='muted'>{len(means)} cases · {cfg['repetitions']} repeats</span></td>")
                elif split == "test" and final is None:
                    cells.append("<td class='muted'>Sealed</td>")
                elif paired.enabled(manifest) and split != "train":
                    cells.append("<td class='muted'>See separate paired cohorts below</td>")
                else:
                    cells.append(f"<td class='muted'>{len(rows)}/{expected} trials; not complete</td>")
                show_details = split == "train" or include_private and (split != "test" or final is not None)
                if show_details:
                    for row in rows:
                        title = f"{label} / {split} / {row['case_id']} / repeat {row['rep']}"
                        previews.add(f"{title} / {row['status']}", row)
            badge = " <span class='pill'>Selected</span>" if label == best else ""
            rows_html.append(f"<tr><td><strong>{esc(label)}</strong>{badge}<br><small>{esc(variant['hypothesis'])}</small></td>{''.join(cells)}</tr>")
        paired_html = ""
        if paired.enabled(manifest):
            cohort_html = []
            for saved in store.db.execute("SELECT id,spec FROM paired_cohorts ORDER BY created,id"):
                cohort, spec = saved["id"], json.loads(saved["spec"])
                split = spec["split"]
                if split == "test" and final is None:
                    cohort_html.append("<p>Final paired cohort: sealed or incomplete; no test details exported.</p>")
                    continue
                try:
                    result = paired.comparison(state, store, manifest, cohort)
                except LabError:
                    result = {"cohort": cohort, "split": split, "status": "incomplete or invalid; no accepted comparison"}
                cohort_html.append(f"<details><summary>{esc(cohort)} / {esc(split)}</summary><pre>{pretty(result)}</pre></details>")
                if include_private:
                    for role in spec["arms"]:
                        for row in store.results(role, split, cohort=cohort):
                            title = f"{cohort} / {role} / {row['case_id']} / repeat {row['rep']}"
                            previews.add(title, row)
            paired_html = "<section><h2>Paired measurement cohorts</h2><p>Each cohort has fresh reference and candidate calls. Scores from different cohorts are not pooled. AB/BA pairing reduces slow drift but does not eliminate environmental confounding.</p>" + "".join(cohort_html) + "</section>"
        outcome = search_policy.outcome_summary(store)
        policy_text = ("Exploratory search uses point-estimate improvement with prespecified baseline guardrails. Archive/parent selection is not release evidence. Final confirmation retains the original gate."
                       if search_policy.enabled(manifest) else
                       "Conservative search requires the primary improvement threshold and every guardrail against both incumbent and original baseline. Final confirmation remains separate.")
        decisions = store.get("search_history", [])
        decision_html = "".join(f"<details><summary>Round {d['round']}: {esc(d['label'])} — {'selected for search' if d['accepted'] else 'not selected for search'}</summary><p>{esc(d['hypothesis'])}</p><pre>{pretty(d)}</pre></details>" for d in decisions)
        if not decision_html:
            decision_html = "<p class='muted'>No automated selection rounds recorded. Manual selection actions, if any, are listed separately below.</p>"
        manual_html = []
        for saved in store.db.execute("SELECT at,data FROM events WHERE kind='manual_selection' ORDER BY id"):
            decision = json.loads(saved["data"])
            action = "promoted" if decision["promoted"] else "not promoted"
            manual_html.append(f"<details><summary>{esc(decision['candidate'])}: {action} / {esc(saved['at'])}</summary><pre>{pretty(decision)}</pre></details>")
        manual_section = ("<section><h2>Manual selection decisions</h2><p>These records show selection actions, including rejections. A comparison's accepted flag describes measurement eligibility; it is not by itself a promotion. Read-only compare commands do not add history.</p>" + "".join(manual_html) + "</section>") if manual_html else ""
        final_html = f"<pre>{pretty(final)}</pre>" if final else "<p>The final test has not been completed. Development and validation improvements are not an independent final result.</p>"
        oracle_gate = manifest.get("oracle_gate", {})
        expert_gate = manifest.get("evidence_gate", {})
        evidence_basis = "expert_calibrated" if expert_gate.get("ready") else "executable_oracle_validated" if oracle_gate.get("ready") else "unverified"
        evidence_record = {"evidence_basis": evidence_basis,
                           "interpretation": "Executable checks passed means finite controls passed, not verified domain truth. Model-authored controls are not human labels; local records are attestations, not authenticated identities.",
                           "executable_oracle": oracle_gate,
                           "expert_calibration": public_evidence_summary(expert_gate),
                           "automation_plan_sha256": manifest.get("automation_plan", {}).get("plan_sha256"),
                           "automation_stop_reason": store.get("automation_stop_reason"),
                           "automation_blocker": store.get("automation_blocker"),
                           "unresolved_optimizer_calls": store.unresolved_optimizers()}
        evidence_section = "<section><h2>Measurement evidence and automation</h2><pre>" + pretty(evidence_record) + "</pre></section>"
        csp_hash = base64.b64encode(hashlib.sha256(JS.encode()).digest()).decode()
        title = esc(cfg["name"])
        doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{csp_hash}'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>{title} · Codex Eval Lab</title><style>{CSS}</style></head><body><main>
<div class="eyebrow">CODEX EVAL LAB / EXPERIMENT REVIEW</div><h1>{title}</h1>
<p class="subtitle">One measurement contract. Reversible proposals. Evidence before promotion.</p>
<nav><a href="#scores">Scores</a><a href="#decisions">Decisions</a><a href="#final">Final test</a><a href="#cases">Case evidence</a></nav>
<div class="cards"><div class="card"><strong>{esc(best)}</strong><span>SELECTED CANDIDATE</span></div><div class="card"><strong>{len(manifest['cases']):,}</strong><span>CASES / {cfg['repetitions']} REPEATS</span></div><div class="card"><strong>{budget['trials']:,}</strong><span>RESERVED OR COMPLETED TRIALS</span></div><div class="card"><strong>${budget['eval_charged_usd']:,.4f}</strong><span>EVAL ACCOUNTING / OPTIMIZER SEPARATE</span></div></div>
<div class="notice"><strong>{'Final test complete' if final else 'Exploratory until final confirmation'}.</strong> Related cases are grouped; repeated samples are not counted as new independent tasks. Local mode is cooperative, not a secret-isolation boundary.</div>
<section id="scores"><h2>Candidate scorecard</h2><p class="muted">Primary metric: <code>{esc(metric)}</code> · {esc(cfg['objective']['direction'])}. Only complete runs receive scores.</p><div class="scroll"><table><thead><tr><th>Candidate / hypothesis</th><th>Development</th><th>Validation</th><th>Final test</th></tr></thead><tbody>{''.join(rows_html)}</tbody></table></div></section>
{paired_html}
<section id="decisions"><h2>Optimization decisions</h2><p class="muted">{esc(policy_text)}</p><pre>{pretty(outcome)}</pre>{decision_html}</section>
{manual_section}
<section id="final"><h2>Independent final comparison</h2>{final_html}</section>
<section><h2>Accounting and provenance</h2><pre>{pretty({'budget':budget,'source_hashes':{v['label']:v['source_hash'] for v in variants},'created':manifest['created'],'environment':manifest['environment'],'runtime_version':manifest['tool_version']})}</pre></section>
{evidence_section}
<section id="cases"><h2>Case evidence</h2><p class="muted">{'PRIVATE EXPORT: includes validation details and completed final-test details. Do not feed this report to the optimizer.' if include_private else 'Development evidence only. Validation and unfinished test transcripts are not embedded.'} Model outputs are displayed as escaped text, never executed.</p>{previews.notice(state)}<label for="filter">Filter displayed case previews</label><input id="filter" type="search" placeholder="Search displayed evidence…">{''.join(previews.details)}</section>
<footer>Generated {esc(utc_now())}. Self-contained report; no external scripts, fonts, analytics, or network requests. Keep reports containing real user data private.</footer>
</main><script>{JS}</script></body></html>"""
        atomic_text(output, doc)
        return {"report": str(output), "variants": len(variants), "private_details_included": include_private, "final_test_complete": bool(final), "trace_preview": previews.summary()}
