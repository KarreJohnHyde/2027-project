# MedTwin Final Integration Report

> **Historical snapshot (23 October 2026).** This report predates the 24 October master-directive execution and is retained for provenance. It is superseded for current status by `docs/development/FINAL_REPORT.md`, `docs/implementation_status.md`, and `docs/testing/EXECUTED_TEST_RESULTS.md`; do not use the model, OCR, queue, anatomy, dataset-readiness, or browser counts below as current facts.

**Evidence cutoff:** 23 October 2026  
**Workspace:** `D:\project`  
**Scope:** software integration and reproducibility evidence only

## Executive conclusion

MedTwin is now a runnable software-only research prototype built around one authenticated React and FastAPI application. The verified baseline can keep a pseudonymous case, accept an explicitly de-identified report through the versioned API, store the file by SHA-256, run a transparent rule-based report processor, persist source-linked findings and numeric measurements, compare compatible dated measurements, append a human-review decision without overwriting the extracted label, reload the evidence and audit history, export a versioned JSON evidence package, and display four selectable generic L1 anatomy models.

This is not a clinically validated medical AI system. The audited datasets are not approved for training or validation, no learned medical model is activatable, and no MURA, PTB-XL/MIT-BIH, annotated clinical-text, fusion, registration, or forecasting evaluation has been completed. The saved benchmarks measure local software behavior only.

## Integrated application baseline

| Area | Current evidence-backed state | Boundary |
| --- | --- | --- |
| Application contract | `backend/app/main.py` is the canonical FastAPI entry point. `src/App.tsx` and `src/services/api.ts` use the authenticated `/api/v1` contract. Development seeding is environment-controlled. | No production identity-provider or tenant-isolation assessment. |
| Case and evidence storage | Case-authorized uploads require de-identification attestation, calculate SHA-256, and use content-addressed local storage with persisted metadata and audit events. | No resumable upload, malware sandbox, object store, or validated retention/deletion workflow. |
| Report processing | TXT, DOCX, and embedded-text PDF parsing is implemented. The transparent rules baseline records assertions, negation/temporality metadata, numeric values, units, and exact source spans. | Image-only PDF is rejected because OCR is not implemented. The rules have not been evaluated on an annotated clinical corpus. |
| Longitudinal evidence | Dated, examination-linked measurements are compared only when names and units match. The response preserves both source values and spans and returns arithmetic deltas without clinical interpretation. | No unit-normalization study, clinical change model, or longitudinal forecasting evaluation. |
| Review and export | Review decisions are appended while the original extracted output is preserved. The browser exports `medtwin-evidence-export-1.0.0` JSON containing the case, uploads, jobs, findings, report statements, measurements, provenance, and a capability snapshot. | No PDF evidence export, signed report, or tamper-evident audit-retention mechanism. |
| Registries | Read-only model/capability and dataset registries expose readiness blockers and fail closed for activation. | No learned model currently satisfies the artifact-bundle activation gate. |
| Anatomy viewer | Heart, Lungs, Brain, and GI are selectable, visibly rendered GLBs in one React Three Fiber viewer. All are labeled generic L1 reference anatomy. | No patient-specific geometry, L2 registration result, or L3 reconstruction. Upstream asset/license review is not complete. |
| Image and ECG paths | File validation and preprocessing/preview paths exist and return explicit unavailable/not-run states when weights are absent. | No image or ECG learned inference or clinical performance result. |

Analysis jobs are persisted but currently execute synchronously in the request. Durable background workers, retries, cancellation, and failure recovery remain future work.

## Workspace and repository inventory

The bounded workspace inventory recorded:

- 205 root entries: 136 files and 69 directories;
- 69 ZIP archives, all 69 with readable central-directory metadata; archive payload CRCs were not revalidated;
- 15 extracted repositories named by the integration prompt; and
- one named archive-only repository, `Foresight-main.zip`, inspected in place and not extracted.

