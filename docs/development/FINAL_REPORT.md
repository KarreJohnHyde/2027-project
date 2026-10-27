# MedTwin 2.0 - final report for this session

Date 2026-10-25, branch `feature/medtwin-2-integration` (local commits `1aedb23`,
`3e60b8b`; this repository has no remote and its history was never pushed). A
history-free snapshot of `3e60b8b` is published as `45c25ce` in
`https://github.com/KarreJohnHyde/2027-project`. The research application is implemented
and tested in the scopes below, but the full directive is **not complete**, this local
repository's history is not safe to share, and no model is clinically validated or
activatable.

## Final evidence snapshot

| Evidence | Status | Executed result |
| --- | --- | --- |
| `artifacts/verify/20261025T140444Z.json` | `IMPLEMENTED_TESTED` | Commit `1aedb23`, clean tree, overall pass: backend **260 passed, 1 skipped**; frontend typecheck/lint/build and current-tree privacy scan exited 0. Non-blocking lint and bundle-size warnings remain recorded. |
| `%TEMP%\medtwin-qa\walkthrough-20261025T140444Z\walkthrough.json` | `IMPLEMENTED_TESTED` | Edge 156: **17/17 desktop**, **17/17 responsive** (including Data sources and licences), **43/43 anatomy variants**, **7/7 2-D image workflows**, **11/11 trained reports** (including cardiac MRI); lifecycle, lab, evidence, correction, queue, evaluator and prognosis assertions passed; zero console/page/failed-request errors. |
| Screenshot review of the new screens | `IMPLEMENTED_TESTED` | The cardiac report, Model Registry, Dataset Registry and attribution page were inspected in the run's screenshots: medical names throughout, source credits only on the attribution page. |
| `model_registry/validation_status.json` | `IMPLEMENTED_UNVALIDATED` | **21 entries; 11 research-runnable; 0 clinically activatable**. Nine run on uploads behind research-only gates (seven 2-D image models, the ECG classifier on digital WFDB/CSV records, the cardiac MRI segmenter on single NIfTI frames); the two survival baselines are evaluation-only. |

Detailed state: `docs/development/MASTER_PROGRESS.md`; queued decisions and next
actions: `docs/development/NEXT_ACTIONS.md`; executed tests:
`docs/testing/EXECUTED_TEST_RESULTS.md`.

## Acceptance matrix

| Domain | Status | Evidence and boundary |
| --- | --- | --- |
| Archive imports | `IMPLEMENTED_TESTED` | All 24 named archives are accounted for: 23 canonical mappings plus one safe 6,795/6,795 extraction. Ninety-one extras were audited and two unsafe symlink archives were refused. |
| Dataset audit | `IMPLEMENTED_TESTED` | 61 dataset units / 32 tasks: 10 ready, 1 exploratory-only, 21 blocked; 11 training-eligible. Presence never overrides licence, privacy, label, split, or leakage gates; cardiac MRI opened only on the owner's recorded authorization. |
| UI/browser | `IMPLEMENTED_TESTED` | The canonical Edge walkthrough covered every desktop/phone route, all anatomy variants, all seven 2-D image workflows, ten reports, upload/queue persistence, structured/censored labs, original-preserving corrections, OCR/NLP controls, request IDs, hash-only provenance, and prognosis abstention. Visible Chrome inspection independently opened the high-value paths. |
| Server and persistence | `IMPLEMENTED_TESTED` | The isolated backend, worker, and Vite proxy passed health checks. Queue restart recovery, AES-256-GCM upload encryption/rotation/migration, and tamper rejection are tested. SQLite/database backups remain plaintext. |
| Reports, OCR, NLP | `IMPLEMENTED_UNVALIDATED` | Embedded and scanned documents, RapidOCR, terminology/context rules, numerical labs, and strict OCR/NLP evaluators execute. No lawful independently annotated representative medical corpus has established extraction accuracy. |
| Longitudinal analytics | `IMPLEMENTED_TESTED` | Comparisons require source links, compatible analyte/unit context, and dated examinations; duplicate and censored observations are excluded with provenance. No disease-progression or causal interpretation is invented. |
| Images | `IMPLEMENTED_TESTED` | Raster PNG/JPEG/BMP, single DICOM objects, NIfTI, NRRD, and MetaImage metadata/rendering paths are covered. Boxes and masks map back to source pixels. Multi-file DICOM series assembly remains unsupported. |
| Research models | `IMPLEMENTED_UNVALIDATED` | Seven image models, the ECG classifier (digital WFDB/CSV records) and the cardiac MRI segmenter (single NIfTI frames) have research-only upload inference in their evaluated numeric precision; the two Cox survival models have evaluation-only evidence. All checkpoints/reports are internally evaluated public-research artifacts, not clinical models. |
| Volumetric imaging | `IMPLEMENTED_UNVALIDATED` | The 3-D NIfTI pipeline trained a cardiac cine-MRI segmenter (owner-authorized research use): 50 frozen test patients, macro Dice 0.750, LV ejection-fraction MAE 9.1 points against reference masks, volumes overestimated. Research-only upload inference for single NIfTI frames inside the development spacing envelope; 98/98 held-out masks reproduced exactly. |
| Naming and attribution | `IMPLEMENTED_TESTED` | Datasets, tasks, models and anatomy assets appear under medical names; original names, creators, licences and citations are only on the Data sources and licences page, which the walkthrough rendered on desktop and phone. |
| External client configuration | `IMPLEMENTED_UNVALIDATED` | The Supabase browser client is installed and constructs with the configured project URL and publishable key (no request sent). Nothing in the application uses it yet; patient data must not leave the deployment by default. |
| Anatomy | `IMPLEMENTED_TESTED` | 43/43 variants across 10/10 systems rendered after interaction with WebGL counters and canvas-pixel checks. Assets are generic reference anatomy unless explicitly registered otherwise. |
| 2-D-to-3-D mapping | `IMPLEMENTED_UNVALIDATED` | Source evidence can navigate to verified/schematic regions under canonical mapping states. Without reviewed registration, research geometry remains in source pixels and never becomes a patient-specific atlas point. |
| Prognosis interface | `IMPLEMENTED_TESTED` | `/prognosis-studio` is independent from Anatomy and returns reason-coded abstention. The final browser receipt contains zero numeric risk statements. |
| Prognostic/treatment estimation | `BLOCKED` | PBC and heart-failure baselines are event/censor evaluations, not repeated longitudinal patient forecasts or causal treatment models. Required longitudinal cohorts, temporal validation, estimands, activation, and clinical evidence are absent. |
| IEEE research traceability | `IMPLEMENTED_TESTED` | Exactly 56 claims are reconciled: 28 tested, 18 partial, 5 implemented-not-validated, 3 proposed-only, 2 unsupported. Revised Eq. (1)-(12) remains separate from the earlier Eq. (1)-(16). |
| Repository security/release | `BLOCKED` (local history) | Published as a history-free snapshot: the snapshot repository's history and tree scans exited 0, all 14 screenshots were reviewed as synthetic, and a fresh clone of GitHub matched the local commit file-for-file with 2 commits. PHI remains in this repository's reachable history, so it must never be pushed, bundled or shared; further publication repeats the snapshot procedure in `docs/security/PHI_RELEASE_BLOCKER.md`. |
| Docker | `BLOCKED` | Docker client 29.9.2 and Compose 5.6.1 are installed; base/worker Compose configurations pass. The Linux engine is unavailable, so images and containers were not built or run. |

