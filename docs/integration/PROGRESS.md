# MedTwin integration progress

> **Historical snapshot.** This phase record predates the current master-directive implementation. Current status is maintained in `docs/development/MASTER_PROGRESS.md` and `docs/implementation_status.md`.

## Phase

Foundation recovery and unification are complete enough to support one
authenticated evidence workflow. Repository and dataset cataloging, truthful
model/dataset registries, a transparent document baseline, source-linked numeric
comparison, human review, JSON export, and a four-asset generic L1 anatomy
selector are present. The authenticated browser path has been exercised against
the current backend through persisted evidence, review, export, reload, and all
four anatomy selections. Learned-model experiments and clinical validation have
not started.

## Completed

- Established `backend/app/main.py` as the canonical FastAPI application and
  archived the competing backend implementation.
- Connected the React client to the authenticated `/api/v1` contract for users,
  cases, examinations, uploads, jobs, findings, statements, measurements,
  reviews, provenance, anatomy, model/capability status, and dataset evidence.
- Replaced fixed fallback credentials with environment-controlled development
  seeding.
- Implemented content-addressed upload storage, full SHA-256 provenance,
  de-identification attestation, persisted jobs/evidence, and reload retrieval.
- Implemented TXT, embedded-text PDF, and DOCX parsing plus a transparent rule
  baseline. The baseline emits no calibrated probability and requires human
  review.
- Added explicit numeric extraction with exact source spans, units, source file,
  and examination provenance.
- Added evidence-preserving longitudinal comparison for compatible statement
  and numeric evidence without diagnostic or causal interpretation.
- Added clinician/admin review that appends decisions, preserves original
  outputs, and writes audit history.
- Added client-side, versioned JSON evidence export with a research-only notice.
  A browser export was verified as schema `medtwin-evidence-export-1.0.0` with
  2 uploads, 2 jobs, 2 findings, 2 statements, 12 measurements, and 8
  provenance records at export time.
- Added a strict model/capability registry: 11 records, 0 validated, 0
  activation-eligible.
- Added an authenticated read-only dataset registry: 33 catalog records, 0
  training-eligible, 0 validation-eligible, and no mutation/activation endpoint.
- Curated four attributed generic L1 GLBs into one selectable viewer. All four
  match their registry byte sizes and SHA-256 values and pass GLB v2 structural
  parsing. Each was also selected and visibly rendered in the browser after
  bounds normalization, without console errors; one upstream `THREE.Clock`
  deprecation warning remains. Anatomical/provenance audits remain pending.
- Exercised the authenticated browser workspace against the current backend.
  Two synthetic de-identified reports were submitted through the authenticated
  API, completed as 2 text jobs with 2 findings and 2 statements, produced 12
  source-linked measurements, and remained present after application reload.
  Current audit history contained 9 events. Their SHA-256 values were
  `4f4fd1fdf5a38ca569ce4f07eed661bdef6f72234e13973bda1a68bfccf93b44`
  and
  `fdae8b1ffce67657da6fc46e6d874060154e64c626d18760fa0091e9af9a1e56`.
- Verified longitudinal comparison of those reports produced 6 compatible
  arithmetic deltas with no interpretation. An append-only synthetic
  `REJECTED` review preserved the original label and was retained in audit
  history.
- Completed 120/120 synthetic de-identified report workflows over HTTP with
  persisted/reloaded SHA-256, measurements, findings, and provenance; 0 failed
  and all temporary state was removed.
- Completed 1200/1200 measured static catalog HTTP requests with response-byte
  validation and 0 failures.
- Added Docker/Compose and CI definitions while keeping datasets, checkpoints,
  environments, dependencies, and generated state outside normal source
  tracking.

## Files created

Key artifacts created or now present for this phase:

- `model_registry/models.json`
- `dataset_registry/datasets.json`
- `scripts/audit_datasets.py`
- `backend/app/services/model_registry.py`
- `backend/app/services/dataset_registry.py`
- `backend/app/routers/registry.py`
- `backend/app/routers/datasets.py`
- `backend/tests/test_model_registry.py`
- `backend/tests/test_dataset_registry.py`
- `backend/tests/test_measurements_and_longitudinal.py`
- `backend/tests/test_human_review_workflow.py`
- `benchmarks/report_workflow_benchmark.py`
- `benchmarks/results/report-workflow-benchmark-20261023-223734.json`
- `benchmarks/results/http-benchmark-20261023-224119.json`
- `public/models/registry.json`
- `public/models/ATTRIBUTION.md`
- `public/models/medtwin_l1_heart.glb`
- `public/models/medtwin_l1_respiratory.glb`
- `public/models/medtwin_l1_brain.glb`
- `public/models/medtwin_l1_digestive.glb`
- `docs/integration/DATASET_AUDIT.md`
- `docs/integration/WORKSPACE_INVENTORY.md`
- `docs/integration/FILE_REGISTRY.json`
- `docs/integration/COMPONENT_REGISTRY.json`
- `docs/screenshots/current/` browser acceptance screenshots

