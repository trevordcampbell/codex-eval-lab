"""Deliberately imperfect, deterministic toy application. No model or API calls."""
import json
import sys


def route(text: str) -> str:
    for word, label in (("invoice", "billing"), ("crash", "technical"), ("tracking", "shipping")):
        if word in text:
            return label
    return "other"


if __name__ == "__main__":
    request = json.load(sys.stdin)
    answer = route(request["input"]["text"])
    json.dump({"output": answer, "usage": {"cost_usd": 0}, "model": "deterministic-router-v1",
               "trace": [{"role": "application", "content": answer}]}, sys.stdout)
