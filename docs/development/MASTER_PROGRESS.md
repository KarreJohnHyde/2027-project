# MedTwin 2.0 - master progress

> Historical session record. Consult the [2026-10-29 audit](../verification/COMPLETENESS_AUDIT_2026-10-29.md) for current capabilities and remaining work; do not interpret older NOT_STARTED/environment statements as current facts.

Verified handoff snapshot for subsequent sessions. This is not a declaration that the
full directive or any clinical-validation programme is complete. Every status below is
backed by an executed command, saved artifact, browser walkthrough, or explicit blocker.
Branch `feature/medtwin-2-integration` (local commit `1aedb23` carries this work). This
repository has no configured remote and its history must not be pushed; publication goes
only through a separate history-free snapshot (see the release row below).
Last updated 2026-10-25.

## Final local evidence

- `artifacts/verify/20261025T140444Z.json` (commit `1aedb23`, clean tree, all steps
  passed): backend **260 passed, 1 skipped**; frontend typecheck, lint, production
  build, and current-tree privacy scan exited 0. Non-blocking React lint and bundle-size
  warnings remain recorded.
- `%TEMP%\medtwin-qa\walkthrough-20261025T140444Z\walkthrough.json` (same run):
  Microsoft Edge 156 passed **17/17 desktop routes** (now including Data sources and
  licences), **17/17 responsive routes**, **43/43 anatomy variants across 10/10
  systems**, **7/7 2-D image-model workflows** (no evaluation-only model was offered for
  upload), and **11/11 trained-model reports** including the cardiac MRI view, with
  lifecycle, lab, evidence, correction, queue, evaluator and prognosis assertions (0
  numeric risk statements) and zero console errors, page errors, or failed requests.
- `model_registry/validation_status.json`: **21 registry entries, 11 research-runnable,
  0 clinically activatable**. Nine support gated upload inference (seven 2-D image models,
  the 12-lead ECG classifier and the cardiac MRI segmenter); both survival baselines are
  evaluation-only.
  All are internal, research-only results.

Companion files: `docs/development/NEXT_ACTIONS.md`,
`docs/development/FINAL_REPORT.md`, `docs/testing/EXECUTED_TEST_RESULTS.md`, and
`docs/anatomy/BROWSER_WALKTHROUGH.md`.

## Directive sections

