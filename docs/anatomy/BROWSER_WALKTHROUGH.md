# Browser walkthrough

Run 2026-10-25T14:07:06.801Z → 2026-10-25T14:11:24.417Z with Microsoft Edge 156.0.4314.42 (playwright-core 1.63.0, headless) against the isolated QA stack (http://127.0.0.1:8453; started by `scripts/dev.ps1 -Mode qa`: isolated scratch SQLite database, encrypted upload store, worker-mode job queue with a separate worker process, synthetic QA login). The QA database contains no patient record; browser-created inputs are explicitly synthetic, and optional imaging inputs must be public research examples supplied on the command line.

Reproduce from a new synthetic QA state: `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Mode qa -Fresh`, then `node tools/browser-qa/walkthrough.mjs --state %TEMP%\medtwin-qa --out <dir> --sections routes,responsive,anatomy,lifecycle,labs,evidence,corrections,queue,imaging,validation,trained,prognosis --model-image MODEL_ID:MODALITY=<public-research-image> ...`, repeating `--model-image` once for every runnable `image_2d` model listed by `/research-models`, or `scripts/verify.ps1 -Browser`. Screenshots are written to the output directory, outside the repository.

Unexpected browser errors over the whole run: **0 console errors, 0 uncaught page errors, 0 failed requests**. Expected client-error probes recorded separately: **1**.

Fail-closed walkthrough assertion gate: **PASS**.
Raw evaluator fixture text absent from `walkthrough.json`: **PASS**.

## Routes

17 of 17 routes rendered a page heading without an error boundary.

| Route | Heading | Result | New browser errors |
| --- | --- | --- | --- |
| `/` | DEV-20261025-001 | PASS | 0 |
| `/cases` | DEV-20261025-001 | PASS | 0 |
| `/upload` | Add evidence to DEV-20261025-001 | PASS | 0 |
| `/documents` | Clinical document analysis | PASS | 0 |
| `/imaging` | Imaging viewer and modality coverage | PASS | 0 |
| `/biomarkers` | Documented measurements over time | PASS | 0 |
| `/history` | Examination-pair comparison | PASS | 0 |
| `/anatomy-studio` | Heart | PASS | 0 |
| `/prognosis-studio` | MedTwin Prognosis Studio — Evidence-Based Longitudinal Risk and Scenario Analysis | PASS | 0 |
| `/multimodal` | Modality inventory, fusion and concordance | PASS | 0 |
| `/risk` | Risk instruments and explanation methods | PASS | 0 |
| `/models` | Models and activation gates | PASS | 0 |
| `/datasets` | Dataset evidence and task readiness | PASS | 0 |
| `/validation` | Model evaluation, traceability and test evidence | PASS | 0 |
| `/reports` | Evidence-linked research report | PASS | 0 |
| `/settings` | Workspace settings | PASS | 0 |
| `/attribution` | Data sources and licences | PASS | 0 |

## Phone-width route checks

**17 of 17 routes passed at 390 × 844 CSS pixels.** A pass requires a rendered page heading, the requested viewport, no error boundary and no page-level horizontal overflow. Wide tables may scroll inside their own containers. A screenshot was captured for every route.

Mobile navigation opened and closed through its visible controls: PASS.

| Route | Heading | Viewport | Page overflow | New browser errors | Result |
| --- | --- | --- | ---: | ---: | --- |
| `/` | DEV-20261025-001 | PASS | 0 px | 0 | PASS |
| `/cases` | DEV-20261025-001 | PASS | 0 px | 0 | PASS |
| `/upload` | Add evidence to DEV-20261025-001 | PASS | 0 px | 0 | PASS |
| `/documents` | Clinical document analysis | PASS | 0 px | 0 | PASS |
| `/imaging` | Imaging viewer and modality coverage | PASS | 0 px | 0 | PASS |
| `/biomarkers` | Documented measurements over time | PASS | 0 px | 0 | PASS |
| `/history` | Examination-pair comparison | PASS | 0 px | 0 | PASS |
| `/anatomy-studio` | Heart | PASS | 0 px | 0 | PASS |
| `/prognosis-studio` | MedTwin Prognosis Studio — Evidence-Based Longitudinal Risk and Scenario Analysis | PASS | 0 px | 0 | PASS |
| `/multimodal` | Modality inventory, fusion and concordance | PASS | 0 px | 0 | PASS |
| `/risk` | Risk instruments and explanation methods | PASS | 0 px | 0 | PASS |
| `/models` | Models and activation gates | PASS | 0 px | 0 | PASS |
| `/datasets` | Dataset evidence and task readiness | PASS | 0 px | 0 | PASS |
| `/validation` | Model evaluation, traceability and test evidence | PASS | 0 px | 0 | PASS |
| `/reports` | Evidence-linked research report | PASS | 0 px | 0 | PASS |
| `/settings` | Workspace settings | PASS | 0 px | 0 | PASS |
| `/attribution` | Data sources and licences | PASS | 0 px | 0 | PASS |

## Anatomy Studio — ten systems

**43 of 43 variants rendered; 10 of 10 systems with every variant rendered.** Each variant was opened at `/anatomy-studio?system=<id>&variant=<id>`, orbited with a mouse drag, and counted as rendered only when the viewer's WebGL counters reported triangles or points and the canvas showed real content (luminance σ > 3, > 1 % non-background pixels). Per-variant numbers: `docs/anatomy/ASSET_QA.md`.

| System | Variants | Rendered |
| --- | --- | --- |
| heart | 4 | 4 |
| lungs | 7 | 7 |
| brain | 7 | 7 |
| liver | 4 | 4 |
| pancreas | 3 | 3 |
| intestines | 2 | 2 |
| nervous | 2 | 2 |
| skeletal | 3 | 3 |
| hybrid | 1 | 1 |
| kidneys | 10 | 10 |

## Upload lifecycle (synthetic report)

- Upload Center: file chosen, case-match and de-identification confirmations ticked, uploaded and processed: PASS (row reached *Completed*).
- Queue transition message was visible in the upload row: PASS (`Queued job #1: Queued`).
- Durable jobs recorded for the case: #1 UPLOAD_ANALYSIS SUCCEEDED (worker, attempts 1).
- Document Intelligence: 2 source-linked statements rendered; measurement text visible: PASS.

## Manual laboratory entry and deduplication

- Submitted a synthetic creatinine transcription through the real dialog: PASS.
- Linked the selected synthetic source upload: PASS.
- Blank laboratory/specimen rendered as *not documented*: PASS.
- No printed interval rendered *Indeterminate*, while the catalog interval was labelled orientation-only: PASS.
- Duplicate exclusion was visible in Biomarker Analytics and persisted in the returned series: PASS (`DUPLICATE_OF_M2`).
- Dated creatinine points after deduplication: 1.
- Entered a second, unlinked software fixture with laboratory, specimen and assay fields plus a `<` comparator: PASS.
- Structured provenance and the censoring operator round-tripped through the API; the censored value remained *Indeterminate* instead of being range-classified: PASS.

## Source evidence to Anatomy Studio

- Synthetic source statement and its Lungs link rendered in Document Intelligence: PASS.
- Clicking the link opened the Lungs workspace and displayed the exact source span with a schematic-only mapping: PASS.
- Submitted *Needs landmark registration* through the hybrid placement-review UI and re-read the persisted review: PASS. The review deliberately does not promote the layer to patient registration.

## Clinician correction proposal

- Opened the synthetic finding's clinician-review controls and submitted a typed removal proposal: PASS.
- The API retained `PROPOSED_NOT_APPLIED`, set the original-output-preserved flag, and left the source statement unchanged: PASS.
- The UI separately displayed *Original evidence · preserved* and *Proposed correction · not applied*: PASS.

## Durable queue evidence

- Upload UI displayed a queued-job transition: PASS.
- Case Workspace still displayed persisted analysis job #1 after a hard browser reload: PASS.
- Queue record #1 remained queryable after reload: PASS; status `SUCCEEDED`, execution mode `worker`, attempts 1.
- Scope: Browser reload plus persisted database record; worker-process restart is covered by backend tests and was not performed in this walkthrough.

## Research models in Medical Imaging

- Runnable `image_2d` registry contract: 7 models (`angiography_stenosis_detector`, `angiography_syntax_segmenter`, `gi_gastrovision_27class_classifier`, `gi_kvasir_seg_polyp_segmenter`, `gi_kvasir_v2_classifier`, `hematology_cnmc_all_classifier`, `kidney_stone_detector`).
- Every model had exactly one explicit `MODEL_ID:MODALITY=image` binding, with no missing, unexpected or duplicate IDs: PASS. Missing: none; unexpected: none; duplicates: none.
- Seven-workflow regression contract (including Kvasir-SEG and C-NMC) matches the live registry: PASS.

| Input type | Model | Task | Upload stored (row badge) | Completed in UI | Overlay shapes drawn | Probability rows |
| --- | --- | --- | --- | --- | --- | --- |
| ENDOSCOPY | `gi_kvasir_v2_classifier` | image_classification | PASS (Not run) | PASS | 0 | 8 |
| ANGIOGRAPHY | `angiography_stenosis_detector` | object_detection | PASS (Not run) | PASS | 5 | — |
| CT | `kidney_stone_detector` | object_detection | PASS (Not run) | PASS | 1 | — |
| ANGIOGRAPHY | `angiography_syntax_segmenter` | semantic_segmentation | PASS (Not run) | PASS | 1 | — |
| ENDOSCOPY | `gi_gastrovision_27class_classifier` | image_classification | PASS (Not run) | PASS | 0 | 27 |
| ENDOSCOPY | `gi_kvasir_seg_polyp_segmenter` | semantic_segmentation | PASS (Not run) | PASS | 1 | — |
| MICROSCOPY | `hematology_cnmc_all_classifier` | image_classification | PASS (Not run) | PASS | 0 | 2 |

Each run required the input-type confirmation checkbox, went through the worker queue (GPU resource), and showed the *Research only · not clinically validated* banner with the model's internal held-out evaluation. Detection boxes are drawn as an SVG layer in source-pixel coordinates over the original image; classification draws no overlay. The C-NMC workflow used its native `.bmp` file through upload, display, applicability confirmation, and inference.

## Validation Center evaluator controls

- A schema-invalid Clinical NLP upload produced a visible API request ID matching the 422 response header: PASS.
- Clinical NLP strict-schema controls ran, persisted hash-only artifact provenance and remained exploratory: PASS.
- OCR strict-schema controls ran, displayed and persisted `raw_text_persisted=false`, and remained exploratory: PASS.
The inputs are de-identified, hand-authored software-contract fixtures. Their numeric scores are deliberately not reproduced here and are not scientific model evidence.

## Registered trained-model reports

11 of 11 registry reports rendered the task-specific evidence view, provenance and applicable evaluation-only/exploratory badges.

## Prognosis Studio

- Separate route `/prognosis-studio` with no 3D canvas of its own: PASS.
- Capability panel shows unavailability states before evaluation (not trained / not validated / estimand undefined): 4 markers.
- *Evaluate* for kidneys renders the two scenario panels (4 scenario headings) with abstention reason codes (`MODEL_NOT_VALIDATED`, `INTERVENTION_NOT_SPECIFIED`, ...): 5 markers — PASS.
- Numeric risk or probability statements: 0 — PASS (none may appear without a validated model).

## Not covered by this walkthrough

- Automated pixel-diff visual-regression baselines (screenshots are captured but not compared against a golden image).
- A worker-process restart during this browser run; restart persistence remains covered by the backend queue regression test.
- Docker images (engine not running).
