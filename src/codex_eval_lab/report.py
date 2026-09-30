"""Offline, escaped HTML reports. No model-supplied markup is executed."""
from __future__ import annotations

import base64
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from .engine import manifest_for
from .stats import case_means
from .store import Store
from .util import LabError, atomic_text, canonical, utc_now

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
    return html.escape(str(value), quote=True)


def pretty(value: Any) -> str:
    return esc(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def render_report(state: Path, output: Path, *, include_private: bool = False) -> dict[str, Any]:
    with Store(state / "state.sqlite3") as store:
        manifest = manifest_for(state, store)
        cfg, splits = manifest["config"], manifest["splits"]
        best, final = store.get("best"), store.get("final_result")
        budget = store.budget()
        variants = store.variants()
        metric = cfg["objective"]["metric"]
        rows_html = []
        details = []
        for variant in variants:
            label = variant["label"]
            cells = []
            for split in ("train", "validation", "test"):
                allowed = split != "test" or final is not None
                rows = store.results(label, split) if allowed else []
                expected = len(splits[split]) * cfg["repetitions"]
                complete = len(rows) == expected and expected > 0 and all(r["status"] == "ok" for r in rows)
                if complete:
                    means = case_means(rows, metric)
                    score = sum(means.values()) / len(means)
                    cells.append(f"<td><strong>{score:.5g}</strong><br><span class='muted'>{len(means)} cases · {cfg['repetitions']} repeats</span></td>")
                elif split == "test" and final is None:
                    cells.append("<td class='muted'>Sealed</td>")
                else:
                    cells.append(f"<td class='muted'>{len(rows)}/{expected} trials; not complete</td>")
                show_details = split == "train" or include_private and (split != "test" or final is not None)
                if show_details:
                    for row in rows:
                        title = f"{label} / {split} / {row['case_id']} / repeat {row['rep']}"
                        details.append(f"<details data-case><summary>{esc(title)} <span class='pill'>{esc(row['status'])}</span></summary><pre>{pretty(row)}</pre></details>")
            badge = " <span class='pill'>Selected</span>" if label == best else ""
            rows_html.append(f"<tr><td><strong>{esc(label)}</strong>{badge}<br><small>{esc(variant['hypothesis'])}</small></td>{''.join(cells)}</tr>")
        decisions = store.get("search_history", [])
        decision_html = "".join(f"<details><summary>Round {d['round']}: {esc(d['label'])} — {'keep' if d['accepted'] else 'do not promote'}</summary><p>{esc(d['hypothesis'])}</p><pre>{pretty(d)}</pre></details>" for d in decisions)
        if not decision_html:
            decision_html = "<p class='muted'>No automated candidate decisions yet. Manual comparisons are available through the CLI.</p>"
        final_html = f"<pre>{pretty(final)}</pre>" if final else "<p>The final test has not been completed. Development and validation improvements are not an independent final result.</p>"
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
<section id="decisions"><h2>Optimization decisions</h2><p class="muted">Candidates must clear the primary improvement threshold and every guardrail against both the incumbent and original baseline.</p>{decision_html}</section>
<section id="final"><h2>Independent final comparison</h2>{final_html}</section>
<section><h2>Accounting and provenance</h2><pre>{pretty({'budget':budget,'source_hashes':{v['label']:v['source_hash'] for v in variants},'created':manifest['created'],'environment':manifest['environment'],'runtime_version':manifest['tool_version']})}</pre></section>
<section id="cases"><h2>Case evidence</h2><p class="muted">{'PRIVATE EXPORT: includes validation details and completed final-test details. Do not feed this report to the optimizer.' if include_private else 'Development evidence only. Validation and unfinished test transcripts are not embedded.'} Model outputs are displayed as escaped text, never executed.</p><label for="filter">Filter by case, candidate, output, or explanation</label><input id="filter" type="search" placeholder="Search evidence…">{''.join(details)}</section>
<footer>Generated {esc(utc_now())}. Self-contained report; no external scripts, fonts, analytics, or network requests. Keep reports containing real user data private.</footer>
</main><script>{JS}</script></body></html>"""
        atomic_text(output, doc)
        return {"report": str(output), "variants": len(variants), "private_details_included": include_private, "final_test_complete": bool(final)}
