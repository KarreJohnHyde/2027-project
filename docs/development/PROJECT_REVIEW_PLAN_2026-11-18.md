# MedTwin project review plan — 18 November 2026

> Execution follow-up: use the [13 November implementation report](../review-2026-11-13/MEDTWIN_IMPLEMENTATION_STATUS_2026-11-13.md) for work actually implemented and measured after this planning snapshot. Runtime observations and verification counts below describe the earlier assessment.

Prepared on 13 November 2026 from the local source, registry, model reports and dated implementation evidence. This is an implementation backlog and review plan; it does not claim these changes have been made or promise an accuracy increase.

## Recommended review scope

Demonstrate one complete document/laboratory workflow and one well-characterized research-model workflow. Explain the supported inputs, measured performance, failure cases and refusal behavior. Five days are enough to improve reliability and evidence; they are not enough to establish clinical validation across the application's specialties.

Recommended document flow: de-identified report → text/OCR → structured values and assertions → source verification → reviewer decision → longitudinal view → exported report.

Recommended research flow: supported public digital input → eligibility and quality checks → immutable model/preprocessing → output in source coordinates → reference comparison → review → export. Choose a model only after confirming that its actual checkpoint and reference inputs are available and eligible under the selected usage profile. Do not bypass the commercial-purpose gate for a demonstration.

## Findings that drive the priorities

| Finding in existing evidence | Implication |
| --- | --- |
| On November 13, the targeted backend test process failed during application import: Windows Application Control blocked PyTorch `torch/lib/shm.dll` or a dependency (`WinError 4551`). | Verify/repair the approved runtime first and re-run the checks. This observation concerns this test process; the already-running preview/backend may have a different loaded environment. Do not assume earlier runtime repairs still cover the current environment. |
| OCR is implemented, including direct PDF text, local OCR, rotation and row de-skew. The documented 12-page OCR benchmark is synthetic. | Add independent human transcription and field-level evaluation before claiming real-report extraction accuracy. Replacing the OCR engine alone is not the first step. |
| Document context rules and several NLP adapters exist; the error audit still records unresolved coreference and unreadable values. | Evaluate assertion, temporality, entity/site linking and numerical extraction separately. Preserve uncertainty when text cannot be read. |
| Applicability gates exist, but the recorded GastroVision gate refuses only 14.7% of tested angiograms. Kvasir-SEG refuses 14/120 genuine test frames. | An appearance gate does not establish modality or anatomical suitability. Measure wrong-input acceptance and valid-input refusal independently. |
| The rejected KiTS19 model has renal-tumour Dice 0.000 on 32 positive-reference test patients. | Keep the failed model blocked. An empty prediction cannot be interpreted as absence of tumour. |
| The newer fracture report records AP50 0.155 and recall 0.222 at threshold 0.55 on 169 images. | Treat fracture detection as weak development evidence, not a reliable demonstration of clinical detection. Patient identity is unavailable in this source. |
| ARCADE stenosis records precision about 0.215 and recall about 0.381 at its selected threshold. | False positives and missed lesions both require development. Threshold adjustment alone cannot establish a strong detector. |
| Skin image/tabular fusion records internal accuracy 0.658 and macro F1 0.615; only five melanoma test images are documented. | Report per-class support and uncertainty; do not generalize this to high accuracy across skin disease. |
| ECG demographic fusion's paired AUROC difference interval includes zero. | No fusion benefit has been established for that comparison. Include unimodal baselines and paired uncertainty. |
| DICOM handling, geometry checks, research upload parity, review and provenance already exist. | Extend and re-run these controls for changed models instead of listing them as absent. |
| The November 9 priority report supersedes earlier runtime, acquisition and container blockers. A November 10 fracture artifact is newer than the saved validation-status snapshot. | Reconcile current artifacts and registries. Do not present historical totals or repaired problems as the current state. |

Primary project evidence: `docs/development/PRIORITY_EXECUTION_2026-11-09.md`, `docs/development/IMPLEMENTATION_PROGRESS_2026-11-09.md`, `docs/validation/IMAGE_APPLICABILITY_GATE.md`, `docs/validation/OCR_BENCHMARK.md`, `docs/validation/UPLOAD_INFERENCE_PARITY.md`, `docs/validation/models/bone_fracture_detector.json`, and `model_registry/validation_status.json`.

