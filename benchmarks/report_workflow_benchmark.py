"""Benchmark the genuine de-identified MedTwin report workflow over HTTP.

This harness starts the canonical ``app.main:app`` against a disposable SQLite
database and upload directory. Every payload is generated synthetic text. It
measures software latency, throughput, failures, and process-tree RSS only; it
does not measure clinical or model performance.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import secrets
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import httpx
import psutil


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
BENCHMARK_SOURCE = Path(__file__).resolve()
API_PREFIX = "/api/v1"

EXPECTED_MEASUREMENT_UNITS = {
    "heart_rate": "bpm",
    "oxygen_saturation": "%",
    "hemoglobin": "g/dL",
    "glucose": "mg/dL",
    "systolic_blood_pressure": "mmHg",
    "diastolic_blood_pressure": "mmHg",
}


class WorkflowFailure(RuntimeError):
    """A request or a persisted-result validation failed at a named stage."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workflows-per-repeat",
        type=int,
        default=20,
        help="Complete case/report workflows per repeat (default: %(default)s)",
    )
    parser.add_argument(
        "--concurrency",
        nargs="+",
        default=["1", "4"],
        help="Workflow concurrency levels, separated by spaces or commas",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Fresh-server repeats per concurrency level (default: %(default)s)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=30.0,
    )
    parser.add_argument(
        "--startup-timeout-seconds",
        type=float,
        default=90.0,
    )
    parser.add_argument(
        "--rss-sample-ms",
        type=float,
        default=20.0,
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=0.25,
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Result path; defaults to a timestamped JSON under benchmarks/results",
    )
    args = parser.parse_args()

    levels: list[int] = []
    for raw in args.concurrency:
        for value in str(raw).split(","):
            levels.append(int(value.strip()))
    args.concurrency = levels

    if args.workflows_per_repeat < 1:
        parser.error("--workflows-per-repeat must be >= 1")
    if args.repeats < 1:
        parser.error("--repeats must be >= 1")
    if not levels or any(level < 1 for level in levels):
        parser.error("every concurrency level must be >= 1")
    if args.request_timeout_seconds <= 0 or args.startup_timeout_seconds <= 0:
        parser.error("timeouts must be > 0")
    if args.rss_sample_ms <= 0:
        parser.error("--rss-sample-ms must be > 0")
    if args.settle_seconds < 0:
        parser.error("--settle-seconds must be >= 0")
    return args


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_manifest() -> dict[str, Any]:
    paths = sorted(
        {
            BENCHMARK_SOURCE,
            *(BACKEND_DIR / "app").rglob("*.py"),
            *(path for path in BACKEND_DIR.glob("requirements*.txt") if path.is_file()),
        },
        key=lambda path: path.relative_to(PROJECT_ROOT).as_posix(),
    )
    entries = {
        path.relative_to(PROJECT_ROOT).as_posix(): sha256_file(path)
        for path in paths
        if path.is_file()
    }
    canonical = "".join(f"{entries[name]}  {name}\n" for name in sorted(entries))
    return {
        "algorithm": "sha256",
        "file_count": len(entries),
        "tree_manifest_sha256": sha256_bytes(canonical.encode("utf-8")),
        "files": entries,
    }


def package_versions() -> dict[str, str | None]:
    names = (
        "bcrypt",
        "fastapi",
        "httpx",
        "numpy",
        "pydantic",
        "psutil",
        "python-jose",
        "python-multipart",
        "sqlalchemy",
        "starlette",
        "torch",
        "uvicorn",
    )
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def command_output(command: list[str], timeout_seconds: float = 15.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"returncode": None, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def collect_git_state() -> dict[str, Any]:
    inside = command_output(["git", "rev-parse", "--is-inside-work-tree"])
    if inside["returncode"] != 0:
        return {"available": False, "reason": inside["stderr"] or "not a Git worktree"}
    head = command_output(["git", "rev-parse", "HEAD"])
    branch = command_output(["git", "branch", "--show-current"])
    status = command_output(["git", "status", "--porcelain=v1", "--untracked-files=normal"])
    lines = status["stdout"].splitlines() if status["stdout"] else []
    return {
        "available": True,
        "head": head["stdout"] if head["returncode"] == 0 else None,
        "head_error": head["stderr"] if head["returncode"] != 0 else None,
        "branch": branch["stdout"] or None,
        "dirty": bool(lines),
        "status_entry_count": len(lines),
        "status_sha256": sha256_bytes((status["stdout"] + "\n").encode("utf-8")),
    }


def collect_hardware() -> dict[str, Any]:
    result: dict[str, Any] = {
        "cpu_physical_count": psutil.cpu_count(logical=False),
        "cpu_logical_count": psutil.cpu_count(logical=True),
        "total_ram_bytes": int(psutil.virtual_memory().total),
        "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER"),
    }
    if os.name == "nt":
        powershell = shutil.which("powershell.exe") or shutil.which("powershell")
        if powershell:
            query = (
                "$cpu=Get-CimInstance Win32_Processor|Select-Object -First 1;"
                "$os=Get-CimInstance Win32_OperatingSystem;"
                "[pscustomobject]@{cpu_name=$cpu.Name;physical_cores=$cpu.NumberOfCores;"
                "logical_processors=$cpu.NumberOfLogicalProcessors;os_caption=$os.Caption;"
                "os_version=$os.Version;os_build=$os.BuildNumber}|ConvertTo-Json -Compress"
            )
            queried = command_output([powershell, "-NoProfile", "-Command", query])
            if queried["returncode"] == 0 and queried["stdout"]:
                try:
                    result["windows_cim"] = json.loads(queried["stdout"])
                except json.JSONDecodeError:
                    result["windows_cim_error"] = "invalid JSON"
            else:
                result["windows_cim_error"] = queried["stderr"] or "no output"
    return result