| Section | Area | Status | Verified state and boundary |
| --- | --- | --- | --- |
| 1-2 | Re-verification, platform, input roots | `IMPLEMENTED_TESTED` | Python 3.12 `.venv`, torch/MONAI, RTX 5060 Laptop 8 GB, Node, Edge plus visible Chrome, WSL Ubuntu, Docker client 29.9.2 and Compose 5.6.1 were inspected. Docker engine is absent. |
| 3 | 24 Downloads archives | `IMPLEMENTED_TESTED` | All 24 named ZIPs were SHA-256 catalogued and structurally safety-checked; 23 canonical mappings were CRC-verified and one archive was atomically extracted and reverified 6,795/6,795. Ninety-one additional ZIPs were audited; two symlink-unsafe archives were not extracted. |
| 4 | Data governance and task gates | `IMPLEMENTED_TESTED` | `dataset_registry/tasks.json` contains 61 dataset units / 32 tasks: 10 `READY_FOR_TRAINING`, 1 `EXPLORATORY_TRAINING_ONLY`, 21 `BLOCKED`; 11 are training-eligible. Cardiac cine-MRI became eligible only after the repository owner's recorded authorization (2026-10-25; no licence text exists). Patient/subject grouping is used where available, with exact/near-duplicate checks; the microscopy split joins subjects that share pixel-identical images. |
| 5 | Runtime, adapters, jobs | `IMPLEMENTED_TESTED` | Durable database jobs implement leases, retries, cancellation, idempotency, GPU quota, and a separate worker. Browser reload persistence and backend cross-process restart recovery pass. |
| 6 | Documents, OCR, NLP, numerical labs | `IMPLEMENTED_UNVALIDATED` | RapidOCR, rules-v2 extraction, optional WSL scispaCy, structured/censored labs, strict OCR CER/WER and clinical-NLP span/context evaluators, immutable input digests, and hash-only provenance execute and pass software tests. No lawful independent annotated medical corpus has established clinical accuracy. |
| 7 | 2-D imaging training and inference | `IMPLEMENTED_UNVALIDATED` | Seven checkpointed models support research-only upload inference: GI endoscopy 8- and 27-class classifiers, colorectal polyp segmenter, leukaemic-blast cell classifier, coronary stenosis detector, coronary segment segmenter and renal calculus detector. Inference now reproduces each model's evaluated numeric precision (bfloat16 autocast on CUDA); float32 serving had changed 84 of 1,867 held-out cell predictions. |
| 7 | ECG and survival evaluation | `IMPLEMENTED_UNVALIDATED` | PTB-XL ECG and PBC/heart-failure Cox baselines have frozen internal held-out reports. The ECG model now has research-only upload inference for digital WFDB/CSV records (exact readers, contract gate, parity with its held-out predictions in `docs/validation/UPLOAD_INFERENCE_PARITY.md`); the Cox baselines have no upload path and do not constitute a validated patient forecast. |
| 7 | Volumetric segmentation | `IMPLEMENTED_UNVALIDATED` | The 3-D NIfTI pipeline trained a cardiac cine-MRI ventricular segmenter after the owner's authorization (298 retained cases / 149 patients; development patient055 excluded for duplicating test images). On 50 frozen test patients: mean case macro Dice 0.750 (LV 0.812, myocardium 0.731, RV 0.707); LV ejection fraction against reference-mask values MAE 9.1 points (bias −5.8). Volumes are overestimated (no prespecified post-processing). Research-only upload inference for single NIfTI frames inside the recorded development spacing envelope reproduces 98/98 held-out masks exactly (`docs/validation/UPLOAD_INFERENCE_PARITY.md`). |
| 8 | Anatomy engine, ten systems | `IMPLEMENTED_TESTED` | One WebGL engine rendered 43/43 real variants across all 10 systems, using renderer counters, canvas-content checks, and orbit interaction. Assets remain generic/reference anatomy unless separately registered. |
| 8 | Evidence and 2-D-to-3-D mapping | `IMPLEMENTED_UNVALIDATED` | Source-linked statements and canonical mapping states are implemented. Research outputs remain in source-image coordinates; only a clinician-confirmed schematic organ association is permitted without registration. No patient-specific pin or transform is claimed. |
| 9 | Historical analytics | `IMPLEMENTED_TESTED` | Source-linked same-analyte/same-unit observations, structured/censored exclusions, deduplication, exact arithmetic deltas, and provenance execute. The service abstains when comparison links or compatibility are absent. |
| 9 | Prognosis Studio safety | `IMPLEMENTED_TESTED` | The independent `/prognosis-studio` route renders evidence/eligibility/scenario panels and reason-coded abstention. The canonical browser run emitted zero numeric risk/probability statements. |
| 9 | Longitudinal forecasting and treatment effects | `BLOCKED` | Existing survival baselines use baseline covariates and event/censor outcomes; they are not repeated longitudinal trajectories, workspace-integrated forecasts, or causal treatment models. No eligible cohort, chronological forecast validation, clinical activation bundle, or target-trial estimand exists. |
| 10 | Risk and evaluation tooling | `IMPLEMENTED_TESTED` | Validation Center implements classification, detection, segmentation, forecast, survival, regression, labs, OCR, and clinical-NLP metrics. Dataset/report/path/size/format/task/split/hash checks bind reportable runs to actual bytes; altered or missing inputs remain exploratory. Unsupported patient risk stays unavailable. |
| 11 | Working-tree privacy and upload encryption | `IMPLEMENTED_TESTED` | Redacting current-tree scan, pre-push guard, AES-256-GCM upload encryption, key rotation, legacy migration, and tamper rejection pass. SQLite pages and backups are not asserted to be encrypted. |
| 11 | Repository release and sharing | `BLOCKED` (local history) | A history-free snapshot of `3e60b8b` was published on the owner's request as `45c25ce` in `https://github.com/KarreJohnHyde/2027-project` after clean history and tree scans of the snapshot repository and a verified fresh clone (2 commits, 588 identical files). The PHI-bearing blob remains reachable on both local branches: never push or share this repository or its Git metadata; rewriting it still needs owner authorization and a secure-backup/evidence decision. |
| 12 | Browser QA and managed QA stack | `IMPLEMENTED_TESTED` | The isolated QA stack, Vite proxy, worker, route/responsive/anatomy/model/evaluator workflows, and visible Chrome inspection were executed. Evidence paths are listed above. |
| 12 | Docker configuration | `IMPLEMENTED_TESTED` | Base and worker-profile `docker compose config --quiet` both exited 0 with a temporary non-secret validation key. |
| 12 | Docker build and runtime | `BLOCKED` | Docker Desktop's Linux engine pipe is absent. No image build, container start, migration, health, persistence, or shutdown claim is made. |
| 13 | IEEE traceability | `IMPLEMENTED_TESTED` | `docs/research/traceability.json` contains exactly 56 claims: 28 tested, 18 partially implemented, 5 implemented-not-validated, 3 proposed-only, and 2 unsupported. Revised Eq. (1)-(12) remains distinct from the earlier Eq. (1)-(16). |
| 14 | Resource-aware execution and resumable handoff | `BLOCKED` | Locally executable gates ran, but the directive cannot close while privacy, licensing, Docker, patient registration, lawful validation data, and external/clinical validation remain blocked. |
| 15 | Required artifacts | `IMPLEMENTED_TESTED` | Required registries, manifests, reports, cards, verification receipts, scripts, and progress documents exist at their prescribed paths. |
| 16 | Required execution sequence | `BLOCKED` | The local sequence reached final verification and reconciliation. External-authority and scientific-validation prerequisites below remain unresolved. |

