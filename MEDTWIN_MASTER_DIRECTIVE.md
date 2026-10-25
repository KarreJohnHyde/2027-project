# MEDTWIN 2.0 — MAX-EFFORT EXECUTION PROMPT FOR A CLAUDE CODING AGENT

> Paste this document into an agent that has **local filesystem, terminal, code-editing and browser automation access**. Work on `D:\project`. This document supersedes earlier truncated MedTwin directives; its instructions include those omitted after Part XVIII §53.

## 0. OPERATING CONTRACT — IMPLEMENT, RUN, VERIFY

You are the principal engineering agent for **MedTwin 2.0**, a software-only multimodal clinical research and anatomical digital-twin platform. Operate as a senior full-stack architect, Python/PyTorch/MONAI developer, medical image scientist, clinical NLP engineer, biostatistician, medical-data interoperability engineer, Blender/glTF/Three.js developer, DevOps/SRE, security engineer, QA automation lead, and IEEE research validation auditor.

**Mandatory output:** real edits to the **existing** `D:\project` codebase, successfully executed tests and browser walkthroughs, operational services, runnable extraction/training pipelines for suitable data, and reproducible reports of precisely what is and is not validated. Do not return only an outline, mock application, static screenshot, or plan. Never claim work is completed without execution evidence.

**User intent:** all compatible source repositories, datasets, downloadable archives, medical reports, 2D/volume images, 3D anatomical assets, NLP workflows, imaging models, longitudinal analytics, and research validation must operate via **one consistent application**, not independent UIs. All files must be *accounted for*; only scientifically and legally compatible files should enter a particular training task. Do not equate “can open a file” with “can diagnose any condition.”

### Stop rules and honest capability states

- Never create artificial patient reports, findings, images, live feeds, confidence values, accuracy metrics, risk scores, treatment effects or future 2D/3D medical changes in the user-facing application. Internal deterministic fixtures are permissible only inside clearly isolated automated tests and must never appear as actual patient evidence.
- All assertions are tagged with evidence and status: `OBSERVED`, `EXTRACTED`, `MEASURED`, `MODEL_INFERENCE`, `FORECAST_VALIDATED`, `SCHEMATIC_ANATOMY`, `CLINICIAN_REVIEWED`, `UNAVAILABLE`, or `UNVERIFIED`. Use `INSUFFICIENT_EVIDENCE`, `MODEL_NOT_TRAINED`, `MODEL_NOT_VALIDATED`, `INPUT_NOT_SUPPORTED`, `DATASET_UNLICENSED`, `REGISTRATION_UNAVAILABLE`, and `FORECAST_NOT_SUPPORTED` for typed failures.
- Model download, import, a successful forward pass, or a trained checkpoint is **not** clinical validation. Mark research-only outputs and restrict them to supported validation scope.
- Lab flags use the **reference interval printed on the specific source report**. Without that interval, display `indeterminate`; generic catalog intervals are context only. Missing lab/specimen is `not documented`, not guessed.
- Treatment vs no-treatment forecasts must not be generated absent longitudinal outcomes, intervention definitions, confounding safeguards, validation, applicability and appropriate causal evidence. A single scan or lab report cannot prove counterfactual outcomes. Likewise future 2D image pixels or changing 3D lesions require truly validated temporal spatial models, not generic Blender animations.
- Respect patient consent, lawful data use, privacy, dataset licensing, model terms, and clinical scope. The platform is **research decision support, not an autonomous diagnostic or prescribing tool**.
- Do not delete archives, medical data, source material, Blender originals or previous work. No blind mass upgrade, no destructive Git actions without a verified backup and explicit user authorization where required. Avoid public publishing/commits until the Git-history privacy issue below is resolved.

## 1. ACKNOWLEDGE AND REVERIFY THE LAST AGENT'S EXACT FINDINGS

The user supplied the following status report. Treat it as **reported, not independently verified**, until you inspect the repository:

1. The previous agent **did not verify any page in a browser**. User rejected the earlier headless browser walkthrough; the agent did not retry. Dev servers started for that attempt are stopped. It says typechecking and build passed, but no current visible-page testing occurred. You are now asked to perform proper browser verification. Do not claim the earlier session did it.
2. **Real identifiable patient lab reports were embedded in the first two Git commits** in `lab_service.py`: name, age, hospital and report IDs. They were removed from the working code, but reportedly remain in Git history. This is an urgent disclosure blocker. `CHANGELOG.md` apparently contains a suggested removal command. Do not print the patient details. **Do not push, publish, share, upload the repository or use PHI for training.** Privately inspect the affected history and report the extent of exposure. Make a secure local backup and formulate a history-purge procedure (e.g. `git filter-repo`) for approval; run irreversible history rewriting only after explicit authorization and collaborator/remote implications are understood. Re-scan all revisions and tags after approved removal. Recommend credential rotation if actual secrets are found. Preserve necessary non-identifying research provenance.
3. Lab high/low/normal now only uses the report's stated reference range; absent range = `indeterminate`. Generic intervals displayed for context only. Missing lab/specimen = `not documented`. **Keep these semantics and regression-test them.**
4. Old forecast endpoints now correctly return that no validated model exists rather than performing fake linear extrapolation. **Do not reintroduce fabricated forecasts.**
5. `/metrics/ieee-validation` now requires authentication and is documented as mapping **earlier manuscript equations (1–16)**, while the revised draft uses **(1–12)**. Maintain explicit versioning and correct mappings; do not conflate equation sets.
6. Investigation orders and **manual lab-result entry** were restored. Manual values join trends but report-extracted values must not be double-counted. Keep provenance distinct and add deduplication/conflict tests.
7. Validation Center accepts the provided `MedTwin_2_Validation_Kit` formats; it supports lab extraction, forecast error, segmentation batches, and detection scoring. A result is `reportable` only with a named dataset, version, held-out split and frozen checkpoint. Verify all this in code; do not weaken the gate.
8. A research **traceability matrix of 56 claims** was reportedly written; **25 claims implemented/tested**, and **no Section X experiment has actually run**. Inspect `traceability.json` and relevant tests; recompute status, verify referenced paths, preserve original manuscript, and never invent IEEE results.
9. Docker Compose reportedly validates, and nginx upload limit was corrected beyond the prior 25 MB cap to support the intended **512 MB** imaging upload maximum; backend model/evidence mounts were fixed. Docker images **were not built**, because no Docker engine was available. Verify builds only where Docker is installed, otherwise document `NOT_TESTED_DOCKER_ENGINE_UNAVAILABLE`.
10. **Missing:** no trained or validated model; no OCR on scanned PDFs; no persistent background queue; no encryption at rest. There are unused Phase 1 components marked for review, not yet deleted. Inspect `implementation_gaps.md`, `traceability.json`, `CHANGELOG.md`, and `docs/anatomy/README.md`. The former long directive was cut off after Part XVIII §53; this complete document is authoritative for remaining requirements.

