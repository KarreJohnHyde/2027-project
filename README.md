> **Whole-body expansion (2026-11-13):** The synchronized Twin Control Room now includes source-coordinate2D/3D, exact-finding provenance/refusal context, matched temporal image comparisons, a same-input model disagreement explorer and a source-backed anatomy hierarchy. Integrated backend:1,109 passed/5 skipped; frontend checks and focused browser/accessibility checks passed. See the [five-priority implementation and publication audit](docs/universal/EXPANSION_REPORT_2026-11-13.md) and [public source setup](docs/universal/PUBLIC_SOURCE_SETUP.md). Commercial-development rights gates remain enabled; zero clinical activations. Earlier dated counts below are historical.

> **Completion audit (2026-11-13):** Commercial-use eligibility remains required. Official FY2027 terminology, explicit4D/RAS spatial processing, source-bound research diagnostics, chronological backtests, opt-in word OCR and actual encrypted container recovery now work within documented contracts. Current verification:1,072 backend passes/5 skips. See the [completion report and18 November agenda](docs/universal/COMPLETION_REPORT_2026-11-13.md) and [reproduction](docs/universal/COMPLETION_REPRODUCTION.md). Independent full-report validation, six original model-family rights prerequisites and clinical/publication blockers remain open. Earlier dated counts below are historical.

# MedTwin 2.0

> **MedTwin Universal (2026-11-13):** New **Case Command Center** (`/universal`) and **Model Arena** (`/arena`). The [Universal implementation packet](docs/universal/README.md) records all 25 body-system workspaces, source-linked graph/copilot, actual native MRI workflows, refusal boundaries and all 24 requirement statuses. Research catalogue coverage is separate from model support and clinical validation.

> **Review implementation (2026-11-13):** The [executed implementation report](docs/review-2026-11-13/MEDTWIN_IMPLEMENTATION_STATUS_2026-11-13.md) and [demo/reproduction guide](docs/review-2026-11-13/MEDTWIN_DEMO_GUIDE_2026-11-13.md) record the current isolated document/imaging workflows, source-preserving OCR and input-contract fixes, dataset checks, measured checkpoint parity and remaining blockers. New real-model training remains permission-gated; original weights and clinical activation status are unchanged. Historical verification figures below are dated evidence, not the current test total.

> **Priority execution (2026-11-09):** The target is commercial clinician decision support in India; release remains blocked. Python startup is repaired, Transformers/RadGraph are migrated, and hardened containers passed a full local encrypted recovery drill. All 131 MSD liver CT/mask cases have a checked 91/20/20 manifest. The RCC-AID candidate now has 142 paired scans from 101 patient groups, with curation and rights review pending; the kidney tumour model remains rejected. The [current work and verification report](docs/development/PRIORITY_EXECUTION_2026-11-09.md), [local startup repair](docs/development/LOCAL_STARTUP_REPAIR_2026-11-09.md) and [India release review](docs/deployment/INDIA_COMMERCIAL_RELEASE_REVIEW_2026-11-09.md) distinguish completed work from remaining clinical, rights, native-policy and off-host recovery blockers. Zero models are clinically activated or commercially cleared. Earlier verification counts below are historical.

> **Image security:** All reported critical findings were removed through updates and unused-component removal. Four high backend OS findings remain, plus a frontend scanner/vendor-version discrepancy. See the [image audit and remaining work](docs/security/IMAGE_SECURITY_REVIEW_2026-11-09.md). Passing functional tests does not clear these release blockers.

> **Heterogeneous evidence update (2026-11-06):** source-linked report synthesis now works when imaging abstains; raster/PDF film-panel previews, examination linking, multimodel job batches and opt-in chronological research baselines are integrated. See [implementation status, root causes and reproducible checks](docs/implementation/HETEROGENEOUS_EVIDENCE_STATUS.md). Private case access is the default; demo guests remain isolated even in explicit shared-workspace mode. Existing data is preserved through additive migrations.

> **Current verification (2026-11-06):** the [continued acceptance status](docs/implementation/CONTINUED_ACCEPTANCE_STATUS.md) records the final comparison, baseline, film-control and anatomy-navigation repairs: 613 backend tests passed, four skipped; frontend checks and all four browser acceptance checks passed. Seventeen application screenshots and four JSON outputs were saved. A separate RSNA held-out digital CT control completed real checkpoint inference. The [master implementation status](docs/implementation/MASTER_IMPLEMENTATION_STATUS.md) describes the integrated workflow and capability limits. Earlier audits and test counts below are historical. This is research software, not clinical validation or a deployment.