## P0 — complete or explicitly account for before the review

| Work item | Concrete implementation or verification | Acceptance evidence |
| --- | --- | --- |
| 0. Resolve the current runtime block | Diagnose the PyTorch DLL/dependency denial using the approved environment and application-control evidence. Use a permitted compatible build or the responsible IT/runtime-owner process; do not weaken machine policy. Verify the actual demo API and worker environments separately. | Successful application/PyTorch import, API health, one real permitted checkpoint inference through the worker, and a completed targeted regression run. A passing frontend check alone is insufficient. |
| 1. Freeze two demonstration tasks | Define input format, modality, anatomy, target, supported population/protocol, expected output and usage profile. Select the exact checkpoint and preprocessing version. | One capability sheet per flow; unsupported inputs visibly abstain. |
| 2. Build an independent reference set | Start a practical 30–50-page, de-identified, permitted report set across layouts and scan/photo quality, plus a separate development set. Manually transcribe fields and source locations; independently check ambiguous and critical fields. If fewer pages are available, report the actual count. | Versioned manifest, documented sampling and annotation process, reference JSON/CSV and split separation. This is a pilot, not a statistically sufficient clinical sample. |
| 3. Lock data separation | Split by patient before fitting transforms. Keep an entire examination, video/procedure and related near-duplicate group in one partition. Check overlap across datasets and parent collections. | Patient/group overlap report, SHA-256 and visual-duplicate audit, class counts and exclusions. Mark independence unknown where identities are unavailable. |
| 4. Protect the final test | Learn preprocessing on training data; select architecture, threshold, applicability settings and calibration using development/validation data only. | Frozen manifests and configuration hashes. Previously inspected test sets are disclosed; new tuning requires an untouched final evaluation set. |
| 5. Verify training/serving parity | Share preprocessing definitions between training and upload adapters. Compare normalized tensors, output scores/masks and threshold decisions on fixed controls. | Per-model parity report with predefined numerical tolerance, precision/device, counts, refusals and all decision changes. |
| 6. Strengthen input routing | Require an explicit supported input contract, use trustworthy metadata when available, and refuse contradictions. Test document photos, film photographs, screenshots, wrong body parts and wrong modalities. | Independent challenge matrix with in-scope acceptance, wrong-input acceptance and reason codes. Avoid claiming the current appearance gate proves modality. |
| 7. Make uncertainty visible | Distinguish extracted text, reported diagnosis, model prediction, reviewer confirmation and unavailable output. Preserve unreadable fields and missing metadata as uncertain. | UI/export examples with source links and reasons; no missing value or refused prediction becomes normal/negative. |
| 8. Reconcile current model evidence | Compare the live registry, checkpoint reports, generated status and capability coverage, including the newer fracture result. Keep failed targets blocked. | Dated model table with exact checkpoint/hash, task, evaluation unit, metrics, sample counts and limitations. Do not manually grant clinical activation. |
| 9. Exercise the complete workflow | Run upload → processing → source verification → review → comparison → export → reload on an isolated test stack. Include a rejected input and one worker failure/retry. | Current software-check output and demo artifacts. Report software tests separately from predictive performance. |

## P1 — preprocessing work by input type

These are extensions and verification tasks for existing services, not claims that every listed function is absent.

### Reports, PDF, photographs and clinical text

- Detect usable embedded text per page; route scanned or corrupted-text pages to OCR without duplicating text. Preserve page boundaries and reading order in mixed documents.
- Apply rotation correction and conservative de-skew. Evaluate glare, blur, clipping, compression and perspective distortion; request a better scan when information is lost.
- Keep original bytes and page/box coordinates. Store extraction/preprocessing version and uncertainty with each field.
- Make lab extraction layout-aware: analyte, result, decimal separator, unit, H/L flag, reference interval, specimen, collection/result date and source cell must remain associated.
- Explicitly evaluate multi-column tables, repeated headers, wrapped rows, age/sex-specific intervals, footnotes and packet boundaries. A numeric result must not migrate to an adjacent test.
- Normalize units using analyte-specific registered conversions; reject incompatible/ambiguous units. Keep the original value and unit. Do not infer an abnormal flag without the appropriate documented interval/context.
- Test negation, uncertainty, family history, historical disease, indications, planned tests and comparison statements. A mention in an indication is not a confirmed current finding.
- Verify OCR confidence against actual errors on the reference set; it is not a probability that a clinical statement is correct. Use field-specific review rules for decimals, units and negation.
- Measure CER/WER, then end-to-end field precision/recall and exact correctness for value+unit+analyte association. Separately report assertion/temporality errors and missing fields.
- Use independently annotated text to evaluate NLP and independently transcribed pages to evaluate the whole OCR→NLP pipeline. Do not derive the reference answer from the same extractor being scored.