def collect_gpu() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"detected": False, "used_by_workload": False}
    queried = command_output(
        [
            executable,
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    devices: list[dict[str, Any]] = []
    if queried["returncode"] == 0:
        for line in queried["stdout"].splitlines():
            values = [value.strip() for value in line.split(",")]
            if len(values) == 3:
                devices.append(
                    {
                        "name": values[0],
                        "driver_version": values[1],
                        "memory_mib": int(values[2]) if values[2].isdigit() else values[2],
                    }
                )
    return {
        "detected": bool(devices),
        "used_by_workload": False,
        "devices": devices,
        "query_error": queried["stderr"] or None,
    }


def available_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def process_tree_rss(root_pid: int) -> tuple[int, list[int]]:
    try:
        root = psutil.Process(root_pid)
        processes = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0, []
    total = 0
    pids: list[int] = []
    seen: set[int] = set()
    for process in processes:
        if process.pid in seen:
            continue
        seen.add(process.pid)
        try:
            total += int(process.memory_info().rss)
            pids.append(process.pid)
        except psutil.Error:
            continue
    return total, sorted(pids)


class RssSampler:
    def __init__(self, root_pid: int, interval_ms: float) -> None:
        self.root_pid = root_pid
        self.interval_seconds = interval_ms / 1000.0
        self.values: list[int] = []
        self.pids: set[int] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample(self) -> None:
        rss_bytes, pids = process_tree_rss(self.root_pid)
        self.values.append(rss_bytes)
        self.pids.update(pids)

    def _run(self) -> None:
        self._sample()
        while not self._stop.wait(self.interval_seconds):
            self._sample()
        self._sample()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="report-workflow-rss", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 5))

    def summary(self, baseline_rss_bytes: int) -> dict[str, Any]:
        peak = max(self.values, default=0)
        return {
            "scope": "sum of canonical Uvicorn process and all descendants",
            "sample_interval_ms": round(self.interval_seconds * 1000, 3),
            "sample_count": len(self.values),
            "baseline_rss_bytes": baseline_rss_bytes,
            "minimum_sampled_rss_bytes": min(self.values, default=0),
            "peak_rss_bytes": peak,
            "peak_minus_baseline_bytes": max(0, peak - baseline_rss_bytes),
            "sampled_pids": sorted(self.pids),
        }


def nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def rounded(value: float | None, digits: int = 6) -> float | None:
    return round(value, digits) if value is not None else None


def synthetic_report(workflow_token: str, ordinal: int) -> tuple[bytes, dict[str, float]]:
    heart_rate = 60 + ordinal % 20
    oxygen_saturation = 95 + ordinal % 5
    hemoglobin = round(12.0 + (ordinal % 10) / 10.0, 1)
    glucose = 90 + ordinal
    systolic = 110 + ordinal % 20
    diastolic = 70 + ordinal % 10
    text = (
        "SYNTHETIC DE-IDENTIFIED RESEARCH REPORT\n"
        f"Workflow token: {workflow_token}\n"
        "FINDINGS: No pleural effusion or pneumothorax. Prior fracture is chronic.\n"
        "MEASUREMENTS:\n"
        f"Heart rate: {heart_rate} bpm.\n"
        f"Oxygen saturation: {oxygen_saturation}%.\n"
        f"Hemoglobin: {hemoglobin:.1f} g/dL.\n"
        f"Glucose: {glucose} mg/dL.\n"
        f"Blood pressure: {systolic}/{diastolic} mmHg.\n"
        "IMPRESSION: Normal sinus rhythm.\n"
        "This fixture is synthetic and contains no person name, contact detail, medical record number, or date of birth.\n"
    )
    return text.encode("utf-8"), {
        "heart_rate": float(heart_rate),
        "oxygen_saturation": float(oxygen_saturation),
        "hemoglobin": float(hemoglobin),
        "glucose": float(glucose),
        "systolic_blood_pressure": float(systolic),
        "diastolic_blood_pressure": float(diastolic),
    }


