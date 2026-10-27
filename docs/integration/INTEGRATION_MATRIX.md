# MedTwin 2.0 integration matrix

Reconciled 2026-10-25 against the current registries, executed tests, automated Edge
walkthrough, and supplemental visible Chrome inspection. This is software-research
evidence, not clinical validation. The repository must not be shared while the
Git-history privacy blocker remains open.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `IMPLEMENTED_TESTED` | Executed by an automated test, recorded browser walkthrough, or named verification artifact. |
| `IMPLEMENTED_UNVALIDATED` | Workflow runs, but task-specific external/clinical validation is absent. |
| `BLOCKED` | Named authorization, dataset, licence, runtime, or evidence prerequisite is missing. |
| `UNSUPPORTED` | Deliberately unavailable from current evidence/implementation. |
| `NOT_STARTED` | No qualifying implementation or verification has begun. |

Component states such as `READY_UNVALIDATED`, `EXPLORATORY_TRAINING_ONLY`,
`NOT_MAPPABLE`, and `SCHEMATIC_ORGAN_ONLY` do not replace the directive statuses.

## Verified integrated state

| Area | Status | Integrated state and boundary | Evidence |
| --- | --- | --- | --- |
| Release and repository sharing | `BLOCKED` | Current-tree scan is clean, but a PHI-bearing blob remains reachable on both local branches. Zero remotes/tags/stashes is containment, not remediation. No repository/Git metadata may be shared before authorized remediation and a clean history scan. | `docs/security/PHI_RELEASE_BLOCKER.md`, `scripts/privacy_scan.py`, `backend/tests/test_release_privacy.py` |
| Required Downloads archives | `IMPLEMENTED_TESTED` | All 24 named ZIPs have SHA-256 and safe-entry audits; 23 canonical mappings were CRC-verified and one archive atomically extracted 6,795/6,795. Ninety-one extras were audited; two symlink-unsafe archives were not extracted. | `docs/import/ARCHIVE_REPORT.md`, `docs/import/ARCHIVE_MANIFEST.csv`, `dataset_registry/imported.json` |
| Dataset identity/task gates | `IMPLEMENTED_TESTED` | 61 units / 32 tasks: 10 ready, 1 exploratory-only, 21 blocked; 11 training-eligible. Licence, privacy, label, grouping, duplicate/leakage, split, and sample gates are recorded. | `dataset_registry/tasks.json`, `docs/data/DATA_READINESS_MATRIX.md` |
| Research registry | `IMPLEMENTED_UNVALIDATED` | 21 entries / 11 research-runnable / 0 clinically activatable. Seven are gated 2-D upload models; the ECG classifier, both survival baselines and the cardiac MRI segmenter are evaluation-only. Every runnable bundle has immutable checkpoint/report evidence appropriate to its scope. | `model_registry/models.json`, `model_registry/validation_status.json`, `docs/validation/models/` |
| Research image inference | `IMPLEMENTED_TESTED` | All seven `image_2d` workflows completed through Medical Imaging and the worker queue with explicit input-type confirmation. Classifications and source-pixel boxes/masks rendered with research-only warnings. Native BMP upload/display/inference passed for C-NMC. | `docs/anatomy/BROWSER_WALKTHROUGH.md`, `backend/tests/test_research_inference.py` |
| Volumetric segmentation | `IMPLEMENTED_UNVALIDATED` | Generic NIfTI 3-D manifest/train/evaluate/checkpoint/resume. After the owner's recorded authorization (2026-10-25) it trained a cardiac cine-MRI segmenter on 298 retained cases / 149 patients: 50 frozen test patients, macro Dice 0.750, LV ejection-fraction MAE 9.1 points against reference masks; evaluation-only. | `docs/imaging/VOLUMETRIC_SEGMENTATION_PIPELINE.md`, `backend/tests/test_training_volumetric.py` |
| Durable queue | `IMPLEMENTED_TESTED` | Database jobs support worker execution, leases, retries, cancellation, idempotency, GPU quota, browser reload persistence, and cross-process restart recovery. | `backend/tests/test_job_queue.py`, `docs/anatomy/BROWSER_WALKTHROUGH.md` |
| Documents and scanned-PDF OCR | `IMPLEMENTED_UNVALIDATED` | Embedded/scanned documents execute; RapidOCR records page/engine provenance. The strict CER/WER evaluator binds actual bytes and persists hash-only/no-raw-text provenance. No representative independent medical gold set has run. | `backend/tests/test_ocr.py`, `backend/tests/test_ocr_evaluation.py`, `docs/clinical/NLP_EXTRACTION_EVALUATION.md` |
| Clinical NLP/numerical labs | `IMPLEMENTED_UNVALIDATED` | Rules v2 preserves spans, assertion/negation, certainty, temporality, experiencer, anatomy, values, units, intervals, and sources; optional scispaCy executes. Strict span/context evaluation, request IDs, structured/censored labs, deduplication, and raw-text exclusion pass. No expert-corpus performance claim exists. | `backend/tests/test_clinical_nlp_evaluation.py`, `test_request_ids.py`, `test_catalog_and_lab.py` |
| Clinician corrections | `IMPLEMENTED_TESTED` | Typed correction proposals are append-only. Original evidence remains unchanged and the UI/API explicitly record `PROPOSED_NOT_APPLIED`. | `backend/tests/test_human_review_workflow.py`, `docs/anatomy/BROWSER_WALKTHROUGH.md` |
| Historical/longitudinal analytics | `IMPLEMENTED_TESTED` | Dated, source-linked, compatible observations are deduplicated and compared with exact deltas/provenance; censored/duplicate observations are excluded. Missing links or incompatible units cause abstention. No causal/progression claim is inferred. | `backend/app/services/comparison_service.py`, `backend/tests/test_measurements_and_longitudinal.py` |
| Ten-system anatomy | `IMPLEMENTED_TESTED` | One WebGL engine exposes 43 variants across all 10 systems. Edge rendered 43/43 with counters, pixel evidence, and orbit interaction; visible Chrome exposed the ten-system UI. Assets remain generic/reference anatomy. | `public/anatomy/manifest.json`, `docs/anatomy/ASSET_QA.md`, `docs/anatomy/BROWSER_WALKTHROUGH.md` |
| Evidence-to-anatomy mapping | `IMPLEMENTED_UNVALIDATED` | Unreviewed research findings are `NOT_MAPPABLE`; clinician confirmation may establish only a schematic organ association. Source boxes/masks never become atlas/patient coordinates without reviewed registration. | `backend/app/services/anatomy_evidence.py`, `backend/tests/test_research_inference.py` |
| Prognosis Studio | `IMPLEMENTED_TESTED` | Independent route and scenario panels abstain with reason codes. PBC/HF baselines are not exposed as patient forecasts. No numeric risk, future image/geometry, or treatment effect is emitted. | `docs/forecast/SCENARIO_ELIGIBILITY.md`, `docs/anatomy/BROWSER_WALKTHROUGH.md` |
| Risk/evaluation tooling | `IMPLEMENTED_TESTED` | Classification, detection, segmentation, regression, forecast, survival, labs, OCR, and clinical-NLP metrics have provenance/reportability gates. Server-computed digests bind reportable inputs; altered/missing bytes remain exploratory. | `backend/tests/test_evaluation_context.py`, `test_metrics_experiment_evidence.py`, `test_ocr_evaluation.py`, `test_clinical_nlp_evaluation.py` |
| Upload encryption/deletion | `IMPLEMENTED_TESTED` | AES-256-GCM upload objects support rotation, legacy migration and tamper rejection; scoped deletion is implemented. Database pages/backups, legal schedules, media handling, and tamper-evident audit retention are not production-complete. | `docs/security/ENCRYPTION_TESTS.md`, `docs/security/RETENTION_AND_DELETION.md` |
| Browser acceptance | `IMPLEMENTED_TESTED` | Edge passed 17/17 desktop, 17/17 responsive, 43/43 anatomy, 7/7 image workflows, 11/11 reports (`artifacts/verify/20261025T140444Z.json`), labs, corrections, OCR/NLP controls, request-ID correlation, hash-only provenance, queue persistence, and prognosis abstention. Zero console/page/failed-request errors. | `docs/anatomy/BROWSER_WALKTHROUGH.md`, `docs/testing/EXECUTED_TEST_RESULTS.md` |
| Docker packaging | `BLOCKED` | Client 29.9.2 / Compose 5.6.1 installed; base and worker configuration pass. Linux engine pipe absent, so no build/start/migration/health/runtime result is claimed. | `docker-compose.yml`, `backend/Dockerfile` |
| IEEE reconciliation | `IMPLEMENTED_TESTED` | Exactly 56 claims: 28 tested, 18 partial, 5 implemented-not-validated, 3 proposed-only, 2 unsupported. Internal research evidence remains distinct from clinical claims. | `docs/research/traceability.json`, `docs/research/IEEE_TRACEABILITY_REPORT.md` |