Files: `backend/app/services/ocr.py`, `document_parser.py`, `nlp_processor.py`, `lab_service.py`, `ocr_evaluation.py`, `clinical_nlp_evaluation.py`.

### CT, MRI, X-ray and other medical images

- Validate file contents, decompression, finite pixels, dimensions and bounded memory use. Preserve source bit depth before modality-specific transformations.
- For CT, verify slope/intercept and HU handling, acquisition/contrast protocol and the exact training window. A PNG or film photo does not recover original HU.
- For DICOM series, verify series identity, patient-position ordering, orientation, spacing, duplicates, gaps and missing/inconsistent geometry. Exclude localizers and incompatible series.
- For MRI, verify required sequence channels and ordering, spatial alignment, missing sequences and intended acquisition/phase. Keep normalization matched to the checkpoint; do not add arbitrary skull stripping or intensity correction to a pretrained pipeline.
- Record crop, padding, resampling and orientation transforms. Interpolate labels with a label-preserving method; return final masks/boxes to source coordinates with tested inverse transforms.
- Review tiny-lesion information loss during resampling. Choose spacing/patch size from development evidence and memory limits, rather than applying one resolution to every task.
- Validate modality-specific blur/contrast/exposure/artifact checks. Do not apply histogram equalization, sharpening or denoising universally: each changes the input distribution and needs development evaluation.
- Quantify accepted-case performance and refusal coverage together. Keep explicit negative cases when estimating false positives; a polyp-only set cannot establish behavior on polyp-free examinations.

Files: `backend/app/services/imaging_readers.py`, `dicom_series.py`, `dicom_raster.py`, `model_inference.py`, `volume_inference.py`, `image_ood.py`, `model_router.py`.

### Digital ECG, echo/video and other signals

- Verify lead names/order, mV conversion, sampling rate, duration, NaNs, saturation, flat leads and missing channels before prediction. An ECG photograph is not a digital waveform.
- The documented ECG adapter accepts 100 Hz, 10-second, 12-lead inputs. Add other rates/durations only through a separately validated adapter; retain fail-closed behavior meanwhile.
- Evaluate any baseline-wander, mains-noise filtering or resampling against the original training pipeline. Preserve waveform morphology and record filter parameters.
- For echo/video, check view, frame rate, clipping and temporal sampling; aggregate only within the same patient/study. Keep all frames from a procedure in one split.
- Report signal/input refusal rates and patient-level performance. EDF/EEG display remains a reader capability until an actual task-specific model and evaluation exist.

Files: `backend/app/services/ecg_processor.py`, `ecg_inference.py`, `echo_inference.py`, `video_frames.py`, `edf_reader.py`.

### Biomarkers, tabular data and multimodal evidence

- Fit imputation, scaling, feature selection and categorical encoders on training patients only. Save these artifacts with the checkpoint; define unknown-category and missingness behavior.
- Keep units, specimen and dates aligned. Define handling of repeat measurements and corrected reports. Do not pool different analytes because their labels look similar.
- Use only information available at the prediction time. Keep outcome-derived variables and later reports out of predictors.
- Align modalities using the same patient, examination and permitted time window. Never pair unrelated dataset rows to create apparent multimodal training examples.
- Compare image-only, signal-only, metadata-only and combined variants on the same held-out patients. Report paired uncertainty and missing-modality results.
- Keep contradictory evidence visible. A report mention, model score and biomarker abnormality do not automatically constitute three independent confirmations.

