"""Executable-oracle checks, separate from expert semantic calibration.

Replaying controls establishes behavior on those controls, not label truth or
independence of implementations. Local receipts are content-bound records, not
signed identities. Only initialization executes checks; audits are read-only.
"""
from __future__ import annotations

from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time
from typing import Any

from .artifacts import collect, copy_files, hashes
from .evidence import evaluator_fingerprint, validate_criterion_results
from .process import invoke, minimal_env, substitute
from . import oracle_controls
from .util import LabError, canonical, contained, digest, finite, file_hash, read_json, relative_name, safe_name, strict_json, unknown_keys, utc_now, write_json

LIMITS = [
    "Executed controls verify finite examples, not universal correctness or production representativeness.",
    "Source origin, derivations and implementation independence are declared, not authenticated or proved.",
    "Model-authored specifications, anchors and reference code remain model-authored; agreement is not ground truth.",
    "Local trusted code can access its OS account; disposable copies are not hostile-code or network isolation.",
    "External dependencies and toolchain behavior beyond recorded identities remain operator responsibilities.",
]


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 8192 or "\x00" in value:
        raise LabError(f"Oracle {field} requires nonempty text (at most 8192 bytes)")
    return value


def oracle_files(cfg: dict) -> list[str]:
    return [cfg["oracle"]["contract"]] if cfg.get("oracle") else []