The extracted named repositories are `scispacy-main`, `radgraph-master`, `MONAI-dev`, `health-assistant-main`, `metriport-develop`, `cogstack-nlp-main`, `MedCAT-main`, `TwinWeaver-main`, `CogStack-SemEHR-master`, `SIH_26047-main`, `medical-main`, `medvault-ai-main`, `human-atlas-main`, `anatomy-main`, and `3d-anatomy-atlas-main`.

They were not merged wholesale into MedTwin. Source presence is treated as discovery evidence, not proof that a dependency, trained model, license, or runnable adapter is available. The machine-readable records are `docs/integration/FILE_REGISTRY.json` and `docs/integration/COMPONENT_REGISTRY.json`.

## Dataset and model readiness

| Gate | Audited result | Decision |
| --- | ---: | --- |
| Registered dataset paths | 33 | Discovery catalog only |
| Raw files observed | 154,817 | Non-deduplicated file count, not patients or independent samples |
| Raw size observed | 46.06 GiB | Overlapping roots must not be summed as independent datasets |
| Training eligible | 0 / 33 | Blocked |
| Validation eligible | 0 / 33 | Blocked |
| Unknown license status | 30 / 33 | Source/license resolution required |
| Model records | 11 | Registry metadata only |
| Activation eligible | 0 / 11 | No learned medical model may be activated |

The model registry contains one transparent `READY_UNVALIDATED` processor-only rules baseline, one discovered record, three dependency-missing records, five weights-missing records, and one unsupported record. A complete activation bundle must include dataset/version/license, a patient/study split manifest, task and label definition, preprocessing version, checkpoint and hash, calibration data, decision and abstention thresholds, held-out predictions, an evaluation report, and a model card.

## Current authenticated acceptance evidence

The browser acceptance case `BROWSER-QA-20261023` used two synthetic, de-identified TXT fixtures:

1. `browser_acceptance_report.txt` - SHA-256 `4f4fd1fdf5a38ca569ce4f07eed661bdef6f72234e13973bda1a68bfccf93b44`.
2. `browser_acceptance_report_followup.txt` - SHA-256 `fdae8b1ffce67657da6fc46e6d874060154e64c626d18760fa0091e9af9a1e56`.

The persisted case contained two dated examinations, two uploads, two completed rule-baseline jobs, two findings, two report statements, and 12 source-linked measurements. The longitudinal comparison returned six matched numeric deltas. A `REJECTED` human review was appended with `original_output_preserved=true`; the original `Clinical Impression (AFFIRMED)` label remained unchanged, and a separate `HUMAN_REVIEW_SUBMITTED` event was retained.

The JSON export was exercised with schema `medtwin-evidence-export-1.0.0`. For the selected acceptance case it carried two uploads, two analysis jobs, two findings, two report statements, 12 measurements, nine case-scoped provenance events, the two-examination case record, and the current capability snapshot.

Current screenshots are retained under `docs/screenshots/current/`:

- `browser-evidence-success.jpg`
- `browser-upload-sha256.jpg`
- `browser-registry-gates.jpg`
- `browser-human-review.jpg`
- `browser-audit-history.jpg`
- `browser-longitudinal-comparison.jpg`
- `browser-reload-overview-3d.jpg`
- `browser-3d-lungs-selected.jpg`
- `browser-3d-brain-selected.jpg`
- `browser-3d-gi-selected.jpg`

**Browser-upload limitation:** the browser-control extension could not call `setFiles` because it lacks **Allow access to file URLs** permission. The two files were therefore uploaded and processed through the same authenticated API, after which the browser UI and a browser reload verified the persisted evidence, review, audit history, comparison, export action, and four GLB selections. A complete direct browser file-picker upload action has **not** been verified.

## Final software checks

