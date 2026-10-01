#!/usr/bin/env python3
"""Build a self-contained local plugin, deterministic ZIP, and SHA-256 manifest.

No installation, marketplace modification, provider call or public registration.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(root: Path, out: Path) -> dict:
    root, out = Path(root).resolve(), Path(out).absolute()
    if out.exists():
        raise ValueError("Plugin build destination exists; choose a new directory")
    if any(p.is_symlink() for p in (out, *out.parents)):
        raise ValueError("Plugin output must not contain symlinks")
    template = root / "plugin" / "codex-eval-lab"
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    planned: list[tuple[Path, Path]] = []
    for directory, extensions in [(template, {".json", ".py"}), (root / "src", {".py", ".html", ".js", ".css", ".txt"}), (root / "skills", {".md", ".json", ".py", ".txt", ".toml", ".yaml"}), (root / "docs", {".md", ".html", ".json", ".txt", ".svg"}), (root / "examples", {".md", ".py", ".toml", ".json", ".jsonl", ".txt", ".rs"}), (root / "scripts", {".py"}), (root / "requirements", {".txt"})]:
        for file in sorted(directory.rglob("*")):
            if "__pycache__" in file.parts or "node_modules" in file.parts:
                continue
            if file.is_symlink():
                raise ValueError(f"Plugin sources must not contain symlinks: {file}")
            if not file.is_file() or file.suffix not in extensions:
                continue
            relative = file.relative_to(template) if directory == template else file.relative_to(root)
            planned.append((file, relative))
    for name in ("pyproject.toml", "README.md", "LICENSE", "SECURITY.md", "AGENTS.md", "CONTRIBUTING.md", "CHANGELOG.md"):
        file = root / name
        if file.is_symlink():
            raise ValueError("Plugin sources must not contain symlinks")
        planned.append((file, Path(name)))
    # Read all selected sources before writing any partial build.
    payloads = {str(relative): file.read_bytes() for file, relative in planned}
    for key in ("plugin.json", ".codex-plugin/plugin.json"):
        if json.loads(payloads[key])["version"] != version:
            raise ValueError("Plugin and Python package versions must match")
    if not any(k.startswith("skills/") and k.endswith("SKILL.md") for k in payloads):
        raise ValueError("Plugin requires bundled skills")
    catalog = out / "catalog"
    target = catalog / "plugins" / "codex-eval-lab"
    target.mkdir(parents=True)
    for relative, payload in payloads.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    manifest = {"schema_version": 1, "name": "codex-eval-lab", "version": version,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())}}
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    (target / "PLUGIN_MANIFEST.json").write_bytes(manifest_bytes)
    payloads["PLUGIN_MANIFEST.json"] = manifest_bytes
    marketplace = {"name": "codex-eval-lab-local", "interface": {"displayName": "Codex Eval Lab local"},
                   "plugins": [{"name": "codex-eval-lab", "source": {"source": "local", "path": "./plugins/codex-eval-lab"},
                                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}, "category": "Productivity"}]}
    marketplace_bytes = (json.dumps(marketplace, indent=2) + "\n").encode()
    marketplace_path = catalog / ".agents" / "plugins" / "marketplace.json"
    marketplace_path.parent.mkdir(parents=True)
    marketplace_path.write_bytes(marketplace_bytes)
    archive = out / f"codex-eval-lab-plugin-v{version}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
        archive_files = {"plugins/codex-eval-lab/" + name: data for name, data in payloads.items()}
        archive_files[".agents/plugins/marketplace.json"] = marketplace_bytes
        for name, data in sorted(archive_files.items()):
            entry = zipfile.ZipInfo("codex-eval-lab-local/" + name, (2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            zipped.writestr(entry, data)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / (archive.name + ".sha256")).write_text(f"{sha}  {archive.name}\n")
    return {"plugin": str(target), "catalog": str(catalog), "archive": str(archive), "sha256": sha, "files": len(payloads)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(ROOT, args.out), indent=2))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
