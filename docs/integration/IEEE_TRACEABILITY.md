# MedTwin IEEE manuscript claim-to-evidence traceability

> **Historical matrix for the earlier manuscript/baseline.** The authoritative revised 56-claim matrix is `docs/research/traceability.json`, with the current narrative in `docs/research/IEEE_TRACEABILITY_REPORT.md`. Counts and implementation statements below are retained only to preserve the earlier Eq. 1-16 record.

**Evidence cutoff:** 23 October 2026  
**Manuscript reviewed:** `C:\Users\johnn\Downloads\MedTwin_IEEE_Manuscript_Final.docx`  
**Workspace reviewed:** `D:\project`

This document maps the manuscript's objectives, contributions, equations, and proposed evaluation to the current MedTwin working tree. It reports software evidence only unless a row explicitly names a held-out clinical evaluation artifact. It does **not** establish diagnostic accuracy, clinical effectiveness, regulatory compliance, patient-specific anatomy, or real-time clinical operation.

The working tree is currently initialized as a Git repository but has no committed baseline: all project files are untracked at this cutoff. Paths below therefore identify the inspected working tree, not an immutable commit.

## Status meanings

| Status | Meaning in this document |
| --- | --- |
| **Implemented baseline** | An executable non-clinical implementation exists and is covered by a relevant automated test or saved software-only artifact. |
| **Partially implemented** | Some required software exists, but the claimed end-to-end workflow or acceptance evidence is incomplete. |
| **Not implemented** | No operational MedTwin implementation of the claimed capability was found. |
| **Not validated** | Code or a design may exist, but the required independent, leakage-aware, held-out clinical/task evaluation has not been completed. This label may accompany an implementation label. |

## Overall conclusion

MedTwin has progressed beyond the manuscript's original all-proposed implementation table into a runnable research application baseline. Authentication, case isolation, de-identified upload attestation, SHA-256 storage, persisted report processing, source-linked evidence, audit history, review decisions, read-only registries, browser JSON export, generic L1 anatomy, and explicit unavailable/abstention states are implemented and tested. A current authenticated browser session reloaded the same persisted two-report case, displayed 12 source-linked measurements and six matched arithmetic deltas, preserved an append-only synthetic review, and visibly rendered all four generic GLBs without console errors. The Chrome automation extension could not obtain permission to use the file chooser, so the two files were uploaded and processed through the authenticated API before browser reload; this does not verify direct interaction with the UI file picker.

The manuscript's clinical-performance boundary remains unchanged. No learned medical model is activatable; no MURA, PTB-XL/MIT-BIH, or annotated clinical-text experiment has produced a complete artifact bundle; and no patient-data fusion, registration, forecasting, segmentation, detection, calibration, or external validation result exists. The words **real-time**, **diagnostic**, **clinically validated**, and **patient-specific digital twin** are not supported by the current evidence.

## 1. Manuscript objectives and contributions

