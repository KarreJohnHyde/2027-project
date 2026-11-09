# MedTwin implementation and verification status

Date: 2026-11-06. Active root: `D:\project`. This report covers the supplied master brief and the remaining integration work completed after the screenshot fixes. Existing uncommitted work was preserved. No commit, push, deployment, model training or clinical activation was performed.

Follow-up verification is complete: **613 backend tests passed, four skipped; all four browser acceptance checks and frontend checks passed; 17 real application screenshots and four JSON outputs were saved.** See [continued acceptance status](CONTINUED_ACCEPTANCE_STATUS.md) for the subsequent comparison, baseline, film-control and anatomy-navigation repairs, evidence scope and output location. The counts and screenshot limitation in the earlier results section below describe the preceding verification run.

A later pass the same day checked these results on the stored CASE-D record and fixed re-analysis duplicates, secondary-NLP entities from glued OCR, secondary readings counted as findings, the negated-fracture site, unexplained applicability refusals and misleading registry counts: see [CASE-D audit](CASE_D_AUDIT_2026-11-06.md).

The canonical application in this checkout is React/Vite plus `backend/app/main.py`, SQLAlchemy and `/api/v1`. The brief's proposed Node gateway on 8787 and inference service on 8790 are not the canonical running architecture documented here. The existing authentication, storage and routing boundaries were reused.

## Root causes and repairs

The twelve original reported failures, image-preprocessing audit, OOD control scores and prior fixes are documented in [HETEROGENEOUS_EVIDENCE_STATUS.md](HETEROGENEOUS_EVIDENCE_STATUS.md). The photographed-film controls, duplicate OCR findings and misleading completion states are covered in [SCREENSHOT_ISSUES_FIXED.md](SCREENSHOT_ISSUES_FIXED.md).

Further gaps found in this pass:

| Root cause | Actual change |
| --- | --- |
| No single case view connects the supported processing stages | Added typed `GET /cases/{id}/workflow` and `POST /cases/{id}/workflow/process-reports`. The snapshot follows active sources, actual processing runs, source review, examination links, synthesis, atlas associations and saved forecast evaluations. The Case Workspace now presents these stages with actions. |
| Reprocessing a case can duplicate report extraction unnecessarily | Workflow processing skips content hashes already processed from active sources, excludes withdrawn/superseded/unassociated files, and reuses active queue jobs. It processes up to ten pending unique reports per UI request through the existing processor; model input attestations and clinical review are never generated automatically. |
| Development signing keys change on every process import | Development now retains a private signing key beside the SQLite database or at `MEDTWIN_DEV_SECRET_FILE`. Concurrent API/worker startup reuses it. Explicit `SECRET_KEY` takes precedence; production/staging still require a configured key of at least 32 characters. Invalid persisted keys fail instead of being silently rotated. Previously lost ephemeral keys cannot be reconstructed; this change prevents future rotation rather than inventing access to old sessions. |
| Reading forecast eligibility writes a new evaluation | GET forecast routes now use a read-only evaluation. POST remains the explicit persisted action. Existing evaluations are retained. Invalid forecast horizons are rejected on reads as well as writes. |
| Comparing examinations checks case access but lacks explicit pair identity confirmation | The comparison API and UI now require same-patient confirmation for a case with two or more examinations. Changing the selected pair resets confirmation. Comparison state resets when switching cases. The confirmation is recorded in the audit event. |
| Reports omit saved research baseline evaluations and claim no forecast exists | Export schema `medtwin-evidence-export-4.0.0` includes workflow state and the most recent 100 saved forecast evaluations, with their original source series and validation metadata. The printable report distinguishes historical research estimates from unavailable clinically validated prognosis. |
| Repeated inference results on identical source/model versions appear as separate evidence | Synthesis retains the latest matching result and every historical run/upload reference. Different model versions and labels remain distinguishable. Probabilities are not averaged, and statistical independence is not asserted. |
| Brain-case navigation can open a default heart prognosis or retain another case's scenario | Brain workflow links select brain context; other cases require an explicit organ selection. Prognosis state resets on case changes. Stored model-output links follow image versus signal modality. |

