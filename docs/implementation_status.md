# MedTwin implementation status

Last verified 25 October 2026 on branch `feature/medtwin-2-integration` at baseline
commit `c67342f4503d`, with uncommitted implementation work present. This is a
software-research status record, not evidence of clinical safety, diagnostic
effectiveness, or deployment readiness.

Canonical evidence: `docs/development/MASTER_PROGRESS.md`,
`docs/testing/EXECUTED_TEST_RESULTS.md`, `docs/anatomy/BROWSER_WALKTHROUGH.md`,
`docs/imaging/DATASET_TRAINING_RESULTS.md`, and the 56-claim matrix in
`docs/research/traceability.json`.

| Area | Status | Verified scope and boundary |
| --- | --- | --- |
| Repository release / patient-data history | `BLOCKED` | Current-tree scan passes, but a PHI-bearing blob remains reachable on both local branches and the pre-push guard refuses release. An authorized rewrite or new sanitized repository plus clean history scan is required. |
| 24 named Downloads archives | `IMPLEMENTED_TESTED` | All were structurally inspected and SHA-256 catalogued; 23 canonical mappings were verified and one archive was atomically extracted/reverified 6,795/6,795. Ninety-one extras were audited; two symlink-unsafe archives were not extracted. |
| Dataset discovery and task audit | `IMPLEMENTED_TESTED` | 61 dataset units / 32 tasks: 10 ready, 1 exploratory-only, 21 blocked; 11 training-eligible. Licence, privacy, labels, grouping, duplicate/leakage, and split evidence are explicit. |
| Authentication, authorization, cases, evidence | `IMPLEMENTED_TESTED` | JWT authentication, isolation/sharing, de-identification attestation, content signatures, SHA-256 provenance, encrypted QA uploads, request IDs, deletion, and audit events are covered. |
| Durable background queue | `IMPLEMENTED_TESTED` | Separate-worker execution, leases, retries, cancellation, idempotency, GPU quota, browser reload persistence, and backend restart recovery pass. |
| Document parsing and scanned-PDF OCR | `IMPLEMENTED_UNVALIDATED` | TXT, DOCX, embedded/scanned PDF, CSV/XLSX and FHIR paths execute. The strict OCR evaluator supports CER/WER with byte-bound hash-only provenance, but no lawful representative medical-document gold set has been run. |
| Clinical NLP and numerical labs | `IMPLEMENTED_UNVALIDATED` | Exact spans, assertion/negation, certainty, temporality, experiencer, terminology, numeric values/units/intervals, structured/censored fields, deduplication, and strict span/context evaluation execute. No expert-annotated clinical corpus has established accuracy. |
| Clinician correction workflow | `IMPLEMENTED_TESTED` | Typed correction proposals are append-only, retain the original extractor/model output, display “proposed, not applied,” and produce audit evidence. |
| Longitudinal reports, biomarkers, serial evidence | `IMPLEMENTED_TESTED` | Source-linked comparisons, unit/identity compatibility gates, duplicate and censored-value exclusion, and exact arithmetic execute. They remain descriptive, not causal or prognostic. |
| Imaging readers | `IMPLEMENTED_TESTED` | PNG/JPEG/BMP, single DICOM objects, NIfTI, NRRD and MetaImage metadata/rendering paths are covered, including BMP signature rejection. Multi-file DICOM series assembly remains unsupported. |
| Research model registry | `IMPLEMENTED_UNVALIDATED` | 21 entries / 11 research-runnable / 0 clinically activatable. Seven 2-D image models support gated upload inference; the ECG classifier, both survival baselines and the cardiac MRI segmenter are evaluation-only. All results are internal research evidence. |
| Volumetric segmentation | `IMPLEMENTED_UNVALIDATED` | Generic 3-D NIfTI train/evaluate/checkpoint/resume; cardiac cine-MRI trained after the owner's recorded authorization (298 retained cases / 149 patients): 50 frozen test patients, macro Dice 0.750, LV ejection-fraction MAE 9.1 points; evaluation-only. |
| Live Anatomy Studio | `IMPLEMENTED_TESTED` | One engine rendered 43/43 real variants across all 10 systems in Edge; visible Chrome also opened the ten-system UI. Assets remain generic/reference anatomy. |
| Evidence-to-anatomy mapping | `IMPLEMENTED_UNVALIDATED` | Canonical states distinguish registered, region-verified, schematic-only, and not-mappable evidence. No precise atlas/patient location is created without reviewed registration. |
| Patient-specific registration / L3 reconstruction | `BLOCKED` | No reviewed patient landmarks, transforms, held-out TRE evaluation, or patient-specific meshes exist. |
| Prognosis Studio safety | `IMPLEMENTED_TESTED` | Independent route, eligibility/scenario panels, reason-coded abstention, and zero numeric risk/probability claims passed automated and visible browser inspection. |
| Validated forecasting or treatment effects | `BLOCKED` | Two baseline Cox evaluations exist, but no repeated longitudinal forecast cohort, chronological validation, integrated clinical model, causal estimand, or activation evidence exists. |
| Risk and statistical evaluation | `IMPLEMENTED_TESTED` | Task-appropriate metrics and immutable artifact binding are implemented; missing/mismatched inputs remain exploratory and unsupported patient risk remains unavailable. |
| IEEE traceability | `IMPLEMENTED_TESTED` | Exactly 56 claims: 28 tested, 18 partial, 5 implemented-not-validated, 3 proposed-only, 2 unsupported; revised Eq. (1)-(12) is preserved. |
| Docker configuration | `IMPLEMENTED_TESTED` | Docker client 29.9.2 / Compose 5.6.1; base and worker-profile configuration both exit 0 with a temporary non-secret validation key. |
| Docker build/container runtime | `BLOCKED` | The Desktop Linux engine pipe is absent; no image-build, migration, container-start, health, worker, persistence, or shutdown claim is made. |
| External/clinical validation and production release | `BLOCKED` | No independent-site/prospective study, clinical safety case, regulatory review, production threat model, database-at-rest solution, or production security assessment exists. |

## Latest executed verification

- Backend: **258 passed, 1 skipped** (`artifacts/verify/20261025T112434Z.json`).
- Frontend: typecheck, lint, and production build exited 0; recorded warnings remain
  non-failing engineering debt.
- Browser: **17/17 desktop**, **17/17 responsive**, **43/43 anatomy**, **7/7 image
  workflows**, **11/11 reports**; labs/corrections/OCR/NLP/request-ID/provenance/
  prognosis gates passed; zero unexpected console/page/failed-request errors. One
  intentional 422 tested request-ID display.
- Visible Chrome: correction history, BMP/C-NMC, Prognosis abstention, and the
  ten-system Anatomy interface were opened and inspected.
- Privacy: current-tree scan exits 0; history scan/pre-push remain intentionally blocked.
- Docker: Compose configuration exits 0; engine query fails because the engine is absent.

No status above upgrades an internal held-out result to external or clinical validation.
