# Model card: Maternal-fetal ultrasound plane, 6 classes (FETAL_PLANES_DB, research)

- **Model id:** `ultrasound_fetal_plane_classifier` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** fetal-planes-classification — fetal_abdomen, fetal_brain, fetal_femur, fetal_thorax, maternal_cervix, other
- **Data:** FETAL_PLANES_DB: common maternal-fetal ultrasound planes (CC BY 4.0; source https://zenodo.org/api/records/3904280). Dataset version `a533cf8ea9436f09`.
- **Split:** publisher patient split kept for test; 15% of the publisher's training patients for validation (seed 20261024, stratified by plane); counts {'train': 5973, 'val': 1156, 'test': 5271}.
- **Architecture:** efficientnet_b0 (selected by validation macro-F1 from resnet18, efficientnet_b0), ImageNet-pretrained torchvision weights.
- **Checkpoint:** `artifacts/training/ultrasound_fetal_plane_classifier-20261114T085532Z/model.pt`, SHA-256 `0f1e7ef110927c0dadd26319b74bc4d76f1aa844f44c16250a4e79fa482244f7`.

## Data adequacy and class imbalance

- **Run scope:** `STANDARD_INTERNAL_EVALUATION`; validation-ready: `true`.
- **Training loss:** inverse-frequency weighted cross-entropy (`w_c = N_train / (K * n_train,c)`), computed from training counts only.
- The source audit did not flag any class for insufficient samples.

## Held-out test results (internal, evaluated once)

- Accuracy 0.935 (95% CI 0.929-0.942); macro-F1 0.931 (95% CI 0.924-0.938); balanced accuracy 0.955 (95% CI 0.949-0.961).
- Macro one-vs-rest AUROC 0.995. ECE 0.031 uncalibrated, 0.016 after temperature scaling (T = 1.276).
- n = 5271 test images in 896 patients (bootstrap unit).

## Limitations

- Training used inverse-frequency weighted cross-entropy computed from the training split only. Weighting changes optimisation but does not create rare-class evidence or correct evaluation uncertainty.
- Pseudonymous patient ids come from the publisher's folders. The publisher's validation split, used as the test set, shares no patient with its training split; training patients were divided into train and validation, and the bootstrap resamples patients.
- Internal held-out test from the same source distribution; no external validation.
- Temperature scaling was fitted on the internal validation split; probabilities are not calibrated for any clinical population.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/ultrasound_fetal_plane_classifier.json`.
