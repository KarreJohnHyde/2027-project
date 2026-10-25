# IEEE traceability report

Machine-readable source: `docs/research/traceability.json` (schema
`medtwin-traceability-1.0.0`), served by `GET /api/v1/research/traceability` and
shown in **Validation Center -> Traceability**. The manuscripts were read, not
modified.

## Manuscript versions and equation numbering

| Manuscript | Equations | Mapping in MedTwin |
| --- | --- | --- |
| `MedTwin_2_Software_Only_IEEE_Revised_Research_Draft.docx` (revised draft, SHA-256 `dbcbc8c3...`, `manuscript_modified: false`) | (1)-(12) | `docs/research/traceability.json`: exactly 56 claims |
| `MedTwin_IEEE_Manuscript_Final.docx` (earlier version) | Eq. 1-16 | `GET /api/v1/metrics/ieee-validation` and `docs/integration/IEEE_TRACEABILITY.md`; shown separately as the earlier equation map |

The numberings are deliberately separate. The revised matrix contains only
equations 1-12. `test_regression_contracts.py::test_earlier_and_revised_equation_numbering_stay_distinct_and_authenticated`
checks both authenticated endpoints and their manuscript identities. The matrix
integrity test additionally fixes the revised claim count at 56 and rejects an
equation number outside 1-12.

## Claim status (56 claims)

| Status | Count | Meaning (from `status_definitions`) |
| --- | ---: | --- |
| `IMPLEMENTED_AND_TESTED` | 28 | executable software plus an automated test or saved artifact; software evidence only |
| `PARTIALLY_IMPLEMENTED` | 18 | part exists; the gap field states what is missing |
| `IMPLEMENTED_NOT_VALIDATED` | 5 | software exists, but the manuscript's required evaluation has not run |
| `PROPOSED_ONLY` | 3 | described, not implemented |
| `UNSUPPORTED` | 2 | cannot be supported with available evidence |

`test_medtwin2_capabilities.py::test_traceability_matrix_cites_only_real_code_and_tests`
checks all 56 unique IDs, every module path, every evidence path, named test
functions, the five allowed statuses, the 1-12 equation boundary, and that each
`IMPLEMENTED_AND_TESTED` claim has evidence.

## Executed internal research evaluations

These are internal held-out evaluations on public research datasets. They are
not clinical or external validation, and none of the evaluated models is
clinically activatable.

| Model and evidence | Internal held-out result | Important limitation |
| --- | --- | --- |
| Kvasir v2 8-class endoscopy classifier, `docs/validation/models/gi_kvasir_v2_classifier.json` | n=1,202; accuracy 0.926 (95% group-bootstrap CI 0.911-0.940); macro-F1 0.926 | Source patient identifiers are unavailable, so patient-level separation cannot be verified; internal source distribution only |
| GastroVision 27-class endoscopy classifier, `docs/validation/models/gi_gastrovision_27class_classifier.json` | **Exploratory only**; n=1,225; accuracy 0.737 (95% group-bootstrap CI 0.713-0.761); macro-F1 0.553 | Not validation-ready: Angiectasia, Erythema, Esophageal varices and Ulcer have fewer than 20 total samples (held-out support 4, 3, 2 and 1 respectively); inverse-frequency weighting does not create missing evidence; source patient identifiers are unavailable and there is no external test |
| ARCADE coronary stenosis detector, `docs/validation/models/angiography_stenosis_detector.json` | n=300; mAP 0.0618, AP50 0.2029, AR100 0.3585 | Publisher split contains cross-split near-duplicate components; conservative n=290 sensitivity result is mAP 0.0611/AP50 0.1983; no external test |
| TEZ kidney-stone detector, `docs/validation/models/kidney_stone_detector.json` | n=196; mAP 0.2312, AP50 0.6286, AR100 0.3600 | Acquisition-session/near-duplicate-aware re-split, but source patient identifiers are unavailable; no external test |
| ARCADE SYNTAX coronary segmenter, `docs/validation/models/angiography_syntax_segmenter.json` | n=300; vessel Dice 0.6829, vessel IoU 0.5352; mean foreground Dice per image 0.3070 | Segment 10a has no held-out reference mask and segment 10 has fewer than 20 held-out images; 512 x 512 pixels, not millimetres; no external test |
| Kvasir-SEG polyp segmenter, `docs/validation/models/gi_kvasir_seg_polyp_segmenter.json` (2026-10-25) | n=120; polyp Dice 0.768 (95% image-bootstrap CI 0.725-0.809); IoU 0.670 | Same-source publisher list; patient independence unavailable; partial source overlap with Kvasir v2 means the two results are not independent evidence; no external test |
| C-NMC ALL-vs-normal cell classifier, `docs/validation/models/hematology_cnmc_all_classifier.json` (2026-10-25) | n=1,867 / 28 subject clusters; accuracy 0.807 (95% cluster-bootstrap CI 0.659-0.894); macro-F1 0.790 | Filename-derived subjects are not independently verified patient identities; wide cluster-bootstrap intervals; no external test |
| ACDC cardiac cine-MRI 3-D segmenter, `docs/validation/models/acdc_cardiac_mri_3d_unet.json` (2026-10-25; owner-authorized research use) | n=100 ED/ES volumes / 50 patients; mean case macro Dice 0.750 (95% patient-bootstrap CI 0.719-0.778); LV 0.812, myocardium 0.731, RV 0.707; LV EF vs reference masks MAE 9.1 points (bias -5.8, r 0.852) | Single-centre publisher test set; volumes overestimated (no prespecified connected-component post-processing); evaluation evidence only, no volume upload path |
| PTB-XL 12-lead ECG superclass classifier, `docs/validation/models/ptbxl_ecg_baseline.json` (2026-10-25) | n=2,163 ECGs / 1,881 patients (fold 10); macro AUROC 0.917 (95% patient-bootstrap CI 0.909-0.925); macro AUPRC 0.805 | Patient-disjoint publisher folds (asserted), but single source (PTB, 1989-1996); no external ECG cohort; no upload inference path |
| PBC survival, Mayo covariates, `docs/validation/models/pbc_mayo_survival_cox.json` (2026-10-25) | Hold-out = 104 non-randomized patients (35 deaths); Harrell's C 0.786 (0.709-0.854); integrated Brier 0.105 vs 0.146 Kaplan-Meier | Population-specific (Mayo PBC 1974-1984); transplant censored as a competing risk; not a manuscript Section X claim |
| Heart-failure survival, `docs/validation/models/heart_failure_survival_cox.json` (2026-10-25) | **Exploratory only**; n=90 (29 deaths); Harrell's C 0.671 (0.569-0.774); integrated Brier 0.168 vs 0.158 Kaplan-Meier (no skill) | No held-out calibration skill over the population average; small cohort |