## Capability matrix

| Capability and code path | Dependencies / checkpoint | Actual verification | Status / remaining limitation |
| --- | --- | --- | --- |
| Input containers and scan metadata: `imaging_readers.py`, `dicom_series.py`, `routers/modalities.py` | Existing DICOM/NIfTI/NRRD/MHA readers | Existing container, geometry and series regression tests; live digital CT PNG metadata request | Operational readers. A raster's native origin, HU, spacing and patient coordinates cannot be established from its pixels. |
| Film workflow: `film_processing.py`, `FilmPanelPreview.tsx`, `PdfFilmPanels.tsx` | Pillow, OpenCV, PDFium; no diagnostic weights | Synthetic single-panel and montage tests, supplied PDF's redacted derivative, authenticated panel PNG response | Viewing heuristic. Preserves source positions and source marks; it can miss panels. Glare/perspective are limitations, not a validated diagnostic reconstruction. |
| Native/digital imaging research: `model_inference.py`, `volume_inference.py`, `ResearchModelPanel.tsx` | Registry checkpoints, hashes, licences, model-specific preprocessing | Live RSNA held-out digital CT control completed real checkpoint inference with structured multilabel output; existing volume/series/parity tests | Research only. The live control is a PNG, not a native DICOM geometry test or an accuracy study. Whole-slice classification does not produce a lesion boundary. |
| Document intelligence: `nlp_processor.py`, `ocr_text.py`, `terminology.py` | Existing RapidOCR/ONNX, wordninja and optional WSL NLP adapters | Supplied redacted report: 18 statements retained in eight synthesis groups; tests check laterality, contusion/oedema and negated shift/fracture | Rules and OCR remain unvalidated clinical extraction. Optional NLP repositories without valid models do not become inference-ready. Human verification remains explicit. |
| Multimodel inference: `routers/research_models.py`, `job_handlers.py`, `MultimodelPanel.tsx` | Existing compatible models and durable queue | All-abstention batch, continued processing after adapter error, independent result retention and cross-account tests | Operational separate runs. No validated cross-model probability combination or statistical independence is established. |
| Missing-modality synthesis: `evidence_synthesis.py`, `fusion_service.py`, `EvidenceSynthesisPanel.tsx` | Existing source records and review/correction services; no learned fusion checkpoint | Report retained alongside film abstention; repeated-run/source deduplication; no fabricated probability; live report and scan-only API cases | Rule-based evidence concordance. Learned case-level prediction remains unavailable without paired training, compatible encoders and independent validation. |
| Report-to-atlas and spatial support: `anatomy_evidence.py`, `AnatomyStudioPage.tsx`, `registration_service.py` | Existing atlas/GLBs and registration mathematics; eligible segmentation adapters | Existing mapping, correction, registration/TRE tests and source-linked anatomy API | Reported regions are schematic. No verified patient-to-atlas registration was available for the supplied film. Native-grid masks are not silently placed on generic anatomy. |
| Examination and history: `files.py`, `comparison.py`, `comparison_service.py`, `HistoricalComparisonPage.tsx` | Actual linked examinations, source dates and comparable measurements | HTTP linking, source isolation, chronological comparison and new identity-confirmation tests | Source-based descriptive comparison. Missing dates/calibration, incompatible studies and uncertain lesion identity remain explicit. No unsupported clinical progression category is inferred. |
| Conditional forecasting: `research_baselines.py`, `forecasting_service.py`, `ResearchBaselinePanel.tsx` | NumPy; reviewed source-linked numeric history; no disease-specific clinical checkpoint | Existing 1/2/3/5-date tests, chronological backtests and horizon gates; new GET no-write test | Persistence/linear research prototypes with retained history. Sparse qualitative CT evidence yields no trajectory. No unsupported ARIMA fit, clinical recovery/death probability or calibrated interval is produced. |
| Unified workflow and reporting: `case_workflow.py`, `routers/workflow.py`, `CaseWorkflowPanel.tsx`, `ReportsPage.tsx` | Existing services/queue; no extra model or database schema | Combined/document-only/scan-only states, queue reuse, processed-report skipping, authorization and live API checks; frontend type/lint/build | Implemented. Current gates and required review steps are visible; status is not itself clinical validation. Exports label the latest-100 forecast-history scope. |
| Registry integrity: `model_registry.py`, `dataset_registry.py`, task audit | Local artifacts and existing task metadata | Read-only audit: 27 registered models, 15 research-eligible, zero clinically activated; 64 task-audit entries, 14 training-eligible and 14 validation-ready tasks | Exact per-model gates/checkpoint/report paths are in the saved audit JSON. These counts do not prove clinical applicability. The large datasets were not re-indexed or relicensed in this pass. |
| Authentication, data preservation and demo isolation: `local_secrets.py`, `auth.py`, `migrations.py`, existing guest service | Existing JWT/SQLAlchemy and explicit production secret | Two fresh-process key imports, concurrent-start test, unchanged-key JWT verification, cross-account tests; disposable migration audit preserves all 27 original tables' existing rows/columns | Existing account/data records preserved. Original database examined read-only: 10 users, 14 cases, 122 examinations, 20 uploads, 149 audit events. No real patient evidence was added to a demo. |

