#!/usr/bin/env python3
"""Validate packaged local plugin structure, exact launcher, and byte manifest.

This project check complements (does not replace) current host schema validation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tomllib


def validate(root: Path) -> dict:
    root = root.resolve()
    required = {"plugin.json", "mcp.json", ".mcp.json", ".codex-plugin/plugin.json", "scripts/mcp_server.py",
                "src/codex_eval_lab/plugin_server.py", "src/codex_eval_lab/ui/app.js", "PLUGIN_MANIFEST.json"}
    for name in required:
        path = root / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing or unsafe plugin component: {name}")
    portable = json.loads((root / "plugin.json").read_text())
    compat = json.loads((root / ".codex-plugin/plugin.json").read_text())
    package = tomllib.loads((root / "pyproject.toml").read_text())
    if portable["name"] != root.name or portable["name"] != compat["name"]:
        raise ValueError("Plugin directory and manifest names must match")
    if portable["version"] != compat["version"] or portable["version"] != package["project"]["version"]:
        raise ValueError("Plugin/package version mismatch")
    if (root / ".app.json").exists():
        raise ValueError("This local plugin must not imply registered remote apps")
    for file in ("mcp.json", ".mcp.json"):
        config = json.loads((root / file).read_text())
        server = config["mcpServers"]["eval_lab"]
        if server["command"] != "python3" or server["args"] != ["${PLUGIN_ROOT}/scripts/mcp_server.py"] or server["cwd"] != "${PLUGIN_ROOT}":
            raise ValueError("Unexpected plugin launcher configuration")
    manifest = json.loads((root / "PLUGIN_MANIFEST.json").read_text())
    for name, expected in manifest["files"].items():
        path = root / name
        if not path.resolve().is_relative_to(root) or path.is_symlink() or not path.is_file():
            raise ValueError("Invalid manifest path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Plugin checksum mismatch: {name}")
    result = subprocess.run([sys.executable, str(root / "scripts/mcp_server.py"), "--check"],
                            cwd=root.parent, capture_output=True, text=True,
                            env={"PATH": str(Path(sys.executable).parent)}, timeout=20)
    if result.returncode or json.loads(result.stdout).get("packets") != []:
        raise ValueError("Relocated no-scope launcher smoke test failed: " + result.stderr)
    return {"valid": True, "name": portable["name"], "version": portable["version"],
            "files": len(manifest["files"]), "scope": "structure, checksums, relocated launcher; host UI installation unverified"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.plugin), indent=2))
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
