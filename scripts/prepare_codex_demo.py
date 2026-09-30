#!/usr/bin/env python3
"""Create a separate, unapproved routing suite using the REAL Codex backend."""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def prepare(destination: Path):
    if destination.exists(): raise ValueError("Destination exists; refusing to overwrite")
    shutil.copytree(ROOT / "examples" / "routing", destination,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    config = (destination / "eval.toml").read_text()
    config = config.replace('harness_paths = ["grader.py", "demo_optimizer.py"]', 'harness_paths = ["grader.py"]')
    config = config[:config.index('# This fixture')] + '[optimizer]\nbackend = "codex"\ntimeout_s = 600\n'
    (destination / "eval.toml").write_text(config)
    (destination / "demo_optimizer.py").unlink()
    return destination

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    try: destination=prepare(a.out)
    except (ValueError,OSError) as exc:p.exit(2,f'{exc}\n')
    print(f"Created an UNAPPROVED live-Codex suite at {destination}. Audit, start with approvals, then loop with --approve-optimizer. Codex usage is separate from the free app eval.")
if __name__ == '__main__':main()