MedTwin is a software-only research prototype for authenticated, provenance-preserving review of de-identified clinical evidence. It is not a validated medical device, does not replace a clinician, and must not be used with identifiable patient data in this development phase.

The application uses one backend entry point, `backend/app/main.py` (`app.main:app`), and one versioned API contract under `/api/v1`. The previous standalone backend is archived at `backend/legacy/main_pre_v1.py` and is not a supported server.

Every patient-facing result traces to an uploaded source and a recorded computation. Where evidence or a validated model is missing, the application returns a machine-readable state (`NOT_AVAILABLE`, `INSUFFICIENT_EVIDENCE`, `MODEL_NOT_VALIDATED`, `INDETERMINATE`, `REGISTRATION_UNAVAILABLE`, ...) instead of a value.

## What is operational

- **Workspace:** 16 sections (Overview, Case Workspace, Document Intelligence, Medical Imaging, Biomarker Analytics, Historical Comparison, Live Anatomy Studio, Prognosis Studio, Multimodal Intelligence, Risk & Explainability, Research Analytics, Model Registry, Dataset Registry, Validation Center, Reports, Settings) plus a unified Upload Center, with light and dark themes.
- **Access control:** JWT authentication, case-scoped authorization, case sharing (viewer/editor), rate limiting, security headers, readiness checks and audit history. Patients and caregivers use a scoped "My record" portal. Public users may create a private record and upload only de-identified documents to it; clinician-linked records can also be viewed. The portal shows documents and clinician-confirmed results only, never research-model output or unreviewed extraction, and a patient decides which caregivers can see their record. Portal access does not grant access to clinical case APIs.
- **Uploads:** content-signature checks and SHA-256 storage for PDF, DOCX, TXT, CSV, XLSX, JSON/FHIR, HL7 v2, PNG/JPEG/BMP, DICOM, NIfTI, NRRD, MHA, digital ECG (WFDB `.hea`/`.dat`, CSV) and EDF/EDF+/BDF recordings (EEG and other physiological signals). A de-identification attestation is required. Stored files are encrypted at rest with AES-256-GCM whenever a storage key is configured (`MEDTWIN_STORAGE_ENCRYPTION=required` makes it mandatory); files can be versioned or withdrawn without altering the original bytes. The SQLite database can be SQLCipher-encrypted (`MEDTWIN_DB_ENCRYPTION=sqlcipher`, the Compose default); `scripts/encrypt_database.py` converts an existing database into a verified encrypted copy.
- **OCR:** born-digital text is read directly; scanned PDF pages and photographed reports are read with local RapidOCR at 300 DPI, with tilted rows de-skewed and sideways pages read upright. Text after a line OCR could not read is marked uncertain rather than asserted. A photograph of a printed document is refused by the image models.
- **Documents:** the clinical-text rules baseline `rules-v2.0.0` scopes negation, uncertainty, hypothetical, historical, family and comparison context per clause, so "No evidence of…" or "Rule out…" never becomes a diagnosis. Measurements keep source spans, documented intervals, flags and dates; FHIR Observations and HL7 v2 result messages (OBR/OBX/NTE; patient, visit and staff segments are never read) are imported with their documented codes. All outputs await clinician review; the baseline has not been evaluated on an annotated corpus.
- **Imaging:** DICOM, NIfTI, NRRD and MHA metadata and slice rendering, with HU window presets only when rescale data exist and identifier warnings. Multi-file DICOM series are grouped, ordered by patient position, checked for gaps, duplicates and inconsistent geometry, and displayed plane by plane (Medical Imaging, DICOM series). EDF recordings are shown channel by channel with their annotations; the header's patient and recording fields are never displayed.
- **Research models (research only, not clinically validated):** seven 2-D image models (GI endoscopy classification and polyp segmentation, coronary angiography stenosis detection and segment segmentation, kidney-stone CT detection, blood-cell microscopy), a 12-lead ECG classifier for digital WFDB/CSV records and a cardiac cine-MRI segmenter for single NIfTI frames or assembled DICOM series run on uploads behind checkpoint-hash, licence and input-contract gates; outputs stay pending human review. Each 2-D model first checks that the image resembles its training images and refuses it otherwise (`docs/validation/IMAGE_APPLICABILITY_GATE.md`). The ECG and MRI paths reproduce their held-out predictions, and series input reproduces the NIfTI path exactly (`docs/validation/UPLOAD_INFERENCE_PARITY.md`, `docs/validation/SERIES_INFERENCE_PARITY.json`).
- **Background jobs:** a durable job queue with a separate worker (`python -m app.worker`) and an inline mode for development.
- **Biomarkers:** longitudinal series with registered unit conversions, Δx, Δx%, rate, OLS/Theil–Sen from n ≥ 3 and Mann–Kendall from n ≥ 4. CKD-EPI 2021 eGFR is computed only from documented inputs.
- **Laboratory transcription:** transcription against the test catalog, and investigation orders. A position is computed only against the laboratory's printed interval; without one it is `INDETERMINATE`.
- **Anatomy:** ten system workspaces, 43 generic reference variants plus the Z-Anatomy atlas, structure hierarchy, sections and clinician-confirmed region mapping (`docs/anatomy/README.md`). This is reference anatomy only, never patient anatomy.
- **Prognosis and risk:** a target-trial specification and organ capability registry. Opt-in persistence and linear research baselines use reviewed, dated measurements and chronological backtesting; retained history and horizon limits are exposed in Prognosis Studio. These are not validated medical forecasts. Disease-specific scenarios, risk scores and treatment effects remain unavailable with reasons.
- **Validation Center:** evaluates uploaded held-out predictions in the `MedTwin_2_Validation_Kit` formats. Tasks: classification, multiclass, regression, survival, forecast, lab-extraction audit, segmentation (single pair or ZIP) and COCO detection. Bootstrap CIs are cluster-aware. Each run is bound to dataset, version, split, checkpoint and code commit.
- **Research traceability:** `docs/research/traceability.json` maps the revised draft's claims and equations to code, tests and gaps (`docs/research/implementation_gaps.md`).
- **Registries and reports:** read-only dataset and model registries (every model is blocked from clinical activation), append-only review with four-eyes approval of corrections, and JSON evidence export with SHA-256 plus a printable report.