| ID | Manuscript objective or claim | Current repository evidence and observed result | Status | Evidence still required |
| --- | --- | --- | --- | --- |
| O1 / C1 | Ingest and validate digital files while preserving evidence status, provenance, and abstention. | Canonical routes in `backend/app/routers/files.py`, storage in `backend/app/services/file_storage.py`, audit service, and explicit `EvidenceStatus` values. `backend/tests/test_phase1_persistence_gate.py` verifies mandatory `deidentified=true`, exact SHA-256, processing, and persisted reload. A current authenticated acceptance case persisted two synthetic de-identified reports with SHA-256 values `4f4fd1fdf5a38ca569ce4f07eed661bdef6f72234e13973bda1a68bfccf93b44` and `fdae8b1ffce67657da6fc46e6d874060154e64c626d18760fa0091e9af9a1e56`; both analysis jobs completed and the browser displayed the same evidence after reload. | **Implemented baseline** | Automate browser success and failure paths, including direct file-picker upload; add malware scanning, archive/sandbox handling, resumable upload, and privacy/penetration review. |
| O1 / C1 | Keep files bound to an authorized case and do not infer identity. | JWT authentication and case checks in `backend/app/services/auth.py`; cross-case isolation tests in `backend/tests/test_auth_and_access.py`; unassociated files are rejected from analysis and fusion. | **Implemented baseline** | Independent authorization/tenant-isolation assessment and adversarial testing. |
| C1 | Provide an end-to-end application and durable evidence history. | `backend/app/main.py` is the canonical FastAPI entry point; the React client uses `/api/v1`. The automated phase-1 test verifies upload-through-reload persistence. Current browser verification authenticated against the running canonical backend, reloaded the two-report case, and displayed the same two uploads, two completed jobs, two findings, source-linked evidence, and audit history. The Chrome automation extension was denied file chooser permission, so upload/processing used the authenticated API and the browser verified reload and presentation. | **Implemented baseline** | Add a repeatable browser suite that can exercise the native file chooser and success/failure paths without API-assisted setup. |
| O2 | Use a task-specific image model justified by its labels. | `backend/app/services/image_processor.py` validates and normalizes readable images, then returns `MODEL_UNAVAILABLE`, `NOT_RUN`, no confidence, and no explanation. `backend/tests/test_evidence_and_fusion.py` verifies that no prediction is invented. | **Partially implemented; Not validated** | A label-appropriate dataset, patient-aware split, immutable checkpoint and hash, preprocessing version, held-out predictions, calibration/abstention, evaluation report, and model card. |
| O2 | Analyze digital ECG while rejecting poor-quality input. | `backend/app/services/ecg_processor.py` parses CSV signals, checks length, NaN/Inf, extreme amplitude, and flatlines, and creates a non-diagnostic waveform preview. It returns `MODEL_UNAVAILABLE` and `NOT_RUN`; quality rejection is unit-tested. | **Partially implemented; Not validated** | A declared PTB-XL or MIT-BIH task, official/patient-disjoint split, checkpoint, held-out patient-level metrics, signal-quality evaluation, calibration, and abstention analysis. |
| O2 / Eq. 7 | Extract entities, assertion/negation, temporality, numeric values, and source spans from reports. | `backend/app/services/document_parser.py` handles TXT/MD/JSON/CSV, DOCX, and embedded-text PDF; image-only PDF is rejected because OCR is absent. `backend/app/services/nlp_processor.py` provides a transparent rule baseline. DOCX parsing, exact spans, measurements, persistence, negation/temporality behavior, and OCR rejection are tested. Outputs remain `PENDING_HUMAN_REVIEW` and have no calibrated probability. | **Implemented baseline; Not validated** | Select a licensed annotated corpus and report exact/overlap entity span F1, assertion/negation metrics, temporality metrics, document-level metrics, confidence intervals, and error analysis. |
| O3 | Handle missing, invalid, low-quality, or unassociated evidence explicitly. | Analysis, image, ECG, and fusion services emit `REJECT`, `ABSTAIN`, `NOT_RUN`, `NOT_ELIGIBLE`, and `MAPPING_UNSUPPORTED`; tests cover zero/single modality, invalid extension, poor ECG quality, and unassociated evidence. | **Implemented baseline** | Prospective failure-mode and human-factors testing with predeclared acceptance criteria. |
| C2 / Eq. 8-10 | Masked gated multimodal fusion combines valid same-case modalities and remains defined with missing inputs. | `backend/app/services/fusion_service.py` implements the PyTorch masked-gating mathematics; synthetic tensor tests verify zero weight for a missing modality and weights summing to one. The case service abstains at zero modalities and does not run at one or multiple modalities without paired-data/model evidence. | **Partially implemented; Not validated** | Genuinely paired same-patient data, compatible timestamps, patient-disjoint splits, validated modality encoders, a frozen fusion checkpoint, calibration, ablation studies, and held-out multimodal evaluation. |
| C2 | Report concordance flags disagreement without overwriting either source. | `backend/app/services/concordance_service.py` and `backend/tests/test_evidence_and_fusion.py` verify a `REVIEW_DISCORDANCE` flag and preservation of both source records. | **Implemented baseline; Not validated** | Evaluation on independently annotated paired reports/findings. Report agreement must continue to be described as concordance, not diagnostic accuracy. |
| O4 | Compare dated observations without inventing clinical interpretation. | Examination-bound measurements and `backend/app/services/comparison_service.py` compare exact same-name/same-unit source-linked values. The current two-report acceptance case persisted six measurements per examination (12 total); browser comparison returned six matched arithmetic deltas. Tests cover deltas, case ownership, and abstention when evidence links are absent. Image change and anatomical change remain `NOT_RUN`/`MAPPING_UNSUPPORTED`. | **Implemented baseline; Not validated** | Corpus-level extraction/comparison accuracy, unit harmonization protocol, ambiguous-value abstention, and clinician usability/error testing. |
| O4 / C3 | Show generic, finding-associated, and patient-specific anatomy as distinct L1/L2/L3 levels. | Four attributed, hashed GLBs exist under `public/models`; `scripts/validate_glb_assets.mjs` parsed all four and confirmed renderable meshes/triangles. `src/components/DigitalTwin3D.tsx` loads them through React Three Fiber and labels the view `L1 ONLY`. In the current authenticated browser session, Heart, Lungs, Brain, and GI were each selected and visibly rendered with loaded status and zero console errors. This followed removal of the in-canvas `Html` loader and finite-bounds normalization/centering in `DigitalTwin3D.tsx`. | **Implemented baseline** | Add automated WebGL/browser regression and failure-path coverage; complete the upstream asset/license audit. This evidence remains generic L1 visualization only. |
| C3 / Eq. 11-12 | Permit L2 mapping only after a held-out target-registration-error gate. | Arun rigid-transform and TRE utilities exist in `backend/app/services/registration_service.py`; synthetic tests exercise pass/fail mathematics and require an evidence manifest for research-only L2. The public route does not accept a self-asserted verification flag, so raw coordinates remain L1. | **Partially implemented; Not validated** | Real source/target anatomy, provenance-reviewed landmarks, fitting/held-out separation, predeclared TRE threshold, observer variability, and external registration evaluation. |
| C3 | Support patient-specific L3 reconstruction. | No patient-specific volumetric reconstruction, validated deformable registration, or L3 artifact is registered. | **Not implemented** | A separately governed volumetric reconstruction study with validated geometry, registration, uncertainty, review, and privacy controls. |
| C4 | Enforce leakage-aware evaluation and reproducible activation. | `model_registry/artifact-bundle.schema.json` and `backend/app/services/model_registry.py` require dataset/version/license, split manifest, task/labels, preprocessing, checkpoint/hash, calibration, thresholds, held-out predictions, evaluation report, and model card. A unit test proves activation requires a matching checkpoint hash. | **Implemented baseline; Not validated** | Populate and independently verify a complete bundle for a real model. Current registry result: 11 models, 0 activatable. |
| C4 / Eq. 15 | Calibrate confidence and expose it only when valid. | Brier score, ECE, and temperature-scaling utilities are implemented and unit-tested on synthetic arrays. UI logic withholds confidence unless a finding is marked calibrated. | **Implemented baseline; Not validated** | Disjoint calibration data, frozen parameters and thresholds, held-out reliability analysis, Brier/ECE with confidence intervals, subgroup analysis, and drift monitoring. |
| Eq. 13-14 | Forecast a defined longitudinal target only when eligible. | `backend/app/services/forecasting_service.py` gates on at least three dated, source-linked, same-target/same-unit observations and can compute persistence/linear baselines. Ineligible cases are tested. No learned forecast or MAE/RMSE result exists. | **Partially implemented; Not validated** | One predeclared target, unit, horizon, adequate longitudinal cohort, chronological hold-out, baseline comparison, MAE/RMSE, calibration/coverage, and failure/subgroup analysis. |
| Title / C4 / Eq. 16 | "Real-time" service behavior. | Saved local software-only benchmarks exist. They do not exercise a learned model or clinical workload, and each artifact records `clinical_performance_measured=false`. | **Not validated** | Predeclare an end-to-end clinical-workflow latency threshold; benchmark upload, queueing, preprocessing, inference, persistence, and rendering on the intended deployment; report repetitions, failures, p50/p95/p99, throughput, CPU/GPU/RAM, and concurrency. |
| Algorithm 1 | Authenticate, validate/hash, associate, process, persist, review, and audit transactionally. | Authentication, hashing, association gate, modality dispatch, persisted findings/statements/measurements, review decisions, and audit records exist. The current synthetic browser case recorded a `REJECTED` human review with `original_output_preserved=true` and a separate `HUMAN_REVIEW_SUBMITTED` audit event; the source finding was not overwritten. Browser JSON evidence export was also exercised successfully. Analysis still runs synchronously inside the request despite persisted job records and polling endpoints. | **Partially implemented** | Real background workers, durable queue/retry/cancellation/idempotency under process failure, transaction-recovery tests, PDF export, and load/fault testing. |
| Safety statement | MedTwin is research software, not a diagnostic device. | README, API notices, UI labels, registry gates, and unavailable-model outputs preserve this boundary. | **Implemented baseline** | Independent privacy, security, regulatory, clinical-safety, and human-factors review before any clinical pilot. |