async def request_json(
    *,
    client: httpx.AsyncClient,
    stage: str,
    stage_records: list[dict[str, Any]],
    method: str,
    path: str,
    expected_status: int,
    **kwargs: Any,
) -> Any:
    started_ns = time.perf_counter_ns()
    try:
        response = await client.request(method, path, **kwargs)
    except Exception as exc:
        latency_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
        stage_records.append(
            {
                "stage": stage,
                "method": method,
                "path_template": path,
                "latency_ms": round(latency_ms, 6),
                "status_code": None,
                "response_bytes": 0,
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        raise WorkflowFailure(stage, f"HTTP exception: {type(exc).__name__}: {exc}") from exc

    latency_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
    status_ok = response.status_code == expected_status
    record = {
        "stage": stage,
        "method": method,
        "path_template": path,
        "latency_ms": round(latency_ms, 6),
        "status_code": response.status_code,
        "response_bytes": len(response.content),
        "ok": status_ok,
        "error": None,
    }
    stage_records.append(record)
    if not status_ok:
        excerpt = response.text[:500].replace("\n", " ")
        record["error"] = f"expected HTTP {expected_status}; body={excerpt}"
        raise WorkflowFailure(stage, str(record["error"]))
    try:
        return response.json()
    except ValueError as exc:
        record["ok"] = False
        record["error"] = "response was not JSON"
        raise WorkflowFailure(stage, "response was not valid JSON") from exc


def require(condition: bool, stage: str, message: str) -> None:
    if not condition:
        raise WorkflowFailure(stage, message)


async def execute_workflow(
    *,
    write_client: httpx.AsyncClient,
    reload_client: httpx.AsyncClient,
    run_tag: str,
    concurrency: int,
    repeat_index: int,
    workflow_index: int,
) -> dict[str, Any]:
    workflow_token = f"{run_tag}-c{concurrency}-r{repeat_index}-w{workflow_index:03d}"
    pseudonym = f"BENCH-{workflow_token}"
    filename = f"synthetic_{workflow_token}.txt"
    payload, expected_measurements = synthetic_report(workflow_token, workflow_index)
    expected_sha256 = sha256_bytes(payload)
    stages: list[dict[str, Any]] = []
    started_ns = time.perf_counter_ns()
    case_id: int | None = None
    examination_id: int | None = None
    upload_id: int | None = None
    job_id: int | None = None
    finding_id: int | None = None
    checks: dict[str, Any] = {}

    try:
        case = await request_json(
            client=write_client,
            stage="create_case",
            stage_records=stages,
            method="POST",
            path=f"{API_PREFIX}/cases",
            expected_status=201,
            json={
                "pseudonymous_id": pseudonym,
                "patient_ref": None,
                "description": "Synthetic de-identified HTTP benchmark case.",
            },
        )
        case_id = int(case["id"])
        require(case["pseudonymous_id"] == pseudonym, "create_case", "pseudonymous ID mismatch")

        examination = await request_json(
            client=write_client,
            stage="create_examination",
            stage_records=stages,
            method="POST",
            path=f"{API_PREFIX}/cases/{case_id}/examinations",
            expected_status=201,
            json={
                "exam_date": "2026-01-15T10:30:00Z",
                "modality": "REPORT",
                "clinical_indication": "Synthetic software benchmark only.",
            },
        )
        examination_id = int(examination["id"])
        require(int(examination["case_id"]) == case_id, "create_examination", "case ID mismatch")
        require(examination["modality"] == "REPORT", "create_examination", "modality mismatch")

        upload = await request_json(
            client=write_client,
            stage="upload_report",
            stage_records=stages,
            method="POST",
            path=f"{API_PREFIX}/cases/{case_id}/uploads",
            expected_status=201,
            files={"file": (filename, payload, "text/plain")},
            data={
                "examination_id": str(examination_id),
                "is_associated": "true",
                "deidentified": "true",
                "association_notes": "Synthetic benchmark evidence.",
            },
        )
        upload_id = int(upload["id"])
        require(int(upload["case_id"]) == case_id, "upload_report", "upload case ID mismatch")
        require(int(upload["examination_id"]) == examination_id, "upload_report", "examination ID mismatch")
        require(upload["file_hash"] == expected_sha256, "upload_report", "server SHA-256 mismatch")
        require(len(upload["file_hash"]) == 64, "upload_report", "server hash length was not 64")
        require(upload["modality"] == "REPORT", "upload_report", "upload modality mismatch")
        require(upload["is_associated"] is True, "upload_report", "upload association mismatch")

        job = await request_json(
            client=write_client,
            stage="run_analysis_job",
            stage_records=stages,
            method="POST",
            path=f"{API_PREFIX}/uploads/{upload_id}/analysis-jobs",
            expected_status=201,
        )
        job_id = int(job["id"])
        require(int(job["case_id"]) == case_id, "run_analysis_job", "job case ID mismatch")
        require(int(job["upload_id"]) == upload_id, "run_analysis_job", "job upload ID mismatch")
        require(job["status"] == "COMPLETED", "run_analysis_job", f"unexpected job status {job['status']}")
        require(
            job["model_name"] == "Rule-Based Clinical Text Baseline",
            "run_analysis_job",
            "unexpected processor identity",
        )
        require(bool(job["findings"]), "run_analysis_job", "job returned no finding")
        finding_id = int(job["findings"][0]["id"])
        require(
            job["findings"][0]["review_status"] == "PENDING_HUMAN_REVIEW",
            "run_analysis_job",
            "finding did not retain human-review state",
        )

        # A separate HTTP connection pool models an application reload reading
        # persisted state, rather than consuming in-memory objects from writes.
        reloaded_uploads = await request_json(
            client=reload_client,
            stage="reload_uploads",
            stage_records=stages,
            method="GET",
            path=f"{API_PREFIX}/cases/{case_id}/uploads",
            expected_status=200,
        )
        matching_upload = next((item for item in reloaded_uploads if int(item["id"]) == upload_id), None)
        require(matching_upload is not None, "reload_uploads", "uploaded file missing after reload")
        require(
            matching_upload["file_hash"] == expected_sha256,
            "reload_uploads",
            "persisted upload hash mismatch",
        )

        measurements = await request_json(
            client=reload_client,
            stage="reload_measurements",
            stage_records=stages,
            method="GET",
            path=f"{API_PREFIX}/cases/{case_id}/measurements",
            expected_status=200,
        )
        by_name = {item["name"]: item for item in measurements}
        for name, expected_value in expected_measurements.items():
            require(name in by_name, "reload_measurements", f"missing measurement {name}")
            observed = by_name[name]
            require(
                math.isclose(float(observed["value"]), expected_value, rel_tol=0, abs_tol=1e-9),
                "reload_measurements",
                f"measurement mismatch for {name}",
            )
            require(
                observed["unit"] == EXPECTED_MEASUREMENT_UNITS[name],
                "reload_measurements",
                f"unit mismatch for {name}: {observed['unit']}",
            )
            require(int(observed["source_file_id"]) == upload_id, "reload_measurements", "source upload mismatch")
            require(observed["source_span"], "reload_measurements", f"missing source span for {name}")

        findings = await request_json(
            client=reload_client,
            stage="reload_findings",
            stage_records=stages,
            method="GET",
            path=f"{API_PREFIX}/cases/{case_id}/findings",
            expected_status=200,
        )
        finding = next((item for item in findings if int(item["id"]) == finding_id), None)
        require(finding is not None, "reload_findings", "analysis finding missing after reload")
        require(
            finding["evidence_provenance"]["input_hash"] == expected_sha256,
            "reload_findings",
            "finding provenance hash mismatch",
        )
        require(finding["is_demo"] is False, "reload_findings", "finding was marked as demo")
        require(
            finding["calibrated_confidence"] is None,
            "reload_findings",
            "uncalibrated rule baseline returned calibrated confidence",
        )
        require(bool(finding["report_statements"]), "reload_findings", "source-linked statements missing")

        provenance = await request_json(
            client=reload_client,
            stage="reload_provenance",
            stage_records=stages,
            method="GET",
            path=f"{API_PREFIX}/cases/{case_id}/provenance",
            expected_status=200,
        )
        actions = {event["action"] for event in provenance}
        require("FILE_UPLOADED" in actions, "reload_provenance", "FILE_UPLOADED audit event missing")
        require(
            "ANALYSIS_JOB_COMPLETED" in actions,
            "reload_provenance",
            "ANALYSIS_JOB_COMPLETED audit event missing",
        )

        checks = {
            "server_sha256_matches_client": True,
            "reload_sha256_matches_client": True,
            "job_status": job["status"],
            "processor": {
                "name": job["model_name"],
                "version": job["model_version"],
                "preprocessing_version": job["preprocessing_version"],
                "clinical_performance_measured": False,
            },
            "measurement_names": sorted(by_name),
            "expected_measurements_found": sorted(expected_measurements),
            "measurement_count": len(measurements),
            "finding_count": len(findings),
            "statement_count": len(finding["report_statements"]),
            "finding_review_status": finding["review_status"],
            "calibrated_confidence": finding["calibrated_confidence"],
            "provenance_actions": sorted(actions),
        }
        ok = True
        failure_stage = None
        error = None
    except WorkflowFailure as exc:
        ok = False
        failure_stage = exc.stage
        error = str(exc)
    except Exception as exc:  # Unexpected exceptions are retained as benchmark evidence.
        ok = False
        failure_stage = "unexpected_exception"
        error = f"{type(exc).__name__}: {exc}"

    latency_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
    return {
        "workflow_index": workflow_index,
        "workflow_token": workflow_token,
        "pseudonymous_case_id": pseudonym,
        "synthetic_input": True,
        "deidentified_attestation_sent": True,
        "input_filename": filename,
        "input_size_bytes": len(payload),
        "input_sha256": expected_sha256,
        "ok": ok,
        "failure_stage": failure_stage,
        "error": error,
        "end_to_end_latency_ms": round(latency_ms, 6),
        "persisted_ids": {
            "case_id": case_id,
            "examination_id": examination_id,
            "upload_id": upload_id,
            "job_id": job_id,
            "finding_id": finding_id,
        },
        "checks": checks,
        "stages": stages,
    }


async def run_workload(
    *,
    base_url: str,
    token: str,
    run_tag: str,
    concurrency: int,
    repeat_index: int,
    workflow_count: int,
    timeout_seconds: float,
) -> tuple[list[dict[str, Any]], float]:
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "MedTwinReportWorkflowBenchmark/1.0",
    }
    limits = httpx.Limits(
        max_connections=max(2, concurrency * 2),
        max_keepalive_connections=max(2, concurrency * 2),
        keepalive_expiry=30.0,
    )
    timeout = httpx.Timeout(timeout_seconds)
    results: list[dict[str, Any] | None] = [None] * workflow_count
    next_index = 0

    async with (
        httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            limits=limits,
            follow_redirects=False,
        ) as write_client,
        httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout,
            limits=limits,
            follow_redirects=False,
        ) as reload_client,
    ):

        async def worker() -> None:
            nonlocal next_index
            while next_index < workflow_count:
                index = next_index
                next_index += 1
                results[index] = await execute_workflow(
                    write_client=write_client,
                    reload_client=reload_client,
                    run_tag=run_tag,
                    concurrency=concurrency,
                    repeat_index=repeat_index,
                    workflow_index=index,
                )

        started_ns = time.perf_counter_ns()
        await asyncio.gather(*(worker() for _ in range(concurrency)))
        wall_seconds = (time.perf_counter_ns() - started_ns) / 1_000_000_000

    return [item for item in results if item is not None], wall_seconds


