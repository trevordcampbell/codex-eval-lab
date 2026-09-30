#!/usr/bin/env python3
"""Summarize human/judge categorical agreement. Never calls a model."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from codex_eval_lab.util import LabError, strict_json

def calibrate(rows):
    if not rows: raise ValueError("No calibration examples")
    ids=set(); matrix=Counter(); human=Counter(); judge=Counter()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={"id","human","judge"}:
            raise ValueError("Each row must contain exactly id, human, judge")
        if not all(isinstance(row[k],str) and row[k] for k in row):
            raise ValueError("id, human, judge must be nonempty strings")
        if row["id"] in ids: raise ValueError("Duplicate calibration id")
        ids.add(row["id"]); h,j=row["human"],row["judge"]
        matrix[h,j]+=1;human[h]+=1;judge[j]+=1
    labels=sorted(human.keys()|judge.keys()); n=len(rows)
    observed=sum(matrix[x,x] for x in labels)/n
    expected=sum(human[x]*judge[x] for x in labels)/(n*n)
    kappa=(observed-expected)/(1-expected) if expected<1 else None
    return {"n":n,"labels":labels,"agreement":observed,"cohens_kappa":kappa,
            "confusion_matrix":{"rows":"human","columns":"judge","counts":[[matrix[h,j] for j in labels] for h in labels]},
            "disagreements":[row["id"] for row in rows if row["human"]!=row["judge"]],
            "limitations":["Describes this labeled sample only; no automatic deployment threshold.",
                           "Kappa is undefined when both raters always use the same single label.",
                           "Human labels need independent review; agreement does not establish truth.",
                           "For pairwise judges, include order-swapped, tied, adversarial and boundary cases."]}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("labels",type=Path);a=p.parse_args()
    try:
        rows=[strict_json(line) for line in a.labels.read_text().splitlines() if line.strip()]
        print(json.dumps(calibrate(rows),indent=2,allow_nan=False))
    except (ValueError,LabError,OSError) as exc: p.exit(2,f"{exc}\n")
if __name__ == "__main__":main()
