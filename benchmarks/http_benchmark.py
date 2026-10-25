"""Reproducible local HTTP benchmark for the MedTwin FastAPI service.

This harness measures software-serving performance only. It deliberately uses
the public, deterministic catalog endpoint and does not invoke clinical models.
The backend receives an isolated temporary SQLite database and upload folder so
its startup seeding cannot modify the workspace's normal application state.
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
from typing import Any, Sequence

import httpx
import psutil


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"
SOURCE_FILES = (
    Path(__file__).resolve(),
    PROJECT_ROOT / "backend" / "app" / "main.py",
    PROJECT_ROOT / "backend" / "app" / "config.py",
    PROJECT_ROOT / "backend" / "app" / "database.py",
    PROJECT_ROOT / "backend" / "app" / "routers" / "catalog.py",
    PROJECT_ROOT / "backend" / "app" / "services" / "clinical_catalog.py",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        default="/api/v1/catalog/packages",
        help="GET path to benchmark (default: %(default)s)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=20,
        help="Warm-up requests before every repeat (default: %(default)s)",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=200,
        help="Measured requests per repeat (default: %(default)s)",
    )
    parser.add_argument(
        "--concurrency",
        nargs="+",
        default=["1", "8"],
        help="Concurrency levels, separated by spaces or commas (default: 1 8)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Measured repeats per concurrency level (default: %(default)s)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Server port; 0 selects an available loopback port",
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=10.0,
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
        help="Server process-tree RSS sampling interval",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=0.5,
        help="Idle interval before each repeat",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Result JSON path; defaults to a timestamped file under benchmarks/results",
    )
    args = parser.parse_args()

    concurrency: list[int] = []
    for value in args.concurrency:
        for item in value.split(","):
            concurrency.append(int(item.strip()))
    args.concurrency = concurrency

    if not args.path.startswith("/"):
        parser.error("--path must begin with '/'")
    if args.warmup < 0 or args.requests < 1 or args.repeats < 1:
        parser.error("warmup must be >= 0; requests and repeats must be >= 1")
    if not args.concurrency or any(value < 1 for value in args.concurrency):
        parser.error("every concurrency value must be >= 1")
    if args.rss_sample_ms <= 0:
        parser.error("--rss-sample-ms must be > 0")
    return args


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def median_or_none(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def round_or_none(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


def available_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def package_versions() -> dict[str, str | None]:
    packages = (
        "fastapi",
        "uvicorn",
        "starlette",
        "pydantic",
        "sqlalchemy",
        "httpx",
        "psutil",
        "torch",
        "numpy",
        "pillow",
    )
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def command_output(command: list[str], timeout: float = 10.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"returncode": None, "stdout": "", "stderr": repr(exc)}


def collect_windows_hardware() -> dict[str, Any] | None:
    if os.name != "nt":
        return None
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        return None
    script = (
        "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1;"
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$sys=Get-CimInstance Win32_ComputerSystem;"
        "[pscustomobject]@{"
        "cpu_name=$cpu.Name;"
        "physical_cores=$cpu.NumberOfCores;"
        "logical_processors=$cpu.NumberOfLogicalProcessors;"
        "ram_bytes=[int64]$sys.TotalPhysicalMemory;"
        "os_caption=$os.Caption;"
        "os_version=$os.Version;"
        "os_build=$os.BuildNumber"
        "}|ConvertTo-Json -Compress"
    )
    result = command_output([powershell, "-NoProfile", "-Command", script])
    if result["returncode"] != 0 or not result["stdout"]:
        return {"error": result["stderr"] or "CIM query returned no output"}
    try:
        hardware = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return {"error": "CIM query returned invalid JSON", "raw": result["stdout"]}
    power_plan = command_output(["powercfg", "/GETACTIVESCHEME"])
    hardware["active_power_plan"] = power_plan["stdout"] or power_plan["stderr"]
    return hardware


def collect_gpu() -> dict[str, Any]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"detected": False, "used_by_workload": False}
    result = command_output(
        [
            executable,
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    devices: list[dict[str, str]] = []
    if result["returncode"] == 0:
        for line in result["stdout"].splitlines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) == 3:
                devices.append(
                    {
                        "name": fields[0],
                        "driver_version": fields[1],
                        "memory_mib": fields[2],
                    }
                )
    return {
        "detected": bool(devices),
        "used_by_workload": False,
        "devices": devices,
        "query_error": result["stderr"] or None,
    }


def collect_git_state() -> dict[str, Any]:
    head = command_output(["git", "rev-parse", "HEAD"])
    if head["returncode"] != 0:
        return {
            "available": False,
            "reason": head["stderr"] or "git metadata unavailable",
        }
    status = command_output(["git", "status", "--short"])
    return {
        "available": True,
        "head": head["stdout"],
        "dirty": bool(status["stdout"]),
        "status_short": status["stdout"].splitlines(),
    }


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
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_ns = 0

    def _sample(self) -> None:
        rss_bytes, pids = process_tree_rss(self.root_pid)
        self.samples.append(
            {
                "elapsed_ms": round((time.perf_counter_ns() - self._started_ns) / 1_000_000, 3),
                "rss_bytes": rss_bytes,
                "pids": pids,
            }
        )

    def _run(self) -> None:
        self._sample()
        while not self._stop.wait(self.interval_seconds):
            self._sample()
        self._sample()

    def start(self) -> None:
        self._started_ns = time.perf_counter_ns()
        self._thread = threading.Thread(target=self._run, name="rss-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 5))

    @property
    def peak_rss_bytes(self) -> int:
        return max((sample["rss_bytes"] for sample in self.samples), default=0)


async def request_batch(
    *,
    base_url: str,
    path: str,
    request_count: int,
    concurrency: int,
    timeout_seconds: float,
    expected_payload: bytes,
) -> tuple[list[dict[str, Any]], float]:
    results: list[dict[str, Any]] = []
    next_request_id = 0
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
        keepalive_expiry=30.0,
    )
    timeout = httpx.Timeout(timeout_seconds)

    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        limits=limits,
        headers={"User-Agent": "MedTwinLocalBenchmark/1.0"},
        follow_redirects=False,
    ) as client:

        async def worker() -> None:
            nonlocal next_request_id
            while next_request_id < request_count:
                request_id = next_request_id
                next_request_id += 1
                started_ns = time.perf_counter_ns()
                status_code: int | None = None
                response_bytes = 0
                failure_type: str | None = None
                error: str | None = None
                try:
                    response = await client.get(path)
                    latency_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
                    status_code = response.status_code
                    response_bytes = len(response.content)
                    if not 200 <= response.status_code < 300:
                        failure_type = "non_2xx"
                    elif response.content != expected_payload:
                        failure_type = "payload_mismatch"
                except Exception as exc:  # Failure details are part of benchmark output.
                    latency_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
                    failure_type = "exception"
                    error = f"{type(exc).__name__}: {exc}"
                results.append(
                    {
                        "request_id": request_id,
                        "latency_ms": round(latency_ms, 6),
                        "status_code": status_code,
                        "response_bytes": response_bytes,
                        "ok": failure_type is None,
                        "failure_type": failure_type,
                        "error": error,
                    }
                )

        wall_started_ns = time.perf_counter_ns()
        await asyncio.gather(*(worker() for _ in range(concurrency)))
        wall_seconds = (time.perf_counter_ns() - wall_started_ns) / 1_000_000_000

    results.sort(key=lambda item: item["request_id"])
    return results, wall_seconds


def summarize_requests(records: Sequence[dict[str, Any]], wall_seconds: float) -> dict[str, Any]:
    successes = [record for record in records if record["ok"]]
    success_latencies = [float(record["latency_ms"]) for record in successes]
    failure_counts: dict[str, int] = {}
    for record in records:
        failure_type = record["failure_type"]
        if failure_type:
            failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1
    attempted = len(records)
    succeeded = len(successes)
    failed = attempted - succeeded
    return {
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "failure_rate": round(failed / attempted, 6) if attempted else None,
        "failure_counts": failure_counts,
        "wall_seconds": round(wall_seconds, 6),
        "attempted_throughput_rps": round(attempted / wall_seconds, 3) if wall_seconds else None,
        "successful_throughput_rps": round(succeeded / wall_seconds, 3) if wall_seconds else None,
        "success_latency_ms": {
            "definition": "client-observed full-response latency; nearest-rank percentiles",
            "min": round_or_none(min(success_latencies) if success_latencies else None, 6),
            "p50": round_or_none(nearest_rank(success_latencies, 0.50), 6),
            "p95": round_or_none(nearest_rank(success_latencies, 0.95), 6),
            "max": round_or_none(max(success_latencies) if success_latencies else None, 6),
            "mean": round_or_none(
                statistics.fmean(success_latencies) if success_latencies else None,
                6,
            ),
        },
    }


def aggregate_repeats(repeats: Sequence[dict[str, Any]]) -> dict[str, Any]:
    p50_values = [
        repeat["summary"]["success_latency_ms"]["p50"]
        for repeat in repeats
        if repeat["summary"]["success_latency_ms"]["p50"] is not None
    ]
    p95_values = [
        repeat["summary"]["success_latency_ms"]["p95"]
        for repeat in repeats
        if repeat["summary"]["success_latency_ms"]["p95"] is not None
    ]
    throughput_values = [
        repeat["summary"]["successful_throughput_rps"]
        for repeat in repeats
        if repeat["summary"]["successful_throughput_rps"] is not None
    ]
    return {
        "repeat_count": len(repeats),
        "p50_latency_ms_median_across_repeats": round_or_none(median_or_none(p50_values), 6),
        "p95_latency_ms_median_across_repeats": round_or_none(median_or_none(p95_values), 6),
        "successful_throughput_rps_median_across_repeats": round_or_none(
            median_or_none(throughput_values), 3
        ),
        "total_attempted": sum(repeat["summary"]["attempted"] for repeat in repeats),
        "total_succeeded": sum(repeat["summary"]["succeeded"] for repeat in repeats),
        "total_failed": sum(repeat["summary"]["failed"] for repeat in repeats),
        "max_peak_rss_bytes": max((repeat["memory"]["peak_rss_bytes"] for repeat in repeats), default=0),
    }


def wait_until_ready(
    process: subprocess.Popen[Any],
    base_url: str,
    timeout_seconds: float,
) -> float:
    started = time.perf_counter()
    deadline = started + timeout_seconds
    last_error = "server did not accept a request"
    with httpx.Client(timeout=1.0) as client:
        while time.perf_counter() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Uvicorn exited during startup with code {process.returncode}")
            try:
                response = client.get(f"{base_url}/")
                if response.status_code == 200:
                    return time.perf_counter() - started
                last_error = f"readiness returned HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.1)
    raise TimeoutError(f"Uvicorn was not ready after {timeout_seconds}s ({last_error})")


def stop_server(process: subprocess.Popen[Any]) -> None:
    """Stop Uvicorn and every descendant before removing its SQLite workspace."""
    try:
        root = psutil.Process(process.pid)
        descendants = root.children(recursive=True)
    except psutil.Error:
        descendants = []

    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.Error:
            pass
    if process.poll() is None:
        process.terminate()

    _, alive = psutil.wait_procs(descendants, timeout=10)
    for child in alive:
        try:
            child.kill()
        except psutil.Error:
            pass
    if alive:
        psutil.wait_procs(alive, timeout=5)

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_RESULTS_DIR / f"http-benchmark-{stamp}.json"


def main() -> int:
    args = parse_args()
    output_path = (args.output or default_output_path()).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    port = args.port or available_port(args.host)
    base_url = f"http://{args.host}:{port}"
    generated_at = datetime.now(timezone.utc)
    local_now = datetime.now().astimezone()

    source_hashes = {
        str(path.relative_to(PROJECT_ROOT)): sha256_file(path)
        for path in SOURCE_FILES
        if path.is_file()
    }

    report: dict[str, Any] = {
        "schema_version": 1,
        "benchmark_kind": "local_software_http_serving_only",
        "clinical_performance_measured": False,
        "generated_at_utc": generated_at.isoformat(),
        "local_timezone": {
            "name": str(local_now.tzinfo),
            "utc_offset": local_now.strftime("%z"),
        },
        "workload": {
            "method": "GET",
            "path": args.path,
            "base_url": base_url,
            "warmup_requests_per_repeat": args.warmup,
            "measured_requests_per_repeat": args.requests,
            "concurrency_levels": args.concurrency,
            "repeats_per_concurrency": args.repeats,
            "request_timeout_seconds": args.request_timeout_seconds,
            "rss_sample_interval_ms": args.rss_sample_ms,
            "settle_seconds": args.settle_seconds,
            "network_scope": "same-host IPv4 loopback",
            "payload_validation": "HTTP 2xx and byte equality with preflight response",
        },
        "environment": {
            "project_root": str(PROJECT_ROOT),
            "python_executable": sys.executable,
            "python_version": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER"),
            "cpu_physical_count": psutil.cpu_count(logical=False),
            "cpu_logical_count": psutil.cpu_count(logical=True),
            "total_ram_bytes": int(psutil.virtual_memory().total),
            "windows_hardware": collect_windows_hardware(),
            "gpu": collect_gpu(),
            "packages": package_versions(),
            "sqlite_version": sqlite3.sqlite_version,
            "git": collect_git_state(),
            "source_sha256": source_hashes,
        },
        "server": {},
        "profiles": [],
    }

    process: subprocess.Popen[Any] | None = None
    log_handle: Any = None
    log_path: Path | None = None

    try:
        with tempfile.TemporaryDirectory(prefix="medtwin-http-bench-") as temp_name:
            temp_root = Path(temp_name).resolve()
            database_path = temp_root / "benchmark.db"
            uploads_path = temp_root / "uploads"
            uploads_path.mkdir(parents=True, exist_ok=True)
            log_path = temp_root / "uvicorn.log"

            environment = os.environ.copy()
            environment.update(
                {
                    "DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
                    "UPLOAD_DIR": str(uploads_path),
                    "SECRET_KEY": "benchmark-isolated-state-not-for-production",
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
            report["server"] = {
                "app": "app.main:app",
                "app_dir": str(BACKEND_DIR),
                "command": command,
                "workers": 1,
                "reload": False,
                "access_log": False,
                "database": {
                    "kind": "isolated temporary SQLite",
                    "url": environment["DATABASE_URL"],
                    "journal_mode_configured": "WAL",
                },
                "upload_dir": str(uploads_path),
                "temporary_state_removed_after_run": True,
            }

            log_handle = log_path.open("w", encoding="utf-8")
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                env=environment,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
            report["server"]["pid"] = process.pid
            report["server"]["startup_seconds"] = round(
                wait_until_ready(process, base_url, args.startup_timeout_seconds),
                6,
            )

            startup_rss, startup_pids = process_tree_rss(process.pid)
            report["server"]["rss_after_startup_bytes"] = startup_rss
            report["server"]["process_tree_after_startup"] = startup_pids

            with httpx.Client(base_url=base_url, timeout=args.request_timeout_seconds) as client:
                preflight = client.get(args.path)
            if not 200 <= preflight.status_code < 300:
                raise RuntimeError(f"Preflight request returned HTTP {preflight.status_code}")
            expected_payload = preflight.content
            report["workload"]["preflight_status_code"] = preflight.status_code
            report["workload"]["expected_response_bytes"] = len(expected_payload)
            report["workload"]["expected_response_sha256"] = hashlib.sha256(
                expected_payload
            ).hexdigest()

            for concurrency in args.concurrency:
                profile: dict[str, Any] = {"concurrency": concurrency, "repeats": []}
                print(f"benchmarking concurrency={concurrency}", flush=True)
                for repeat_index in range(1, args.repeats + 1):
                    if args.settle_seconds:
                        time.sleep(args.settle_seconds)

                    warmup_records, warmup_wall = asyncio.run(
                        request_batch(
                            base_url=base_url,
                            path=args.path,
                            request_count=args.warmup,
                            concurrency=concurrency,
                            timeout_seconds=args.request_timeout_seconds,
                            expected_payload=expected_payload,
                        )
                    ) if args.warmup else ([], 0.0)
                    warmup_summary = summarize_requests(warmup_records, warmup_wall)
                    if warmup_summary["failed"]:
                        raise RuntimeError(
                            f"Warmup had {warmup_summary['failed']} failures at concurrency {concurrency}"
                        )

                    baseline_rss, baseline_pids = process_tree_rss(process.pid)
                    sampler = RssSampler(process.pid, args.rss_sample_ms)
                    sampler.start()
                    try:
                        records, wall_seconds = asyncio.run(
                            request_batch(
                                base_url=base_url,
                                path=args.path,
                                request_count=args.requests,
                                concurrency=concurrency,
                                timeout_seconds=args.request_timeout_seconds,
                                expected_payload=expected_payload,
                            )
                        )
                    finally:
                        sampler.stop()

                    summary = summarize_requests(records, wall_seconds)
                    repeat = {
                        "repeat": repeat_index,
                        "warmup_summary": warmup_summary,
                        "summary": summary,
                        "memory": {
                            "scope": "sum of Uvicorn root process and descendants",
                            "baseline_rss_bytes": baseline_rss,
                            "baseline_pids": baseline_pids,
                            "peak_rss_bytes": sampler.peak_rss_bytes,
                            "peak_minus_baseline_bytes": max(
                                0, sampler.peak_rss_bytes - baseline_rss
                            ),
                            "samples": sampler.samples,
                        },
                        "requests": records,
                    }
                    profile["repeats"].append(repeat)
                    print(
                        "  repeat={repeat} p50={p50:.3f}ms p95={p95:.3f}ms "
                        "success_rps={rps:.1f} failures={failures}".format(
                            repeat=repeat_index,
                            p50=summary["success_latency_ms"]["p50"] or 0.0,
                            p95=summary["success_latency_ms"]["p95"] or 0.0,
                            rps=summary["successful_throughput_rps"] or 0.0,
                            failures=summary["failed"],
                        ),
                        flush=True,
                    )

                profile["aggregate"] = aggregate_repeats(profile["repeats"])
                report["profiles"].append(profile)

            report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
            report["status"] = "completed"
            stop_server(process)
            process = None
            log_handle.flush()
            report["server"]["uvicorn_log"] = log_path.read_text(
                encoding="utf-8", errors="replace"
            )
            # Windows will not remove the temporary directory while this file
            # handle is open, even though the server process has exited.
            log_handle.close()
            log_handle = None

    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        if process is not None:
            stop_server(process)
            process = None
        if log_handle is not None:
            log_handle.flush()
        if log_path is not None and log_path.exists():
            report.setdefault("server", {})["uvicorn_log"] = log_path.read_text(
                encoding="utf-8", errors="replace"
            )
        output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"benchmark failed; diagnostic result: {output_path}", file=sys.stderr)
        raise
    finally:
        if process is not None:
            stop_server(process)
        if log_handle is not None:
            log_handle.close()

    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"result: {output_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