def summarize_workflows(records: Sequence[dict[str, Any]], wall_seconds: float) -> dict[str, Any]:
    successes = [record for record in records if record["ok"]]
    success_latencies = [float(record["end_to_end_latency_ms"]) for record in successes]
    failures_by_stage: dict[str, int] = {}
    for record in records:
        if not record["ok"]:
            stage = str(record["failure_stage"] or "unknown")
            failures_by_stage[stage] = failures_by_stage.get(stage, 0) + 1
    stage_latencies: dict[str, list[float]] = {}
    stage_failures: dict[str, int] = {}
    for record in records:
        for stage in record["stages"]:
            name = str(stage["stage"])
            stage_latencies.setdefault(name, []).append(float(stage["latency_ms"]))
            if not stage["ok"]:
                stage_failures[name] = stage_failures.get(name, 0) + 1
    stage_summary = {
        name: {
            "sample_count": len(values),
            "mean_ms": rounded(statistics.fmean(values)),
            "p50_ms": rounded(nearest_rank(values, 0.50)),
            "p95_ms": rounded(nearest_rank(values, 0.95)),
            "max_ms": rounded(max(values)),
            "failed": stage_failures.get(name, 0),
        }
        for name, values in sorted(stage_latencies.items())
    }
    attempted = len(records)
    succeeded = len(successes)
    failed = attempted - succeeded
    input_hashes = [record["input_sha256"] for record in records]
    return {
        "attempted_workflows": attempted,
        "succeeded_workflows": succeeded,
        "failed_workflows": failed,
        "failure_rate": round(failed / attempted, 6) if attempted else None,
        "failures_by_stage": failures_by_stage,
        "wall_seconds": round(wall_seconds, 6),
        "attempted_workflow_throughput_per_second": rounded(attempted / wall_seconds, 3)
        if wall_seconds
        else None,
        "successful_workflow_throughput_per_second": rounded(succeeded / wall_seconds, 3)
        if wall_seconds
        else None,
        "successful_end_to_end_latency_ms": {
            "definition": "client-observed case creation through persisted provenance reload; nearest-rank percentiles",
            "min": rounded(min(success_latencies)) if success_latencies else None,
            "mean": rounded(statistics.fmean(success_latencies)) if success_latencies else None,
            "p50": rounded(nearest_rank(success_latencies, 0.50)),
            "p95": rounded(nearest_rank(success_latencies, 0.95)),
            "p99": rounded(nearest_rank(success_latencies, 0.99)),
            "max": rounded(max(success_latencies)) if success_latencies else None,
        },
        "unique_input_hash_count": len(set(input_hashes)),
        "all_input_hashes_unique": len(input_hashes) == len(set(input_hashes)),
        "stage_latency_ms": stage_summary,
    }