def load_contract(suite: Path, cfg: dict) -> dict:
    try:
        return _load_contract(suite, cfg)
    except (TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise LabError("Invalid executable-oracle contract fields") from exc


def _load_contract(suite: Path, cfg: dict) -> dict:
    if cfg["execution"].get("grader_env"):
        raise LabError("Executable-oracle preflight requires empty grader_env so controls and real trials use the same credential-free grader environment")
    path = contained(suite, cfg["oracle"]["contract"])
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise LabError("Oracle contract must be an ordinary JSON file of at most 5 MB")
    c = read_json(path)
    if not isinstance(c, dict):
        raise LabError("Oracle contract must be an object")
    unknown_keys(c, {"schema_version", "claim_scope", "source", "author", "reference_command", "reference_rationale", "specifications", "criteria", "measurement_metrics", "anchors", "trust_assumptions", "max_wall_time_s", "generated_controls"}, "oracle contract")
    if type(c.get("schema_version")) is not int or c["schema_version"] != 1:
        raise LabError("Oracle schema_version must be 1")
    _text(c.get("claim_scope"), "claim_scope")
    for field, kinds in (("source", {"synthetic", "project_fixtures", "production_sample"}), ("author", {"model", "human", "imported"})):
        value = c.get(field)
        if not isinstance(value, dict) or set(value) != {"kind", "reference"} or value["kind"] not in kinds:
            raise LabError(f"Invalid oracle {field} provenance")
        _text(value["reference"], field + ".reference")
    _text(c.get("reference_rationale"), "reference_rationale")
    if not isinstance(c.get("trust_assumptions"), list) or not c["trust_assumptions"]:
        raise LabError("Oracle trust assumptions must be explicit")
    for item in c["trust_assumptions"]:
        _text(item, "trust assumption")
    finite(c.get("max_wall_time_s"), "oracle.max_wall_time_s", minimum=1, maximum=300)
    declared = collect(suite, cfg["harness_paths"])
    specs = c.get("specifications")
    if not isinstance(specs, list) or not specs:
        raise LabError("Oracle requires bound specification or established-fixture source files")
    for name in specs:
        if relative_name(name) not in declared:
            raise LabError("Oracle specification is not declared in harness_paths")
    command = c.get("reference_command")
    if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x or "\x00" in x for x in command):
        raise LabError("Oracle requires an explicit reference argv")
    bound = []
    for arg in command:
        rest = arg.replace("{python}", "")
        if arg.startswith("{suite}/"):
            name = relative_name(arg[len("{suite}/"):])
            if name not in declared or name in specs:
                raise LabError("Oracle reference must use a declared implementation file")
            bound.append(name)
            rest = ""
        if "{" in rest or "}" in rest:
            raise LabError("Oracle reference allows only {python} and explicit {suite}/file paths")
    if not bound or command == cfg["execution"]["grader_command"]:
        raise LabError("Oracle reference must be distinct from the actual grader command")
    grader_files = {arg[len("{suite}/"):] for arg in cfg["execution"]["grader_command"] if arg.startswith("{suite}/")}
    if set(bound) & grader_files:
        raise LabError("Oracle reference entry point must be separate from the grader")
    criteria = c.get("criteria")
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 128:
        raise LabError("Oracle requires 1–128 deterministic criteria")
    ids, metrics = set(), set()
    gates = {x["metric"]: x["direction"] for x in [cfg["objective"], *cfg["guardrails"]]}
    for item in criteria:
        if not isinstance(item, dict) or set(item) != {"id", "metric"}:
            raise LabError("Oracle criteria require exactly id and metric")
        safe_name(item["id"])
        metric = item["metric"]
        if item["id"] in ids or metric in metrics or metric not in cfg["metrics"] or gates.get(metric) != "maximize":
            raise LabError("Oracle criteria require unique maximize gate metrics")
        if metric in {"latency_s", "cost_usd"}:
            raise LabError("Runner-owned metrics cannot be oracle criteria")
        bounds = cfg["metrics"][metric]
        if bounds.get("minimum", 0) > 0 or bounds.get("maximum", 1) < 1:
            raise LabError("Oracle criterion metrics must permit 0 and 1")
        ids.add(item["id"])
        metrics.add(metric)
    measurement = c.get("measurement_metrics", [])
    if not isinstance(measurement, list):
        raise LabError("Oracle measurement_metrics must be a list")
    for item in measurement:
        if not isinstance(item, dict) or set(item) != {"metric", "basis", "assumption"}:
            raise LabError("Measurement metrics require metric, basis and assumption")
        metric = item["metric"]
        if metric not in gates or metric in metrics or metric in {"latency_s", "cost_usd"} or item["basis"] not in {"candidate_reported", "trusted_harness"}:
            raise LabError("Invalid or duplicate oracle measurement metric")
        _text(item["assumption"], "measurement assumption")
        metrics.add(metric)
    if set(gates) - metrics - {"latency_s", "cost_usd"}:
        raise LabError("Every selection metric needs oracle coverage or an explicit measurement trust basis")
    oracle_controls.validate_policy(c)
    anchors = c.get("anchors")
    if not isinstance(anchors, list) or not 2 <= len(anchors) <= 128:
        raise LabError("Oracle requires 2–128 independently derived development anchors")
    seen, groups, positives, negatives = set(), set(), {i: set() for i in ids}, {i: set() for i in ids}
    seen_inputs = {}
    for anchor in anchors:
        if not isinstance(anchor, dict):
            raise LabError("Invalid oracle anchor")
        if set(anchor) != {"id", "group", "role", "basis", "source_ref", "derivation", "input", "expected", "output", "mutations"}:
            raise LabError("Oracle anchor requires exact source, role, derivation, input/output and mutation fields")
        safe_name(anchor["id"])
        safe_name(anchor["group"])
        if anchor["id"] in seen or anchor["role"] != "development":
            raise LabError("Oracle anchor IDs must be unique and role must be development")
        if anchor["basis"] not in {"specification_derived", "established_fixture"} or anchor["source_ref"] not in specs:
            raise LabError("Oracle anchors need specification-derived or established-fixture provenance, not model consensus")
        _text(anchor["derivation"], "anchor derivation")
        seen.add(anchor["id"])
        fingerprint = digest(anchor["input"])
        if fingerprint in seen_inputs and seen_inputs[fingerprint] != anchor["group"]:
            raise LabError("Duplicate oracle inputs must share a declared group")
        seen_inputs[fingerprint] = anchor["group"]
        groups.add(anchor["group"])
        for id_ in ids:
            positives[id_].add(anchor["group"])
        mutations = anchor["mutations"]
        if not isinstance(mutations, list) or not 1 <= len(mutations) <= 16:
            raise LabError("Each oracle anchor needs 1–16 known-wrong output mutations")
        mids = set()
        outputs = []
        for mutation in mutations:
            if not isinstance(mutation, dict) or set(mutation) != {"id", "output", "fails"}:
                raise LabError("Oracle mutations require id, output and fails")
            safe_name(mutation["id"])
            equivalent = oracle_controls.equivalent if c.get("generated_controls") else lambda a, b: a == b
            if mutation["id"] in mids or mutation["id"] in {"reference", "positive"} or equivalent(mutation["output"], anchor["output"]):
                raise LabError("Oracle mutations must be distinct from correct outputs and uniquely named")
            if c.get("generated_controls") and any(equivalent(mutation["output"], other) for other in outputs):
                raise LabError("Generated exact-JSON controls require distinct declared mutation outputs")
            outputs.append(mutation["output"])
            mids.add(mutation["id"])
            if not isinstance(mutation["fails"], list) or not mutation["fails"] or any(i not in ids for i in mutation["fails"]):
                raise LabError("Oracle mutations must identify criteria that must fail")
            for id_ in mutation["fails"]:
                negatives[id_].add(anchor["group"])
    if len(groups) < 2 or any(len(positives[i]) < 2 or len(negatives[i]) < 2 for i in ids):
        raise LabError("Every oracle criterion needs positive and negative controls in at least two declared groups")
    # Count incrementally instead of materializing a possibly over-budget matrix.
    anchor_calls = 0
    for anchor in anchors:
        anchor_calls += 2 + len(anchor["mutations"])
        if c.get("generated_controls"):
            generated, _ = oracle_controls.generate(anchor, c["generated_controls"])
            anchor_calls += len(generated)
        if anchor_calls > 1000:
            raise LabError("Oracle preflight exceeds 1000 calls")
    # Reusable development anchors cannot be relabeled as untouched private cases.
    from .config import load_cases, make_splits
    cases = load_cases(suite, cfg)
    if anchor_calls + 2 * len(cases) > 1000:
        raise LabError("Combined anchor and all-case oracle preflight exceeds 1000 calls")
    if any(case["assets"] for case in cases):
        raise LabError("Executable-oracle consistency currently supports JSON-only cases without file assets; use an independently validated task-specific path for artifact outcomes")
    split = make_splits(cases, cfg["seed"])
    private_ids = set(split["validation"] + split["test"])
    private = [case for case in cases if case["id"] in private_ids]
    if any(a["id"] in private_ids or a["group"] in {p["group"] for p in private}
           or digest(a["input"]) in {digest(p["input"]) for p in private} for a in anchors):
        raise LabError("Oracle development controls overlap private evaluation cases")
    return c


