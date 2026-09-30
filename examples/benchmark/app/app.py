"""An intentionally quadratic order-preserving deduplication implementation."""
import json
import statistics
import sys
import time


def unique(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


if __name__ == "__main__":
    request = json.load(sys.stdin)
    values = request["input"]["values"]
    unique(values)  # unmeasured warmup
    timings = []
    for _ in range(7):
        start = time.perf_counter_ns()
        output = unique(values)
        timings.append((time.perf_counter_ns() - start) / 1_000_000)
    json.dump({"output": {"values": output, "kernel_ms": statistics.median(timings)},
               "usage": {"cost_usd": 0}, "model": "python-kernel"}, sys.stdout)
