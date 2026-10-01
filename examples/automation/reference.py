"""Separate, model-authored reference for the written synthetic routing policy."""
import json
import sys

request = json.load(sys.stdin)
text = request["input"]["text"].casefold()
# Deliberately separate from the application implementation. Shared assumptions
# remain declared; different code is not evidence of independent domain truth.
found = {word: word in text for word in ["invoice", "crash", "tracking"]}
answer = "billing" if found["invoice"] else "technical" if found["crash"] else "shipping" if found["tracking"] else "other"
json.dump({"output": answer, "usage": {"cost_usd": 0}, "model": "synthetic-reference-v1"}, sys.stdout)