## 2. Proposed evaluation table versus present evidence

The manuscript states that no experimental results were reported. That remains accurate for medical-model performance.

| Proposed evaluation | Present evidence | Status | Required completion artifact |
| --- | --- | --- | --- |
| MURA study-level normal/abnormal classification | `mura_study_baseline` is `WEIGHTS_MISSING`; no MURA dataset root was identified by the name-based registry scan. No AUROC, precision, recall, F1, confusion matrix, calibration, or confidence interval exists. | **Not implemented; Not validated** | Licensed dataset card, patient/study split manifest, trained checkpoint/hash, held-out predictions, complete report and model card. Do not claim detection or segmentation from MURA labels. |
| Box-based image detection | No detector, box checkpoint, or bounding-box evaluation artifact is registered. | **Not implemented** | Licensed box annotations, patient split, detector/comparator, AP metrics, calibration, error analysis, and artifact bundle. |
| Mask-based image segmentation | No segmentation checkpoint or mask evaluation artifact is registered. | **Not implemented** | Licensed masks, patient split, Dice/IoU and boundary metrics, failure analysis, and artifact bundle. |
| PTB-XL or MIT-BIH ECG classification | `ptbxl_ecg_baseline` is `WEIGHTS_MISSING`; no held-out predictions or metrics exist. | **Not implemented; Not validated** | Declared task, official/patient-disjoint folds, waveform preprocessing, checkpoint/hash, macro/micro AUROC/F1/precision/recall, calibration, rejection/abstention metrics, report and model card. |
| Clinical-text extraction | Executable rule baseline only; no annotated-corpus evaluation. | **Implemented baseline; Not validated** | Licensed corpus, frozen labels/splits, exact/overlap span results, assertion/negation, temporality, document metrics, confidence intervals and error analysis. |
| Report concordance | Rule behavior is unit-tested on a synthetic disagreement. | **Implemented baseline; Not validated** | Independent paired annotations and concordance evaluation; no diagnostic-accuracy wording. |
| Paired multimodal fusion | Mathematical layer is unit-tested; runtime fusion intentionally remains `NOT_RUN`. | **Partially implemented; Not validated** | Same-patient paired cohort, timestamp policy, patient split, validated encoders/fusion model, ablations, calibration, and held-out report. |
| Forecasting | Evidence gate and unvalidated linear/persistence baselines exist; no chronological benchmark. | **Partially implemented; Not validated** | Predeclared target/unit/horizon, chronological hold-out, MAE/RMSE and calibration/coverage report. |
| Anatomical mapping | Synthetic TRE mathematics only; no patient landmark benchmark. | **Partially implemented; Not validated** | Reviewed real landmark manifest, separate fitting/held-out points, predeclared threshold, TRE distribution and external evaluation. |
| Calibration | Metric utilities only; no clinical model probabilities/labels. | **Implemented baseline; Not validated** | Frozen calibration parameters and thresholds plus held-out reliability, Brier/ECE and confidence intervals. |
| Service performance | Local artifacts measure software routes and a synthetic report workflow only. | **Implemented baseline; Not validated for "real-time"** | Intended-deployment end-to-end benchmark with a predeclared threshold and real model execution. |