Files: `backend/app/services/fusion_service.py`, `effective_evidence.py`, `evidence_synthesis.py`, `biomarker_trends.py`, `ml_training/skin_fusion.py`, `ml_training/ecg_fusion.py`.

## P1/P2 — model-development upgrades after the input/evaluation foundations

| Task | Development work | Evaluation that must decide whether it helped |
| --- | --- | --- |
| Renal tumour segmentation | Inspect labels and post-resampling tumour sizes; verify foreground sampling. Compare class-balanced patches, foreground Dice plus weighted cross-entropy and suitable resolution. Select training duration/early stopping using validation. Check data-purpose eligibility before training. | Per-patient and per-class Dice, lesion recall, small-tumour results, false-positive components and fresh independent final evaluation. Keep the failed checkpoint blocked. |
| Fracture and stenosis detection | Review annotation completeness, class mapping, negative images and target size. Evaluate appropriate input resolution, sampling, pretrained detector fine-tuning and longer bounded development runs. | AP50 and AP50:95, recall/precision at validation-selected thresholds, false positives/image and size/site breakdowns. Do not tune thresholds against the exposed test. |
| Skin/GastroVision classification | Review rare-class counts/labels and patient grouping; compare training-only class weighting or balanced sampling, fine-tuning and conservative task-appropriate augmentation. | Macro F1, per-class sensitivity/precision and support, confusion matrix, calibration and independently tested subgroups. Overall accuracy alone hides rare-class failure. |
| Stroke/small-lesion segmentation | Review missed-lesion size, sequence quality and resolution; compare lesion-aware sampling and bounded postprocessing chosen on validation. | Lesion sensitivity/F1, false positives/case, per-case Dice, HD95 in physical units where spacing is known, and lesion-size breakdown. |
| Probability calibration | Fit temperature/other appropriate calibrators using a reserved development partition, keep task-specific probability semantics and persist fitted parameters. | Before/after Brier/ECE and reliability diagrams on untouched data. Detector confidence is not automatically disease probability. Calibration need not improve classification accuracy. |
| Metric implementation integrity | Audit shapes, finite values, empty inputs, multiclass/multilabel definitions and grouping. In `calibration_service.py`, the current ECE bin rule excludes confidence exactly zero; test/fix that boundary before using this helper for evidence. Its default temperature is not a fitted calibrator. | Independent hand-computed boundary examples and cross-checks against established implementations. The generic calibration helper was found referenced by tests, not the inspected serving paths; this is not evidence that served model metrics are wrong. |

Apply augmentation only to training data and ensure it preserves the label/anatomy. More epochs, a larger architecture, more datasets or ensembles are experiments, not guaranteed upgrades. Use controlled comparisons and retain unsuccessful results.

## Evaluation outputs needed for the review

| Output/task | Report |
| --- | --- |
| Extraction | Correct fields/total reference fields, precision/recall, value+unit exact match, association/date/assertion errors, unreadable/refused counts and representative failures. |
| Classification | Confusion matrix, per-class support, macro F1, sensitivity/specificity, AUROC and AUPRC when applicable. State the prediction unit and frozen thresholds. |
| Detection | AP50:95/AP50, precision/recall at the declared operating point, lesion matching rule and false positives/image or examination. |
| Segmentation | Per-case/per-class Dice and IoU, empty-mask policy, lesion recall and false-positive components; surface distances with units. |
| Regression/EF | MAE, bias and error distribution with task units. Use agreement analysis when appropriate. |
| Forecasting/survival | Defined endpoint, time zero and horizon; chronological separation, censoring handling, calibration and comparison against simple baselines. Keep unsupported forecasts unavailable. |
| All model tasks | Patients/studies/images separately, dataset/version/split, checkpoint hash, preprocessing, code revision, reference-label process, exclusions/refusals and cluster-aware confidence intervals. |

Predeclare task-specific acceptance criteria with the supervisor/domain reviewer. There is no universal acceptable percentage across OCR, classification, detection and segmentation. If criteria are unmet, present the failure and next experiment instead of marking the model validated.

## Reliability and longer-term upgrades

