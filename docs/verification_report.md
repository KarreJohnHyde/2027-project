# MedTwin Software Verification Report

> **Historical verification (23 October 2026).** The current executed evidence is `docs/testing/EXECUTED_TEST_RESULTS.md` and the raw record named there. The 51-test/four-asset statements below are not the current baseline.

**Verified:** 23 October 2026  
**Workspace:** `D:\project`

## Verification outcome

At this historical snapshot, the MedTwin source built and its 51-test backend suite passed. The canonical authenticated report workflow, persistence, reload, review, longitudinal comparison, JSON export, registries, and four generic L1 anatomy selections had software evidence at that date. No result in this report establishes medical-model accuracy, clinical validity, security compliance, or production readiness.

## Executed checks

| Check | Result | Status |
| --- | --- | --- |
| Backend suite | `.venv\Scripts\python.exe -m pytest backend\tests -q` -> **51 passed in 22.78 s** | Passed |
| Frontend | `npm run check` -> exit 0; TypeScript clean; oxlint reported 5 warnings; Vite production build succeeded in 12.13 s | Passed with warnings |
| Frontend bundle | Vite reported a JavaScript chunk larger than 500 kB | Engineering warning |
| Python compilation | Compile-all check completed cleanly | Passed |
| L1 anatomy assets | Validator accepted all four selectable GLBs | Passed structurally |
| Compose | `docker compose config --quiet` passed with a temporary non-secret `SECRET_KEY` | Configuration passed |
| Docker images/runtime | Docker Desktop engine unavailable | Not run |

## Verified application evidence

| Capability | Current evidence | Result |
| --- | --- | --- |
| Canonical application | React uses the authenticated `/api/v1` client against `backend/app/main.py` | Verified baseline |
| Upload integrity | Content-addressed storage and exact SHA-256 are persisted behind case authorization and de-identification attestation | Verified baseline |
| Report formats | TXT, DOCX, and embedded-text PDF parsers are covered; image-only PDF fails explicitly because OCR is absent | Verified baseline with explicit limitation |
| Extraction | Transparent rules persist source spans, assertion/negation/temporality metadata, and numeric values/units | Verified software behavior; not corpus validated |
| Longitudinal comparison | Compatible examination-linked values produce source-to-source arithmetic deltas | Verified software behavior |
| Human review | Append-only decision preserves the original extracted output and adds an audit event | Verified software behavior |
| Evidence export | Browser produces versioned JSON for case, uploads, jobs, findings, statements, measurements, provenance, and capability snapshot | Verified browser action |
| Registries | 33 dataset records are read-only and ineligible; 11 model records expose activation blockers; 0 models are activatable | Verified gates |
| Anatomy | Heart, Lungs, Brain, and GI were selectable and visibly loaded as generic L1 models with current screenshots | Verified generic visualization only |

## Authenticated acceptance case

The current synthetic case used two de-identified TXT fixtures:

- SHA-256 `4f4fd1fdf5a38ca569ce4f07eed661bdef6f72234e13973bda1a68bfccf93b44`
- SHA-256 `fdae8b1ffce67657da6fc46e6d874060154e64c626d18760fa0091e9af9a1e56`

After processing and reload, the UI showed two uploads, two completed jobs, two findings, 12 source-linked measurements, and six matched longitudinal deltas. The `REJECTED` review record retained `original_output_preserved=true`, kept the original finding label, and added a separate audit event.

The browser export used schema `medtwin-evidence-export-1.0.0` and contained the two-examination case, 2 uploads, 2 analysis jobs, 2 findings, 2 report statements, 12 measurements, 9 case-scoped provenance events, and the capability snapshot.

Current evidence images are in `docs/screenshots/current/`, covering persisted evidence, SHA-256 display, registry gates, review, audit history, comparison, reload, and Heart/Lungs/Brain/GI selection.

**Incomplete browser step:** the browser-control extension could not use `setFiles` because **Allow access to file URLs** was not enabled. Upload and processing were performed through the authenticated API, then the browser UI and reload verified the resulting state. Direct browser file-picker upload is not complete and must not be reported as passed.

## Benchmark results

### Static HTTP path

`benchmarks/results/http-benchmark-20261023-224119.json`  
SHA-256 `a0aa79f8325a9fbc8df7a1f264417db4033c225de25003f1b1dc4b9ad80cb9ae`

1,200/1,200 measured requests succeeded with zero failures.

| Concurrency | p50 | p95 | Successful throughput | Maximum RSS |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2.4457 ms | 14.8431 ms | 239.191 req/s | 675,319,808 bytes |
| 8 | 36.3531 ms | 102.1521 ms | 176.089 req/s | 681,177,088 bytes |

### Report workflow

`benchmarks/results/report-workflow-benchmark-20261023-223734.json`  
SHA-256 `23218cea29b4b2d0fd4122dc95b9e3b27c0f1c550fb8e50b1102ec8f2b620627`

120/120 synthetic de-identified upload-through-provenance-reload workflows succeeded with zero failures.

| Concurrency | p50 | p95 | Successful throughput | Maximum RSS |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 126.6303 ms | 154.5894 ms | 7.878 workflows/s | 678,268,928 bytes |
| 4 | 215.0010 ms | 382.4426 ms | 15.816 workflows/s | 681,021,440 bytes |

Both artifacts explicitly record `clinical_performance_measured=false`. They are local software benchmarks, not evidence of real-time clinical operation.

## Inventory and readiness facts

- 205 root entries were inventoried.
- All 69 ZIP central directories were readable; payload CRCs were not revalidated.
- 15 named repositories are extracted; `Foresight-main.zip` remains archive-only.
- The dataset audit covers 33 paths, 154,817 raw files, and 46.06 GiB.
- No dataset is training- or validation-eligible; 30 of 33 have unknown license status.
- The registry contains 11 model records and no activatable learned medical model.

## Unverified or unavailable capabilities

The following are not complete: OCR; resumable uploads; durable asynchronous workers; PDF evidence export; tamper-evident audit retention; container build/runtime verification; MURA, PTB-XL/MIT-BIH, or annotated NLP evaluation; clinically evaluated fusion, registration, or forecasting; patient-specific L3 anatomy; and independent security, privacy, regulatory, clinical-safety, or human-factors review.

Accordingly, do not claim diagnostic accuracy, calibrated learned-model confidence, clinical effectiveness, real-time clinical operation, HIPAA compliance, patient-specific anatomical localization, or production deployment readiness.
