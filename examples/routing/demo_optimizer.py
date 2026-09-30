"""SCRIPTED TEST FIXTURE, NOT CODEX OR AN AI OPTIMIZER.

First propose case normalization; subsequently propose an intentionally bad change
so the real controller exercises rejection and patience. Never reads heldout data.
"""
import json
from pathlib import Path
import sys

request = json.load(sys.stdin)
source = Path("app.py").read_text(encoding="utf-8")
if "text = text.casefold()" not in source:
    source = source.replace("def route(text: str) -> str:\n", "def route(text: str) -> str:\n    text = text.casefold()\n")
    hypothesis = "Case-insensitive routing should handle capitalization without changing category semantics."
else:
    source = source.replace("return label", 'return "other"')
    hypothesis = "NEGATIVE CONTROL: intentionally break routing; the controller must reject this."
json.dump({"hypothesis": hypothesis, "edits": [{"path": "app.py", "content": source}],
           "notes": "Scripted fixture to test orchestration only; no intelligence or live model is involved."}, sys.stdout)
