# MedTwin 2.0

MedTwin is a software-only research prototype for authenticated, provenance-preserving review of de-identified clinical evidence. It is not a validated medical device, does not replace a clinician, and must not be used with identifiable patient data in this development phase.

The application uses one backend entry point, `backend/app/main.py` (`app.main:app`), and one versioned API contract under `/api/v1`. The previous standalone backend is archived at `backend/legacy/main_pre_v1.py` and is not a supported server.

Every patient-facing result traces to an uploaded source and a recorded computation. Where evidence or a validated model is missing, the application returns a machine-readable state (`NOT_AVAILABLE`, `INSUFFICIENT_EVIDENCE`, `MODEL_NOT_VALIDATED`, `INDETERMINATE`, `REGISTRATION_UNAVAILABLE`, ...) instead of a value.

## What is operational

- **Workspace:** 16 sections (Overview, Case Workspace, Document Intelligence, Medical Imaging, Biomarker Analytics, Historical Comparison, Live Anatomy Studio, Prognosis Studio, Multimodal Intelligence, Risk & Explainability, Research Analytics, Model Registry, Dataset Registry, Validation Center, Reports, Settings) plus a unified Upload Center, with light and dark themes.
- **Access control:** JWT authentication, case-scoped authorization, case sharing (viewer/editor), rate limiting, security headers, readiness checks and audit history.
- **Uploads:** content-signature checks and SHA-256 storage for PDF, DOCX, TXT, CSV, XLSX, JSON/FHIR, HL7 v2, PNG/JPEG/BMP, DICOM, NIfTI, NRRD, MHA and digital ECG (WFDB `.hea`/`.dat`, CSV). A de-identification attestation is required. Stored files are encrypted at rest with AES-256-GCM whenever a storage key is configured (`MEDTWIN_STORAGE_ENCRYPTION=required` makes it mandatory); files can be versioned or withdrawn without altering the original bytes.
- **OCR:** born-digital text is read directly; scanned PDF pages and photographed reports are read with local RapidOCR at 300 DPI, with tilted rows de-skewed and sideways pages read upright. Text after a line OCR could not read is marked uncertain rather than asserted. A photograph of a printed document is refused by the image models.
- **Documents:** the clinical-text rules baseline `rules-v2.0.0` scopes negation, uncertainty, hypothetical, historical, family and comparison context per clause, so "No evidence of…" or "Rule out…" never becomes a diagnosis. Measurements keep source spans, documented intervals, flags and dates; FHIR Observations and HL7 v2 result messages (OBR/OBX/NTE; patient, visit and staff segments are never read) are imported with their documented codes. All outputs await clinician review; the baseline has not been evaluated on an annotated corpus.
- **Imaging:** DICOM, NIfTI, NRRD and MHA metadata and slice rendering, with HU window presets only when rescale data exist and identifier warnings. Multi-file DICOM series are grouped, ordered by patient position and checked for gaps, duplicates and inconsistent geometry; an assembled series is not yet rendered or passed to a model.
- **Research models (research only, not clinically validated):** seven 2-D image models (GI endoscopy classification and polyp segmentation, coronary angiography stenosis detection and segment segmentation, kidney-stone CT detection, blood-cell microscopy), a 12-lead ECG classifier for digital WFDB/CSV records and a cardiac cine-MRI segmenter for single NIfTI frames run on uploads behind checkpoint-hash, licence and input-contract gates; outputs stay pending human review. The ECG and MRI paths reproduce their held-out predictions (`docs/validation/UPLOAD_INFERENCE_PARITY.md`).
- **Background jobs:** a durable job queue with a separate worker (`python -m app.worker`) and an inline mode for development.
- **Biomarkers:** longitudinal series with registered unit conversions, Δx, Δx%, rate, OLS/Theil–Sen from n ≥ 3 and Mann–Kendall from n ≥ 4. CKD-EPI 2021 eGFR is computed only from documented inputs.
- **Laboratory transcription:** transcription against the test catalog, and investigation orders. A position is computed only against the laboratory's printed interval; without one it is `INDETERMINATE`.
- **Anatomy:** ten system workspaces, 43 generic reference variants plus the Z-Anatomy atlas, structure hierarchy, sections and clinician-confirmed region mapping (`docs/anatomy/README.md`). This is reference anatomy only, never patient anatomy.
- **Prognosis and risk:** a target-trial specification and organ capability registry. Every forecast, scenario, risk score and treatment effect is reported as unavailable, with reasons.
- **Validation Center:** evaluates uploaded held-out predictions in the `MedTwin_2_Validation_Kit` formats. Tasks: classification, multiclass, regression, survival, forecast, lab-extraction audit, segmentation (single pair or ZIP) and COCO detection. Bootstrap CIs are cluster-aware. Each run is bound to dataset, version, split, checkpoint and code commit.
- **Research traceability:** `docs/research/traceability.json` maps the revised draft's claims and equations to code, tests and gaps (`docs/research/implementation_gaps.md`).
- **Registries and reports:** read-only dataset and model registries (every model is blocked from clinical activation), append-only review with four-eyes approval of corrections, and JSON evidence export with SHA-256 plus a printable report.

## What is not operational

- No image, ECG or clinical-language model is clinically activated; the research models above have internal held-out evaluations only, with no external or clinical validation. Of the manuscript's Section X experiments, the image classification, detection/segmentation and PTB-XL runs were executed as internal evaluations; `X-MURA`, `X-DOC-EXTRACTION`, `X-MIMIC-CXR` and `X-FORECAST` have not been run (`docs/research/IEEE_TRACEABILITY_REPORT.md`).
- No forecast, calibrated diagnostic confidence, patient-specific anatomy (L3), validated registration or case-level multimodal fusion is produced.
- Not implemented: EEG/EDF readers, inference on assembled DICOM series, database encryption at rest, patient or caregiver accounts and views, and a browser regression suite in CI. A scripted browser walkthrough exists (`tools/browser-qa/walkthrough.mjs`) but is run by hand and has no approved golden images.
- Docker: CI builds both images and they build locally (Docker 29.9); a full Compose run with migrations, health checks and worker persistence has not been executed.

## Requirements

- Node.js 22.12 or newer.
- Python 3.12. The unqualified `python` command on this workstation selects Python 3.15, so use `.venv\Scripts\python.exe` explicitly.
- Docker with the Compose plugin for the container workflow.
- Git LFS before committing the curated GLB asset.

## Local development

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

## Optional development seed

There are no embedded or fallback credentials. Development seeding is opt-in, is rejected outside `development` or `test`, and requires an explicit username, password, and email. The password must contain at least 12 characters.

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
| Authentication | `POST /api/v1/auth/login`, `GET /api/v1/auth/me` |
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