## 3. Architecture realization relative to the manuscript

| Manuscript component | Current realization | Status and limitation |
| --- | --- | --- |
| React/Vite client | Authenticated API-backed cockpit in `src/App.tsx` and `src/services/api.ts`; a current browser session authenticated, reloaded persisted evidence, ran the two-examination comparison, preserved/displayed review and audit history, and completed browser JSON export. | **Implemented baseline.** The Chrome automation extension was blocked from using the local file chooser, so uploads were API-assisted; no automated browser suite or direct picker acceptance is yet recorded. |
| Three.js/Blender viewer | React Three Fiber/drei GLB loader in `src/components/DigitalTwin3D.tsx`; four curated L1 files and hashes are present. Heart, Lungs, Brain, and GI were selected and visibly rendered in the current authenticated browser session after loader/bounds fixes, with zero console errors. | **Implemented baseline.** Generic reference only; no patient registration, automated WebGL regression, or completed upstream license audit. |
| FastAPI backend | `backend/app/main.py`, versioned `/api/v1`, environment-controlled seed, JWT and case authorization. | **Implemented baseline.** |
| Database | SQLAlchemy persistence with SQLite locally and in Compose. | **Partially implemented.** The manuscript's proposed PostgreSQL deployment is not the current default and has no integration result here. |
| File store | Local content-addressed storage with exact SHA-256 and persisted metadata. | **Implemented baseline.** No object-store, malware-scan, encryption-at-rest, or retention validation. |
| Analysis workers | Persisted job entity and polling API; processing occurs synchronously in the request. | **Partially implemented.** No queue/worker/retry system. |
| Learned image/ECG/NLP models | Image and ECG validation/previews; report rules baseline. | **Not implemented** for learned inference; rule NLP is an **Implemented baseline; Not validated**. |
| Docker deployment | Compose and both Dockerfiles are present; `docker compose config --quiet` passed with a temporary non-secret value on this audit. | **Partially implemented.** Docker Desktop's engine was unavailable, so images were not built or run locally. |
| CI | `.github/workflows/ci.yml` defines frontend, Python 3.12 backend, Compose validation, and two-image build jobs. | **Partially implemented.** Configuration exists, but no GitHub Actions run is evidenced in this uncommitted repository. |