def aggregate_profile(repeats: Sequence[dict[str, Any]]) -> dict[str, Any]:
    p50_values = [
        repeat["summary"]["successful_end_to_end_latency_ms"]["p50"]
        for repeat in repeats
        if repeat["summary"]["successful_end_to_end_latency_ms"]["p50"] is not None
    ]
    p95_values = [
        repeat["summary"]["successful_end_to_end_latency_ms"]["p95"]
        for repeat in repeats
        if repeat["summary"]["successful_end_to_end_latency_ms"]["p95"] is not None
    ]
    throughput_values = [
        repeat["summary"]["successful_workflow_throughput_per_second"]
        for repeat in repeats
        if repeat["summary"]["successful_workflow_throughput_per_second"] is not None
    ]
    return {
        "repeat_count": len(repeats),
        "total_attempted_workflows": sum(repeat["summary"]["attempted_workflows"] for repeat in repeats),
        "total_succeeded_workflows": sum(repeat["summary"]["succeeded_workflows"] for repeat in repeats),
        "total_failed_workflows": sum(repeat["summary"]["failed_workflows"] for repeat in repeats),
        "p50_latency_ms_median_across_repeats": rounded(statistics.median(p50_values))
        if p50_values
        else None,
        "p95_latency_ms_median_across_repeats": rounded(statistics.median(p95_values))
        if p95_values
        else None,
        "successful_throughput_median_across_repeats": rounded(statistics.median(throughput_values), 3)
        if throughput_values
        else None,
        "maximum_process_tree_peak_rss_bytes": max(
            (repeat["memory"]["peak_rss_bytes"] for repeat in repeats),
            default=0,
        ),
        "all_temp_state_removed": all(repeat["temporary_state"]["removed"] for repeat in repeats),
    }


