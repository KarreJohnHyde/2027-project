# MedTwin 2.0 implementation-gap report

Verified 25 October 2026; updated 28 October 2026 for ECG and cardiac MRI upload inference,
DICOM series assembly and Docker builds. The authoritative claim matrix is
`docs/research/traceability.json` (exactly 56 claims) and its narrative is
`docs/research/IEEE_TRACEABILITY_REPORT.md`. Software evidence does not establish
clinical accuracy, safety, or fitness for patient care.

## Blocking gaps

| Area | Status | What exists | What is still required |
| --- | --- | --- | --- |
| Repository release | `BLOCKED` | Current-tree privacy scan and pre-push containment pass. | PHI remains in reachable history on both local branches. Obtain explicit authorization and evidence-retention decision, then purge/verify or create a new sanitized canonical repository before sharing. |
| Remaining dataset tasks | `BLOCKED` | 61 dataset units / 32 tasks audited; 10 ready, 1 exploratory, 21 blocked. | Resolve licences, privacy, labels, modality/provenance, patient grouping, leakage, missing images, or sample/split limitations per task. Archive-05 requires privacy review. |
| Clinical NLP/OCR validation | `BLOCKED` | OCR, terminology/context rules, numerical extraction, strict OCR and NLP evaluators, immutable input digests, and hash-only provenance execute. | Lawful independently annotated representative corpus, adjudication, prespecified metrics, error analysis, and executed real evaluation. |
| External/clinical model validation | `BLOCKED` | Eleven research-runnable internal bundles exist: nine run on uploads (seven 2-D image models, the ECG classifier on digital records, the cardiac MRI segmenter on single NIfTI frames) and two survival baselines are evaluation-only. | Independent-site data, prespecified endpoints, subgroup/failure-mode analysis, applicability/OOD checks, calibration transfer, clinical review, prospective safety evidence, and activation governance. |
| Patient spatial registration | `BLOCKED` | Rigid fitting, held-out TRE, and reviewed landmark manifests: one verified clinician proposes landmark pairs with held-out landmarks declared up front, a second approves, and only an approved manifest whose held-out TRE is within its limit can lift a finding to L2 (`/findings/{id}/landmark-manifests`). | A landmark-placement interface, reviewed patient landmarks on real studies, justified thresholds, and an observer/external evaluation of registration accuracy. |
| Paired multimodal fusion | `BLOCKED` | Fusion gates and tensor invariants are tested. | Authorized same-patient paired data, validated encoders, patient-level splits, and a prespecified fusion evaluation. |
| Forecasting/treatment scenarios | `BLOCKED` | Prognosis Studio enforces eligibility/abstention; PBC and heart-failure Cox baselines have internal event/censor evaluations. | Repeated longitudinal cohort, defined time zero/population/endpoint/horizon, chronological hold-out, integrated validated forecast model, and a target-trial estimand/causal assumptions for interventions. |
| Docker execution | `DONE` (local) | A full Compose run with the worker profile passed on 2026-10-28: health, migrations, worker-executed job, encrypted uploads and SQLCipher database on the volume, non-root containers, frontend security headers, restart persistence, clean shutdown. | Repeat on the deployment host; CI builds the images but does not start them. |
| Production release | `NOT_STARTED` | Local research stack and software verification suite exist. | Production identity/tenant review, database key rotation and encrypted backups, threat model, malware scanning, retention/deletion policy, tamper-evident audit retention, penetration testing, accessibility/human factors, clinical safety case, and regulatory assessment. |

## Implemented but not clinically or externally validated

| Capability | Evidence boundary |
| --- | --- |
| Scanned-PDF OCR and clinical NLP | Functional and strict-evaluator tests pass; no lawful representative independent gold study exists. |
| Kvasir v2 classifier | Internal n=1,202; accuracy/macro-F1 0.926; source patient identities unavailable. |
| GastroVision classifier | Exploratory internal n=1,225; accuracy 0.737, macro-F1 0.553; rare classes lack adequate support. |
| ARCADE stenosis detector | Internal n=300; mAP 0.0618, AP50 0.2029; near-duplicate sensitivity analysis exists. |
| TEZ kidney-stone detector | Internal n=196; mAP 0.2312, AP50 0.6286; no external CT cohort. |
| ARCADE SYNTAX segmenter | Internal n=300; vessel Dice 0.6829, mean foreground Dice/image 0.3070; sparse/absent segment support. |
| Kvasir-SEG segmenter | Internal n=120; Dice 0.7679, IoU 0.6696; same-source and patient independence unavailable. |
| C-NMC classifier | Internal n=1,867 / 28 filename-derived clusters; accuracy 0.807, macro-F1 0.790; identity assumptions and wide cluster intervals limit interpretation. |
| PTB-XL ECG baseline | Internal n=2,163 / 1,881 patients; macro AUROC 0.917, macro AUPRC 0.805; single historical source; research-only upload inference for digital records (parity with held-out predictions verified). |
| PBC Cox baseline | Internal n=104 hold-out patients; Harrell's C 0.786; population-specific, evaluation-only, not a longitudinal trajectory product. |
| Heart-failure Cox baseline | Exploratory n=90; Harrell's C 0.671; integrated Brier is worse than Kaplan-Meier; no patient forecast is exposed. |
| Generic volumetric pipeline / cardiac MRI | Owner-authorized cardiac cine-MRI training: macro Dice 0.750 and LV ejection-fraction MAE 9.1 points on 50 frozen test patients; volumes overestimated; research-only single-frame NIfTI upload inference inside the spacing envelope; no external validation. |

