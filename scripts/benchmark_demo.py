#!/usr/bin/env python3
"""Offline timing/correctness study with a hand-written change, NOT a Codex discovery."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from codex_eval_lab.engine import initialize,run,register,select,finalize
from codex_eval_lab.report import render_report
from codex_eval_lab.store import Store


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    state=a.out.resolve();suite=ROOT/'examples/benchmark'
    initialize(suite,suite/'app',state,approvals={'cases':True,'grader':True,'execution':True},
               note='Explicitly invoked offline synthetic integer benchmark; hand-authored change, zero API calls.')
    for split in ('train','validation'):run(state,'baseline',split)
    with tempfile.TemporaryDirectory(prefix='eval-lab-known-optimization-') as tmp:
        app=Path(tmp)/'app';shutil.copytree(suite/'app',app)
        source=(app/'app.py').read_text()
        start=source.index('def unique(values):');end=source.index('\n\nif __name__',start)
        source=source[:start]+'def unique(values):\n    return list(dict.fromkeys(values))\n'+source[end:]
        (app/'app.py').write_text(source)
        register(state,app,'ordered-hash-dedup','Replace quadratic list membership with ordered hash deduplication for supported integer inputs.')
    for split in ('train','validation'):run(state,'ordered-hash-dedup',split)
    decision=select(state,'ordered-hash-dedup')
    final=finalize(state,approved=True)
    report=render_report(state,state/'report.html')
    with Store(state/'state.sqlite3') as store:budget=store.budget()
    print(json.dumps({'demonstration':'Hand-authored optimization, NOT a model performance benchmark; cooperative kernel timing on synthetic integer lists.',
                     'selection':decision,'final':final,'budget':budget,'report':report},indent=2))
    if not final['accepted']:raise SystemExit('No confirmed speed improvement under the measured noise/guardrails; inspect the report.')
if __name__=='__main__':main()