| Check | Current result | Interpretation |
| --- | --- | --- |
| Backend tests | `51 passed in 22.78 s` | Software behavior passed the current test suite; this is not clinical validation. |
| Frontend check | `npm run check` exited 0: TypeScript clean, oxlint completed with 5 warnings, Vite build succeeded in 12.13 s | Build passes. The warnings and the Vite chunk larger than 500 kB remain engineering work. |
| Python compilation | Clean | Current Python sources compile. |
| GLB validation | All 4 selectable L1 GLBs valid | Structural asset validation only. |
| Compose configuration | `docker compose config --quiet` passed with a temporary non-secret `SECRET_KEY` | Compose resolves successfully. |
| Docker runtime | Unavailable | Docker Desktop's engine was unavailable, so no local image build or container runtime result is claimed. |

## Reproducible software benchmarks

Both artifacts record `clinical_performance_measured=false`. They used same-host IPv4 loopback, one Uvicorn worker, isolated temporary SQLite/upload state, Python 3.12.15, and a Windows 11 host. The detected RTX 5060 Laptop GPU was not used by either workload.

### Static service path

Artifact: `benchmarks/results/http-benchmark-20261023-224119.json`  
SHA-256: `a0aa79f8325a9fbc8df7a1f264417db4033c225de25003f1b1dc4b9ad80cb9ae`

The `/api/v1/catalog/packages` run completed 1,200 of 1,200 measured requests with zero failures.

| Concurrency | Median-of-repeats p50 | Median-of-repeats p95 | Median successful throughput | Maximum process-tree RSS |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2.4457 ms | 14.8431 ms | 239.191 req/s | 675,319,808 bytes |
| 8 | 36.3531 ms | 102.1521 ms | 176.089 req/s | 681,177,088 bytes |

### Synthetic report workflow

Artifact: `benchmarks/results/report-workflow-benchmark-20261023-223734.json`  
SHA-256: `23218cea29b4b2d0fd4122dc95b9e3b27c0f1c550fb8e50b1102ec8f2b620627`

The create-case through provenance-reload workload completed 120 of 120 workflows with zero failures. Every workflow used unique synthetic text, sent `deidentified=true`, matched the client/server/reloaded SHA-256, completed the rules job, persisted six expected measurements, and reloaded findings and audit provenance.

| Concurrency | Median-of-repeats p50 | Median-of-repeats p95 | Median successful throughput | Maximum process-tree RSS |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 126.6303 ms | 154.5894 ms | 7.878 workflows/s | 678,268,928 bytes |
| 4 | 215.0010 ms | 382.4426 ms | 15.816 workflows/s | 681,021,440 bytes |

These numbers do not establish real-time clinical operation, diagnostic accuracy, model inference performance, or intended-deployment capacity.

## Remaining completion gates

1. Automate the authenticated browser path with direct file-picker upload, reload assertions, success/failure cases, JSON-download content checks, and WebGL failure coverage.
2. Resolve source, license, patient/study identity, split, label, corruption, and deduplication evidence before approving any dataset for training or validation.
3. Complete one immutable model artifact bundle and held-out evaluation, preferably the MURA study-level classification baseline, before starting additional model integrations.
4. Run PTB-XL/MIT-BIH and licensed annotated clinical-text evaluations independently with patient-aware or official splits and saved predictions.
5. Implement and test malware scanning, sandboxing, resumable uploads, durable background workers, PDF export, tamper-evident audit retention, backup/recovery, and data-retention/deletion controls.
6. Treat paired multimodal fusion, landmark registration, forecasting, DeepSA reproduction, and patient-specific L3 anatomy as separate research projects with their own data and acceptance contracts.
7. Build and run the containers when Docker is available, then complete threat modeling, penetration testing, privacy review, clinical-safety review, human-factors testing, and regulatory assessment before any pilot.

## Claims boundary

The defensible description is: **MedTwin is an authenticated, provenance-preserving software research prototype with a transparent, unvalidated report-processing baseline and generic L1 anatomy visualization.**

Do not claim OCR, resumable upload, asynchronous workers, PDF export, tamper-evident audit retention, trained or clinically validated medical models, MURA/PTB-XL/NLP performance, validated fusion/registration/forecasting, patient-specific digital twins, real-time clinical operation, diagnostic effectiveness, HIPAA compliance, or deployment readiness from the current evidence.
