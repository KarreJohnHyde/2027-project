# Model card: 12-lead ECG + age and sex fusion classifier (research)

- **Model id:** `ptbxl_ecg_demographic_fusion` (registry status `READY_UNVALIDATED`; research-only).
- **Fusion:** intermediate fusion; the ECG network's pooled features (512) are joined with a 16-unit embedding of age and sex (age/100 clipped to 0.9, age-missing flag, female/male, sex-missing flag) before the classifier.
- **Data:** PTB-XL 1.0.1 (CC BY 4.0 (Creative Commons Attribution 4.0 International)); publisher folds 1-8 / 9 / 10, patient-disjoint; {'train': 17111, 'val': 2156, 'test': 2163}. Age missing for 85 records, sex for 0.
- **Comparison arm:** the same ECG network without age and sex, trained with identical data order, augmentation, epochs and seed.
- **Checkpoint:** `artifacts/training/ptbxl_ecg_demographic_fusion-20261105T093352Z/model.pt`, SHA-256 `21a7e9f044f898f99ee21fd93075ec1f4d1de5dc3bd24b2e10b645026b883200`.

## Held-out test (fold 10, 2163 records, evaluated once)

- Fusion macro AUROC 0.9196 (95% CI 0.9118 to 0.9268); macro F1 at validation thresholds 0.725.
- ECG only macro AUROC 0.9184 (95% CI 0.9110 to 0.9254); macro F1 0.736.
- Paired difference (fusion minus ECG only) +0.0013 (95% CI -0.0012 to 0.0038): **no difference shown**.
- Per class: NORM +0.0033 (0.0005 to 0.0062); MI -0.0019 (-0.0079 to 0.0037); STTC +0.0022 (-0.0015 to 0.0057); CD +0.0054 (-0.0003 to 0.0114); HYP -0.0028 (-0.0092 to 0.0037).

## Limitations

- Single-source internal evaluation (PTB-XL, recordings 1989-1996); no external or clinical validation.
- On the same held-out records, adding age and sex did not measurably change macro AUROC over the ECG-only network (paired difference in the report).
- Age and sex come from the request or the case's reviewed demographics, never from extracted text; without both the run is refused.
- Superclass labels aggregate cardiologist SCP statements; they are not adjudicated clinical diagnoses.
- Only 100 Hz, 10-second, 12-lead resting ECGs in the PTB-XL lead order are in scope.
- Platt calibration was fitted on the validation fold of the same source; probabilities are not calibrated for any clinical population.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/ptbxl_ecg_demographic_fusion.json`.