## 4. Executed software checks and saved artifacts

These results verify software behavior, not medical performance.

| Check | Actual result | Interpretation |
| --- | --- | --- |
| Backend test suite | `.venv\Scripts\python.exe -m pytest backend/tests -q` -> **51 passed in 22.78 s**. | Covers authentication/access isolation, upload/hash/persistence, parsers, rule extraction, measurements, comparisons, review, registries, explicit unavailable/abstention behavior, synthetic fusion/TRE/calibration math, and API workflows. |
| Python compilation | Final `compileall` validation completed without an error. | Python syntax/import compilation passed; this is not behavioral or clinical validation. |
| Frontend check | Final post-fix `npm run check` exited **0**: TypeScript was clean, oxlint completed with five warnings, and Vite built successfully in 12.13 s. Vite retained the greater-than-500-kB chunk warning. | Post-fix buildability is established. Browser behavior was also checked manually; accessibility and automated browser coverage are not established. |
| GLB validation | `node scripts/validate_glb_assets.mjs` parsed every entry in `public/models/registry.json`; all four assets contained renderable meshes and triangles and were reported valid. | Binary/loader validity is established for the four generic L1 assets; this is not patient-specific anatomy or registration evidence. |
| Authenticated browser/API acceptance | The current canonical backend authenticated the synthetic case `BROWSER-QA-20261023`. Two exact SHA-256-addressed reports produced two completed rule-baseline jobs, two findings, 12 source-linked measurements, and six matched longitudinal arithmetic deltas after browser reload. One append-only synthetic rejection preserved the original output and appeared in audit history. Browser JSON export download completed. All four L1 GLBs were selected and visibly rendered; the final console error count was zero. | Software workflow evidence only. Chrome extension permission blocked the browser file chooser, so authenticated API upload/processing plus browser reload was used; direct UI-picker upload remains unverified. No learned-model or clinical result was produced. |
| PyTorch GPU visibility | Python 3.12.15, `torch 2.14.1+cu130`; `torch.cuda.is_available()` returned **True** for an NVIDIA GeForce RTX 5060 Laptop GPU. | CUDA visibility is verified. No medical model inference, correctness, speed, or memory-fit claim follows from this check. |
| Latest completed HTTP artifact | `benchmarks/results/http-benchmark-20261023-224119.json`: `/api/v1/catalog/packages`, 600/600 successes at concurrency 1 and 600/600 at concurrency 8. Median-across-repeats p50/p95: 2.4457/14.8431 ms at c=1 and 36.3531/102.1521 ms at c=8; throughput 239.191 and 176.089 successful requests/s; max sampled RSS 681,177,088 bytes. | Same-host catalog-serving measurement only; no upload or model inference. A preceding artifact (`...223909.json`) is correctly marked failed because Windows could not remove a locked temporary SQLite file, despite successful requests. |
| Synthetic report workflow artifact | `benchmarks/results/report-workflow-benchmark-20261023-223734.json`: 120/120 workflows succeeded, 0 failures. Median-across-repeats p50/p95: 126.6303/154.5894 ms at c=1 and 215.001/382.4426 ms at c=4; throughput 7.878 and 15.816 workflows/s; max sampled RSS 681,021,440 bytes. | Local synthetic de-identified report upload-through-provenance-reload benchmark; explicitly `clinical_performance_measured=false`. |
| Docker | Compose interpolation/validation passed when `SECRET_KEY` was supplied; Docker client 29.9.1 was present. The engine connection failed because the Docker Desktop Linux pipe was unavailable. | Configuration evidence only; no local container build/runtime result. |

