# Heterogeneous evidence implementation status

Date: 2026-11-06. This describes the changes for the supplied implementation brief, separately from earlier uncommitted work. No commit, push, deployment, training, clinical activation, or live database migration was performed.

## Audit findings and root causes

The active root is `D:\project`. The running-source architecture is React/Vite plus the canonical FastAPI application `backend/app/main.py`, `/api/v1`, SQLAlchemy, and the existing local/Supabase adapters. The brief's separate Node gateway on 8787 and inference service on 8790 are not the canonical implementation documented in this checkout. They were not invented or substituted for the existing authentication/storage boundary.

`CASE-D-NEURO-CT` does not exist under that exact pseudonymous ID in the local SQLite database examined read-only. Its original 58,899,915.13 score, three uploads, zero examinations and 0/88 review display cannot be reproduced against that record here. The supplied PDF was read directly in disposable OCR storage; a synthetic equivalent was exercised through authenticated API requests. No real patient record was imported into a demo or test fixture.

| Reported failure | Observed cause/evidence | Change or remaining boundary |
| --- | --- | --- |
| Film rejected by native CT model | The RSNA contract accepts axial digital brain-window images; film photographs/montages lack that provenance and geometry. No panel workflow existed. | OpenCV candidate-panel assessment, ordered source rectangles and PNG previews for raster uploads and PDF pages. Film candidates abstain before native-image inference. Classification is an unvalidated heuristic and requires review. |
| Very large OOD score | Actual served checkpoint and reference reproduce finite, very large scores for the supplied film photograph and inappropriate endoscopy. The dominant contribution is input-statistics stage 0, whose PPCA residual variance is approximately 1.04e-5. Five own held-out images score 0.944-1.213 against unchanged limit 2.499984. All model input tensors are finite with the expected normalized range. | No demonstrated 255x input scaling error and no threshold change. Added finite/shape/variance/overflow checks. This smoke check does not prove clinical applicability or recalibrate the reference. Exact original score remains unreproduced. |
| Glued OCR findings | Existing normalization already split many glued words. Laterality was lost in 'right high parietal lobe'; scalp swelling had no dedicated entity rule. | Bounded anatomical-modifier matching, explicit scalp swelling, preserved raw OCR and source offsets. Never infer a parietal brain lesion from scalp swelling. |
| Missing report dates | Full-page OCR can misread or omit the small tilted header date, including O/0 substitutions. | Conditional upper-right header reread for imaging reports, original extraction retained, source rectangles recorded, date candidates requiring review. The supplied PDF now yields matching date candidates on its repeated report pages. |
| No statements verified | Extraction is not human verification. A zero review count is not itself a software defect. | Existing human-review workflow retained. Synthesis exposes pending/confirmed states and approved corrections; it never silently marks extraction as reviewed. |
| Uploads without examinations | Upload association and examination association are distinct. There was no API to attach an existing upload to an examination. | Audited same-case examination linking, explicit same-patient/date attestation, optional matching date-attribute provenance, measurement examination links updated without changing their documented dates. |
| Generic brain anatomy | A report supplies a symbolic site, not a lesion mask, volume or patient-space transform. | Existing atlas and GLBs reused. Affirmed, certain, current report evidence offers 'View reported region' with an explicit unregistered/pending-review caption. Existing reviewed landmark/TRE gate remains; no patient lesion geometry is invented. |
| 0/27 activation eligible | Current registry audit: 27 models; 15 pass research inference gates; 0 pass clinical activation. The RSNA checkpoint exists and is research-runnable, with unverified clinical calibration/activation requirements. | Research and clinical gates remain separate. Checkpoints, licences, hashes and reports are checked using existing registry code. No status was raised to improve counts. |
| 0/33 datasets eligible | The 33-entry path-discovery inventory differs from the later 64-entry task audit, which currently has 14 training-eligible and 14 validation-ready tasks. | Preserve both inventories and their meanings. Task-audit readiness is visible separately. This run did not rescan every dataset, annotation or legal agreement. |
| Fusion blocked with image abstention | Old service retained one finding per modality and required a trained paired fusion model for all case synthesis. | Added a distinct rule-based evidence inventory with all source-linked report statements, image abstentions, per-source reviews, corrections, exact-entity assertion conflicts and missing modalities. Learned diagnostic fusion remains gated. No overall disease confidence is emitted. |
| Prognosis unavailable | Old forecasting service only returned eligibility, and deleted prior evaluations. Single scans provide no quantitative trajectory. | Append-only evaluation history and opt-in persistence/linear research baselines on reviewed, dated, source-linked measurements. Chronological backtests and horizon gates apply. No calibrated intervals, recovery probabilities or disease-specific prognosis are invented. |
| Cross-account/demo isolation | The checkout defaulted to one shared workspace. | Private case boundaries are now the default. Explicit shared deployments remain configurable; guests cannot read other users' cases even in shared mode. Tests cover protected previews, synthesis, queued jobs and guest isolation. |

