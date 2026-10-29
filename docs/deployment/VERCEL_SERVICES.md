# Deploying MedTwin on Vercel (Services)

`vercel.json` deploys the repository as one Vercel project with two services. Nothing has been deployed from this repository by its maintainers; this page is the operator's guide. MedTwin remains a research prototype: a deployment is not clinical validation, and real patient documents must not be uploaded to a deployment that is not approved for them.

## Topology

| Service | Root | Built as | Public route |
| --- | --- | --- | --- |
| `app` | `.` | Vite static build (`npm ci`, `npm run build`, `dist/`) | everything not routed to `backend`; extension-less paths fall back to `index.html`, missing files return 404 |
| `backend` | `backend/` | Python runtime, FastAPI `app.main:app`, Python 3.12 | `/api/*` and `/health`, path unchanged (the API owns `/api/v1`) |

- `benchmarks/` is not a service: it is a command-line load test whose result JSON the API reads.
- No service bindings: the browser calls `/api/v1` on the same domain, and the backend calls no other service.
- No worker service: analysis jobs run inside the upload request (`MEDTWIN_JOB_EXECUTION=inline`, the default), within the function's 300-second limit.
- The `app` service sends the same security headers as the nginx image (CSP, frame denial, no referrer).

Vercel Services and large functions are Beta; the Python runtime is generally available.

## How the backend is packaged

- `backend/pyproject.toml` and `backend/uv.lock`, which Vercel uses instead of `requirements.txt`, pin the same versions with two differences: OpenCV is the headless build (the GUI build that RapidOCR names needs libGL, which Vercel's runtime lacks), and `vercel-blob` is added. A backend test fails if the pins drift or the lock is stale; regenerate it with `uv lock` in `backend/`.
- PyTorch is not installed. The API starts without it; the research models report the missing dependency (their checkpoints are not in Git either).
- `backend/vercel_build.py` copies the evidence the API reads (model and dataset registries, validation reports, traceability, anatomy manifest, benchmark results) into the bundle, because Vercel bundles only `backend/`.
- The installed bundle is about 850 MB uncompressed, above the standard 500 MB Python limit, so it uses large functions (up to 5 GB). New projects have them by default; an existing project needs the environment variable `VERCEL_SUPPORT_LARGE_FUNCTIONS=1`.
- `.vercelignore` is a closed allowlist: a CLI deploy from a working copy uploads build inputs and evidence only, never datasets, databases, uploads, keys or model weights.

## Two ways to run it

**Demonstration (nothing configured).** The SQLite database and uploads live in the instance's temporary directory, so they are lost when the instance stops (after a few idle minutes) and are not shared between instances. Every signed-in page shows a warning banner. Use synthetic data only.

**Persistent.** Configure all three:

1. A PostgreSQL database: set `DATABASE_URL` (a `postgres://` URL from Neon through the Vercel Marketplace, Supabase or any host works; the psycopg driver is installed). Schema creation and migrations run at start-up under an advisory lock, so instances starting together do not race.
2. A **private** Vercel Blob store connected to the project (it provides `BLOB_STORE_ID`; outside Vercel use `BLOB_READ_WRITE_TOKEN`). Every stored upload is also written there and fetched by instances that lack it.
3. `MEDTWIN_STORAGE_KEYS`: Blob storage accepts encrypted uploads only (AES-256-GCM, key held by the API), and refuses uploads without a key.

With both a database and an object store, `/api/v1/system/health` reports `temporary_storage: false` and the banner disappears.

## Environment variables

| Variable | When | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | always | 32+ random characters. Without it every instance signs tokens with its own random key and users are signed out between instances. |
| `ENVIRONMENT` | persistent | `production` refuses a short `SECRET_KEY` and the development seed. |
| `DATABASE_URL` | persistent | PostgreSQL, as above. |
| `MEDTWIN_STORAGE_KEYS` | persistent | Base64 AES-256 key(s), newest first. Generate with `python -c "from app.services.storage_crypto import generate_key; print(generate_key())"` in `backend/`. |
| `BLOB_STORE_ID` / `BLOB_READ_WRITE_TOKEN` | persistent | Set by connecting a private Blob store, or a store token. |
| `DEV_SEED_ENABLED`, `DEV_SEED_USERNAME`, `DEV_SEED_PASSWORD`, `DEV_SEED_EMAIL`, `DEV_SEED_ROLE` | demonstration only | With `ENVIRONMENT=development`, creates one verified account at start-up (password 12+ characters). |
| `VERCEL_SUPPORT_LARGE_FUNCTIONS` | existing projects | `1` enables bundles above 500 MB. |

Never put secrets in `VITE_` or `NEXT_PUBLIC_` variables: those are compiled into the browser bundle. Leave `VITE_MEDTWIN_API_URL` unset so the browser uses the same domain.

## First professional account (persistent mode)

No public endpoint grants a professional role and the development seed is refused in production. With the hosted database's URL exported in a local shell, the operator runs, from `backend/`:

```powershell
$env:DATABASE_URL = '<the deployment database URL>'
$env:MEDTWIN_PROVISION_PASSWORD = '<a new password, 12+ characters>'
python -m app.provision --username dr.example --email dr@example.org --role clinician
```

An existing self-registered account is verified and given the role without touching its password. Every change is audit-logged.

## Project settings outside `vercel.json`

- **Git LFS** (Project Settings → Git): the published repository stores the 3D models (`public/models/*.glb`) and images in Git LFS. Without LFS the deployment serves 131-byte pointer files and the anatomy viewer cannot load them.
- **Request size**: Vercel accepts at most 4.5 MB per request. Larger uploads are rejected before reaching the API; the app shows an HTTP 413 message.

## What does not work on Vercel

- Research-model inference (no PyTorch, no checkpoints in Git), GPU telemetry and the background worker.
- Uploads above 4.5 MB (photographed report packets are usually smaller; DICOM series and volumes often are not).
- The derived anatomy library (not in Git; only the simplified reference models are published).

## Checking a deployment

`/health` and `/api/v1/system/readiness` report the database, migrations, upload storage (`temporary`, `durable_copies`), encryption and the model registry. After deploying: sign in, open a deep link directly (for example `/cases`), upload a small synthetic report, confirm it is analysed, and, in persistent mode, confirm it is still readable after the instance has been idle for ten minutes.

Local checks without deploying: `node --test scripts/vercel-config.test.mjs` and the backend tests `test_serverless_runtime.py`, `test_durable_storage.py` and, with a disposable database in `MEDTWIN_TEST_POSTGRES_URL`, `test_postgres_smoke.py`.