## Files modified

Principal integration surfaces modified during this phase include:

- `src/App.tsx`
- `src/services/api.ts`
- `src/components/DigitalTwin3D.tsx`
- `backend/app/main.py`
- `backend/app/routers/__init__.py`
- `backend/app/routers/analysis.py`
- `backend/app/routers/cases.py`
- `backend/app/routers/comparison.py`
- `backend/app/routers/files.py`
- `backend/app/routers/reviews.py`
- `backend/app/services/document_parser.py`
- `backend/app/services/file_storage.py`
- `backend/app/services/nlp_processor.py`
- `backend/app/models/entities.py`
- `backend/app/schemas/entities.py`
- `backend/Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `.env.example`
- `.gitignore`
- `.gitattributes`
- `.github/workflows/ci.yml`

## Services integrated

- Canonical authenticated FastAPI API and persistent SQLite development store.
- React/Vite evidence workspace using the authenticated API rather than static
  browser-seeded clinical results.
- Document parsing and transparent clinical-text/numeric rule processor.
- Case-scoped longitudinal comparison and provenance services.
- Append-only human-review workflow preserving original evidence.
- Read-only model/capability activation-gate service.
- Read-only dataset evidence-registry service.
- Curated generic L1 anatomy registry and selectable Three.js/React Three Fiber
  viewer.
- JSON evidence export in the client.

External MedCAT, scispaCy, RadGraph, SemEHR, MONAI task inference, Metriport,
TwinWeaver, Foresight, and other supplied applications are not runtime-integrated
services; they remain isolated candidates, asset sources, or references.

## Commands executed

- `py -0p` and environment-specific Python/import checks for `.venv`,
  `.venv-blender`, and `.venv-medtw`.
- PyTorch CUDA availability, allocation, matrix multiplication, torchvision,
  torchaudio, and MONAI source smoke checks.
- `npm run check`: exit 0 after the latest UI fixes, with 5 existing React lint
  warnings and the Vite bundle-size warning for a chunk over 500 kB.
- `.\.venv\Scripts\python.exe -m pytest backend\tests -q`: 51 passed in
  22.78 seconds.
- `.\.venv\Scripts\python.exe -m compileall backend\app`: completed cleanly.
- `.\.venv\Scripts\python.exe -m pytest backend\tests\test_dataset_registry.py -q`
- `.\.venv\Scripts\python.exe scripts\audit_datasets.py`
- `.\.venv\Scripts\python.exe benchmarks\report_workflow_benchmark.py` using
  its recorded defaults: 20 workflows per repeat, concurrency 1 and 4, and
  three repeats per concurrency.
- `.\.venv\Scripts\python.exe benchmarks\http_benchmark.py` using 200 measured
  requests per repeat, concurrency 1 and 8, and three repeats per concurrency.
- `docker compose config --quiet` with a temporary `SECRET_KEY`: passed.
- Read-only GLB header/JSON-chunk/checksum validation for the four curated
  assets.
- Authenticated browser acceptance against the current backend for reload,
  evidence/audit history, longitudinal comparison, human review, JSON export,
  and all four anatomy selections. Uploads for this acceptance run used the
  authenticated API because the browser file chooser was blocked by the Chrome
  extension's `Allow access to file URLs` permission.

## Tests passed

- Complete backend suite: 51 passed.
- Frontend `npm run check`: exit 0 after the latest minor UI fixes. It reported
  5 existing React lint warnings and a Vite chunk-size warning; neither caused
  failure.
- Backend Python byte-compilation check: clean.
- Dataset-registry focused contract tests: 5 passed, covering authentication,
  exact payload preservation, detail/404 behavior, absence of mutation methods,
  and fail-closed missing-artifact behavior.
- Synthetic de-identified report workflow benchmark: 120 attempted, 120
  completed, 0 failed, failure rate 0.0, temporary state removed.
- Static catalog benchmark: 1,200 attempted, 1,200 completed, 0 failed, with
  HTTP success and exact response-byte validation.
- Docker Compose configuration validation passed; image build/run remains
  unperformed because the Docker runtime is unavailable.
- Four curated GLBs: 4/4 valid GLB v2 containers with matching registry hashes,
  JSON chunks, scenes, nodes, meshes, and declared Meshopt/quantization
  extensions.
- Dataset audit: all 33 named paths cataloged without scan truncation; generated
  JSON parsed and required safety/readiness fields were checked.
- Numeric extraction, longitudinal comparison, and human-review acceptance tests
  exist and exercised their provenance-preserving contracts during integration.
- Browser acceptance authenticated to the current backend, reloaded the same 2
  uploads and 9-event audit history, displayed 2 completed text jobs, 2
  findings, 2 statements, and 12 source-linked measurements, produced 6
  compatible non-interpretive arithmetic deltas, preserved the original label
  after an append-only `REJECTED` review, verified the versioned JSON export,
  and visibly rendered all 4 registered GLBs without console errors.

## Tests failed

- Complete backend suite: 0 of 51 failed.
- Focused dataset-registry tests: 0 failed.
- Workflow benchmark: 0 of 120 failed.
- Static catalog benchmark: 0 of 1,200 failed.
- GLB structural checks: 0 of 4 failed.
- Browser file selection remains untested: the Chrome extension blocked the
  chooser solely because `Allow access to file URLs` was not enabled. The two
  accepted files were therefore uploaded through the authenticated API and then
  verified and reloaded in the browser. This is not a completed browser-upload
  test and is not evidence of an application upload failure.
- Docker BuildKit validation/build could not execute because the Docker Desktop
  Linux engine pipe is unavailable; this is an unperformed check, not a passing
  or failing image build.
- Frontend check: 0 errors. Its 5 existing React lint warnings and the Vite
  chunk-size warning remain non-failing cleanup/performance work.

## Unsupported components

- MURA classifier, PTB-XL/MIT-BIH ECG classifier, brain model, lung model, GI
  model, and DeepSA inference: no complete executable/evaluated artifact.
- MedCAT, scispaCy, and RadGraph runtime adapters: missing/conflicting
  dependencies, model packs/checkpoints, ontology rights, or evaluation corpora.
- SemEHR runtime: legacy Python 2.7 source only.
- Learned image/ECG predictions: validation and preview paths exist, but no
  validated checkpoint is configured.
- Paired multimodal fusion: no legitimately paired cohort and no held-out
  evaluation.
- Patient-specific L2/L3 mapping: no reviewed landmark manifest, held-out TRE
  evidence, patient geometry, or validated reconstruction.
- Forecasting: no defined validated target/unit/horizon with adequate
  chronological data.
- OCR for image-only PDFs, signed PDF evidence export, FHIR exchange, and live
  HIE interoperability.
- Clinical diagnosis, treatment recommendation, real-time operation, HIPAA
  compliance, regulatory approval, and clinical effectiveness claims.

## Remaining blockers

- Enable the Chrome extension's `Allow access to file URLs` permission or use a
  browser-test harness that can set the file input, then complete the actual
  browser upload path. Do not treat the authenticated API upload plus browser
  verification as a completed browser-upload test.
- Automate the now-manually-verified browser paths and add job failure, WebGL
  fallback, logout, narrow-screen, and exported-download regression coverage.
- Restore a working Docker engine and build/run both images from Compose.
- Resolve dataset source/version/license and patient/study-disjoint splits. The
  current dataset registry has 0 training-eligible and 0 validation-eligible
  entries.
- Repair duplicate COCO annotation IDs and overlapping Kvasir roots through
  versioned derived manifests without rewriting originals.
- Complete DICOM de-identification/privacy review and install only the
  modality-specific libraries required by the selected task.
- Acquire the official licensed MURA and PTB-XL data or formally change the
  first experiment; neither is presently registered as a usable local dataset.
- Create a complete artifact bundle before enabling any learned model.
- Complete threat modeling, malware/file sandboxing, encryption/secret rotation,
  tenant isolation, tamper-evident audit retention, backup/recovery,
  retention/deletion, human-factors testing, and independent privacy,
  regulatory, security, and clinical-safety review.

## Next implementation task

First unblock or harness browser file selection and turn the current manual
acceptance receipt into repeatable browser tests. Address the existing frontend
warnings and restore Docker build/run verification when the engine is available.
Then begin one reproducible model experiment only after its licensed dataset
and patient-aware split are available. The preferred next research task remains
MURA study-level
normal/abnormal classification; its dataset version, license, patient/study
split manifest, preprocessing version, checkpoint hash, calibration, thresholds,
held-out predictions, evaluation report, and model card must all exist before UI
activation.