## 5. Registry readiness

- `model_registry/models.json` contains 11 entries and the authenticated registry tests assert **0 activatable models**.
- `clinical_rules_v1` is `READY_UNVALIDATED` and `processor_only=true`.
- MURA and PTB-XL baselines are `WEIGHTS_MISSING`.
- MedCAT, scispaCy, and RadGraph adapters are dependency/weight blocked.
- `dataset_registry/datasets.json` contains 33 discovery records; all have `training_eligible=false` and `validation_eligible=false`. Global status is `CATALOG_ONLY_NOT_TRAINING_READY`.
- The registry's name-based presence check reports MURA and PTB-XL as not found, while correctly warning that this does not prove absence from every archive or nested path.

Therefore, the number of learned medical models with a complete, held-out-evaluated, calibrated MedTwin artifact bundle is **zero**.

## 6. DeepSA results are separate from MedTwin

DeepSA is a separate coronary-angiography paper and proposed future adapter. Its PDF is not a MedTwin checkpoint, executable adapter, dataset contract, or evaluation artifact.

The supplied DeepSA paper reports Stage-2 validation AUROC/F1/accuracy of **0.9777 / 0.9046 / 0.9257** and an ARCADE image split of 1,000/200/300. These are **author-reported DeepSA results only**. They were not reproduced in `D:\project`, were not generated by MedTwin, and must not appear in a MedTwin results table as MedTwin performance.

The same paper also identifies unresolved evidence gaps and implementation inconsistencies: segmentation Dice/IoU and a persisted confusion matrix are pending; a 96x96, stride-64 loop leaves an uncovered 32-pixel image strip; and interface severity thresholds differ (0.55 versus 0.60). The current MedTwin registry accurately marks `deepsa_angiography_adapter` as `UNSUPPORTED`, with no executable, weights, or validated dataset contract.

DeepSA may be integrated only after an independent reproduction that:

1. obtains legally usable source, weights, and data and records their immutable hashes;
2. freezes patient/study-disjoint train, calibration, validation, and test manifests;
3. resolves the sliding-window boundary and severity-threshold discrepancies before testing;
4. evaluates segmentation, localization/detection, grading, calibration, abstention, and subgroup/failure behavior separately;
5. saves held-out per-example predictions, confusion matrices, confidence intervals, model card, and complete artifact bundle; and
6. exposes it as a versioned angiography adapter without changing or retroactively attributing results to MedTwin.

## 7. Defensible manuscript wording at this cutoff

Supported wording:

- "MedTwin is a runnable software-only research prototype with an authenticated, provenance-preserving report-processing baseline."
- "Image and ECG files can be validated/preprocessed, but learned inference is unavailable."
- "The clinical-text component is a transparent rule baseline pending annotated-corpus evaluation."
- "The viewer presents attributed generic L1 anatomy; no patient-specific reconstruction is claimed."
- "Fusion and registration mathematics have synthetic code-level tests, while case-level clinical evaluation remains pending."
- "Local software benchmarks were completed and do not measure clinical performance."

Unsupported wording:

- "MedTwin has demonstrated diagnostic accuracy, clinical effectiveness, real-time clinical operation, or HIPAA compliance."
- "MURA, PTB-XL/MIT-BIH, clinical NLP, fusion, registration, or forecasting performance has been established."
- "The generic GLB is a patient-specific digital twin or an image-derived 3D localization."
- "DeepSA performance is MedTwin performance" or "DeepSA is operational in MedTwin."

## 8. Evidence gates before revising the manuscript from proposal to results paper

1. Commit an immutable source baseline and preserve environment, dependency, and hardware manifests.
2. Convert the completed API-assisted authenticated browser acceptance into a repeatable automated browser suite, including native file chooser upload, reload, identical SHA-256/evidence/audit assertions, all four GLB loaded states, JSON export, and success/failure screenshots.
3. Finish one artifact pipeline end to end, preferably MURA study-level classification, before beginning the ECG and NLP experiments.
4. Run PTB-XL/MIT-BIH and annotated clinical-text experiments independently with the declared leakage-aware protocols.
5. Report confidence only after calibration, preserve abstention/rejection rates, and retain held-out predictions for audit.
6. Treat paired fusion, landmark registration, forecasting, DeepSA, and L3 reconstruction as separate studies with their own data contracts and acceptance criteria.
7. Complete security, privacy, clinical-safety, human-factors, and regulatory review before any clinical pilot or compliance claim.