## What is not operational

- No image, ECG or clinical-language model is clinically activated; the research models above have internal held-out evaluations only, with no external or clinical validation. Of the manuscript's Section X experiments, the image classification, detection/segmentation and PTB-XL runs were executed as internal evaluations; `X-MURA`, `X-DOC-EXTRACTION`, `X-MIMIC-CXR` and `X-FORECAST` have not been run (`docs/research/IEEE_TRACEABILITY_REPORT.md`).
- No clinically validated forecast, calibrated diagnostic confidence, patient-specific anatomy (L3), validated registration or learned case-level multimodal prediction is produced. Rule-based report synthesis and research baselines remain distinct from those claims. Validation requires a longitudinal cohort with a defined endpoint, paired multimodal data, or independently reviewed patient landmarks and an observer study, respectively.
- Clinical validation of any component needs independent, annotated clinical data under an approved protocol; none has been done. No EEG model exists (recordings are read and shown, not interpreted).
- Docker: a full Compose run (worker profile) has been executed locally: health, migrations, an analysis job run by the worker container, encrypted uploads and database on the volume, non-root containers, frontend security headers, restart persistence and clean shutdown. CI builds both images and runs a Playwright browser regression suite against a throwaway stack (`tools/browser-qa/e2e`).

## Requirements

- Node.js 22.12 or newer.
- Python 3.12. The unqualified `python` command on this workstation selects Python 3.15, so use `.venv\Scripts\python.exe` explicitly.
- Docker with the Compose plugin for the container workflow.
- Git LFS before committing the curated GLB asset.

## Local development

On Windows, start the backend and frontend together (reusing verified MedTwin services already running):

```powershell
cd D:\project
npm run dev:full
```

Open `http://localhost:8443`. Stop only the services this launcher started with `npm run dev:stop`. Startup logs and ownership state are under `.cache/dev-stack`; reused managed services are left running. This uses the existing Python environment and installed Node dependencies.