## Seven browser-runnable 2-D research models

All are `IMPLEMENTED_UNVALIDATED`: checkpointed software and same-source internal
evaluation exist, but no external/clinical activation evidence exists.

| Model | Input/task | Internal held-out evidence | Browser state | Scientific boundary |
| --- | --- | --- | --- | --- |
| `gi_kvasir_v2_classifier` | ENDOSCOPY, 8-class | n=1,202; accuracy/macro-F1 0.926 | PASS; 8 probability rows | Source lacks patient IDs; internal only |
| `gi_gastrovision_27class_classifier` | ENDOSCOPY, 27-class | n=1,225; accuracy 0.737; macro-F1 0.553 | PASS; 27 rows | Exploratory; rare classes under-supported |
| `angiography_stenosis_detector` | ANGIOGRAPHY, detection | n=300; mAP 0.0618; AP50 0.2029 | PASS; source-pixel boxes | Limited/uncalibrated; no external test |
| `kidney_stone_detector` | CT slice, detection | n=196; mAP 0.2312; AP50 0.6286 | PASS; source-pixel boxes | Session-aware split; patient IDs unavailable |
| `angiography_syntax_segmenter` | ANGIOGRAPHY, segmentation | n=300; vessel Dice 0.6829; mean image Dice 0.3070 | PASS; source-pixel mask | Sparse/absent segment support; pixel-space only |
| `gi_kvasir_seg_polyp_segmenter` | ENDOSCOPY, polyp segmentation | n=120; Dice 0.7679; IoU 0.6696 | PASS; source-pixel mask | Same source; patient independence unavailable |
| `hematology_cnmc_all_classifier` | MICROSCOPY/BMP, binary | n=1,867 / 28 clusters; accuracy 0.807; macro-F1 0.790 | PASS; 2 probability rows | Filename clusters not independently verified identities |

