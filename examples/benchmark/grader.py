import json
import math
import sys

r = json.load(sys.stdin)
out = r["output"]
correct = isinstance(out, dict) and out.get("values") == r["expected"]
# Measure the kernel, not Python process startup; report correctness separately.
json.dump({"metrics": {"correctness": int(correct), "kernel_ms": out["kernel_ms"]},
           "explanation": "Exact ordered output plus median of seven warm kernel timings",
           "usage": {"cost_usd": 0}}, sys.stdout)
