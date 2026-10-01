#!/usr/bin/env python3
"""Offline end-to-end native automation with executed oracle controls; no model calls."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from codex_eval_lab.automation import make_plan, start_automation
from codex_eval_lab.util import write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, required=True, help="New external demonstration directory")
    args = p.parse_args()
    out = args.out.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        p.error("Choose a new output directory outside the repository")
    out.mkdir(parents=True)
    suite = ROOT / "examples" / "automation"
    plan = make_plan(suite, suite / "app")
    write_json(out / "plan.json", plan)
    result = start_automation(suite, suite / "app", out / "state", plan, approved=True,
                             authorization_note="Explicitly invoked offline scripted synthetic demo, including local checks, three fixture proposals and final-test opening. No paid calls or production data.")
    if not result["final_result"]["accepted"] or result["best"] != "round-0001" or result["readiness"]["human_reviewed"]:
        raise SystemExit("Unexpected automation result")
    print(json.dumps({"demonstration": "Executed synthetic scripted fixture, not a live Codex/model benchmark",
                      "best": result["best"], "evidence_basis": result["readiness"]["evidence_basis"],
                      "controls": result["readiness"]["executable"]["controls"],
                      "final": result["final_result"], "budget": result["budget"], "report": result["report"]}, indent=2))


if __name__ == "__main__":
    main()
