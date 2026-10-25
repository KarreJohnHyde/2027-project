# MedTwin 2.0 — Evidence-Only Evaluation Toolkit

This package **does not generate MedTwin accuracy, patient predictions, or medical diagnoses**. It evaluates held-out, reference-labeled outputs produced by legitimately trained and fixed models. Results are valid only to the extent that the test dataset, patient-separated split, reference labels, preprocessing and frozen checkpoint are independently verified.

## Install

```bash
python -m pip install numpy pandas scikit-learn pillow
# Optional for COCO bounding-box mAP:
python -m pip install pycocotools
```

## Classification input

CSV header: `patient_id,y_true,score`. `y_true` = 0/1 according to a declared medical task; `score` = the model's positive-class probability, not a percentage accuracy. A valid **prespecified** threshold is required; default `.5` is only a generic default and must be justified, not tuned on the test set.

```bash
python evaluate_medtw.py classification --csv my_frozen_test_predictions.csv --dataset PTB-XL --dataset-version 1.0.2 --checkpoint sha256:YOUR_REAL_CHECKPOINT_HASH --split test --threshold 0.5 --output results/classifier.json
```

Outputs accuracy, precision, sensitivity, specificity, F1, AUROC when valid, average precision, Brier score, confusion matrix, patient count and a strict `accuracy > 95%` indicator. This indicator is not equivalent to safe clinical deployment. Do not combine top scores from different epochs.

## Segmentation input

CSV header: `patient_id,reference_mask,predicted_mask`. Masks must be binary PNG or NumPy `.npy` 2D arrays with exactly matching dimensions. Empty-mask evaluation convention is fixed: when both masks are empty, Dice = IoU = 1, and nonempty-reference averages are also reported. This is **not** a 3D-volume evaluator.

```bash
python evaluate_medtw.py segmentation --csv my_mask_pairs.csv --dataset REAL_SEGMENTATION_DATASET --dataset-version ACTUAL_VERSION --checkpoint sha256:HASH --split test
```

## Forecast input

CSV header: `patient_id,target,horizon,y_true,y_pred`. The target name and horizon must uniquely define a prediction task; output is MAE and RMSE per target/horizon. Use a chronological held-out evaluation from genuinely longitudinal patient data. Input units and target definitions must be identical within each group.

```bash
python evaluate_medtw.py forecast --csv my_future_target_predictions.csv --dataset REAL_LONGITUDINAL_DATASET --dataset-version ACTUAL_VERSION --checkpoint sha256:HASH --split test
```

## Numeric lab extraction input

CSV header: `patient_id,source_id,analyte_code,reference_value,predicted_value,reference_unit,predicted_unit`. This is a **pre-matched-value accuracy audit**; it does not measure missed test rows, false positive rows, NER recall or incorrect medical interpretation. Verify unit conversions upstream.

```bash
python evaluate_medtw.py lab_extraction --csv my_labeled_lab_pairs.csv --dataset REVIEWED_LAB_ANNOTATIONS --dataset-version 1 --checkpoint extraction-pipeline-hash --split test --abs-tolerance 0.0
```

## Detection input

Use `pycocotools` with a correctly annotated COCO reference JSON (`--annotations`) and COCO detection JSON as `--csv`. The scorer uses the standard COCO `bbox` evaluator, including mAP 0.50:0.95 and AP50/AP75.

```bash
python evaluate_medtw.py detection --csv my_coco_predictions.json --annotations my_coco_reference.json --dataset REAL_BOX_LABELED_DATASET --dataset-version 1 --checkpoint sha256:HASH --split test
```

## Mandatory independent verification before reporting an IEEE metric

- Verify source dataset version, license/consent and inclusion/exclusion rules.
- Separate patients (and studies where appropriate) between train/validation/test, without duplicates or leakage.
- Keep model selection and any threshold tuning out of the final test set.
- Maintain a source-linked evaluation manifest: dataset ID, case ID, acquisition/provenance, label authority, model/commit/hash, preprocessing version and test timestamp.
- Report full sample sizes, class balance, confidence intervals, calibration, subgroups, false positives/false negatives and benchmark operating point.
- Never confuse image confidence with population-level classification accuracy.
- Report **NOT RUN** when a compatible model/dataset/source label does not exist.
- Compare accuracy >95% only within the specific pre-registered classification task. A universal >95% score across all organs is unsupported.

## Supporting standards and data sources

- CLAIM 2024, doi:10.1148/ryai.240300
- TRIPOD+AI 2024, doi:10.1136/bmj-2023-078378
- MURA (study-level labels): https://stanfordmlgroup.github.io/competitions/mura/
- PTB-XL: https://physionet.org/content/ptb-xl/1.0.2/
- MIMIC-CXR (paired chest X-rays and reports; credentialed access): https://physionet.org/content/mimic-cxr/
- HL7 FHIR Observation: https://hl7.org/fhir/observation.html
- DICOM: https://www.dicomstandard.org/