def wait_until_ready(
    process: subprocess.Popen[Any],
    base_url: str,
    timeout_seconds: float,
) -> float:
    started = time.perf_counter()
    deadline = started + timeout_seconds
    last_error = "no response"
    with httpx.Client(timeout=1.0) as client:
        while time.perf_counter() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Uvicorn exited during startup with code {process.returncode}")
            try:
                response = client.get(f"{base_url}/")
                if response.status_code == 200:
                    return time.perf_counter() - started
                last_error = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.1)
    raise TimeoutError(f"server was not ready after {timeout_seconds}s ({last_error})")


def stop_server(process: subprocess.Popen[Any]) -> None:
    # uv-managed Windows environments use a launcher parent plus the real
    # interpreter child. Terminating only the launcher can leave SQLite/upload
    # handles open briefly, so close the captured process tree explicitly.
    descendants: list[psutil.Process] = []
    try:
        descendants = psutil.Process(process.pid).children(recursive=True)
    except psutil.Error:
        pass
    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.Error:
            pass
    if descendants:
        _, alive = psutil.wait_procs(descendants, timeout=10)
        for child in alive:
            try:
                child.kill()
            except psutil.Error:
                pass
        if alive:
            psutil.wait_procs(alive, timeout=5)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def cleanup_temporary_directory(
    context: tempfile.TemporaryDirectory[str],
    temp_root: Path,
) -> dict[str, Any]:
    """Retry removal of the verified benchmark temp path after handle release."""
    attempts = 0
    last_error: str | None = None
    for attempts in range(1, 51):
        try:
            context.cleanup()
        except (OSError, PermissionError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.1)
            continue
        if not temp_root.exists():
            return {"removed": True, "cleanup_attempts": attempts, "cleanup_error": None}
        time.sleep(0.1)
    return {
        "removed": not temp_root.exists(),
        "cleanup_attempts": attempts,
        "cleanup_error": None if not temp_root.exists() else last_error or "path still exists",
    }