## Capability and validation matrix

| Capability | Code/UI | Dependencies/checkpoints | Software verification | Validation status and limits |
| --- | --- | --- | --- | --- |
| Raster and PDF film previews | `services/film_processing.py`, `routers/modalities.py`; `FilmPanelPreview.tsx`, `PdfFilmPanels.tsx` | Existing Pillow, NumPy, OpenCV supplied by RapidOCR; PDFium | Synthetic 10-panel and single-panel fixtures, immutable bytes, coordinates, annotations and case authorization | Research viewing heuristic. Glare/perspective are reported, not diagnostically repaired. Panel detection can miss/crop panels; visual review required. No native DICOM claim from raster pixels. |
| Native containers | Existing `imaging_readers.py`, `dicom_series.py`, model adapters | Existing DICOM/NIfTI readers and registered models | Existing regression/parity tests plus unchanged-checkpoint applicability smoke check | Native 2D DICOM is not automatically accepted by a PNG-only classifier; supported volume/series adapters retain their contracts. |
| Clinical document intelligence | Existing `nlp_processor.py`, `ocr_text.py`, `terminology.py`, `analysis_runner.py` | RapidOCR/ONNX, wordninja; existing optional WSL NLP adapters | Synthetic glued report extracts contusion, oedema, negated shift/fracture and scalp swelling, source pages and laterality; supplied PDF read locally | Transparent rules are not validated clinical NLP. Optional MedCAT/RadGraph/scispaCy were not newly trained or clinically validated. Repeated report extraction remains unreviewed. |
| Multimodel inference | `routers/research_models.py`, `services/job_handlers.py`; `MultimodelPanel.tsx` | Existing durable GPU job queue and eligible checkpoints | Batch unavailable-model abstentions, duplicate-model rejection and job authorization tests; existing served-model regression tests | Separate runs only. Probabilities are never averaged without a registered compatible calibration contract. No learned ensemble checkpoint was added. |
| Missing-modality evidence synthesis | `services/evidence_synthesis.py`, `fusion_service.py`, `routers/fusion.py`; `EvidenceSynthesisPanel.tsx` | Existing persisted statements/runs/reviews; no model weights needed | API workflow and persistence tests, source grouping, abstentions, negations, exclusion of inactive evidence and case access | Rule-based concordance, not a disease predictor. Independent image confirmation is not asserted merely because a model ran. Duplicates are not counted as independent confirmation. |
| Schematic anatomy | Existing `anatomy_evidence.py`, `StudioPanels.tsx`, atlas/GLBs | Existing Three.js and labelled reference structures | Existing anatomy/registration tests and frontend checks | Reported region preview only; atlas side/part availability limits the display. Exact lesion boundary, volume and patient registration unavailable. |
| Spatial registration | Existing `registration_service.py` and reviewed landmark-manifest APIs | Real spatial images, valid masks, independent reviewed landmarks and acceptable TRE | Existing numerical and authorization regression tests | Existing research gate reused. No clinical registration or end-to-end patient-specific lesion rendering was validated on the supplied film. |
| Historical comparison | Existing comparison/biomarker services; examination link endpoint in `routers/files.py` | Comparable dated same-patient source evidence | Existing longitudinal tests and new linking/identity tests | No quantitative lesion change from uncalibrated film. 'Clinical improvement' is not inferred from arbitrary numeric direction. |
| Conditional baselines | `services/research_baselines.py`, `routers/forecast.py`; `ResearchBaselinePanel.tsx` | Reviewed numeric observations; no learned checkpoint | Sparse-history abstention, linear/persistence calculations, chronological folds, append-only history | Research prototype: persistence needs 3 distinct reviewed dates; linear needs 5 for at least two held-out predictions. Horizons beyond backtested spacing abstain. No external validation or calibrated prediction interval. ARIMA and supervised prognosis remain unavailable. |
| Reports | `ReportsPage.tsx` and synthesis export | Existing report/export infrastructure | Frontend checks and API synthesis tests | Includes raw/normalized source links and review states; no invented imaging result. |
| Data preservation | Additive migrations in `migrations.py` | Existing database drivers | Synthetic idempotent migration test; rehearsal on read-only backup of local database | 27 tables checked: every original row/column identical after migration of the disposable copy, including all 10 users, 14 cases, 122 examinations, 20 uploads and 149 audit events. Original database not migrated or reset by this task. |