## Internal research results

These are same-source internal research results, not expected patient performance,
external validation, or clinical activation. Full protocols, intervals, hashes, and
limitations are in `docs/imaging/DATASET_TRAINING_RESULTS.md` and
`docs/validation/models/`.

| Model | Runtime state | Frozen held-out evidence |
| --- | --- | --- |
| Kvasir v2 8-class classifier | 2-D upload inference | n=1,202; accuracy 0.926; macro-F1 0.926 |
| GastroVision 27-class classifier | 2-D upload inference; exploratory | n=1,225; accuracy 0.737; macro-F1 0.553; rare-class support is insufficient |
| ARCADE stenosis detector | 2-D upload inference | n=300; mAP@[.50:.95] 0.0618; AP50 0.2029 |
| TEZ kidney-stone detector | 2-D upload inference | n=196; mAP@[.50:.95] 0.2312; AP50 0.6286 |
| ARCADE SYNTAX segmenter | 2-D upload inference | n=300; vessel Dice 0.6829; mean foreground Dice/image 0.3070 |
| Kvasir-SEG polyp segmenter | 2-D upload inference | n=120; Dice 0.7679; IoU 0.6696 |
| C-NMC ALL-vs-normal classifier | 2-D/BMP upload inference | n=1,867 / 28 subject clusters; accuracy 0.807; macro-F1 0.790 |
| PTB-XL ECG superclass classifier | Research-only upload inference (digital records) | n=2,163 ECGs / 1,881 patients; macro AUROC 0.917; macro AUPRC 0.805 |
| ACDC cardiac cine-MRI segmenter, 3-D | Research-only upload inference (single NIfTI frames) | n=100 volumes / 50 patients; macro Dice 0.750 (LV 0.812, myocardium 0.731, RV 0.707); LV EF MAE 9.1 points, bias −5.8 vs reference masks |
| PBC Mayo survival Cox | Evaluation-only | n=104 hold-out patients; Harrell's C 0.786; integrated Brier 0.105 vs 0.146 Kaplan-Meier |
| Heart-failure survival Cox | Evaluation-only; exploratory | n=90; Harrell's C 0.671; integrated Brier 0.168 vs 0.158 Kaplan-Meier (no skill) |

## Exact blockers

| Blocker | Required evidence or decision |
| --- | --- |
| PHI history | Owner authorization plus approved evidence-retention choice, controlled purge or new sanitized repository, and clean history scan. |
| Docker runtime | Reachable Linux engine, secrets, image builds, migrations, container health, worker/persistence, security, and shutdown checks. |
| Dataset licences/privacy | Authoritative permissions for blocked archives (including your own research use agreements for the musculoskeletal-radiograph and echocardiography sets) and the archive-05 DICOM privacy disposition. |
| Clinical NLP/OCR validation | Lawful independently annotated corpus, prespecified protocol, adjudication, and executed span/context/numeric/CER/WER analysis. |
| Patient registration | Verified source/target landmarks or transforms, coordinate frames, fitting/hold-out separation, TRE threshold, and observer review. |
| Forecasting/treatment effects | Repeated longitudinal outcomes, defined time zero/population/endpoint/horizon, chronological validation, integrated forecast model, and target-trial estimand for causal comparisons. |
| External/clinical validation | Independent-site data, subgroup/failure-mode work, calibration transfer, prospective safety evidence, clinical governance, and production security/regulatory review. |

The directive therefore remains incomplete for reasons that cannot be resolved by
inventing data, diagnoses, coordinates, metrics, or forecasts. The implemented system
fails closed at those boundaries.
