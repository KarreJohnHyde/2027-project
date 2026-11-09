# Model card: Upper-limb radiograph abnormality classifier, MURA (research)

- **Model id:** `mura_study_baseline` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** mura-study-abnormality — abnormal, normal
- **Data:** MURA v1.1 musculoskeletal radiographs (Stanford AIMI) (Stanford AIMI Research Use Agreement: personal, non-commercial research only; no redistribution; each user registers individually; source https://aimi.stanford.edu/datasets/mura-msk-xrays). Dataset version `873c4587ca667acf`.
- **Split:** publisher validation split frozen as test; publisher training patients divided into train/validation, seed 20261024; labels per study from the publisher's CSV; group unit: patient; counts {'train': 30370, 'val': 6438, 'test': 3197}.
- **Architecture:** efficientnet_b0 (selected by validation macro-F1 from resnet18, efficientnet_b0), ImageNet-pretrained torchvision weights.
- **Checkpoint:** `artifacts/training/mura_study_baseline-20261031T115458Z/model.pt`, SHA-256 `e5604f7efe4c480bc58e0a29d159255fb4ba8a08644cfa10de76f665595215be`.

## Data adequacy and class imbalance

- **Run scope:** `STANDARD_INTERNAL_EVALUATION`; validation-ready: `true`.
- **Training loss:** inverse-frequency weighted cross-entropy (`w_c = N_train / (K * n_train,c)`), computed from training counts only.
- The source audit did not flag any class for insufficient samples.

## Held-out test results (internal, evaluated once)

- Accuracy 0.822 (95% CI 0.802-0.840); macro-F1 0.821 (95% CI 0.801-0.839); balanced accuracy 0.820 (95% CI 0.800-0.838).
- Macro one-vs-rest AUROC 0.887. ECE 0.031 uncalibrated, 0.023 after temperature scaling (T = 1.250).
- n = 3197 test images in 783 patients (bootstrap unit).

## Limitations

- Training used inverse-frequency weighted cross-entropy computed from the training split only. Weighting changes optimisation but does not create rare-class evidence or correct evaluation uncertainty.
- Pseudonymous patient ids come from the publisher's folders. The publisher's validation split, used as the test set, shares no patient with its training split; training patients were divided into train and validation, and the bootstrap resamples patients.
- Internal held-out test from the same source distribution; no external validation.
- Temperature scaling was fitted on the internal validation split; probabilities are not calibrated for any clinical population.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/mura_study_baseline.json`.

_Correction (2026-10-31): the bootstrap unit is the patient; earlier labels said near-duplicate group. No value changed._
