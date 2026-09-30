#!/usr/bin/env python3
"""Publish a verified release to a NEW private GitHub repository using local gh auth.

The source archive's RELEASE_MANIFEST.json must be present and unmodified.
No token is requested, read, printed, or embedded in any file by this script.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def verified_files(root:Path):
    manifest=json.loads((root/"RELEASE_MANIFEST.json").read_text())
    if manifest.get("schema_version")!=1 or manifest.get("name")!="codex-eval-lab":
        raise ValueError("Unexpected release manifest")
    files=manifest.get("files")
    if not isinstance(files,dict) or not files:raise ValueError("Empty release manifest")
    result=[]
    for name,expected in sorted(files.items()):
        rel=Path(name)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts or "\\" in name or ":" in name:
            raise ValueError("Unsafe release path")
        if any(part in (".git",".env",".venv") or part.startswith(".env.") for part in rel.parts):
            raise ValueError("Sensitive path in release manifest")
        p=root/rel
        if any(x.is_symlink() for x in (p,*p.parents)):raise ValueError("Symlink in release source")
        if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            raise ValueError(f"Release file changed: {name}. Review and rebuild the release before publishing.")
        result.append(rel)
    return result

def run(argv,cwd=None,check=True):
    result=subprocess.run(argv,cwd=cwd,text=True,capture_output=True,check=False)
    if check and result.returncode:
        # CLI authentication errors can include environment-specific details.
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(argv[:3])}. Run it locally to inspect details.")
    return result

def publish(root:Path,repo:str,dry_run=False):
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9][A-Za-z0-9._-]{0,99}",repo):
        raise ValueError("Use owner/repository, without a URL")
    files=verified_files(root)
    if dry_run:
        return {"repo":repo,"visibility":"private","files":len(files),"action":"verified only; no GitHub or git calls made"}
    if not shutil.which("gh") or not shutil.which("git"):
        raise ValueError("Install GitHub CLI (gh) and Git, then run gh auth login on your own machine.")
    run(["gh","auth","status"])
    profile=json.loads(run(["gh","api","user"]).stdout)
    owner=repo.split('/')[0]
    if profile["login"].casefold()!=owner.casefold():
        raise ValueError("This script only creates under the authenticated personal account; owner does not match.")
    # Create from a NEW temporary git repository. Existing local repos, staged
    # changes, history, ignored files, and secrets can never be pushed by accident.
    existing=run(["gh","repo","view",repo,"--json","name"],check=False)
    if existing.returncode==0:
        raise ValueError("Repository already exists. Nothing changed; use a reviewed normal git workflow instead.")
    with tempfile.TemporaryDirectory(prefix="codex-eval-lab-publish-") as tmp:
        work=Path(tmp)
        for rel in files:
            dst=work/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/rel,dst)
        shutil.copyfile(root/"RELEASE_MANIFEST.json",work/"RELEASE_MANIFEST.json")
        run(["git","init","-b","main"],work)
        run(["git","config","user.name",profile["login"]],work)
        run(["git","config","user.email",f"{profile['id']}+{profile['login']}@users.noreply.github.com"],work)
        run(["git","add","--all"],work)
        run(["git","commit","-m","Initial Codex Eval Lab 0.1.0 alpha release"],work)
        run(["gh","repo","create",repo,"--private","--source",str(work),"--remote","origin","--push",
             "--description","Provider-neutral eval design and guarded hillclimbing for Codex"],work)
        metadata=json.loads(run(["gh","repo","view",repo,"--json","url,isPrivate"],work).stdout)
        if metadata.get("isPrivate") is not True:raise RuntimeError("Repository was created, but private visibility could not be verified")
        commit=run(["git","rev-parse","HEAD"],work).stdout.strip()
        return {"url":metadata["url"],"visibility":"private","commit":commit,"files":len(files),
                "note":"Clone the new repository to make further changes; the source archive remains untouched."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo",required=True);p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    try:print(json.dumps(publish(ROOT,a.repo,a.dry_run),indent=2))
    except (ValueError,OSError,RuntimeError,KeyError) as exc:p.exit(2,f"{exc}\n")
if __name__=="__main__":main()