The Figma Make Vite server is already managed on `$PORT` (`8443` by default). Do not start a second Vite process in that environment. Start only the canonical backend:

```powershell
cd D:\project
$env:ENVIRONMENT = "development"
$env:SECRET_KEY = "replace-with-at-least-32-random-characters"
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Open the existing preview at `http://127.0.0.1:8443`. Vite forwards `/api` (including `/api/v1`) to `MEDTWIN_BACKEND_URL`, which defaults to `http://127.0.0.1:8000`.

Outside Figma Make, install dependencies and start Vite with:

```powershell
cd D:\project
npm ci
$env:PORT = "8443"
$env:MEDTWIN_BACKEND_URL = "http://127.0.0.1:8000"
npm run dev
```

Infrastructure health is intentionally unversioned at `GET /health`. Application endpoints and interactive API documentation use `/api/v1` and `/docs`, respectively.

`npm run dev` (and the Figma Make preview) runs only Vite. If nothing listens on `MEDTWIN_BACKEND_URL`, the `/api` proxy answers `503` with `{"code": "BACKEND_UNREACHABLE"}` and the entry page shows "Server unavailable" with a Retry button. Earlier versions showed this as "Request failed (502 Bad Gateway)". Start the backend, or use `npm run dev:full`.

## Entering MedTwin

The welcome page asks for a name and a self-described role (Researcher, Student, Clinician or Other); age and gender are optional. There is no username or password on this page. **Enter MedTwin** creates a new visitor profile, and the browser is then remembered:

- The session is an opaque random value in an `HttpOnly`, `SameSite=Lax` cookie named `medtwin_session` (path `/api`). It is `Secure` over HTTPS; set `MEDTWIN_COOKIE_SECURE=true` behind a TLS proxy that does not send `X-Forwarded-Proto`. The database stores only its SHA-256 hash, in the additive `browser_sessions` table.
- A returning browser goes straight to its workspace (`GET /api/v1/auth/session`). The session lasts `VISITOR_SESSION_DAYS` (90 by default) and is rotated after 12 hours of use. **Sign out** revokes it on the server.
- People are never matched by name, age, gender, address or device, so two people with the same name are two visitors. The stated role grants no privileges: visitors are `public` accounts that see only their own cases.
- Each press of Enter MedTwin or Try Demo sends an `Idempotency-Key`, and retries reuse it, so a network retry never creates a second profile.
- Cookie-authenticated writes must carry `X-MedTwin-Client: web`. This is a CSRF guard; the web client sends it on every request.

**Try Demo** opens a separate 24-hour guest workspace with one fictional sample case. It opens at once, and the three fictional documents are then analysed by the ordinary pipeline while the notice shows progress. The fictional teaching cases (Alex, Maya and Sam) at `/examples` work without the server.

The role list covers research and education, clinical roles (doctor, nurse, clinical staff, surgeon and others), 48 medical specialties, 20 healthcare departments, and patients and families. Every role is self-described and grants nothing.

Accounts registered with a password (administrators and verified professionals among them) sign in at `/account`, which is not part of the welcome page. If the password is not to hand, the operator of the machine that hosts the database can issue a one-time sign-in link (it works once, for 15 minutes, and is audited):

```powershell
.\.venv\Scripts\python.exe scripts\account_access.py list
.\.venv\Scripts\python.exe scripts\account_access.py link --username <account>
.\.venv\Scripts\python.exe scripts\account_access.py share --cases 7 8 9 --with <account>
```

`share` gives another registered account editor (or `--role VIEWER`) access to cases, as their creator would in the app.

### Open workspace (a workstation you control)

To remove sign-in altogether, name a registered account in `MEDTWIN_OPEN_WORKSPACE_ACCOUNT` (a username or numeric id). `npm run dev:full` reads it from the untracked file `.cache\dev-stack\settings.json`:

```json
{ "open_workspace_account": "10" }
```

Every browser then opens the workspace as that account, with no welcome form, sign-in or sign-out. Every case is shared, and "My record" lists every workspace case (with reviewed results only). The sidebar says the workspace is open. Rules:

- The backend refuses to start with this setting on Vercel or with `ENVIRONMENT=production`, because it removes sign-in for every record.
- An administrator account cannot be the open account.
- Demo cases stay with their guests.
- A browser deliberately signed in to another registered account at `/account` keeps that account.