## Required artifacts

| Path | Status | Evidence |
| --- | --- | --- |
| `docs/development/MASTER_PROGRESS.md`, `NEXT_ACTIONS.md`, `FINAL_REPORT.md` | `IMPLEMENTED_TESTED` | Reconciled to the 2026-10-25 verification and browser receipts. |
| `docs/import/ARCHIVE_MANIFEST.csv`, `docs/import/ARCHIVE_REPORT.md` | `IMPLEMENTED_TESTED` | Generated safe-archive inventory and exact import accounting. |
| `dataset_registry/datasets.json`, `dataset_registry/tasks.json` | `IMPLEMENTED_TESTED` | Dataset catalogue and generated readiness/task audit. |
| `model_registry/models.json`, `model_registry/validation_status.json` | `IMPLEMENTED_TESTED` | Registry integrity tests pass; 21 entries / 10 research-runnable / 0 clinically activatable. |
| `assets/anatomy/asset_manifest.json`, `public/anatomy/manifest.json` | `IMPLEMENTED_TESTED` | All 43 variants passed manifest QA and browser rendering. |
| `docs/clinical/`, `docs/imaging/`, `docs/forecast/`, `docs/security/` | `IMPLEMENTED_TESTED` | Scope-specific evidence and explicit scientific/security limits are documented. |
| `docs/testing/EXECUTED_TEST_RESULTS.md`, `docs/research/IEEE_TRACEABILITY_REPORT.md` | `IMPLEMENTED_TESTED` | Generated/updated from executed verification and traceability evidence. |

## Remaining blockers

| Blocker | Status | Exact condition to clear it |
| --- | --- | --- |
| PHI in reachable Git history | `BLOCKED` | Obtain owner authorization, decide secure evidence retention, run the controlled purge or create a new sanitized canonical repository, and require a clean history scan before sharing. |
| Docker execution | `BLOCKED` | Start a reachable Linux engine, provide runtime secrets, build and run backend/worker/frontend, apply migrations, and record health, persistence, security, and shutdown evidence. |
| Dataset licences/privacy | `BLOCKED` | Record authoritative permissions for currently blocked archives and complete the archive-05 DICOM privacy disposition. |
| Clinical NLP/OCR accuracy | `BLOCKED` | Register a lawful independently annotated gold corpus and run the implemented OCR/span/context/numeric evaluators under a prespecified protocol. |
| Patient-specific 2-D-to-3-D localization | `BLOCKED` | Supply reviewed landmarks/transforms, fitting versus held-out partitions, coordinate-frame provenance, and acceptance thresholds. |
| Prognosis and treatment effects | `BLOCKED` | Supply repeated longitudinal outcomes, define population/time zero/endpoints/horizons, use time-respecting splits, validate the integrated forecast, and define a target-trial estimand for treatment effects. |
| External and clinical validation | `BLOCKED` | Execute independent-site evaluation, subgroup/failure-mode analysis, calibration transfer, prospective safety work, governance review, and production security review. |
| Unsupported integrations | `UNSUPPORTED` | EEG interpretation (EDF/BDF recordings are read and shown, no model) and DeepSA weights/executable. Assembled multi-file DICOM series render and run through the cardiac MRI segmenter (orientation convention of scanner series assumed). |

## High-value corrections in the final pass

- Evaluation results are bound to server-computed input digests. Only the exact
  registered Kvasir held-out bytes qualify; legacy metadata-only, altered, or missing
  inputs read back as exploratory.
- Native BMP upload, signature validation, metadata, rendering, model applicability,
  and browser execution were added for the C-NMC microscopy workflow.
- The QA stack now starts from a fresh production build, has bounded readiness checks,
  safely cleans only its isolated state, and records intentional validation failures
  separately from unexpected browser errors.
- ACDC manifest auditing detected a development/test content collision with differing
  masks and removed the complete development patient before forming the retained split.
- Proposed clinician corrections remain append-only and preserve the original model or
  extractor output; the visible browser inspection confirmed the persisted history.
- Served models now reproduce their evaluated numeric precision: float32 serving of a
  bfloat16-evaluated classifier had changed 84 of 1,867 held-out predictions; parity is
  now 21/21 with a maximum probability difference of 0.0008, and outputs state precision.
- The microscopy subject split found pixel-identical images under different subject
  ids (14 subject pairs); subjects are clustered and training subjects linked to the
  frozen test set are removed.
- Strict deterministic algorithms refused CUDA cross-entropy at the first 3-D training
  step; CUDA runs in recorded warn-only mode, and the failed attempt is kept as `FAILED`.
- The application shows medical names for datasets, tasks, models and anatomy assets;
  original names, creators, licences and citations are on one Data sources and licences
  page (`/attribution`). The Supabase browser client is configured for Vite and sends no
  data.
