"""Explicit snapshots, scoped proposal application, and evaluator fingerprints."""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
import shutil
from typing import Any

from .util import LabError, contained, digest, file_hash, relative_name, write_json

EXCLUDED = {".git", "__pycache__", ".venv", "node_modules", ".DS_Store", ".pytest_cache"}


def collect(root: Path, paths: list[str]) -> dict[str, Path]:
    root = root.resolve()
    found: dict[str, Path] = {}
    for name in paths:
        entry = contained(root, name)
        candidates = [entry] if entry.is_file() else sorted(entry.rglob("*"))
        for path in candidates:
            rel = path.relative_to(root).as_posix()
            if any(part in EXCLUDED for part in path.relative_to(root).parts):
                continue
            if path.is_symlink():
                raise LabError(f"Snapshot contains a symlink: {rel}")
            if path.is_file():
                if ".eval-inputs" in path.relative_to(root).parts:
                    raise LabError(".eval-inputs is reserved for per-case assets")
                if path.name == ".env" or path.name.startswith(".env.") and path.name not in (".env.example", ".env.sample"):
                    raise LabError(f"Refusing to snapshot a potential secret file: {rel}")
                if path.stat().st_size > 100_000_000:
                    raise LabError(f"File too large for a source snapshot: {rel}")
                found[rel] = path
    if not found:
        raise LabError("Source/fixture allowlist selects no files")
    return dict(sorted(found.items()))


def hashes(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise LabError(f"Unexpected symlink in frozen data: {p}")
        if p.is_file():
            result[p.relative_to(root).as_posix()] = file_hash(p)
    return result


def copy_files(files: dict[str, Path], target: Path) -> dict[str, str]:
    target.mkdir(parents=True, exist_ok=False)
    for rel, source in files.items():
        dest = contained(target, rel, exists=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Copy bytes, not ownership or unsafe permissions; preserve executable intent only.
        dest.write_bytes(source.read_bytes())
        if source.stat().st_mode & 0o111:
            dest.chmod(0o755)
    return hashes(target)


def snapshot(source: Path, paths: list[str], destination: Path) -> str:
    values = copy_files(collect(source, paths), destination)
    return digest(values)


def allowed_edit(path: str, patterns: list[str]) -> bool:
    relative_name(path)
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def apply_proposal(base: Path, target: Path, proposal: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    if not isinstance(proposal, dict) or set(proposal) - {"hypothesis", "edits", "notes", "usage", "model"}:
        raise LabError("Proposal must contain hypothesis and edits (optional notes, usage, model)")
    if not isinstance(proposal.get("hypothesis"), str) or not proposal["hypothesis"].strip():
        raise LabError("Proposal needs a concrete hypothesis")
    edits = proposal.get("edits")
    if not isinstance(edits, list) or not edits:
        raise LabError("No edits proposed; stop rather than spend an eval on a no-op")
    seen: set[str] = set()
    total = 0
    changed: list[str] = []
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {"path", "content"}:
            raise LabError("Each edit must have exactly path and content")
        rel = relative_name(edit["path"])
        if rel in seen:
            raise LabError(f"Duplicate edit: {rel}")
        seen.add(rel)
        if not allowed_edit(rel, cfg["search"]["editable"]):
            raise LabError(f"Edit outside approved scope: {rel}")
        if not isinstance(edit["content"], str) or "\x00" in edit["content"]:
            raise LabError("Only UTF-8 text replacements are supported; no NUL bytes")
        data = edit["content"].encode("utf-8")
        total += len(data)
        if total > cfg["search"]["max_edit_bytes"]:
            raise LabError("Proposal exceeds max_edit_bytes")
        old = contained(base, rel, exists=False)
        if not old.exists() or not old.is_file() or old.read_bytes() != data:
            changed.append(rel)
    if not changed:
        raise LabError("Proposal is a no-op")
    # Validate every edit before making any changes.
    shutil.copytree(base, target)
    try:
        for edit in edits:
            out = contained(target, edit["path"], exists=False)
            if out.exists() and not out.is_file():
                raise LabError(f"Cannot replace directory with file: {edit['path']}")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(edit["content"], encoding="utf-8", newline="\n")
    except Exception:
        shutil.rmtree(target)
        raise
    return changed