def binding(suite: Path, cfg: dict, contract: dict) -> str:
    from .config import load_cases
    return digest({"evaluator": evaluator_fingerprint(suite, cfg), "contract": contract,
                   "cases": load_cases(suite, cfg)})


def requests(contract: dict, cases: list[dict] | None = None, *, seed: int = 0) -> list[dict]:
    rows = []
    for anchor in contract["anchors"]:
        reference = {"schema_version": 1, "case_id": anchor["id"], "input": anchor["input"], "seed": 0, "rep": 0, "assets": []}
        rows.append({"id": anchor["id"] + ":reference", "kind": "reference", "request": reference, "expected_output": anchor["output"]})
        grade = {"schema_version": 1, "case_id": anchor["id"], "input": anchor["input"], "expected": anchor["expected"], "output": anchor["output"], "trace": None, "rep": 0, "seed": 0}
        rows.append({"id": anchor["id"] + ":positive", "kind": "grader", "request": grade, "fails": []})
        for mutation in anchor["mutations"]:
            rows.append({"id": anchor["id"] + ":" + mutation["id"], "kind": "grader", "request": {**grade, "output": mutation["output"]}, "fails": mutation["fails"]})
        if contract.get("generated_controls"):
            generated, _ = oracle_controls.generate(anchor, contract["generated_controls"])
            for index, control in enumerate(generated):
                rows.append({"id": anchor["id"] + f":generated:{index:03d}", "kind": "grader",
                             "request": {**grade, "output": control["output"]}, "fails": control["fails"],
                             "generated_family": control["family"], "preserve_output_order": True,
                             "output_encoding_sha256": control["output_encoding_sha256"]})
    for case in cases or []:
        # This is private controller validation of the instrument, not candidate
        # evaluation or proposer feedback. No expected value reaches the reference.
        reference = {"schema_version": 1, "case_id": case["id"], "input": case["input"],
                     "seed": int(digest({"seed": seed, "id": case["id"], "rep": 0})[:8], 16), "rep": 0, "assets": []}
        reference_id = "case:" + case["id"] + ":reference"
        rows.append({"id": reference_id, "kind": "case_reference", "request": reference})
        rows.append({"id": "case:" + case["id"] + ":consistency", "kind": "grader", "source_result_id": reference_id,
                     "request": {key: value for key, value in {**reference, "expected": case["expected"], "trace": None}.items() if key != "assets"}, "fails": []})
    return rows


def all_requests(suite: Path, cfg: dict, contract: dict) -> list[dict]:
    from .config import load_cases
    return requests(contract, load_cases(suite, cfg), seed=cfg["seed"])


def actual_request(row: dict, responses: dict) -> dict:
    request = dict(row["request"])
    if row.get("source_result_id"):
        source = responses.get(row["source_result_id"])
        if not isinstance(source, dict) or "output" not in source:
            raise LabError("Missing reference response for case-consistency check")
        request["output"] = source["output"]
        request["trace"] = source.get("trace")
    return request