def authenticate(
    base_url: str,
    username: str,
    password: str,
    timeout_seconds: float,
) -> tuple[str, dict[str, Any]]:
    with httpx.Client(base_url=base_url, timeout=timeout_seconds) as client:
        started_ns = time.perf_counter_ns()
        response = client.post(
            f"{API_PREFIX}/auth/login",
            json={"username": username, "password": password},
        )
        latency_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
        if response.status_code != 200:
            raise RuntimeError(f"development-seed login returned HTTP {response.status_code}: {response.text[:500]}")
        token_data = response.json()
        token = token_data["access_token"]
        me = client.get(
            f"{API_PREFIX}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        if me.status_code != 200:
            raise RuntimeError(f"authenticated /me returned HTTP {me.status_code}")
        user = me.json()
        if user["username"] != username or user["role"] != "clinician":
            raise RuntimeError("environment-controlled development seed identity mismatch")
        return token, {
            "login_latency_ms": round(latency_ms, 6),
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "me_status_code": me.status_code,
        }


def sqlite_row_counts(database_path: Path) -> dict[str, int]:
    table_names = (
        "users",
        "cases",
        "examinations",
        "uploaded_files",
        "inference_runs",
        "findings",
        "clinical_report_statements",
        "medical_measurements",
        "audit_events",
    )
    counts: dict[str, int] = {}
    connection = sqlite3.connect(database_path)
    try:
        for table in table_names:
            counts[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
    finally:
        # sqlite3 connections are transactional context managers but their
        # ``with`` block does not close the Windows file handle.
        connection.close()
    return counts


def snapshot_temp_state(temp_root: Path, database_path: Path, uploads_path: Path) -> dict[str, Any]:
    files = sorted(path for path in temp_root.rglob("*") if path.is_file())
    upload_files = sorted(path for path in uploads_path.rglob("*") if path.is_file())
    row_counts: dict[str, int] = {}
    row_count_error: str | None = None
    if database_path.exists():
        try:
            row_counts = sqlite_row_counts(database_path)
        except (OSError, sqlite3.Error) as exc:
            row_count_error = f"{type(exc).__name__}: {exc}"
    return {
        "root": str(temp_root),
        "database_size_bytes": database_path.stat().st_size if database_path.exists() else None,
        "database_sha256": sha256_file(database_path) if database_path.exists() else None,
        "sqlite_row_counts": row_counts,
        "sqlite_row_count_error": row_count_error,
        "upload_file_count": len(upload_files),
        "upload_total_bytes": sum(path.stat().st_size for path in upload_files),
        "file_count_including_database_sidecars_and_log": len(files),
        "removed": False,
    }


def run_repeat(
    *,
    args: argparse.Namespace,
    run_tag: str,
    concurrency: int,
    repeat_index: int,
) -> dict[str, Any]:
    temp_context = tempfile.TemporaryDirectory(prefix="medtwin-report-benchmark-")
    temp_root = Path(temp_context.name).resolve()
    safe_parent = Path(tempfile.gettempdir()).resolve()
    if temp_root.parent != safe_parent or not temp_root.name.startswith("medtwin-report-benchmark-"):
        temp_context.cleanup()
        raise RuntimeError(f"refusing unexpected temporary path: {temp_root}")

    database_path = temp_root / "benchmark.db"
    uploads_path = temp_root / "uploads"
    log_path = temp_root / "uvicorn.log"
    uploads_path.mkdir(parents=True, exist_ok=True)
    port = available_port(args.host)
    base_url = f"http://{args.host}:{port}"
    username = "benchmark_clinician"
    password = secrets.token_urlsafe(24)
    secret_key = secrets.token_urlsafe(48)

    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "test",
            "DEBUG": "false",
            "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "UPLOAD_DIR": str(uploads_path),
            "SECRET_KEY": secret_key,
            "DEV_SEED_ENABLED": "true",
            "DEV_SEED_USERNAME": username,
            "DEV_SEED_PASSWORD": password,
            "DEV_SEED_EMAIL": "benchmark@medtwin.invalid",
            "DEV_SEED_FULL_NAME": "MedTwin Synthetic Benchmark User",
            "DEV_SEED_ROLE": "clinician",
            "DEV_SEED_CASE_ENABLED": "false",
        }
    )
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--app-dir",
        str(BACKEND_DIR),
        "--host",
        args.host,
        "--port",
        str(port),
        "--workers",
        "1",
        "--no-access-log",
        "--log-level",
        "warning",
    ]
    repeat: dict[str, Any] = {
        "repeat": repeat_index,
        "concurrency": concurrency,
        "base_url": base_url,
        "server": {
            "app": "app.main:app",
            "app_dir": str(BACKEND_DIR),
            "command": command,
            "workers": 1,
            "reload": False,
            "access_log": False,
            "environment": {
                "ENVIRONMENT": "test",
                "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
                "UPLOAD_DIR": str(uploads_path),
                "DEV_SEED_ENABLED": True,
                "DEV_SEED_USERNAME": username,
                "DEV_SEED_EMAIL": "benchmark@medtwin.invalid",
                "DEV_SEED_ROLE": "clinician",
                "DEV_SEED_CASE_ENABLED": False,
                "DEV_SEED_PASSWORD": "[generated and redacted]",
                "SECRET_KEY": "[generated and redacted]",
            },
        },
    }

    process: subprocess.Popen[Any] | None = None
    log_handle: Any = None
    sampler: RssSampler | None = None
    workload_completed = False
    try:
        log_handle = log_path.open("w", encoding="utf-8")
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        repeat["server"]["pid"] = process.pid
        repeat["server"]["startup_seconds"] = round(
            wait_until_ready(process, base_url, args.startup_timeout_seconds),
            6,
        )
        token, auth_evidence = authenticate(
            base_url,
            username,
            password,
            args.request_timeout_seconds,
        )
        repeat["authentication"] = auth_evidence
        if args.settle_seconds:
            time.sleep(args.settle_seconds)

        baseline_rss, baseline_pids = process_tree_rss(process.pid)
        repeat["server"]["process_tree_before_workload"] = baseline_pids
        sampler = RssSampler(process.pid, args.rss_sample_ms)
        sampler.start()
        records, wall_seconds = asyncio.run(
            run_workload(
                base_url=base_url,
                token=token,
                run_tag=run_tag,
                concurrency=concurrency,
                repeat_index=repeat_index,
                workflow_count=args.workflows_per_repeat,
                timeout_seconds=args.request_timeout_seconds,
            )
        )
        sampler.stop()
        repeat["workflows"] = records
        repeat["summary"] = summarize_workflows(records, wall_seconds)
        repeat["memory"] = sampler.summary(baseline_rss)
        workload_completed = True
    except Exception as exc:
        repeat["error"] = f"{type(exc).__name__}: {exc}"
        repeat["summary"] = {
            "attempted_workflows": 0,
            "succeeded_workflows": 0,
            "failed_workflows": args.workflows_per_repeat,
            "failure_rate": 1.0,
            "failures_by_stage": {"repeat_setup": args.workflows_per_repeat},
        }
        repeat["workflows"] = []
        if sampler is not None:
            sampler.stop()
            baseline_rss = repeat.get("memory", {}).get("baseline_rss_bytes", 0)
            repeat["memory"] = sampler.summary(int(baseline_rss))
    finally:
        if process is not None:
            stop_server(process)
            repeat["server"]["returncode"] = process.returncode
        if log_handle is not None:
            log_handle.flush()
            log_handle.close()
        if log_path.exists():
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            repeat["server"]["log_size_bytes"] = len(log_text.encode("utf-8"))
            repeat["server"]["log_sha256"] = sha256_bytes(log_text.encode("utf-8"))
            repeat["server"]["log_excerpt"] = log_text[-2000:]
        repeat["temporary_state"] = snapshot_temp_state(temp_root, database_path, uploads_path)
        cleanup = cleanup_temporary_directory(temp_context, temp_root)
        repeat["temporary_state"].update(cleanup)

    repeat["status"] = (
        "completed"
        if workload_completed and repeat["summary"]["failed_workflows"] == 0 and repeat["temporary_state"]["removed"]
        else "completed_with_failures"
    )
    return repeat


def default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return RESULTS_DIR / f"report-workflow-benchmark-{stamp}.json"