- Re-run existing upload, routing, geometry, reference-comparison, review and export regressions after changes. Re-check parity whenever a checkpoint, preprocessing or inference precision changes.
- Verify queue progress, cancellation/timeout, worker restart, idempotent retries and persistence after refresh. A failed job must not leave a successful-looking stale result.
- Export source IDs/spans, version/hash, quality warnings, uncertainty, model output, review state and limitations together. Preserve original evidence and append review decisions.
- Keep synthetic examples and public reference images labelled as such. Use de-identified, permitted inputs for the review. The project records a Git-history privacy release block; a clean source tree does not make the repository safe to share.
- After the review: representative external/site-held-out evaluation; expert adjudication; subgroup and acquisition-protocol analysis; prospective workflow/usability evaluation where appropriate.
- Separately complete rights, deployment security, off-host recovery and clinical-release prerequisites documented in the project's November 9 release report. Technical accuracy does not resolve those prerequisites.
- Defer new EEG interpretation, whole-slide diagnosis, patient-to-atlas registration, general disease forecasting, treatment simulation and broad specialty expansion. Each needs its own data, trained adapter and evidence; viewers and downloaded datasets do not establish these capabilities.

## Five-day execution schedule

| Date | Focus | Deliverable |
| --- | --- | --- |
| 13 November | Resolve/verify the runtime block; freeze review scope; reconcile model evidence; select permitted demonstration inputs; begin reference annotation. | Working approved demo runtime, scope sheet, dated status table, development/evaluation manifests and prioritized issues. |
| 14 November | Document/OCR/lab quality and field association; independently verify the reference set. | Field-level baseline, error taxonomy and focused development fixes. |
| 15 November | Routing, quality/refusal challenge set, modality-specific preprocessing and train/serve parity. | Acceptance/refusal matrix, transform controls and parity evidence for chosen models. |
| 16 November | Freeze development settings; evaluate once on the reserved set; complete calibration/error analysis when feasible. | Reproducible metrics, confidence intervals where sample size permits, failure examples and comparison with baseline. |
| 17 November | Freeze demo code/artifacts; full workflow/reload/restart checks; export evidence; rehearse. | Demo script, sanitized report, architecture diagram, screenshots/backup recording and tested recovery plan. |
| 18 November | Present scope, methods, results, limitations and next steps. | Stable demonstration plus an honest account of completed, failed and future work. |

If annotation, permission or model training is not feasible in this window, keep the result labelled incomplete and use an existing characterized research flow. Do not replace missing evaluation with an invented accuracy target.

## Review presentation checklist

- [ ] Problem, intended user and two supported review workflows.
- [ ] Architecture from input through preprocessing, model/extractor, provenance and human review.
- [ ] Dataset/reference source, counts, grouping, splits and permission scope.
- [ ] Exact preprocessing and why it matches the trained checkpoint.
- [ ] Baseline and final task-appropriate metrics, thresholds and uncertainty.
- [ ] At least one correct case, one failure and one unsupported-input refusal.
- [ ] Evidence that outputs persist, overlays align and reports trace to source.
- [ ] Clear distinction between research performance and clinical validation.
- [ ] Concrete next experiments addressing observed errors.

## Technical sources

1. [scikit-learn: common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html) supports consistent preprocessing, training-only fitted transforms and avoiding test-driven model choices.
2. [CLAIM 2024 update](https://pubs.rsna.org/doi/full/10.1148/ryai.240300) supports transparent acquisition/preprocessing descriptions, patient-level separation, reference standards and external testing.

## Verification performed during this assessment

Frontend TypeScript checking passed on 13 November (`npm run typecheck`). The targeted backend run for routing, document integrity, DICOM series, ECG fusion and OCR evaluation exited 1 during `conftest.py` application import, before tests ran: Windows Application Control blocked PyTorch `torch/lib/shm.dll` or one of its dependencies (`WinError 4551`). This is not a test pass and does not independently establish whether an already-running server can serve inference. The command was `.venv\\Scripts\\python.exe -m pytest backend/tests/test_model_router.py backend/tests/test_document_integrity.py backend/tests/test_dicom_series.py backend/tests/test_ecg_fusion_inference.py backend/tests/test_ocr_evaluation.py -q -p no:cacheprovider`.

No application logic, model weights or registry eligibility was changed for this plan. Existing local model-registry and fracture-report changes were left intact. Saved historical accuracy figures above were inspected, not reproduced through retraining or a new held-out evaluation.
