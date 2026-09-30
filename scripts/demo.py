#!/usr/bin/env python3
"""Run a completely offline, zero-dollar integration demonstration."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from codex_eval_lab.engine import initialize, finalize
from codex_eval_lab.optimizer import loop
from codex_eval_lab.report import render_report
from codex_eval_lab.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="New directory outside this repository")
    args = parser.parse_args()
    state = args.out.resolve()
    suite = ROOT / "examples" / "routing"
    initialize(suite, suite / "app", state, approvals={"cases": True, "grader": True, "execution": True},
               note="Explicitly invoked offline synthetic scripted integration demo; no models, production data, or paid calls.")
    search = loop(state, approved=True)
    result = finalize(state, approved=True)
    report = render_report(state, state / "report.html")
    with Store(state / "state.sqlite3") as store:
        final_budget = store.budget()
    print(json.dumps({"demonstration": "scripted synthetic fixture, NOT a live Codex/model benchmark", "best": search["best"],
                      "stop_reason": search["stop_reason"], "heldout": result["metrics"], "report": report, "budget": final_budget}, indent=2))
    if search["best"] != "round-0001" or len(search["history"]) != 3 or not result["accepted"]:
        raise SystemExit("DEMO FAILED: unexpected winner, rejection behavior, or final-test result")


if __name__ == "__main__":
    main()
