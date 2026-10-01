#!/usr/bin/env python3
"""Launch the bundled package, independently of source repo or working directory."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
source = root / "src"
if not (source / "codex_eval_lab" / "plugin_server.py").is_file():
    raise SystemExit("Build the distributable first: python scripts/build_plugin.py --out /a/new/directory")
sys.path.insert(0, str(source))
from codex_eval_lab.plugin_server import main
raise SystemExit(main())