## Evaluation-only research bundles

| Model | Evidence | Boundary |
| --- | --- | --- |
| `ptbxl_ecg_baseline` | n=2,163 / 1,881 patients; macro AUROC 0.917, macro AUPRC 0.805 | Research-only upload inference for digital records; no external cohort |
| `pbc_mayo_survival_cox` | n=104 hold-out; Harrell's C 0.786; integrated Brier 0.105 | Population-specific baseline-covariate survival, not longitudinal patient forecasting |
| `heart_failure_survival_cox` | exploratory n=90; Harrell's C 0.671; Brier worse than Kaplan-Meier | No demonstrated calibration skill or patient forecast |

## Boundaries that must remain enforced

- Research output begins pending human review and not mappable; source-pixel geometry is
  never an atlas coordinate.
- Historical comparison reports observed arithmetic only, not progression, prognosis,
  or causality.
- Prognosis stays abstaining until a lawful repeated longitudinal dataset, specified
  endpoint/horizon/population/time zero, chronological evaluation, validated integrated
  model, and (for treatment effects) target-trial estimand exist.
- No registry model is clinically activatable.
- Archive-05 remains excluded pending privacy review; licence-blocked tasks remain
  blocked regardless of file presence.
- A clean working tree does not make Git history releasable. Compose parsing does not
  constitute a Docker runtime pass.

## Remaining blockers

| Blocker | Required evidence to close it |
| --- | --- |
| PHI history/transcript disposition | Owner authorization, approved evidence-retention decision, purge/new sanitized repository, clean history scan, and transcript handling. |
| Dataset privacy/licences | Archive-05 disposition plus authoritative terms, provenance, grouping, and split evidence for blocked tasks. |
| Clinical NLP/OCR accuracy | Lawful independent annotations and executed prespecified span/context/numeric/CER/WER evaluation. |
| Clinical model activation | Representative external data, applicability/OOD and calibration analysis, acceptance criteria, clinical oversight, and prospective safety evidence. |
| Patient-specific registration | Reviewed landmarks/transforms, coordinate frames, fitting/held-out separation, TRE threshold, and observer/external evaluation. |
| Numeric prognosis/treatment effects | Repeated longitudinal outcomes, endpoint/population/horizon/time zero, temporal hold-out, validated integrated model, and causal target-trial specification. |
| Database/backup encryption | Verified encrypted database deployment, migration, backup/restore, key rotation, and recovery. |
| Docker runtime | Available engine plus build/start/migration/health/worker/persistence/security/shutdown evidence. |