## API additions

All routes retain the existing `/api/v1` prefix and case authorization.

- `GET /cases/{case_id}/evidence-synthesis`: current read-only synthesis.
- `POST /cases/{case_id}/fusion`: persist a versioned synthesis alongside the existing predictive fusion gate.
- `GET /cases/{case_id}/fusion/results/{run_id}`: authorized immutable result snapshot.
- `GET /uploads/{id}/imaging/metadata`: raster input assessment included.
- `GET /uploads/{id}/imaging/film-panels/{panel_id}`: deterministic source crop.
- `GET /uploads/{id}/pages/{page}/film-assessment` and `/film-panels/{panel_id}`: photographed PDF scan-page workflow.
- `PATCH /uploads/{id}/examination`: examination ID, `same_patient_confirmed`, optional `source_date_attribute_id`.
- `POST /uploads/{id}/multimodel`: up to six distinct registered model IDs plus declared input type; durable sequential model runs with per-model abstentions.
- `POST /cases/{id}/forecast`: optional `method` (`persistence` or `linear`) and required same-patient attestation; default remains eligibility-only.
- `GET /cases/{id}/forecast-history`: retained evaluation history.

New nullable columns are `clinical_report_statements.source_page`, `multimodal_fusion_records.evidence_synthesis` and `forecast_records.baseline_analysis`. Migrations are applied by the existing application startup workflow. Existing records are not rewritten.

## Reproduction

Run from `D:\project` using the existing Python 3.12 environment. Keep the managed Vite server; do not start a duplicate frontend process.

```powershell
npm run check
& .venv\Scripts\python.exe -m pytest backend/tests -q --tb=short
& .venv\Scripts\python.exe scripts/audit_heterogeneous_evidence.py --output .cache/registry-audit.json
& .venv\Scripts\python.exe scripts/audit_heterogeneous_evidence.py --output .cache/migration-audit.json --database backend/medtwin.db
& .venv\Scripts\python.exe scripts/diagnose_brain_ct_applicability.py --output .cache/brain-ct-applicability.json
```

The optional audit `--pdf <local-source.pdf>` reads a private source locally in disposable OCR storage. Keep its output under ignored `.cache/`, not in a public repository. `--photograph <local-image>` on the applicability diagnostic only measures input features; it does not perform or persist disease inference.

Final verification: **595 backend tests passed, 4 skipped, 10 dependency warnings in 210.94 seconds**. Frontend typecheck, lint and production build pass; 14 existing lint warnings and the large 3D chunk warning remain. Browser visual verification could not run because the computer-use browser host is unavailable. Detailed final test output is recorded locally in `.cache/medtwin-final-tests.txt` and `.cache/medtwin-evidence-tests.xml`. These are software tests, not diagnostic-accuracy or clinical-validation results.

## Remaining work requiring evidence or deployment access

- Import/link the actual case through an authorized user session; that case ID is absent from the local database inspected here.
- Review its extracted statements, source date and same-patient examination associations. No automated code can substitute for that verification.
- Acquire native spatial imaging and independently reviewed registration evidence for precise lesion geometry.
- Supply appropriate paired/longitudinal cohorts and external evaluation before learned fusion, ARIMA, calibrated intervals or disease-specific prognosis can be considered validated.
- Run a browser walkthrough and the deployment-specific PostgreSQL/Supabase migration/RLS checks in the actual deployment. The local SQLite preservation rehearsal is not proof of remote-database migration behavior.
