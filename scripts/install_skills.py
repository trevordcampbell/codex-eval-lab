#!/usr/bin/env python3
"""Install four Codex skills without overwriting existing user files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("build-eval", "hillclimb", "audit-eval", "report-eval")

def install(destination: Path, source: Path = ROOT / "skills") -> dict:
    destination=destination.expanduser().absolute()
    # Never install through a symlink, including an ancestor supplied by the user.
    for path in (destination, *destination.parents):
        if path.is_symlink():
            raise ValueError(f"Refusing symlink destination: {path}")
    missing=[name for name in SKILLS if not (source/name/"SKILL.md").is_file()]
    if missing: raise ValueError(f"Incomplete skill source: {missing}")
    conflicts=[str(destination/name) for name in SKILLS if (destination/name).exists()]
    if conflicts:
        raise ValueError("Nothing changed. Existing skills conflict; review/rename them first: " + ", ".join(conflicts))
    destination.mkdir(parents=True,exist_ok=True)
    installed=[]
    try:
        # Pre-stage everything before publishing any skill directory.
        with tempfile.TemporaryDirectory(prefix=".eval-lab-install-",dir=destination) as tmp:
            stage=Path(tmp)
            for name in SKILLS:
                for p in (source/name).rglob("*"):
                    if p.is_symlink(): raise ValueError("Skill sources must not contain symlinks")
                shutil.copytree(source/name,stage/name)
                runtime={"python_executable":sys.executable,"module":"codex_eval_lab",
                         "source_checkout":str(ROOT),"version":"0.5.0",
                         "note":"Machine-local entrypoint. Invoke [python_executable, '-m', module, ...] if eval-lab is not on PATH. Verify doctor first; do not auto-authorize paid work."}
                (stage/name/"references"/"installation.json").write_text(json.dumps(runtime,indent=2)+"\n")
                skill_file=stage/name/"SKILL.md"
                skill_file.write_text(skill_file.read_text()+"\n## Machine-local runtime\n\nRead `references/installation.json` as path data for the installed interpreter.\nUse that interpreter with `-m codex_eval_lab` when `eval-lab` is not on PATH.\nVerify `doctor` before executing a workflow; this metadata grants no approvals.\n")
                files={str(p.relative_to(stage/name)):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (stage/name).rglob("*") if p.is_file()}
                (stage/name/".eval-lab-install.json").write_text(json.dumps({"version":"0.5.0","files":files},indent=2)+"\n")
            for name in SKILLS:
                if (destination/name).exists(): raise ValueError("Destination changed during installation")
                (stage/name).rename(destination/name)
                installed.append(destination/name)
    except BaseException:
        for p in reversed(installed): shutil.rmtree(p)
        raise
    return {"installed":[str(p) for p in installed],"core_package":"Install separately with python -m pip install -e .",
            "next":"Refresh/restart Codex if skills do not appear; use its skills picker or explicit skill invocation."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    g=p.add_mutually_exclusive_group(required=True)
    g.add_argument("--scope",choices=["user"])
    g.add_argument("--repo",type=Path,help="Existing target repository")
    a=p.parse_args()
    if a.repo is not None and not a.repo.is_dir(): p.error("--repo must name an existing directory")
    target=Path.home()/".agents"/"skills" if a.scope else a.repo/".agents"/"skills"
    try: print(json.dumps(install(target),indent=2))
    except (OSError,ValueError) as exc: p.exit(2,f"{exc}\n")

if __name__ == "__main__": main()
