"""Running isolated NLP environments inside WSL (Ubuntu) from the Windows backend.

spaCy's native extensions are blocked by Windows Smart App Control on this host, so the spaCy-based
tools (scispaCy, medSpaCy, MedCAT) run in user-space virtual environments under ~/.medtwin in WSL.
A tool set to "auto" runs when this is Windows and its environment exists; elsewhere (Linux
servers, Vercel, the test suite) it stays off.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from functools import lru_cache
from pathlib import Path


def distro() -> str:
    return os.getenv("MEDTWIN_WSL_DISTRO", "Ubuntu")


def wsl_path(path: Path) -> str:
    drive, rest = path.drive.rstrip(":").lower(), path.as_posix().split(":", 1)[-1]
    return f"/mnt/{drive}{rest}"


def _shell_path(value: str) -> str:
    """A path for 'bash -lc': shell-quoted, except that a leading ~/ still expands to the home directory."""
    if value.startswith("~/"):
        return '"$HOME"/' + shlex.quote(value[2:])
    return shlex.quote(value)


def command(python: str, worker: Path) -> list[str]:
    return ["wsl.exe", "-d", distro(), "--", "bash", "-lc", f"{_shell_path(python)} {shlex.quote(wsl_path(worker))}"]


def failure_summary(returncode: int, stderr: str) -> str:
    """Exit status and exception type only: a worker's stderr can quote the report text it was given."""
    last = (stderr.strip().splitlines() or [""])[-1]
    match = re.match(r"([A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt))\b", last)
    return f"exited with {returncode}" + (f" ({match.group(1)})" if match else "")


def parse_payload(stdout: str, required: tuple[str, ...]) -> dict:
    """The worker's JSON reply, or ValueError when it is not a JSON object with the required keys."""
    payload = json.loads(stdout)
    if not isinstance(payload, dict) or any(key not in payload for key in required):
        raise ValueError("worker reply is missing required fields")
    return payload


@lru_cache(maxsize=None)
def environment_present(python: str) -> bool:
    """True when WSL can run the environment's interpreter (checked once per process)."""
    if os.name != "nt":
        return False
    try:
        completed = subprocess.run(["wsl.exe", "-d", distro(), "--", "bash", "-lc", f"test -x {_shell_path(python)}"],
                                   capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def enabled(setting: str, python: str) -> bool:
    """Setting "wsl" forces a tool on, "off" forces it off, "auto" (the default) follows environment_present."""
    value = setting.strip().lower()
    return value == "wsl" or (value == "auto" and environment_present(python))
