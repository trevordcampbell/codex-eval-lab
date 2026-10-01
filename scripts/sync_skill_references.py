#!/usr/bin/env python3
"""Keep installable skills self-contained; --check performs no writes."""
import argparse
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
NAMES = ("OPERATING_GUIDE.md", "PROTOCOL.md", "SECURITY.md", "STATISTICS.md", "EVIDENCE.md", "AUTOMATION.md")

def sync(check=False):
    mismatches=[]
    for skill in sorted((ROOT/"skills").iterdir()):
        if not skill.is_dir():
            continue
        for name in NAMES:
            source=(ROOT/"docs"/name).read_bytes()
            target=skill/"references"/name
            if not target.exists() or target.read_bytes()!=source:
                mismatches.append(str(target.relative_to(ROOT)))
                if not check:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(source)
    return mismatches

if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--check",action="store_true")
    a=p.parse_args(); differences=sync(a.check)
    for name in differences: print(name)
    sys.exit(1 if a.check and differences else 0)
