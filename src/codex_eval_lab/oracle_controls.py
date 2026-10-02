"""Bounded, opt-in adversarial probes for declared exact-JSON output contracts.

These are derived controls, not independently sourced labels. Never infer this
contract for a semantic grader. Object order and number spelling are irrelevant;
array order and the distinction between JSON booleans and numbers are relevant.
"""
from __future__ import annotations

from collections import Counter, deque
from copy import deepcopy
import json
import math
from typing import Any

from .util import LabError, canonical, digest, integer

FAMILIES = (
    "object_key_order", "number_representation", "type_mismatch", "value_change",
    "missing_field", "extra_field", "missing_item", "extra_item", "array_order",
)
POSITIVE_FAMILIES = {"object_key_order", "number_representation"}
LIMITS = [
    "Generated controls derive from the declared exact-JSON contract and anchors; they are not independent truth labels.",
    "Control counts and mutation families are finite coverage, not independent samples or a statistical reliability estimate.",
    "The probes test grader behavior, not application metamorphic correctness, source independence or semantic judgments.",
]


def validate_policy(contract: dict) -> None:
    if "generated_controls" not in contract:
        return
    policy = contract["generated_controls"]
    required = {"kind", "criterion", "numeric_equality", "max_per_anchor"}
    if not isinstance(policy, dict) or set(policy) != required:
        raise LabError("Generated controls require exactly kind, criterion, numeric_equality and max_per_anchor")
    if policy["kind"] != "exact_json" or policy["numeric_equality"] != "mathematical":
        raise LabError("Generated controls support only exact_json with mathematical numeric equality")
    criteria = contract["criteria"]
    if len(criteria) != 1 or policy["criterion"] != criteria[0]["id"]:
        raise LabError("Generated exact-JSON controls require one full-output criterion matching criterion")
    integer(policy["max_per_anchor"], "generated_controls.max_per_anchor", minimum=1, maximum=64)


def _validate_value(value: Any) -> None:
    queue = deque([(value, 0)])
    nodes = 0
    while queue:
        current, depth = queue.popleft()
        nodes += 1
        if nodes > 128 or depth > 16:
            raise LabError("Generated exact-JSON controls support at most 128 output nodes and depth 16")
        if type(current) is float and not math.isfinite(current):
            raise LabError("Generated exact-JSON controls reject nonfinite numbers")
        if type(current) not in {dict, list, str, int, float, bool, type(None)}:
            raise LabError("Generated exact-JSON controls require JSON values")
        if isinstance(current, dict):
            if any(not isinstance(key, str) for key in current):
                raise LabError("Generated exact-JSON object keys must be strings")
            queue.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            queue.extend((item, depth + 1) for item in current)
    if len(canonical(value).encode("utf-8")) > 65536:
        raise LabError("Generated exact-JSON controls support outputs of at most 65536 bytes")


def _equal(left: Any, right: Any) -> bool:
    """Typed JSON equality; caller validates values first."""
    if type(left) in {int, float} and type(right) in {int, float}:
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    return left == right


def equivalent(left: Any, right: Any) -> bool:
    """Exact-JSON contract equality, not a general-purpose semantic comparator."""
    _validate_value(left)
    _validate_value(right)
    return _equal(left, right)