def check_response(row: dict, value: Any, contract: dict, cfg: dict) -> None:
    from .engine import response_object
    response_object(value, grader=row["kind"] == "grader")
    if value["usage"]["cost_usd"] != 0:
        raise LabError("Oracle preflight only supports explicitly free local reference and grader checks; reported cost was nonzero")
    if row["kind"] in {"reference", "case_reference"}:
        same = oracle_controls.equivalent if contract.get("generated_controls") else lambda a, b: canonical(a) == canonical(b)
        if row["kind"] == "reference" and not same(value["output"], row["expected_output"]):
            raise LabError("Independent reference disagrees with a source-derived anchor")
        return
    from .engine import validate_grader_metrics
    criteria = contract["criteria"]
    validate_grader_metrics(value, cfg, contract=criteria)
    for item in criteria:
        result = value["criterion_results"][item["id"]]
        expected = "fail" if item["id"] in row["fails"] else "pass"
        if result["status"] != expected or value["metrics"].get(item["metric"]) != (1 if expected == "pass" else 0):
            raise LabError("Oracle grader does not distinguish a positive or known-wrong negative control")


def toolchain(suite: Path, contract: dict, cfg: dict) -> dict:
    executables = {}
    for command in (contract["reference_command"], cfg["execution"]["grader_command"]):
        launcher = command[0].replace("{python}", sys.executable)
        if launcher.startswith("{suite}/"):
            name = relative_name(launcher[len("{suite}/"):])
            key, path = "{suite}/" + name, contained(suite, name)
        else:
            resolved = shutil.which(launcher)
            if not resolved:
                raise LabError("Oracle launcher is unavailable")
            path = Path(resolved)
            key = str(path.resolve())
        # Two roles commonly use the same interpreter. Resolve and validate each
        # role, but read that executable once within this verification boundary.
        # This dictionary is local: every later toolchain call hashes fresh bytes.
        if key not in executables:
            executables[key] = file_hash(path)
    return {"python": platform.python_version(), "platform": platform.platform(), "executables_sha256": executables}


def validate_receipt(suite: Path, cfg: dict, receipt: dict) -> dict:
    c = load_contract(suite, cfg)
    if not isinstance(receipt, dict) or receipt.get("binding") != binding(suite, cfg, c):
        raise LabError("Oracle receipt is missing or stale; start a new experiment")
    if receipt.get("status") != "completed" or receipt.get("environment") != toolchain(suite, c, cfg):
        raise LabError("Oracle preflight incomplete or toolchain identity changed")
    expected = all_requests(suite, cfg, c)
    rows = receipt.get("results")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise LabError("Oracle receipt is incomplete")
    responses = {}
    for request, actual in zip(expected, rows):
        if not isinstance(actual, dict) or actual.get("id") != request["id"] or actual.get("request_sha256") != digest(request) or actual.get("status") != "ok":
            raise LabError("Oracle receipt has missing, changed or failed controls")
        if actual.get("actual_request_sha256") != digest(actual_request(request, responses)):
            raise LabError("Oracle executed request does not match the bound reference output and case data")
        try:
            check_response(request, actual.get("response"), c, cfg)
        except LabError:
            if request["kind"] == "case_reference" or request.get("source_result_id"):
                raise LabError("Private case-consistency receipt could not be verified") from None
            raise
        responses[request["id"]] = actual["response"]
    return {"configured": True, "ready": True, "status": "executable_checks_passed", "evidence_basis": "executable_oracle_validated",
            "human_reviewed": False, "author_kind": c["author"]["kind"], "source_kind": c["source"]["kind"],
            "claim_scope": c["claim_scope"], "source": c["source"], "author": c["author"],
            "binding": receipt["binding"], "receipt_sha256": digest(receipt), "controls": len(rows), "anchor_control_calls": len(requests(c)),
            "case_consistency_cases": (len(rows) - len(requests(c))) // 2, "case_consistency_status": "all_frozen_cases_passed",
            "private_case_receipts": True,
            "control_coverage": oracle_controls.coverage_summary(c),
            "criteria_contract": [{**x, "kind": "deterministic"} for x in c["criteria"]],
            "measurement_metrics": c.get("measurement_metrics", []), "trust_assumptions": c["trust_assumptions"], "limitations": LIMITS}


