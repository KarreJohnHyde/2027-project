# Training experiments, 14 November 2026

Every run uses the owner-approved research purpose and passes the evidence-bound rights gate (`ml_training/volumetric_manifest.py: enforce_training_license`) before data are read. Runs are on CPU, float32, with the GPU hidden. Original checkpoints are unchanged: every new model has its own ID, run directory, SHA-256, report and card.

## Completed: new tabular models (UCI, CC BY 4.0)

> **Superseded:** this first table is replaced by the clean-split re-evaluation in "Update, afternoon of 14 November" at the end of this file.

`python -m ml_training.tabular --all`. Splits are 70/15/15 by outcome, with one person's rows never crossing splits. Model choice, Platt calibration and threshold use validation only; the test part is scored once.

| Model | Test n | Test AUROC (95% CI) | Brier skill vs prevalence | Run scope |
|---|---|---|---|---|
| `tabular_ckd_uci` | 57 | 0.997 (0.987–1.000) | 0.858 | RESEARCH |
| `tabular_hypothyroid_uci` | 452 | 0.997 (0.990–1.000) | 0.857 | RESEARCH |
| `tabular_breast_fna_uci` | 81 | 0.986 (0.964–0.999) | 0.759 | RESEARCH |
| `tabular_hepatitis_mortality_uci` | 22 | 0.941 (0.789–1.000) | 0.490 | RESEARCH |
| `tabular_heart_disease_uci` | 132 | 0.899 (0.837–0.951) | 0.498 | RESEARCH |
| `tabular_diabetes_readmission_uci` | 14,191 | 0.668 (0.651–0.684) | 0.049 | RESEARCH |
| `tabular_liver_patient_uci` | 84 | 0.651 (0.517–0.767) | −0.005 | EXPLORATORY_ONLY |
| `tabular_cervical_biopsy_uci` | 123 | 0.577 (0.386–0.752) | −0.232 | EXPLORATORY_ONLY |
| `tabular_parkinsons_voice_uci` | 25 (≈4 people) | 0.877 (interval not computable) | −0.036 | EXPLORATORY_ONLY |

The three exploratory models are failures in the useful sense: they predict no better than the prevalence. They are kept, reported and marked, not promoted.

**Independent audit** (`scripts/remediation_tabular_audit.py` → `TABULAR_AUDIT.json`):

- Splits rebuild exactly, and no person crosses splits.
- The imputers were fitted on development rows only.
- Every reported metric reproduces exactly.
- **Exact duplicate records** are shared between development and evaluation in five tables (heart: validation only). Test AUROC without them: hypothyroid 0.996, liver 0.642, cervical 0.568; the others are unchanged.
- **Hypothyroid** is near-definitional: FTI alone reaches development AUROC 0.984, because the source label was made from these thyroid tests.

**Serving:** the six research-scope models run from typed values on the Model Registry card (`/research-models/{id}/tabular-inference`). Each input is checked against its development envelope: range, coded values, categories and blank fields. The three exploratory models refuse.

## Running or queued (CPU)

| Run | Data | Split | Status at writing |
|---|---|---|---|
| `blood_smear_malaria_cell_classifier` | NIH/NLM malaria, 27,558 cells | 200 patients, 136/30/34 | ResNet-18 finished (best validation macro-F1 0.949); EfficientNet-B0 training |
| `ecg_mitbih_beat_classifier` | MIT-BIH, 44 non-paced records | Inter-patient DS1/DS2 | Queued; readers verified on record 100 (2,239 N, 33 A, 1 V, matching the publisher) |
| `ultrasound_fetal_plane_classifier` | FETAL_PLANES_DB, 12,400 images | Publisher's patient split kept for test | Queued |
| `mri_hippocampus_segresnet`, `mri_prostate_zones_segresnet`, `ct_spleen_segresnet` | Decathlon Task04/05/09 | Patient split by the manifest builder | Queued, CPU-sized patches |
| GastroVision `none` vs `inverse_frequency` | GastroVision (CC BY 4.0) | Development only; test never loaded | Queued (U-016 controlled experiment) |

## Not run, and why