The accuracy objective above 0.95 was **not met** by any of the three image classifiers.
Kvasir's 95% CI is 0.911-0.940; GastroVision's is 0.713-0.761 and its run is explicitly
exploratory because of insufficient rare-class support; C-NMC's cluster-bootstrap CI is
0.659-0.894. Detection and segmentation results satisfy only the software
execution portion of `X-DETECTION-SEGMENTATION`: the repository does not
establish independent expert re-annotation, patient-level independence for the
source datasets, or external/clinical evaluation. `X-PTBXL` was executed on
2026-10-25 on the publisher's patient-disjoint folds (claim now
`IMPLEMENTED_AND_TESTED`, internal evaluation only). `X-MURA` remains not run: the
data are now present, but the Stanford AIMI agreement requires the user's own
registration. `X-DOC-EXTRACTION`, `X-MIMIC-CXR`, and `X-FORECAST` remain not run.
The two survival models are research evidence outside the manuscript's Section X
claims; `X-FORECAST` concerns longitudinal trajectory forecasting, which they are not.

## Independent validation-kit re-scores

`MedTwin_2_Validation_Kit/evaluate_medtw.py` was run through
`python -m ml_training.kit_crosscheck` in an isolated environment. The saved
cross-checks reproduce the corresponding trainer metrics exactly:

- ARCADE detector: mAP 0.0618425 and AP50 0.202878 in
  `docs/validation/models/angiography_stenosis_detector.kit_crosscheck.json`.
- TEZ detector: mAP 0.231237 and AP50 0.628637 in
  `docs/validation/models/kidney_stone_detector.kit_crosscheck.json`.
- ARCADE segmenter binary whole-vessel view: Dice 0.682880 and IoU 0.535190 in
  `docs/validation/models/angiography_syntax_segmenter.kit_crosscheck.json`.
- Kvasir-SEG: Dice 0.7679 and IoU 0.6696 in
  `docs/validation/models/gi_kvasir_seg_polyp_segmenter.kit_crosscheck.json`.

The kit's binary-classification mode applies to neither the eight-class Kvasir
task nor the 27-class GastroVision task. Their metrics therefore come from the
recorded multiclass trainer reports and research-inference adapter tests; they
are not described as kit cross-checks.

## Browser evidence

`docs/anatomy/BROWSER_WALKTHROUGH.md` records an automated Microsoft Edge run
against the isolated synthetic QA stack: 16/16 desktop routes and 16/16
phone-width routes rendered without page overflow, mobile navigation passed,
43/43 anatomy variants rendered across all ten systems, the synthetic upload,
laboratory, evidence-link and durable-queue workflows passed, all 7/7 explicitly
bound 2-D research-model UI paths completed, and all 10/10 trained-model report
views rendered. Structured and censored laboratory inputs, original-preserving
correction proposals, Clinical NLP/OCR evaluator controls, request-ID correlation,
hash-only/no-raw-text evaluator provenance, and prognosis abstention passed the
fail-closed assertion gate. The run recorded zero unexpected console errors,
uncaught page errors, failed requests, or HTTP 5xx responses; one intentional 422
tested the visible request-ID contract. Geometry counters plus canvas-content
statistics were required for a 3D render pass; `docs/anatomy/ASSET_QA.md` records
the per-variant result. A supplemental visible Chrome session opened the correction
history, BMP/C-NMC path, Prognosis Studio, and ten-system Anatomy UI. This is
software acceptance evidence, not a usability, accessibility, anatomical, or
clinical validation study.

## Final software verification

`docs/testing/EXECUTED_TEST_RESULTS.md` records the final `scripts/verify.ps1`
run (`artifacts/verify/20261025T112434Z.json`): backend tests **258 passed and
1 skipped**, frontend typecheck/lint/build passed, and the current-tree privacy
scan reported no findings. That receipt also points to the same browser run above.
It does not override the
matrix's explicit research-only, internal-evaluation and clinical-validation
limitations.
