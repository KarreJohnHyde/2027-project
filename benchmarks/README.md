# Local HTTP benchmark

This harness measures the software-serving path of `backend/app/main.py`. It
does **not** measure diagnostic accuracy, model inference, clinical validity, or
real-world network performance.

The default target is `GET /api/catalog/packages`, a public deterministic
catalog endpoint that needs no dataset, model artifact, authentication, or
patient data. The harness starts a single Uvicorn worker without reload, gives
it a temporary SQLite database and upload directory, and removes that isolated
state after the run.

## Setup

From `D:\project`, install the benchmark-only packages into the existing
environment:

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r benchmarks\requirements.txt
```

The backend's own runtime dependencies must already be installed in that
environment.

## Run

```powershell
.\.venv\Scripts\python.exe benchmarks\http_benchmark.py `
  --path /api/catalog/packages `
  --warmup 20 `
  --requests 200 `
  --concurrency 1 8 `
  --repeats 3
```

Results are timestamped JSON files under `benchmarks/results/`. Each file
contains per-request timings, per-sample process-tree RSS, failure details,
source hashes, launch configuration, and the hardware/software manifest.

Latency is client-observed full-response time over same-host loopback. p50 and
p95 use the nearest-rank definition and include successful requests only.
Throughput uses the complete measured wall interval. A failure is a transport
exception, non-2xx response, or payload mismatch from the preflight response.

Do not compare results across machines or configurations without preserving the
full environment manifest. Do not describe these measurements as clinical,
model, diagnostic, or real-time performance.
