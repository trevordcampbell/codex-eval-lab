"""Private evaluator. Only this process receives the expected label."""
import json
import sys

request = json.load(sys.stdin)
correct = request["output"] == request["expected"]
json.dump({"metrics": {"accuracy": int(correct)},
           "explanation": "Exact class match" if correct else "Incorrect routing class",
           "usage": {"cost_usd": 0}, "model": "deterministic-exact-match-v1"}, sys.stdout)