def main() -> int:
    args = parse_args()
    output_path = (args.output or default_output_path()).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    local_now = datetime.now().astimezone()
    run_tag = started_at.strftime("%Y%m%dT%H%M%SZ")

    report: dict[str, Any] = {
        "schema_version": "1.0.0",
        "benchmark_kind": "synthetic_deidentified_report_workflow_http",
        "clinical_performance_measured": False,
        "clinical_validation_performed": False,
        "model_accuracy_measured": False,
        "notice": (
            "Software performance and persistence checks only. Synthetic inputs do not measure "
            "clinical accuracy, model quality, diagnostic performance, or clinical effectiveness."
        ),
        "generated_at_utc": started_at.isoformat(),
        "local_timezone": {
            "name": str(local_now.tzinfo),
            "utc_offset": local_now.strftime("%z"),
        },
        "workload": {
            "canonical_app": "app.main:app",
            "transport": "same-host IPv4 loopback HTTP",
            "synthetic_data_only": True,
            "deidentified_attestation": True,
            "workflows_per_repeat": args.workflows_per_repeat,
            "concurrency_levels": args.concurrency,
            "repeats_per_concurrency": args.repeats,
            "fresh_server_database_and_upload_dir_per_repeat": True,
            "workflow_stages": [
                "create pseudonymous case",
                "create report examination",
                "upload unique synthetic TXT with deidentified=true",
                "execute report analysis job",
                "reload upload metadata through a separate client pool",
                "reload measurements through a separate client pool",
                "reload findings through a separate client pool",
                "reload provenance through a separate client pool",
            ],
            "success_contract": {
                "case_and_examination_ids_match": True,
                "server_and_reloaded_sha256_match_client": True,
                "job_status": "COMPLETED",
                "processor": "Rule-Based Clinical Text Baseline",
                "finding_review_status": "PENDING_HUMAN_REVIEW",
                "calibrated_confidence": None,
                "required_measurements": EXPECTED_MEASUREMENT_UNITS,
                "required_audit_actions": ["FILE_UPLOADED", "ANALYSIS_JOB_COMPLETED"],
            },
            "request_timeout_seconds": args.request_timeout_seconds,
            "startup_timeout_seconds": args.startup_timeout_seconds,
            "rss_sample_interval_ms": args.rss_sample_ms,
            "settle_seconds": args.settle_seconds,
        },
        "environment": {
            "project_root": str(PROJECT_ROOT),
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "sqlite_version": sqlite3.sqlite_version,
            "packages": package_versions(),
            "hardware": collect_hardware(),
            "gpu": collect_gpu(),
            "git": collect_git_state(),
            "source": source_manifest(),
        },
        "profiles": [],
    }

    try:
        for concurrency in args.concurrency:
            profile: dict[str, Any] = {"concurrency": concurrency, "repeats": []}
            print(f"profile concurrency={concurrency}", flush=True)
            for repeat_index in range(1, args.repeats + 1):
                repeat = run_repeat(
                    args=args,
                    run_tag=run_tag,
                    concurrency=concurrency,
                    repeat_index=repeat_index,
                )
                profile["repeats"].append(repeat)
                summary = repeat["summary"]
                latency = summary.get("successful_end_to_end_latency_ms", {})
                print(
                    "  repeat={repeat} status={status} success={success}/{attempted} "
                    "p50={p50}ms p95={p95}ms throughput={throughput}/s "
                    "peak_rss={rss}".format(
                        repeat=repeat_index,
                        status=repeat["status"],
                        success=summary["succeeded_workflows"],
                        attempted=summary["attempted_workflows"],
                        p50=latency.get("p50"),
                        p95=latency.get("p95"),
                        throughput=summary.get("successful_workflow_throughput_per_second"),
                        rss=repeat.get("memory", {}).get("peak_rss_bytes"),
                    ),
                    flush=True,
                )
            profile["aggregate"] = aggregate_profile(profile["repeats"])
            report["profiles"].append(profile)

        total_attempted = sum(
            profile["aggregate"]["total_attempted_workflows"] for profile in report["profiles"]
        )
        total_succeeded = sum(
            profile["aggregate"]["total_succeeded_workflows"] for profile in report["profiles"]
        )
        total_failed = sum(
            profile["aggregate"]["total_failed_workflows"] for profile in report["profiles"]
        )
        all_removed = all(profile["aggregate"]["all_temp_state_removed"] for profile in report["profiles"])
        report["overall"] = {
            "total_attempted_workflows": total_attempted,
            "total_succeeded_workflows": total_succeeded,
            "total_failed_workflows": total_failed,
            "failure_rate": round(total_failed / total_attempted, 6) if total_attempted else None,
            "all_temporary_state_removed": all_removed,
            "clinical_performance_measured": False,
        }
        report["status"] = (
            "completed"
            if total_failed == 0 and total_attempted > 0 and all_removed
            else "completed_with_failures"
        )
    except Exception as exc:
        report["status"] = "failed"
        report["fatal_error"] = f"{type(exc).__name__}: {exc}"
    finally:
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        report["duration_seconds"] = round(
            (datetime.now(timezone.utc) - started_at).total_seconds(),
            6,
        )
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    artifact_sha256 = sha256_file(output_path)
    print(f"result={output_path}", flush=True)
    print(f"result_sha256={artifact_sha256}", flush=True)
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