def preflight(suite: Path, cfg: dict, output: Path, store, *, expires_at: float) -> dict:
    """Called only after execution authorization, with a durable receipt path.

    Failures keep raw records. Pending attempts are not silently retried. This is
    local trusted-code execution, not a service for remote arbitrary commands.
    """
    if output.exists():
        raise LabError("Oracle preflight receipt already exists; preserve it and use a new experiment")
    if store.budget()["trials"] or store.budget()["optimizer_calls"]:
        raise LabError("Oracle preflight requires a fresh execution ledger; prior attempts cannot be replayed")
    c = load_contract(suite, cfg)
    receipt = {"schema_version": 1, "binding": binding(suite, cfg, c), "started": utc_now(),
               "environment": toolchain(suite, c, cfg),
               "results": [], "status": "running", "limitations": LIMITS}
    write_json(output, receipt)
    deadline = time.monotonic() + min(c["max_wall_time_s"], expires_at - time.time())
    files = collect(suite, cfg["harness_paths"])
    responses = {}
    for row in all_requests(suite, cfg, c):
        if not store.reserve("oracle-preflight", "oracle", row["id"], 0, cfg["budget"]):
            raise LabError("Oracle control already exists in the ledger; no replay permitted")
        request = actual_request(row, responses)
        result = {"id": row["id"], "request_sha256": digest(row), "actual_request_sha256": digest(request), "status": "pending"}
        receipt["results"].append(result)
        write_json(output, receipt)  # reserve before executable code
        try:
            with tempfile.TemporaryDirectory(prefix="eval-oracle-") as tmp:
                root = Path(tmp)
                work, artifacts = root / "suite", root / "outputs"
                before = copy_files(files, work)
                artifacts.mkdir()
                command = c["reference_command"] if row["kind"] in {"reference", "case_reference"} else cfg["execution"]["grader_command"]
                timeout = min(cfg["execution"]["grader_timeout_s"], deadline - time.monotonic())
                if timeout <= 0:
                    raise LabError("Oracle preflight wall-time limit reached")
                execution_request = {**request, "artifacts_dir": str(artifacts)}
                # Default transport sorts keys. Preserve generated control order
                # explicitly or the positive metamorphic probe would be erased.
                encoding = {}
                if row.get("preserve_output_order"):
                    if digest(oracle_controls.encoded(request["output"])) != row["output_encoding_sha256"]:
                        raise LabError("Generated oracle output encoding does not match its bound request")
                    encoding["input_text"] = oracle_controls.encoded(execution_request) + "\n"
                call = invoke(substitute(command, app=root / "unavailable-app", suite=work, artifacts=artifacts),
                              execution_request, cwd=work,
                              env=minimal_env([], home=root), timeout_s=timeout,
                              max_output_bytes=min(cfg["execution"]["max_output_bytes"], 100_000), **encoding)
                result.update(response=call.value, stdout=call.stdout, stderr=call.stderr, elapsed_s=call.elapsed_s)
                if any(artifacts.iterdir()):
                    raise LabError("Executable-oracle JSON-only preflight does not support reference/grader output artifacts")
                if hashes(work) != before:
                    raise LabError("Oracle check changed its source copy; build/import caches must be outside the snapshot")
                check_response(row, call.value, c, cfg)
                result["status"] = "ok"
        except BaseException as exc:
            result.update(status="error", error=str(exc), elapsed_s=getattr(exc, "elapsed_s", result.get("elapsed_s")), stdout=getattr(exc, "stdout", result.get("stdout", "")), stderr=getattr(exc, "stderr", result.get("stderr", "")))
            receipt.update(status="failed", finished=utc_now())
            charged = cfg["budget"]["trial_reserve_usd"]
            value = result.get("response", {})
            if not value and result.get("stdout"):
                try:
                    value = strict_json(result["stdout"])
                except LabError:
                    value = {}
            try:
                charged = max(charged, finite(value.get("usage", {}).get("cost_usd"), "oracle cost", minimum=0))
            except (LabError, TypeError, AttributeError):
                pass
            result["charged_usd"] = charged
            store.complete("oracle-preflight", "oracle", row["id"], 0, result, charged)
            write_json(output, receipt)
            if row["kind"] == "case_reference" or row.get("source_result_id"):
                raise LabError("Private case-consistency preflight failed; inspect the controller-private receipt. No candidate search was started.") from None
            raise
        responses[row["id"]] = result["response"]
        result["charged_usd"] = 0.0
        store.complete("oracle-preflight", "oracle", row["id"], 0, result, 0.0)
        write_json(output, receipt)
    if binding(suite, cfg, load_contract(suite, cfg)) != receipt["binding"]:
        receipt["status"] = "stale"
        write_json(output, receipt)
        raise LabError("Oracle sources changed during preflight")
    receipt.update(status="completed", finished=utc_now())
    write_json(output, receipt)
    return validate_receipt(suite, cfg, receipt)