Registry state: **21 entries; 13 `READY_UNVALIDATED` (the 11 trained research models plus the
clinical-text rules baseline and the scispaCy adapter); 9 models accept uploads; 0 clinically
activatable**. The other 8 entries lack weights or dependencies, or are unsupported.
Exact intervals, hashes, thresholds, splits, and limitations are in
`docs/imaging/DATASET_TRAINING_RESULTS.md`, `docs/imaging/VOLUMETRIC_SEGMENTATION_PIPELINE.md`,
and `docs/validation/models/`.

## Deliberately unsupported outputs

| Output | Status | Reason |
| --- | --- | --- |
| Patient-specific L3 anatomy or lesion pin from a research image | `UNSUPPORTED` | No reviewed patient registration exists. Source-pixel geometry may become at most a clinician-confirmed schematic organ association. |
| Personalized treatment recommendation or fabricated future risk | `UNSUPPORTED` | No validated integrated causal or longitudinal forecast model exists. Prognosis must continue to abstain. |
| EEG interpretation; DeepSA workflow | `UNSUPPORTED` | EDF/BDF recordings are read and displayed, but no EEG model exists; DeepSA weights and its executable are absent. Assembled DICOM series render and run through the cardiac MRI segmenter; HL7 v2 result import is implemented. ECG upload inference exists for digital WFDB format-16 and CSV records only. |

## Engineering gaps that do not remove the scientific blockers

- Add image-quality checks; the applicability gate (`docs/validation/IMAGE_APPLICABILITY_GATE.md`)
  still accepts most angiograms for the GastroVision classifier.
- Verify the in-plane orientation convention of scanner-native DICOM series for the cardiac
  MRI segmenter (the development NIfTI frames carry no orientation).
- Add golden-image regression and automated accessibility audits to the CI browser suite.
- Exercise worker termination/restart in a browser scenario in addition to backend tests.
- Reduce the large Anatomy bundle and resolve non-failing React lint warnings.
- Add production malware scanning, object storage, database key rotation and encrypted backups,
  retention/deletion policy, recovery tests, and tamper-evident audit retention.

## Completed experiments and verification

- Ten training/evaluation bundles were executed on correctly gated public research
  tasks: seven 2-D image models, the PTB-XL ECG baseline and two survival baselines.
- The 3-D NIfTI pipeline first failed closed at its licence gate; after the owner's recorded
  authorization it trained the cardiac cine-MRI segmenter.
- On 2026-10-28 the ECG and cardiac MRI upload paths were run on their public held-out sets
  and reproduced the saved predictions: ECG max probability difference 0.0024 over 2,161
  records, MRI 98 of 98 masks identical (`docs/validation/UPLOAD_INFERENCE_PARITY.md`).
- Latest software verification (2026-10-28): 331 backend tests passed, 1 intentional skip;
  frontend typecheck/lint/build; GitHub CI green for backend, frontend and Docker image builds.
- Browser QA passed 17/17 desktop, 17/17 responsive, 43/43 anatomy, 7/7 image workflows,
  and 11/11 reports. Labs, corrections, OCR/NLP controls, request IDs, hash-only/no-raw-
  text provenance, queue persistence, and prognosis abstention passed with zero
  unexpected console/page/failed-request errors.
- The 2026-10-25 software suite passed **258 backend tests, 1 intentional skip**, frontend
  typecheck/lint/build, and current-tree privacy scan.
- The 56-claim traceability audit resolves all evidence paths and preserves revised
  Eq. (1)-(12): 28 tested, 18 partial, 5 implemented-not-validated, 3 proposed-only,
  2 unsupported.

## Data-protection finding

Sensitive current-tree content was removed, but Git history is not remediated.
Containment (zero remotes, remote refs, tags, and stashes) is not proof the repository
was never copied. `docs/security/PHI_RELEASE_BLOCKER.md` is the release authority. Do
not push, publish, bundle, clone for transfer, or share the repository while blocked.
GitHub releases are history-free snapshots: the committed files are copied into a
separate clone, verified blob-for-blob, privacy-scanned (history and tree) and only then
pushed; this repository's own history is never transferred.
