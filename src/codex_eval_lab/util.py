"""Strict serialization, safe paths, durable writes, and cooperative locking."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import time
from typing import Any, Iterator


class LabError(Exception):
    """An actionable, user-facing configuration or execution error."""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def strict_json(text: str) -> Any:
    def constant(value: str) -> Any:
        raise LabError(f"Non-finite JSON constant: {value}")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise LabError(f"Duplicate JSON key: {key}")
            obj[key] = value
        return obj

    try:
        return json.loads(text, parse_constant=constant, object_pairs_hook=unique)
    except (ValueError, RecursionError) as exc:
        raise LabError(f"Invalid JSON: {exc}") from exc


def read_json(path: Path) -> Any:
    try:
        return strict_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LabError(f"Cannot read {path}: {exc}") from exc


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path: Path, obj: Any) -> None:
    atomic_text(path, json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def finite(value: Any, name: str, *, minimum: float | None = None,
           maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LabError(f"{name} must be a finite number, not {type(value).__name__}")
    val = float(value)
    if not math.isfinite(val):
        raise LabError(f"{name} must be finite")
    if minimum is not None and val < minimum:
        raise LabError(f"{name} must be >= {minimum}")
    if maximum is not None and val > maximum:
        raise LabError(f"{name} must be <= {maximum}")
    return val


def integer(value: Any, name: str, *, minimum: int = 1, maximum: int = 10**9) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise LabError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return value


def safe_name(name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name):
        raise LabError("Names must use 1–80 ASCII letters, digits, underscores, dots, or hyphens")
    return name


def relative_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name or any(ord(c) < 32 for c in name):
        raise LabError(f"Unsafe relative path: {name!r}")
    p = PurePosixPath(name)
    if p.is_absolute() or any(part in ("..", ".git") for part in p.parts) or ":" in name:
        raise LabError(f"Unsafe relative path: {name!r}")
    if p.as_posix() == ".":
        raise LabError("Explicit file/directory paths required; '.' is not a source allowlist")
    return p.as_posix()


def contained(root: Path, name: str, *, exists: bool = True) -> Path:
    rel = relative_name(name)
    root = root.resolve()
    candidate = root / rel
    cursor = candidate
    while cursor != root:
        if cursor.is_symlink():
            raise LabError(f"Symlinks are not allowed: {cursor}")
        cursor = cursor.parent
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise LabError(f"Path escapes root: {name}")
    if exists and not resolved.exists():
        raise LabError(f"Missing file: {resolved}")
    return resolved


def unknown_keys(obj: dict[str, Any], allowed: set[str], context: str) -> None:
    extra = set(obj) - allowed
    if extra:
        raise LabError(f"Unknown {context} keys: {', '.join(sorted(extra))}")


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


@contextlib.contextmanager
def experiment_lock(state: Path) -> Iterator[None]:
    """Cooperative lock. A stale lock is never silently stolen."""
    lock = state / ".lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise LabError(f"Experiment locked: {lock}. Check the owner; use unlock only when no run is active.") from exc
    try:
        write_json(lock / "owner.json", {"pid": os.getpid(), "started": utc_now()})
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            (lock / "owner.json").unlink()
        with contextlib.suppress(FileNotFoundError):
            lock.rmdir()