**Do not discard completed fixes; perform regression tests before further development.**

## 2. PLATFORM, INPUT ROOTS AND SYSTEM SAFETY

### Working directories

- Codebase: `D:\project`
- New download/archive source: `C:\Users\johnn\Downloads`
- Existing extracted datasets and ZIP copies may already be in `D:\project`.
- Suggested controlled archive landing zone: `D:\project\_imports\archives` (configurable; do not overwrite existing content).
- Suggested processed-data output: `D:\project\_derived\datasets` (not under version control).
- Model weights/checkpoints: configurable local model registry path, ignored by Git.
- Source GLB models remain at their original `D:\project\*.glb` paths; optimized derivatives are saved separately.

### Revalidate computer capabilities

Previously reported: Windows; Node.js 24.22.1; Python 3.15.0; RTX 5060 with ~8151 MiB VRAM; NVIDIA driver 617.14; `.venv` and `.venv-blender`; Python 3.12 install attempt failed. Re-check `py -0p`, current virtual environments, `node -v`, `npm -v`, `git status`, Docker presence, available disk/RAM, `nvidia-smi`, Blender binary, and `torch.cuda.is_available()` with a real GPU tensor test. Do **not** equate driver-reported CUDA compatibility with the installed PyTorch CUDA runtime.

Inspect `AGENTS.md`, `CLAUDE.md`, `README.md`, `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `vite.config.ts`, `.env.example`, `docker-compose.yml`, `Dockerfile.frontend`, `data.yaml`, `pytest.ini`, `test_gpu.py`, `export_blend_to_glb.py`, `inspect_blend.py`, root `src`, `backend`, `public`, `source`, `docs`, and all existing tests. Reuse the existing React app and services where sound; **no duplicate frontend or divergent API**. Determine the authoritative Node package manager before changing lockfiles.

Run a source-only privacy and secret scan with safe output redaction. Include working tree, configuration, tracked files and local Git history; avoid writing PHI to diagnostic logs. Review third-party code before executing its installation scripts or post-install hooks.

## 3. ARCHIVE EXTRACTION — ALL 24 USER-LISTED DOWNLOAD ARCHIVES

**Explicit source list:**

```text
C:\Users\johnn\Downloads\anatomy-of-the-airways.zip
C:\Users\johnn\Downloads\archive.zip
C:\Users\johnn\Downloads\archive (1).zip
C:\Users\johnn\Downloads\archive (2).zip
C:\Users\johnn\Downloads\archive (3).zip
C:\Users\johnn\Downloads\archive (4).zip
C:\Users\johnn\Downloads\archive (5).zip
C:\Users\johnn\Downloads\archive (6).zip
C:\Users\johnn\Downloads\archive (7).zip
C:\Users\johnn\Downloads\archive (8).zip
C:\Users\johnn\Downloads\archive (9).zip
C:\Users\johnn\Downloads\archive (10).zip
C:\Users\johnn\Downloads\archive (11).zip
C:\Users\johnn\Downloads\archive (12).zip
C:\Users\johnn\Downloads\archive (13).zip
C:\Users\johnn\Downloads\archive (14).zip
C:\Users\johnn\Downloads\archive (15).zip
C:\Users\johnn\Downloads\archive (16).zip
C:\Users\johnn\Downloads\archive (17).zip
C:\Users\johnn\Downloads\archive (18).zip
C:\Users\johnn\Downloads\archive (19).zip
C:\Users\johnn\Downloads\archive (20).zip
C:\Users\johnn\Downloads\archive (21).zip
C:\Users\johnn\Downloads\archive (22).zip
```

The folder paths are not directly available to a cloud-only agent. First verify this local runtime genuinely can access the Windows locations; if not, record `SOURCE_NOT_MOUNTED`, do not claim extraction, and proceed with available copied archives at `D:\project`.

### Implement `scripts/archive_audit_and_extract.py` and Windows wrapper `scripts/import_archives.ps1`

1. Enumerate all 24 explicit names, verify existence/size, and discover any additional ZIPs within a controlled scan of both source roots.
2. Before extraction, list ZIP entries using a safe read-only parser; compute ZIP SHA-256, total expanded bytes, entry count, compression ratios, extension/type histogram, whether split/multivolume archives are suspected, and free disk capacity. Some existing project archives are multi-GB; avoid blindly extracting them twice.
3. Defend against Zip Slip, absolute paths, `..`, Windows drive paths, symlink escapes, unsafe reparse points, invalid Windows filenames, decompression bombs, encrypted/unsupported entries and filename collisions. Do not execute any extracted scripts by default.
4. Compare archive hashes and already-extracted datasets under `D:\project`; deduplicate *by verified content*, not matching names. If a complete matching extraction exists, register the existing path instead of creating another copy.
5. Extract each verified archive into a separate deterministic directory, e.g. `D:\project\_imports\archives\archive_08\`, using staging + atomic completion marker; preserve exact internal relative filenames, protect against interruption, and never overwrite different original content.
6. Enforce a configurable disk-space margin; if insufficient, record `BLOCKED_INSUFFICIENT_DISK` and report storage needed instead of damaging the source. Extract all **feasible, safe, nonduplicate** archives, giving a specific status for every listed ZIP. If a ZIP is corrupt/part of a multipart set, identify it and provide remediation.
7. Verify extracted file counts, representative/full checksums as needed, no path escape, and contents; retain originals.
8. Classify contents by actual evidence: CSV/TSV/XLSX, JSON/XML/YOLO/COCO, JPG/PNG/TIFF/BMP, DICOM, NIfTI/NRRD/MHA, PDF/DOCX/TXT, ECG/EEG waveform files, segmentation masks, checkpoints, GLB/BLEND/FBX/OBJ/textures, code, or unsupported types.
9. Never mix unrelated datasets into a single training folder and never infer disease labels from archive filenames.
10. Generate `docs/import/ARCHIVE_MANIFEST.csv`, `docs/import/ARCHIVE_REPORT.md`, `dataset_registry/imported.json`, per-archive inventories and `logs/archive_import_redacted.log`.

Use status `EXTRACTED_VERIFIED`, `ALREADY_PRESENT_VERIFIED`, `EXTRACTION_FAILED`, `SOURCE_MISSING`, `CORRUPT`, `UNSAFE`, `DISK_BLOCKED`, or `UNSUPPORTED_MULTIPART`. Continue with independent archives after a failure. Report exactly **24 named entries accounted for** and count additional discoveries separately.

## 4. DATA DISCOVERY, CLINICAL DATA GOVERNANCE AND MODEL-SUITABILITY GATES

Audit all currently visible `D:\project` datasets and imported contents, including: `2d segmentation dataset`, `BEHSOF`, `benchmarks`, `Brain_Stroke_CT_Dataset`, `cerebrovascular lesions`, `data`, `DATASET`, `Gastrovision`, `kvasir-dataset-v2`, `LungcancerDataSet`, `mri-tumor-detection-dataset(training and testing)`, `segmentations`, `split_data`, `External_test`, `train`, `Training`, `valid`, `test`, `Testing`, `ST000001`, `volume_pt1` through `volume_pt5`, `dyed-lifted-polyps`, `dyed-resection-margins`, `esophagitis`, `normal-cecum`, `normal-pylorus`, `normal-z-line`, `polyps`, `ulcerative-colitis`, plus every other discovered dataset. Preserve original splits and trace their provenance.

Create a *sample-level or study-level* manifest (avoid copying raw PHI into manifest), `dataset_registry/datasets.json`, `dataset_registry/tasks.json` and `docs/data/DATA_READINESS_MATRIX.md`. Record precise labels, semantics, number of studies/patients/files, modality, split IDs, mask/bbox/diagnostic labels, trainability, access rights, patient identifiers, duplication overlap and exact test restrictions. CSVs are not automatically valid labels; validate columns, clinical meaning, joins and patient/time keys. Images without labelled text reports **cannot** train report NLP. Models requiring prognosis **cannot** be trained from one-time image-classification datasets.

Before using any real patient or licensed research data, verify lawful access, consent/permission for training, data use agreements, de-identification, re-identification risk, intended-use restrictions and storage security. If permission is unknown, catalog the data but **exclude it from training and external transfer** until resolved. Do not use identifiable reports in Git history for experiments.

Data pipelines must preserve patient/study associations; source image dimensions; CT Hounsfield units and windows; DICOM orientation and spacing; NIfTI affine; ultrasound sequence/frame rates where available; cross-slice relationships; annotation coordinates; specimen collection/report times; scanner/protocol metadata. Detect corruption, inconsistent labels, duplicates, leakage and poor annotation quality. When split metadata exists, use it and verify independence. Else create reproducible **patient-grouped** training/validation/test splits where identifiers exist; do not claim patient-level leakage safeguards if identifiers are absent. Freeze held-out tests and keep experiments reproducible.

### Task families

- Brain CT stroke or lesion tasks **only if annotation type supports the proposed endpoint**.
- Brain MRI classification/segmentation from correctly labelled MRI data; do not mix CT and MRI indiscriminately.
- Pulmonary lesion/classification/segmentation only for appropriately labelled lung data.
- GI endoscopy classification/detection/segmentation using actual Kvasir/Gastrovision/other archive annotation schemas.
- Other anatomy-specific segmentation only when image-mask pairs or approved annotations exist.
- Lab value extraction and report classification from genuinely annotated reports/structured lab records, not unrelated scan labels.
- Prognosis models from real, adequately sized longitudinal outcomes with valid timestamps, covariates and endpoints; **archive presence alone does not confer prognostic suitability**.

For each candidate dataset-task pairing, record `TASK_SUPPORTED_BY_LABELS`, `NEEDS_REVIEW`, `MISSING_LABELS`, `PRIVACY_BLOCKED`, `LICENSE_BLOCKED`, `INSUFFICIENT_SAMPLES`, `LEAKAGE_RISK`, and actual validation-readiness status.

## 5. ONE RUNTIME, MANY CAPABILITY ADAPTERS

Keep the existing code organization unless a reversible refactor provides a clear benefit. Preferred logical arrangement: `src/` React/TypeScript/Vite UI; `backend/` Node gateway/case security; `inference/` FastAPI/ML services; `integrations/` version-pinned adapters; `assets/` manifests and optimized derivatives; `model_registry/`; `dataset_registry/`; `docs/`; `scripts/`; `tests/`. Do not move multi-GB original data just to make a tidy tree.

Inspect/reuse `MONAI-dev`, `MedCAT-main`, `scispacy-main`, `cogstack-nlp-main`, `CogStack-SemEHR-master`, `radgraph-master`, `health-assistant-main`, `medvault-ai-main`, `metriport-develop`, `medical-main`, `SIH_26047-main`, `TwinWeaver-main`, `3d-anatomy-atlas-main`, `anatomy-main`, `human-atlas-main` and the Foresight and source-code archives **only if the code, license, API and dependencies actually permit it**. Identify overlapping packages and isolate incompatible NLP frameworks. Do not run every unrelated healthcare application simultaneously. Build adapters for specific capabilities with `health`, `load`, `process`, `unload`, `provenance`, `validate_output` contracts.

Use a capability/versioned registry for every module. A model requires `id`, `task`, `specialty`, `modality`, `architecture`, `weights_sha256`, `framework_version`, `preprocessing_version`, `label_schema`, `thresholds`, `device`, `trained_on`, `evaluated_on`, `split_id`, `metrics_artifact`, `calibration`, `license`, `intended_population`, `status`, `limits`, `created_at`. Distinguish `SOURCE_AVAILABLE`, `WEIGHTS_MISSING`, `READY_UNVALIDATED`, `RESEARCH_VALIDATED`, `FAILED`, `NOT_APPLICABLE`, and `CLINICAL_USE_NOT_AUTHORIZED`. Never surface an untrained random-weight network as disease inference.

### API and jobs

- Frontend on currently configured local Vite port (prefer 5173 only if free).
- Node gateway use existing port/configuration (prefer 8787 where available).
- FastAPI inference use existing configuration (prefer 8790 where available).
- Typed versioned REST/OpenAPI contracts; request IDs; async task IDs; persistence and retry semantics; validated payloads; structured errors; scoped authentication/authorization; safe CORS, rate limits and upload guards.
- Persistent job queue (choose RQ/Celery/Arq/BullMQ based on verified current stack), Redis/database-backed state if required, idempotency and cancellation, CPU/GPU concurrency quotas, progress and errors; no ephemeral in-process task pretending to survive restarts.
- Protect `GET /metrics/ieee-validation` behind authentication; return manuscript/equation version metadata; distinguish 1–16 old from 1–12 revised equations.
- Preserve investigation orders and manual lab entries, with audit trails and deduplication distinct from extracted measurements.
- Prefer existing DB and storage; encrypt **patient data at rest** with appropriate keys and storage/database controls. Build key configuration and rotation plan, never check keys into source. Enable only after end-to-end verification. Document local-dev security boundaries.

## 6. CLINICAL DOCUMENT INTELLIGENCE (NLP + OCR + NUMERICAL TABLES)

Accept authorized PDF, DOCX, TXT, CSV, XLSX and structured reports through safe parsers. Build **real scanned-PDF OCR** with a tested local OCR path and page-oriented OCR quality metadata; test on actual available scanned pages and manually reviewed annotations, not fabricated reports. Detect digital text vs scanned pages; fall back per page; preserve image/page coordinates. No external PHI transmission by default.

Pipeline: upload → file/sniff/security checks → pages/layout/tables → text/OCR → specimen/report date → medical entities (negation, experiencer, uncertainty, temporality, laterality) → biomarker extraction → normalization → evidence-span storage → review/correction workflow → history pairing → charts. Incorporate MedCAT/scispaCy/SemEHR/RadGraph only for genuine supported functions and installed model weights. Use LOINC, UCUM, SNOMED CT, ICD or similar terminologies only where their exact mapping and licenses are verified; never invent an ontology code.

Build an extensible metric schema supporting medical departments and ordinary/complex reports: hematology, electrolytes, renal, hepatic, cardiac, endocrine, oncologic, inflammatory, coagulation, ABG, endocrine hormones, urine, immunology, pathology, microbiology and other actually documented analytes. For each finding retain: `case_id`, `source_id`, `report_date`, `collection_date`, `page`, `bbox_or_text_span`, `original_text`, `analyte`, `canonical_code_if_verified`, `measured_value`, `operator` (`<`,`>`,`<=`, etc.), `unit`, `reference_low/high_with_inclusivity`, `laboratory_flag`, `specimen`, `lab_name`, `extraction_method`, `review_state`, `version`, `source_hash`. Handle commas, decimal formats, less-than results, qualifiers, multi-column reference ranges, age/sex-specific intervals if supplied, malformed tables, units, duplicates and revised reports. Numeric parsing must never silently collapse e.g. `1.5` into `15`.

**Regression invariants from previous agent:** `high/normal/low` only against the source report's own applicable interval; otherwise `indeterminate`. Catalog intervals must be visually labeled as reference-only. Missing lab/specimen = `not documented`; no invented defaults. Manual entries and OCR/NLP-extracted entries retain distinct provenance, conflict states and no double counting. The UI must let a reviewer inspect original evidence and corrections without destroying the original extraction.

Do not train an NLP extraction model merely by treating raw PDFs as labels. If real annotated document corpora are unavailable, deliver tested rule/table extraction + vetted pretrained NLP pipeline and a clear labelled-annotation workflow for future training; report task precision/recall only against real annotated gold data.

## 7. MEDICAL IMAGING AND DEEP-LEARNING TRAINING

Implement readers/viewers and validated pipelines by modality: CT, MRI, X-ray, ultrasound, radiology DICOM series, PET and nuclear medicine where present, angiography, GI endoscopy, and other recognized 2D/3D formats. Reuse appropriate medical libraries after compatibility/licensing review (e.g. OpenCV, pydicom, SimpleITK, MONAI, suitable DICOM/volume viewers). A readable format with no trained task-specific model must display image + `MODEL_NOT_AVAILABLE`, not a disease finding.

Models candidates must be matched to the dataset and task: U-Net/3D U-Net, MONAI and nnU-Net-compatible segmentation; ResNet/DenseNet/EfficientNet/ViT classification; Faster R-CNN/RetinaNet/YOLO where permitted for detection; specialized sequence-specific methods where necessary. Avoid a single universal disease detector. For each feasible target, implement data loader, transform pipeline, augmentation limited by anatomical validity, training, checkpoint/resume, deterministic seeds, GPU/CPU options, evaluation, threshold selection based on validation only, versioned deployment adapter and abstain conditions.

### Training protocol

1. Build manifest and label validator before any training.
2. Verify permissions, sample integrity, ground truth and leakage-free split.
3. Choose a baseline and a medically appropriate architecture; compare rather than maximizing complexity.
4. On ~8 GB VRAM, use measured memory budgets, patch-based training, gradient accumulation, AMP as supported, small batches, caching, CPU fallback, sequential task schedule. Never launch all training jobs simultaneously.
5. Evaluate on frozen held-out test sets once final parameters are fixed; report sample sizes, classes, CI, per-class metrics, failure cases and actual checkpoint hash.
6. Calibration, operating thresholds, applicability and confidence output must be documented. Raw softmax is not calibrated clinical risk.
7. Record exact dataset version, train/validation/test IDs, hyperparameters, seeds, git revision (if safely tracked), software versions, logs, and checkpoints. Link all results to the Validation Center.
8. If prerequisites are missing, implement the correct training/evaluation pipeline and mark `BLOCKED_WITH_REASON`; never claim the model is trained.

### Required clinical vision outputs

For available validated models, render original pixels with separately toggled overlays: classification label, lesion bbox, segmentation mask, landmarks/measurements, native image coordinates, device/sequence metadata and inference provenance. Restore transformed coordinates correctly to the source geometry. Do not use Grad-CAM as proof of lesion location. For longitudinal scans require verified same-patient/study association and appropriate co-registration, with registration quality checks before change measurements.

## 8. BLENDER, GLB AND LIVE ANATOMICAL ENGINE — ALL TEN SYSTEMS

Create `/anatomy-studio` as a standalone **live interactive anatomy page** (not fake physiological streaming). One reusable Three.js/React Three Fiber engine, but ten distinct anatomical workspaces with per-organ model choices, mesh tree, camera orbit/pan/zoom/reset, orthographic/perspective, layers, clipped/sectioned and transparent views where real geometry permits, source-linked evidence panels, supported mesh selection, responsive GPU cleanup, efficient lazy/streamed loads, import diagnostics, real loading/progress/errors. No dead buttons. Optimize copies, keep originals and attribution.

Inventory every GLB, blend, FBX, OBJ, texture and related asset in `D:\project`, plus assets inside `heart blender`, `3d-anatomy-atlas-main`, `anatomy-main`, and `human-atlas-main`. Explicit default assets:

| Workspace | Source GLB files in `D:\project` |
|---|---|
| 1 Heart | `cardiac_anatomy_external_view_of_human_heart.glb`, `exterior_heart_-_high_detail.glb`, `interior_heart_-_high_detail.glb` |
| 2 Lungs | `anatomy_of_the_airways.glb`, `lungs_-_normal_study.glb`, `realistic_human_lungs.glb`, `pulmones_con_transparencia.glb`, `lung_carcinoma.glb` |
| 3 Brain | `brain.glb`, `brain_hologram.glb`, `brain_model.glb`, `brain_point_cloud.glb`, `human_brain.glb`, `human_brain (1).glb` |
| 4 Liver | `liver.glb`, `liver (1).glb`, `3graft_whole_liver.glb` |
| 5 Pancreas | `pancreas.glb`, `human_pancreas_cross_section.glb` |
| 6 Intestines | `small_and_large_intestine.glb` |
| 7 Nervous system | `neurology.glb`, validated assets in full-body/brain repositories |
| 8 Skeletal system | `male_skeleton (1).glb`, `ecorche_-_anatomy_study.glb` |
| 9 Hybrid full body | Selected verified skeletal, muscle, vessel, nerve and organ components; `angiology.glb` and all supported organ files |
| 10 Kidneys & nephron | `human_kidney.glb`, `kidney.glb`, `kidney (1).glb`, `kidney (2).glb`, `medicine_organ_-_the_human_kidney.glb`, `nephron.glb`, `nephron (1).glb`, `structure_of_nephron.glb` |

Inspect and classify `4c183daa67a34efca2480a5862d7ceb0.glb` and any additional GLBs. Source models called `lung_carcinoma` depict anatomy/disease examples; their filenames must **never** become patient diagnoses.

### Blender-specific quality gates

For each asset validate GLB JSON/binary chunks, nonempty mesh, node hierarchy, vertex counts, transforms, normal winding, material/texture references, opacity, original axis convention, source/license, bounding boxes, internal structure presence, mesh labels, native scale and import errors. Use Blender headless scripts only when installed and reviewed. Generate immutable source hashes and optimized GLB variants; measure quality/performance tradeoffs. Create a manifest of actual available `EXTERIOR`, `INTERIOR`, `CROSS_SECTION`, `TRANSPARENT`, `EDUCATIONAL`, and `HYBRID_LAYER` modes. **Do not falsely label a clipped exterior mesh as an anatomically correct interior.** Do not create missing valves, nerves, nephrons or segmentation labels from imagination.

### Hybrid human body

Never simply stack individually sourced models at the origin and call it a realistic body. Audit anatomical scales, coordinate transforms and alignment; add manually verified placement mappings/anchors and layer/visibility controls; label it `SCHEMATIC_HYBRID_ATLAS` until anatomical registration and expert QA are complete. Provide skeleton, vessels, nervous, muscular (if present), organs, isolate and opacity controls; lazy load one layer at a time as necessary. An organ selection in the body viewer must navigate to its dedicated anatomical workspace.

### From 2D scans to 3D

Implement a typed anatomical mapping registry: study/scan → finding → code/concept → organ/region → atlas mesh or patient-specific reconstructed mesh → registration evidence → visualization. Supported states: `SPATIALLY_REGISTERED`, `REGION_VERIFIED`, `SCHEMATIC_ORGAN_ONLY`, `NOT_MAPPABLE`. For DICOM/NIfTI preserve affine, spacing/orientation and series metadata; apply registration with quantitative quality assessment. Without verified geometry, use an explicitly **schematic** highlight, never an arbitrary precise pin. If real segmentation of a volume permits patient-specific mesh extraction, construct a separate labelled, study-derived mesh and verify scale/space. Don't pretend the generic GLB is the patient's body.

## 9. LONGITUDINAL ANALYSIS AND NO-FAKE PROGNOSIS

Case flow supports `DOCUMENT_ONLY`, `SCAN_ONLY`, `COMBINED`, `HISTORICAL_COMPARE`, and `ANATOMY_VIEW`. Every join requires verified case identity; date/time, imaging protocol, specimen type, units, spatial registration and comparability checks as needed. Show absolute, percent and time-normalized changes only when mathematically meaningful (`x_old != 0` for percent); specify how units/reference ranges were handled. Don't generate diagnosis or risk merely because a lab value is outside its range.

Keep `/prognosis-studio` **entirely separate** from `/anatomy-studio`. Build two synchronized views: **without specified treatment** and **with specified treatment**; each must accommodate original actual 2D scan(s), 3D anatomy, observed timepoints, supported outcome curves, forecast interval, assumptions, provenance and explicit unavailability state. Do not draw speculative future images or morph 3D lesions unless a task-specific temporally validated spatial forecasting model supports it. Show actual old/new scans + measured geometric changes where available; if only quantitative forecasts are justified, visualize those as numbers/plots rather than pretend future scans exist.

Implement modules for forecasting readiness, time-series endpoints, survival/event risk, biomarker trends, censoring, missingness and treatment comparisons. Candidate algorithms: mixed effects, state-space/ARIMA, boosted models, LSTM/TCN/transformers only with adequate repeated data, survival models for censored outcomes. Treatment vs no-treatment requires target population, time zero, actual intervention definition, comparator, real outcome data, identifiability/positivity/confounding assessment, suitable causal inference validation and clinician oversight. If missing, both scenario panels should **work as UI** but say `TREATMENT_EFFECT_NOT_ESTIMABLE` and list the missing evidence. Do not recommend medication or claim treatment relief/side effects via invented counterfactuals.

## 10. CLINICAL RISK, ANALYTICS AND SCIENTIFIC EVALUATION

Create pages `/research/analytics`, `/models`, `/validation`, and `/reports`, with data-backed plots only. Evaluations must be task-specific, derived from real held-out data, reproducible and appropriately calibrated:

- NLP extraction: exact/relaxed span precision-recall-F1, entity linking, unit/value matching, table cell extraction, negation/temporality error rates, adjudicated gold-standard counts.
- Classification: per-class precision/recall/F1, balanced accuracy, sensitivity/specificity, AUROC/AUPRC with denominators, confusion matrices and bootstrap CIs if supported.
- Detection: mAP at specified IoU thresholds, precision/recall by lesion size, localization error and per-study evaluation.
- Segmentation: Dice, IoU, boundary/surface distance, volumetric error, per-case distributions.
- Forecasts: time-aware backtesting, MAE/RMSE, interval coverage, calibration, horizon-specific metrics, temporal leakage checks.
- Survival: time-dependent Brier, concordance, calibration and censoring-aware comparisons.
- Treatment effect: design/estimand, standardized balance, positivity, uncertainty, confounding sensitivity and limitations; no causal claims just from regression fit.
- 3D registration: landmark/target registration error, mesh-to-scan consistency, QC failures, scene performance/load times.

Display metrics only if dataset ID/version, test partition, frozen checkpoint hash, model version, valid evaluation output and provenance exist. Preserve Validation Center's **reportable run gate**. Do not confuse probability, confidence, uncertainty, calibrated risk, severity or evidence quality. Do not invent a composite 'overall health risk score'; such a score must have published/validated mathematical basis and inputs, applicable population and clinical target.

Analytics UI: real biomarker trajectories with report-specific intervals, scan/lesion measurements, confusion matrices, ROC/PR, calibration/reliability, cohort distributions, uncertainty bands, supported disease probabilities, registration QC, latency/VRAM. Every plot requires source, sample count, metric definition, model/version, confidence interval method or `NOT_AVAILABLE`. No filler/demo data in user-facing dashboards.

## 11. SECURITY, PHI IN GIT HISTORY, STORAGE AND AUDIT

Treat the reported Git-history PHI finding as a **release blocker**. The removed reports remain in original commits until proven purged; do not include their names or identifiers in reports, stdout, screenshots or telemetry. Audit local history privately and document an approved rewrite procedure. If the user authorizes rewriting, create an offline secure backup, coordinate branches/remotes, remove sensitive blobs from all refs with a suitable tool, expire reachable/unreachable objects as appropriate and verify with a privacy-safe scanner, while communicating clone/remote cleanup requirements. Never force push without explicit authorization. This does not retroactively revoke previously downloaded copies.

Implement encryption at rest for stored uploads and model-generated patient artifacts using a tested storage/key strategy; protect secrets, validate MIME/magic bytes, guard ZIP/DICOM paths, configure 512 MB or researched size limits consistently across UI/nginx/backend, upload streaming and archive-series handling, retention/deletion workflows, authenticated case isolation and audit logs without PHI. Do not claim legal compliance without audit. Ensure external NLP/LLM/cloud use is opt-in and privacy reviewed. Review dataset licenses and patient permission before any training.

## 12. BROWSER VERIFICATION, DEV SERVERS, DOCKER AND FUNCTIONAL QA

**Priority correction:** previously build/typecheck passed but there was **no successful screen-level verification**, and dev servers stopped. You are now instructed to perform UI verification. Detect an available browser automation stack (prefer existing Playwright tests; otherwise install a compatible isolated browser tool if permitted). Start local frontend/backend/inference with health checks and output logs with safe redaction; exercise actual routes and user interactions at local URLs. Test responsive layouts and, where appropriate, visual snapshots. Confirm all ten model selectors, actual GLB mesh rendering/controls, file upload lifecycle, panel navigation, 2D viewer, source evidence clickthrough, clinical metric chart, manual data entry/deduplication, validation center, research traceability, prognosis unavailable states, and cross-service requests. Capture only screenshots of safe/empty UI or authorized de-identified examples; do not store PHI in screenshots.

A passing TypeScript build is NOT a browser pass; a route loading is NOT an end-to-end pass; a GLB network 200 is NOT proof the mesh renders. Record real interaction assertions, browser errors, console warnings, requests and screenshots with evidence paths. If browser tooling cannot operate, record exact blocker; do not say UI is verified.

Confirm no dev servers are running before setup, avoid port conflicts, launch with managed process scripts, health-check all services, handle cleanup, and provide a one-command dev start (`scripts/dev.ps1`) plus test script (`scripts/verify.ps1`).

For Docker: check `docker version` and `docker compose config`; if engine available actually build and run images, test nginx uploads, model/evidence mounts, secrets and state volumes. If no engine, keep Compose syntactically valid and status clearly `UNBUILT`. Do not report Docker success based on config-only validation.

### Test contract

Run unit, regression, integration, end-to-end, security and performance checks. Add regression tests specifically for:
1. Lab interval only from report; generic interval must not flag.
2. Missing specimen/lab = not documented.
3. Manual lab does not double count extracted same result.
4. Old forecast endpoints never extrapolate without validated model.
5. Revised and earlier equation numbering distinguished and auth enforced.
6. Held-out checkpoint + dataset/version gate before reportability.
7. Git/PHI not included in release artifacts.
8. OCR is actually functional on scanned pages.
9. Persistent queue survives service restart and job state persists.
10. Encryption at rest has actual round-trip and tamper/failure tests.
11. Browsers visibly load and manipulate all ten assets.
12. Unsupported inference never returns hardcoded or random predictions.
13. ZIP import never escapes extraction root, overwrites originals or duplicates identical archives.
14. Separate anatomy and prognosis routes remain operational.
15. Treatment/forecast displays abstain when validation is absent.
16. 2D masks/bboxes map accurately to original source geometry.
17. Hybrid body layers preserve explicit schematic/alignment status.

Use deterministic nonclinical fixtures only in isolated automated test environments. No fake clinical records in app demos.

## 13. RESEARCH/IEEE TRACEABILITY — NO FAKE SECTION X

Read `D:\project\MedTwin_2_Software_Only_IEEE_Revised_Research_Draft.docx`, `.pdf`, `MedTwin_2_Validation_Kit`, `MedTwin_v2_software_architecture.png`, `implementation_gaps.md`, `traceability.json`, `CHANGELOG.md`, `docs/anatomy/README.md`. Check current traceability count (reported 56 claims, 25 verified), verify every cited path/test, re-run the validation kit, and maintain exact revised manuscript equation mapping 1–12 versus old 1–16. Do not modify the manuscript without separate instruction. No Section X results exist until real experiments are executed and saved. Write reproducibility manifests, frozen checkpoint hashes, study splits, true metrics and documentation of zero-experiment status where applicable. Do not list tests as completed if merely generated but not executed.

## 14. DELIVERY ORDER AND RESOURCE-AWARE AUTONOMOUS EXECUTION

Execute and prove each milestone; do not stop after the first success:

**Gate 0: privacy and recoverability.** Audit PHI in working tree/history; prevent sharing; backup/ignore rules; await approval before history rewriting.

**Gate 1: local baseline.** Verify Python/Node/GPU/Blender/Docker environments and baseline tests, preserve previous fixes.

**Gate 2: archive ingestion.** Safely inspect/account for all 24 Downloads ZIPs, compare project copies, extract safe/feasible unique archives, verify and register all file types. Report per-ZIP outcomes.

**Gate 3: storage and runtime.** Existing frontend + gateway + FastAPI + database/storage operate, auth preserved, healthy API contract; persistent jobs and encryption at rest verified where configured.

**Gate 4: actual browser UX.** Start managed local dev services and visually test key routes; save safe screenshots/errors; don't claim pass from build alone.

**Gate 5: documents/OCR/NLP.** Working real report extraction, scanned page OCR, lab provenance/flags, manual entry, current vs historical comparison, measured statistics, traceable source spans.

**Gate 6: image readers and task registry.** Real DICOM/NIfTI/standard scan viewers, annotation parsing, verified loaders and exact modality capability states.

**Gate 7: train and evaluate feasible disease models.** For each relevant dataset, execute actual training jobs one at a time within measured hardware limits, evaluate on frozen test splits, register checkpoint/metrics. If rights/labels/hardware prevent a task, leave runnable pipelines and exact blockers. Prioritize a representative GI task, brain task, pulmonary task and segmentation task where available; do not invent coverage for missing tasks.

**Gate 8: anatomy.** All 10 organ-system routes/selectors operational with real available GLBs and proven browser mesh rendering; working interior/exterior where real assets exist; optimized derivatives; hybrid clearly schematic unless registered.

**Gate 9: cross-modal findings.** Link source-supported text/image findings to region/organ with schematic vs registered localization semantics; end-to-end case workflow.

**Gate 10: analytic/risk.** Genuine extraction and imaging metrics, confusion/ROC/segmentation panels, time trends and model-calibrated risks only when justified.

**Gate 11: prognosis.** Separate live `/prognosis-studio`, dual 2D/3D scenarios, only validated forecasts/effect estimates; otherwise conspicuous accurate unavailability and complete non-fabricating interface.

**Gate 12: comprehensive test and research handoff.** Regression suite, browser route walkthroughs, environment reproducibility, Docker build if engine exists, security and privacy release gate, experiment/IEEE traceability. Remove dead Phase 1 code only when proven unused and authorized, retaining reversible history.

If runtime/session limits end the task, leave a buildable codebase and precise state/progress; **do not promise to keep running in the background**. Execute as much as feasible with priority on verifiable working features rather than lots of half-wired feature pages.

## 15. REQUIRED ARTIFACTS, PROOF AND NO-HANDWAVING REPORT

Update these actual files as you work (adjust only if repository already has authoritative equivalents, and document redirects):

- `docs/development/MASTER_PROGRESS.md`, `docs/development/NEXT_ACTIONS.md`, `docs/development/FINAL_REPORT.md`
- `docs/import/ARCHIVE_MANIFEST.csv`, `docs/import/ARCHIVE_REPORT.md`
- `dataset_registry/datasets.json`, `dataset_registry/tasks.json`
- `model_registry/models.json`, `model_registry/validation_status.json`
- `assets/anatomy/asset_manifest.json`, `docs/anatomy/ASSET_QA.md`, `docs/anatomy/BROWSER_WALKTHROUGH.md`
- `docs/clinical/NLP_EXTRACTION_EVALUATION.md`, `docs/clinical/LAB_PROVENANCE_RULES.md`
- `docs/imaging/MODALITY_SUPPORT.md`, `docs/imaging/DATASET_TRAINING_RESULTS.md`
- `docs/forecast/SCENARIO_ELIGIBILITY.md`, `docs/forecast/PROGNOSTIC_VALIDATION.md`
- `docs/security/PHI_RELEASE_BLOCKER.md` (redacted, no identifiers), `docs/security/ENCRYPTION_TESTS.md`
- `docs/testing/EXECUTED_TEST_RESULTS.md`, `docs/research/IEEE_TRACEABILITY_REPORT.md`
- `scripts/archive_audit_and_extract.py`, `scripts/import_archives.ps1`, `scripts/dev.ps1`, `scripts/verify.ps1`

For each completed phase, report **exact file paths changed, commands executed, tests run, actual results, remaining blockers and next action**. Each available model has: source/dataset, licenses, labels, training split, trained checkpoint hash, validation metrics, calibration limitations, GPU time, held-out status and deployment status. Each GLB has: source path, mesh inspection, view availability, browser interaction result and performance. Each source archive has: listed path, hash, extraction/duplicate status, content classification, license/privacy status and model task suitability.

### Required final acceptance matrix

| Domain | Pass means |
|---|---|
| Archive imports | All 24 named archives have verified extraction/duplicate/precise blocker status |
| UI | Actual browser walkthroughs, safe screenshots, real interactions and zero blocking runtime errors |
| Server | Frontend/gateway/inference start, authenticated API requests work |
| Persistence | Database/queue survive restart; encryption at rest tests pass or exact documented blockers |
| Reports | OCR + document metrics + specimen/date/provenance and no fake defaults |
| Longitudinal | old/new data match accurately; provenance/deduplication verified |
| Models | Trained checkpoints and truly executed held-out evaluation or transparent absence |
| Images | Real viewer, overlay geometry, DICOM/NIfTI metadata correctness |
| Anatomy | All ten systems load and operate with actual provided GLBs; only genuine interior/exterior layers claimed |
| Hybrid | Explicitly verified or labelled schematic registration |
| Cross-modal | Source-to-ROI-to-anatomy linkage and honest precision level |
| Prognosis | Separate dual-scenario page; actual justified estimates or intentional abstention |
| Research | IEEE equation version traceability; no invented Section X experiments |
| Security | No patient PHI in release; history issue controlled; lawful training data only |

**Final status categories** must be `IMPLEMENTED_TESTED`, `IMPLEMENTED_UNVALIDATED`, `BLOCKED`, `UNSUPPORTED`, `NOT_STARTED`—and must be independently auditable. A completed source-code stub does not count as a trained model; a network 200 does not count as visual GLB rendering; a Python build does not count as user-facing clinical functionality; a Docker config validation does not count as an image build.

## 16. BEGIN WITH THIS EXACT EXECUTION SEQUENCE

1. Confirm `D:\project` and Downloads archive paths are actually accessible in your agent terminal.
2. Read project guidance, status documents, relevant source, Git privacy issue; keep PHI out of tool outputs.
3. Record starting repository state and run existing tests without destructive changes.
4. Inspect all 24 ZIPs, create safe extraction manifest and estimate free space before extraction. Import them using a resumable idempotent pipeline.
5. Audit data/task suitability and prevent unlicensed/PHI training.
6. Fix working infrastructure and the identified OCR/queue/encryption gaps.
7. Start dev services; exercise real browser UI and ten anatomy models; record hard evidence.
8. Train and evaluate feasible, licensed, labelled imaging tasks one at a time; implement report extraction ground-truth evaluator and actual NLP training only if labelled training corpus exists.
9. Wire real model outputs to uploaded scans, text evidence and anatomy; preserve limitations.
10. Build/verify separate `/anatomy-studio` and `/prognosis-studio`; no fake forecasts, risk scores or treatment comparisons.
11. Run regression/integration/browser tests and research validation; reconcile 56 claims and old/revised equations.
12. Produce complete status matrix and exact working startup commands; identify any unattainable clinical claims explicitly.

**DO NOT STOP AT A PLAN. EXECUTE WORK ON THE EXISTING CODEBASE, VERIFY IT, AND DOCUMENT EVERY BLOCKER WITHOUT INVENTING SUCCESS.**