## Actual results

- Full backend suite: **604 passed, four skipped**, with ten existing Torch/dependency warnings. Final targeted workflow/evidence tests also pass.
- `npm run check`: type checking, lint and production check build pass. Existing lint and large-3D-chunk warnings remain.
- `git diff --check`: no whitespace errors.
- Migration audit: `PASSED_ON_DISPOSABLE_COPY`; original opened read-only; existing rows and columns identical across 27 tables. No new schema migration was needed for this follow-up's workflow/status/session changes.
- The supplied report test remains `CASE-D-NEURO-CT-FIX-VERIFICATION` in isolated test storage. The exact original `CASE-D-NEURO-CT` record and its exact 58.9-million score are absent from the original local database inspected here; they were not claimed as reproduced.
- Separate public-dataset control: `RSNA-HELD-OUT-CT-CONTROL`. The served `brain_ct_rsna_ich_classifier` completed inference on one of its own held-out digital CT PNGs. Outputs are stored separately and do not corroborate the supplied report. This is a functional smoke test, not external validation.
- The authenticated API token remained valid through the test API restart with its retained key. No session credential is included in exported artifacts.
- At this earlier checkpoint, fresh authenticated browser screenshots had not yet been verified. The subsequent browser run completed and saved 17 screenshots; see [continued acceptance status](CONTINUED_ACCEPTANCE_STATUS.md). Earlier screenshots were not relabelled as new screenshots.

Artifacts are saved in `C:\Users\johnn\OneDrive\Pictures\MedTwin_Report_Test_2026-11-06\Workflow_Completion`. The source film PNG there is a **panel preview output**, not a screenshot of the application.

## Reproduction and compatibility

```powershell
npm run check
& .venv\Scripts\python.exe -m pytest backend/tests -q --tb=short
& .venv\Scripts\python.exe -m pytest backend/tests/test_case_workflow.py backend/tests/test_heterogeneous_evidence.py -q
& .venv\Scripts\python.exe scripts/audit_heterogeneous_evidence.py --output .cache/master-implementation-audit.json --database backend/medtwin.db
```

Use the existing managed Vite server. Do not start a duplicate frontend or replace the original database with test storage. The live acceptance run used only `.cache/report-app-test/medtwin.db` and its dedicated test uploads.

API conventions remain `/api/v1`. Comparing an examination pair now requires `same_patient_confirmed: true`. GET forecast routes return an unpersisted preview (`id: null`); POST persists an explicit evaluation. `GET /cases/{id}/forecast-history` retains its existing latest-100 contract. Local development should retain its private signing-key file or configure `SECRET_KEY`; production/staging must use the explicit secret configuration.
