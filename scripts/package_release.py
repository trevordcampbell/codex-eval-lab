#!/usr/bin/env python3
"""Create a source release from a strict path allowlist, with SHA-256 manifest."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
TOP={"README.md","LICENSE","SECURITY.md","AGENTS.md","CONTRIBUTING.md","CHANGELOG.md","pyproject.toml",".gitignore",".gitattributes"}
DIRS={"src","skills","scripts","tests","docs","examples",".github"}
EXT={".py",".md",".toml",".json",".jsonl",".yaml",".yml",".html",".txt"}
SKIP={"__pycache__",".git",".venv","node_modules","build","dist",".pytest_cache"}

def release_files(root: Path):
    paths=[]
    for p in sorted(root.rglob("*")):
        rel=p.relative_to(root)
        if any(part in SKIP or part.endswith(".egg-info") for part in rel.parts): continue
        # Reviewed documentation figures only; do not include arbitrary SVGs.
        doc_figure=len(rel.parts)==3 and rel.parts[:2]==("docs","assets") and p.suffix==".svg"
        allowed=str(rel) in TOP or (len(rel.parts)>1 and rel.parts[0] in DIRS and p.suffix in EXT) or doc_figure
        if not allowed: continue
        if p.is_symlink(): raise ValueError(f"Release source cannot be a symlink: {rel}")
        if not p.is_file():continue
        if p.name.startswith(".env") and p.name not in (".env.example",".env.sample"):
            raise ValueError("Environment secrets cannot be released")
        paths.append(p)
    missing=[name for name in TOP if not (root/name).is_file()]
    if missing: raise ValueError(f"Release missing required files: {missing}")
    return paths

def package(root:Path,out:Path):
    root=root.resolve();out=out.resolve()
    if out==root or root in out.parents: raise ValueError("Release destination must be outside source tree")
    paths=release_files(root)
    manifest={"schema_version":1,"name":"codex-eval-lab","version":"0.1.0",
              "files":{str(p.relative_to(root)).replace("\\","/"):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    payload=(json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode()
    out.mkdir(parents=True,exist_ok=True)
    archive=out/"codex-eval-lab-v0.1.0.zip"
    if archive.exists():raise ValueError("Release archive already exists; choose a new destination")
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in paths: z.writestr("codex-eval-lab/"+p.relative_to(root).as_posix(),p.read_bytes())
        z.writestr("codex-eval-lab/RELEASE_MANIFEST.json",payload)
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/(archive.name+".sha256")).write_text(f"{sha}  {archive.name}\n")
    return {"archive":str(archive),"files":len(paths),"sha256":sha}

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    try:print(json.dumps(package(ROOT,a.out),indent=2))
    except (ValueError,OSError) as exc:p.exit(2,f"{exc}\n")
