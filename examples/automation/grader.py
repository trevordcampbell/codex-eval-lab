"""Private exact-output grader, with explicit atomic results."""
import json
import sys

request = json.load(sys.stdin)
correct = request["output"] == request["expected"]
json.dump({"metrics": {"accuracy": int(correct)},
           "criterion_results": {"route": {"status": "pass" if correct else "fail",
                                            "explanation": "Exact class match" if correct else "Incorrect routing class"}},
           "usage": {"cost_usd": 0}, "model": "deterministic-exact-match-v1"}, sys.stdout)
