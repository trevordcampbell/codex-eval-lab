"""Bounded JSON subprocess protocol; no shell interpolation or implicit retries."""
from __future__ import annotations

import contextlib
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

from .util import LabError, canonical, strict_json


@dataclass
class ProcessResult:
    value: Any
    stdout: str
    stderr: str
    elapsed_s: float
    returncode: int


class ProcessFailure(LabError):
    def __init__(self, message: str, *, stdout: str = "", stderr: str = "", elapsed_s: float = 0):
        super().__init__(message)
        self.stdout, self.stderr, self.elapsed_s = stdout, stderr, elapsed_s


def minimal_env(names: list[str], *, home: Path | None = None) -> dict[str, str]:
    result = {"PATH": os.environ.get("PATH", os.defpath), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
    for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP"):
        if key in os.environ:
            result[key] = os.environ[key]
    if home is not None:
        result["HOME"] = str(home)
        result["USERPROFILE"] = str(home)
    for key in names:
        if key not in os.environ:
            raise LabError(f"Explicitly requested environment variable is not set: {key}")
        result[key] = os.environ[key]
    return result


def substitute(command: list[str], *, app: Path, suite: Path, artifacts: Path, docker: bool = False) -> list[str]:
    values = {"{python}": "python3" if docker else sys.executable,
              "{app}": "/app" if docker else str(app), "{suite}": str(suite),
              "{artifacts}": "/artifacts" if docker else str(artifacts)}
    expanded = []
    for argument in command:
        for marker, value in values.items():
            argument = argument.replace(marker, value)
        expanded.append(argument)
    return expanded


def docker_argv(command: list[str], app: Path, artifacts: Path, cfg: dict[str, Any]) -> list[str]:
    if not shutil.which("docker"):
        raise LabError("Docker is not installed; refusing to silently fall back to local execution")
    for path in (app, artifacts):
        if "," in str(path):
            raise LabError("Docker mount paths cannot contain commas")
    argv = ["docker", "run", "--rm", "--interactive", "--network=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=128",
            "--memory", str(cfg.get("docker_memory", "1g")), "--cpus", str(cfg.get("docker_cpus", 1)),
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m", "--workdir", "/app",
            "--mount", f"type=bind,src={app},dst=/app,readonly",
            "--mount", f"type=bind,src={artifacts},dst=/artifacts"]
    if hasattr(os, "getuid"):
        argv += ["--user", f"{os.getuid()}:{os.getgid()}"]
    for key in cfg["app_env"]:
        argv += ["--env", key]
    argv += ["--env", "PYTHONDONTWRITEBYTECODE=1", str(cfg["docker_image"])] + command
    return argv


def terminate(proc: subprocess.Popen[Any]) -> None:
    if os.name == "posix":
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
    else:
        # Windows descendant isolation is not guaranteed by this fallback.
        with contextlib.suppress(OSError):
            proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=5)


def invoke(command: list[str], request: Any, *, cwd: Path, env: dict[str, str], timeout_s: float,
           max_output_bytes: int = 2_000_000, parse_json: bool = True,
           input_text: str | None = None) -> ProcessResult:
    """Execute argv with bounded disk-backed output and kill its process group on POSIX."""
    if not command or any(not isinstance(a, str) or "\x00" in a for a in command):
        raise LabError("Invalid subprocess argv")
    begin = time.monotonic()
    with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        stdin.write((input_text if input_text is not None else canonical(request) + "\n").encode("utf-8"))
        stdin.seek(0)
        try:
            proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=stdin, stdout=stdout,
                                    stderr=stderr, shell=False, start_new_session=(os.name == "posix"))
        except OSError as exc:
            raise ProcessFailure(f"Cannot start {command[0]}: {exc}") from exc
        reason = None
        try:
            while proc.poll() is None:
                if time.monotonic() - begin > timeout_s:
                    reason = f"Process timed out after {timeout_s:g}s"
                    break
                if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > max_output_bytes:
                    reason = f"Process output exceeded {max_output_bytes} bytes"
                    break
                time.sleep(.01)
            if reason:
                terminate(proc)
            proc.wait()
        except BaseException:
            terminate(proc)
            raise
        elapsed = time.monotonic() - begin
        size = os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size
        stdout.seek(0)
        stderr.seek(0)
        out = stdout.read(max_output_bytes).decode("utf-8", errors="replace")
        err = stderr.read(max_output_bytes).decode("utf-8", errors="replace")
        if size > max_output_bytes:
            reason = f"Process output exceeded {max_output_bytes} bytes"
        if reason or proc.returncode:
            raise ProcessFailure(reason or f"Process exited {proc.returncode}", stdout=out, stderr=err, elapsed_s=elapsed)
        try:
            value = strict_json(out) if parse_json else None
        except LabError as exc:
            raise ProcessFailure(str(exc), stdout=out, stderr=err, elapsed_s=elapsed) from exc
        return ProcessResult(value, out, err, elapsed, proc.returncode)
