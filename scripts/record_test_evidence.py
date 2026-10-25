"""Run the project's automated checks and record their actual results.

Writes docs/validation/test-evidence.json, which the Validation Center shows
under "Test evidence". Every number comes from the command's own output; a
suite that cannot run is recorded as NOT_RUN with the reason, never as passed.

Usage (from the repository root):
    .venv/Scripts/python.exe scripts/record_test_evidence.py [--skip-build]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "validation" / "test-evidence.json"
TEST_ENV = {
    "ENVIRONMENT": "test",
    "SECRET_KEY": "test-only-secret-key-at-least-32-characters",
    "DEV_SEED_ENABLED": "false",
}


def git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def run(command: list[str], env: dict[str, str] | None = None, timeout: int = 1800) -> tuple[int | None, str, float]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=timeout, env={**os.environ, **(env or {})})
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc), time.perf_counter() - started
    return completed.returncode, completed.stdout + completed.stderr, time.perf_counter() - started


def display(command: list[str]) -> str:
    return " ".join(Path(part).name if index == 0 else part for index, part in enumerate(command))


def not_run(name: str, command: str, reason: str) -> dict:
    return {"name": name, "command": command, "result": "NOT_RUN", "passed": None, "failed": None, "skipped": None, "duration_seconds": None, "detail": reason}


def backend_suite() -> dict:
    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        return not_run("Backend (pytest)", "pytest backend/tests", f"{python} not found")
    with tempfile.TemporaryDirectory() as scratch:
        report = Path(scratch) / "junit.xml"
        command = [str(python), "-m", "pytest", "backend/tests", "-q", "-p", "no:cacheprovider", f"--junitxml={report}"]
        code, output, seconds = run(command, TEST_ENV)
        if code is None or not report.exists():
            return not_run("Backend (pytest)", display(command[:7]), output.strip()[-500:] or "pytest did not produce a report")
        suite = ElementTree.parse(report).getroot()
        suite = suite if suite.tag == "testsuite" else suite.find("testsuite")
        tests, failures, errors, skipped = (int(suite.get(key, 0)) for key in ("tests", "failures", "errors", "skipped"))
    return {
        "name": "Backend (pytest)", "command": display(command[:7]), "result": "PASSED" if code == 0 else "FAILED",
        "passed": tests - failures - errors - skipped, "failed": failures + errors, "skipped": skipped,
        "duration_seconds": round(seconds, 2), "detail": output.strip().splitlines()[-1] if output.strip() else None,
    }


def node_suite(name: str, arguments: list[str], timeout: int = 900) -> dict:
    npx = shutil.which("npx")
    if npx is None:
        return not_run(name, "npx " + " ".join(arguments), "npx not found on PATH")
    command = [npx, *arguments]
    code, output, seconds = run(command, timeout=timeout)
    if code is None:
        return not_run(name, display(command), output.strip()[-500:])
    entry = {"name": name, "command": display(command), "result": "PASSED" if code == 0 else "FAILED",
             "passed": None, "failed": None, "skipped": None, "duration_seconds": round(seconds, 2), "detail": None}
    if arguments[0] == "tsc":
        errors = len(re.findall(r"error TS\d+", output))
        entry.update({"failed": errors, "detail": f"{errors} type error(s)"})
    elif arguments[0] == "oxlint":
        # Without a terminal oxlint prints one line per diagnostic and no summary.
        warnings = len(re.findall(r"^\S+:\d+:\d+: warning ", output, re.MULTILINE))
        errors = len(re.findall(r"^\S+:\d+:\d+: error ", output, re.MULTILINE))
        entry.update({"failed": errors, "detail": f"{warnings} warning(s), {errors} error(s)"})
    elif arguments[0] == "vite":
        built = re.search(r"built in ([\d.]+\s*m?s)", output)
        entry["detail"] = f"built in {built.group(1)}" if built else (output.strip().splitlines() or ["no output"])[-1]
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-build", action="store_true", help="Skip the production frontend build.")
    args = parser.parse_args()

    status = git("status", "--porcelain", "--untracked-files=no")
    suites = [
        backend_suite(),
        node_suite("Frontend typecheck", ["tsc", "--noEmit", "-p", "."]),
        node_suite("Frontend lint", ["oxlint", "src", "vite.config.ts"]),
    ]
    suites.append(not_run("Frontend production build", "vite build", "Skipped with --skip-build") if args.skip_build else node_suite("Frontend production build", ["vite", "build"]))
    evidence = {
        "schema_version": "medtwin-test-evidence-1.0.0",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git("rev-parse", "HEAD"),
        "git_branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "working_tree_clean": None if status is None else status == "",
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "scope": "Software tests only. Fixtures are synthetic; no result here measures clinical or model performance.",
        "suites": suites,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    for suite in suites:
        print(f"{suite['result']:8} {suite['name']}: {suite['detail']}")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0 if all(suite["result"] in {"PASSED", "NOT_RUN"} for suite in suites) else 1


if __name__ == "__main__":
    raise SystemExit(main())
