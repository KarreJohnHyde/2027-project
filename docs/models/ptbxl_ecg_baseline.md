# Model card: PTB-XL 12-lead ECG diagnostic-superclass classifier (research)

- **Model id:** `ptbxl_ecg_baseline` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** multi-label NORM, MI, STTC, CD, HYP from 10-second 100 Hz 12-lead resting ECGs.
- **Data:** PTB-XL 1.0.1 (CC BY 4.0 (Creative Commons Attribution 4.0 International)). Dataset version `a1f01931077bf242`; 42862 files verified against the publisher's SHA-256 sums; every lead checked against its header checksum.
- **Split:** publisher folds 1-8 / 9 / 10 (17111 / 2156 / 2163 records; patient-disjoint, asserted). 407 records without a diagnostic superclass excluded.
- **Architecture:** compact 1D ResNet trained from scratch; best validation epoch 11 (val macro AUROC 0.923).
- **Checkpoint:** `artifacts/training/ptbxl_ecg_baseline-20261025T072058Z/model.pt`, SHA-256 `687f69a2ff1cb50dcd0c5a26759f2d2154090c71746518db150c7638d9efb067`.

## Held-out test results (fold 10, evaluated once)

- Macro AUROC 0.917 (95% CI 0.909-0.925); macro AUPRC 0.805; macro F1 at validation thresholds 0.734 (95% CI 0.717-0.750).
- n = 2163 ECGs from 1881 patients (bootstrap unit: patient).
- Per class: NORM AUROC 0.938 (CI 0.927-0.947), sensitivity 0.93, specificity 0.79; MI AUROC 0.908 (CI 0.893-0.922), sensitivity 0.75, specificity 0.88; STTC AUROC 0.931 (CI 0.920-0.942), sensitivity 0.75, specificity 0.93; CD AUROC 0.908 (CI 0.889-0.924), sensitivity 0.65, specificity 0.95; HYP AUROC 0.903 (CI 0.881-0.923), sensitivity 0.67, specificity 0.94.
- Mean ECE 0.027 raw, 0.015 after Platt scaling.

## Limitations

- Single-source internal evaluation (PTB-XL, Physikalisch-Technische Bundesanstalt, recordings 1989-1996); no external validation.
- Superclass labels aggregate cardiologist SCP statements; they are not adjudicated clinical diagnoses.
- Only 100 Hz, 10-second, 12-lead resting ECGs in the PTB-XL lead order are in scope; other devices, sampling rates or lead sets are out of distribution.
- Platt calibration was fitted on the validation fold of the same source; probabilities are not calibrated for any clinical population.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/ptbxl_ecg_baseline.json`.