| Experiment | Reason |
|---|---|
| Kidney tumour (KiTS19) foreground sampling and Dice+CE | GPU-scale 3-D training; GPU on hold. The exposed test also needs a fresh cohort. |
| Stroke small-lesion sampling | GPU-scale 3-D training |
| Fracture and stenosis higher resolution | Detection training is impractical on CPU |
| Pancreas (Decathlon Task07) | Prepared and registered only; GPU-scale |
| HC18 foetal head circumference | Downloaded; its segmentation-plus-ellipse trainer is not written yet |

## Update, afternoon of 14 November

### Tabular models: clean split (duplicate records grouped)

Identical records (all features and the label) now share one group, so no duplicate crosses splits. The audit confirms zero duplicates across splits for all nine tables. This is a **re-evaluation after test exposure**: the first split's test part was inspected during the duplicate audit and overlaps this one. It is **not an independent final test**. Models that were exploratory on the first evaluation stay exploratory whatever the re-split shows.

| Model | Test n | Test AUROC (95% CI) | Run scope |
|---|---|---|---|
| CKD | 57 | 0.997 (0.987–1.000) | RESEARCH |
| Breast FNA | 81 | 0.986 (0.964–0.999) | RESEARCH |
| Hypothyroid (near-definitional: label made from these tests) | 452 | 0.969 (0.913–0.999) | RESEARCH |
| Hepatitis mortality | 22 | 0.941 (0.789–1.000) | RESEARCH |
| Coronary disease | 132 | 0.827 (0.748–0.891); earlier 0.899 was optimistic | RESEARCH |
| Diabetes readmission | 14,192 | 0.659 (0.642–0.675) | RESEARCH |
| Liver patient | 83 | 0.748 (0.628–0.858) on the re-split | EXPLORATORY (held back) |
| Cervical biopsy | 123 | 0.687 (0.476–0.891), no Brier skill | EXPLORATORY |
| Parkinson's voice | 25 | 0.877 (interval not computable), no Brier skill | EXPLORATORY |

### Completed CPU runs

| Model | Test result | Gates | Outcome |
|---|---|---|---|
| `blood_smear_malaria_cell_classifier` | 4,390 cells, 34 unseen patients: accuracy 0.965, macro-F1 0.965, ECE 0.014 | Applicability reference: 0.8% of valid test cells refused, 100% of 7 other image families refused. Serving parity on 40 test cells: same decision 40/40, max \|Δp\| 7.3×10⁻⁷. Licence: NLM release, terms unclear for commercial use. | **RESEARCH_ACTIVE** (upload, MICROSCOPY) |
| `ecg_mitbih_beat_classifier` | 22 unseen patients, 49,661 beats: accuracy 0.930, macro-F1 0.423. Sensitivity: N 0.991, S **0.013**, V 0.730, F **0.000** | Inter-patient DS1/DS2; readers verified against the published counts | **EXPLORATORY** (S and F not detected) |
| GastroVision class-weighting experiment, foetal planes, hippocampus, prostate, spleen | Queued or training | n/a | **TRAINING** |
| Pancreas | Downloaded (11.7 GB); preparation queued | GPU-scale | **BLOCKED** (GPU hold) |

## Update, evening of 14 November

| Model | Test result | Gates | Outcome |
|---|---|---|---|
| `ultrasound_fetal_plane_classifier` | Publisher's test patients, 5,271 images: accuracy 0.935, macro-F1 0.932 | Applicability: 0.7% of valid test images refused. Other families refused 95.4% (CT) to 100%; 4.6% of CT and 1.7% of radiographs would be accepted. Serving parity: 40/40 same decision, max \|Δp\| 6.7×10⁻⁷. CC BY 4.0. | **RESEARCH_ACTIVE** (upload, OBSTETRIC_ULTRASOUND) |
| `ultrasound_fetal_head_segmenter` (HC18) | Training (queue 5). Measurement method validated first: an ellipse fit to the sonographer outline reproduces the publisher's circumference with MAE 0.006 mm (p95 0.016 mm) over 999 images | Subject-grouped split 694/150/155 (806 subjects); CC BY 4.0. `scripts/evaluate_hc18_measurement.py` measures held-out circumference in mm through the serving functions after training. | **TRAINING** |
| Hippocampus, prostate, spleen | Queue 3 had a manifest-command error (subcommand order). Fixed and relaunched; hippocampus is training | n/a | **TRAINING** |
| GastroVision class weighting | Running (development only, test untouched) | n/a | **TRAINING** |

Governance fix: `ml_training/segment.py` now calls the shared training-rights gate, as the other trainers do.