def encoded(value: Any) -> str:
    """Bind representations including object order and number spelling."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _replace(output: Any, path: tuple, value: Any) -> Any:
    if not path:
        return deepcopy(value)
    result = deepcopy(output)
    target = result
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = deepcopy(value)
    return result


def generate(anchor: dict, policy: dict) -> tuple[list[dict], dict]:
    """Generate deterministic probes without changing the anchor or reading cases.

    Candidates are unique wire representations and round-robin across applicable
    families before the requested cap. Unselected coverage stays explicit.
    """
    _validate_value(anchor["output"])
    output = json.loads(canonical(anchor["output"]))
    pools = {family: [] for family in FAMILIES}
    seen = {digest(encoded(output))}
    # Do not pretend an already declared negative is fresh generated coverage.
    seen.update(digest(encoded(json.loads(canonical(row["output"])))) for row in anchor["mutations"])

    def add(family: str, path: tuple, replacement: Any) -> None:
        probe = _replace(output, path, replacement)
        is_positive = family in POSITIVE_FAMILIES
        if _equal(probe, output) != is_positive:
            return
        representation = encoded(probe)
        fingerprint = digest(representation)
        if fingerprint in seen:
            return
        seen.add(fingerprint)
        pools[family].append({"family": family, "output": probe,
                              "fails": [] if is_positive else [policy["criterion"]],
                              "output_encoding_sha256": fingerprint})

    queue = deque([((), output)])
    while queue:
        path, value = queue.popleft()
        for alternative in (None, False, True, 0, 1, "", [], {}):
            same_type = type(value) is type(alternative) or type(value) in {int, float} and type(alternative) in {int, float}
            if not same_type:
                add("type_mismatch", path, alternative)
        if isinstance(value, dict):
            keys = sorted(value)
            if len(keys) > 1:
                add("object_key_order", path, {key: value[key] for key in reversed(keys)})
            for key in keys:
                add("missing_field", path, {name: item for name, item in value.items() if name != key})
                queue.append((path + (key,), value[key]))
            extra = "__eval_extra__"
            while extra in value:
                extra += "_"
            add("extra_field", path, {**value, extra: None})
        elif isinstance(value, list):
            for index, item in enumerate(value):
                add("missing_item", path, value[:index] + value[index + 1:])
                queue.append((path + (index,), item))
            add("extra_item", path, value + [None])
            for index in range(len(value) - 1):
                swapped = value.copy()
                swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
                add("array_order", path, swapped)
        elif type(value) in {int, float}:
            add("value_change", path, 0 if value != 0 else 1)
            if type(value) is int:
                try:
                    alternative = float(value)
                except OverflowError:
                    alternative = None
                if alternative is not None and math.isfinite(alternative) and alternative == value:
                    add("number_representation", path, alternative)
            elif value.is_integer():
                add("number_representation", path, int(value))
        elif isinstance(value, str):
            add("value_change", path, value + "!")
        elif type(value) is bool:
            add("value_change", path, not value)

    available = {family: len(pool) for family, pool in pools.items()}
    selected = []
    for index in range(max(available.values(), default=0)):
        for family in FAMILIES:
            if index < len(pools[family]) and len(selected) < policy["max_per_anchor"]:
                selected.append(pools[family][index])
    selected_counts = Counter(row["family"] for row in selected)
    return selected, {"available": available, "selected": dict(selected_counts),
                      "omitted_by_cap": sum(available.values()) - len(selected),
                      "no_applicable_unique_probe": [family for family, count in available.items() if count == 0]}


def coverage_summary(contract: dict) -> dict:
    """Aggregate development-only coverage; never expose outputs or private cases."""
    if "generated_controls" not in contract:
        return {"mode": "declared_only", "generated_controls": 0,
                "limitations": ["No automated exact-JSON adversarial diversity or valid-alternative checks were requested."]}
    validate_policy(contract)
    family_counts = Counter()
    family_groups = {family: set() for family in FAMILIES}
    available_counts = Counter()
    positives = negatives = omitted = capped = 0
    for anchor in contract["anchors"]:
        rows, details = generate(anchor, contract["generated_controls"])
        omitted += details["omitted_by_cap"]
        capped += bool(details["omitted_by_cap"])
        available_counts.update(details["available"])
        for row in rows:
            family_counts[row["family"]] += 1
            family_groups[row["family"]].add(anchor["group"])
            negatives += bool(row["fails"])
            positives += not row["fails"]
    return {"mode": "generated_exact_json", "numeric_equality": "mathematical",
            "generated_controls": positives + negatives, "positive_controls": positives, "negative_controls": negatives,
            "families": {family: {"controls": family_counts[family], "declared_groups": len(family_groups[family]),
                                   "available_unique_probes": available_counts[family]} for family in FAMILIES},
            "no_applicable_unique_probe": [family for family in FAMILIES if not available_counts[family]],
            "applicable_but_unselected_families": [family for family in FAMILIES if available_counts[family] and not family_counts[family]],
            "omitted_by_cap": omitted, "capped_anchors": capped, "limitations": LIMITS}