Uploads still require the de-identification confirmation, so documents with patient names, record numbers, phone numbers or addresses must be redacted before they are added. API clients that do not send `X-MedTwin-Client` keep receiving bearer tokens from `POST /api/v1/auth/login`, `/auth/enter` and `/auth/guest`. A browser that stored a bearer token under an earlier version moves to a cookie session once (`POST /api/v1/auth/session/claim`), and the stored token is then removed.

## Optional development seed

There are no embedded or fallback credentials. Development seeding is opt-in, is rejected outside `development` or `test`, and requires an explicit username, password, and email. The password must contain at least 12 characters.

Self-registration requires a unique username, but multiple accounts may use the same email address. Email sign-in is available only when that address belongs to one account; accounts sharing an address must sign in with their usernames. Professional access is never granted by registration.

Set these in the terminal that starts the backend:

```powershell
$env:DEV_SEED_ENABLED = "true"
$env:DEV_SEED_USERNAME = "choose-a-local-username"
$env:DEV_SEED_PASSWORD = "choose-a-local-password-of-12+-characters"
$env:DEV_SEED_EMAIL = "local-user@example.invalid"
$env:DEV_SEED_FULL_NAME = "Local Research User"
$env:DEV_SEED_ROLE = "clinician"
$env:DEV_SEED_CASE_ENABLED = "true"
```

These are examples, not accepted fixed credentials. Choose local values and never commit them. Existing seed records are not silently given a new password on subsequent starts.

## Canonical API

The frontend contract is rooted at `/api/v1`. Key routes are:

| Resource | Routes |
| --- | --- |
| Authentication | `POST /api/v1/auth/enter`, `POST /api/v1/auth/guest`, `GET /api/v1/auth/session`, `POST /api/v1/auth/session/claim`, `POST /api/v1/auth/logout`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me` |
| Cases | `GET/POST /api/v1/cases`, `GET /api/v1/cases/{case_id}` |
| Examinations | `/api/v1/cases/{case_id}/examinations` |
| Uploads | `POST/GET /api/v1/cases/{case_id}/uploads`, `GET /api/v1/uploads/{upload_id}` |
| Analysis jobs | `POST /api/v1/uploads/{upload_id}/analysis-jobs`, `GET /api/v1/analysis-jobs/{job_id}`, `GET /api/v1/cases/{case_id}/analysis-jobs` |
| Findings, statements, and measurements | `GET /api/v1/cases/{case_id}/findings`, `GET /api/v1/cases/{case_id}/statements`, `GET /api/v1/cases/{case_id}/measurements` |
| Longitudinal comparison | `POST /api/v1/cases/{case_id}/compare` with `prior_exam_id` and `current_exam_id` |
| Model/capability registry | `GET /api/v1/models`, `GET /api/v1/models/{model_id}`, `GET /api/v1/capabilities` |
| Dataset registry | `GET /api/v1/datasets`, `GET /api/v1/datasets/{dataset_id}` |
| Human review | `POST/GET /api/v1/reviews/{finding_id}` |
| Provenance | `GET /api/v1/cases/{case_id}/provenance` |
| Document context | `GET /api/v1/cases/{case_id}/attributes`, `GET /api/v1/uploads/{upload_id}/text` |
| Imaging | `GET /api/v1/modalities`, `GET /api/v1/uploads/{upload_id}/imaging/metadata`, `GET /api/v1/uploads/{upload_id}/imaging/render` |
| Biomarkers | `GET /api/v1/cases/{case_id}/biomarker-trends`, `GET /api/v1/cases/{case_id}/calculations/egfr` |
| Laboratory catalog | `GET /api/v1/catalog/{packages,imaging,lab-tests}`, `GET/POST /api/v1/cases/{case_id}/orders`, `GET/POST /api/v1/cases/{case_id}/lab-reports` |
| Anatomy | `GET /api/v1/anatomy/systems`, `GET /api/v1/cases/{case_id}/anatomy-evidence`, `GET/POST /api/v1/anatomy/registration-reviews` |
| Prognosis and risk | `GET /api/v1/prognosis/capabilities`, `POST /api/v1/prognosis/evaluate`, `GET /api/v1/risk/registry` |
| Evaluation | `POST /api/v1/evaluation/{task}`, `POST /api/v1/evaluation/segmentation/{masks,batch}`, `POST /api/v1/evaluation/detection/coco`, `GET /api/v1/evaluation/runs` |
| Research | `GET /api/v1/analytics/research`, `GET /api/v1/research/traceability` |
| Case sharing | `GET/POST /api/v1/cases/{case_id}/members`, `DELETE /api/v1/cases/{case_id}/members/{user_id}` |
| System | `GET /api/v1/system/{health,readiness,gpu}`, `GET /api/v1/system/audit` (administrators) |

The full contract is at `/docs` (OpenAPI).

Every upload request must include multipart field `deidentified=true`; omission or `false` is rejected. Upload contents require authenticated, case-authorized access.

## Phase 1 completion gate

The acceptance test creates a pseudonymous case, uploads a synthetic de-identified report, verifies the exact 64-character SHA-256, runs the genuine rule-based text processor, then reloads uploads, jobs, findings, source-linked statements, and audit events from persistence:

```powershell
cd D:\project
$env:ENVIRONMENT = "test"
$env:SECRET_KEY = "test-only-secret-key-at-least-32-characters"
$env:DEV_SEED_ENABLED = "false"
& .\.venv\Scripts\python.exe -m pytest backend/tests/test_phase1_persistence_gate.py -q
```

Run the complete local checks with:

```powershell
npm run check
& .\.venv\Scripts\python.exe -m pytest backend/tests -q
$env:SECRET_KEY = "compose-validation-secret-at-least-32-characters"
docker compose config --quiet
```

To record the results that the Validation Center shows under "Test evidence", run:

```powershell
& .\.venv\Scripts\python.exe scripts/record_test_evidence.py
```

This writes `docs/validation/test-evidence.json` from the actual output of pytest, `tsc`, `oxlint` and `vite build`, together with the commit and whether the working tree was clean.

The latest local run on 24 October 2026:

- 107 backend tests passed.
- Type checking was clean.
- Lint reported 12 warnings and no errors; 3 of the warnings are in unreferenced Phase 1 components.
- The production build succeeded, with one chunk-size warning for the lazily loaded 3D viewer (three.js, about 1 MB minified, 276 kB gzip).
- `docker compose config` passed.

The Phase 1 screenshots in `docs/screenshots/` predate the MedTwin 2.0 interface. No browser walk-through has been recorded for the current revision.

## Anatomy assets

`public/anatomy/derived/` (764 MiB) is git-ignored. After a clean clone, regenerate it with the pipeline in `tools/asset-pipeline/`; see `docs/anatomy/README.md` for the steps, licences and fidelity checks. Original GLBs are never modified.

## Docker Compose

`.env.example` contains placeholders only and is intended as the Compose template. Copy it to the ignored `.env`, set a unique `SECRET_KEY`, and optionally fill all three required seed fields:

```powershell
Copy-Item .env.example .env
# Edit .env; do not commit it.
docker compose config --quiet
docker compose up --build
```

The container frontend is published at `http://localhost:5173` by default. Nginx serves the React application, falls back to `index.html` for client-side routes, and forwards `/api/v1` to the canonical backend with a 520 MB streaming upload limit. SQLite data and uploads persist in the named `medtwin_data` volume. `VITE_MEDTWIN_API_URL` should remain blank for this same-origin path; set it only when intentionally serving the API from a different origin.

The backend image contains the model registry and the generated evidence files (traceability matrix, test evidence, anatomy manifest and derivatives, benchmark results). Pass `MEDTWIN_CODE_COMMIT=$(git rev-parse HEAD)` so evaluation runs inside the container record the commit. The frontend image contains `public/anatomy/derived/`, so generate the derivatives before building.

## CI and repository hygiene

`.github/workflows/ci.yml` runs frontend checks, Python 3.12 backend tests, Compose validation, and both Docker builds. The ignore rules exclude local databases, uploads, runtime files, virtual environments, datasets, archives, downloaded upstream repositories, and model checkpoints. Curated application anatomy assets under `public/models` are intentionally tracked with Git LFS.

Do not merge the downloaded medical-AI repositories wholesale. Integrate selected components behind small adapters only after licensing, dependency, checkpoint, split, evaluation, and provenance requirements are satisfied.
