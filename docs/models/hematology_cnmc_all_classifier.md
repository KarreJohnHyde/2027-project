# Model card: C-NMC ALL vs normal cell classifier (research)

- **Model id:** `hematology_cnmc_all_classifier` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** cnmc-all-vs-normal — all, hem
- **Data:** C-NMC 2019 leukaemia cell images (TCIA) (CC BY 3.0 (TCIA Data Usage Policy; citation required); source https://www.cancerimagingarchive.net/collection/c-nmc-2019/). Dataset version `6d29f9139eccdb72`.
- **Split:** subject clusters (subject id from the file name; subjects sharing a pixel-confirmed near-duplicate image joined) split train/validation 85/15 per class, seed 20261024; the publisher's labelled preliminary-phase test images are the frozen test set, and training subjects sharing an image with it are removed; bootstrap unit = subject cluster; counts {'train': 8157, 'val': 1430, 'test': 1867}.
- **Architecture:** efficientnet_b0 (selected by validation macro-F1 from resnet18, efficientnet_b0), ImageNet-pretrained torchvision weights.
- **Checkpoint:** `artifacts/training/hematology_cnmc_all_classifier-20261025T082713Z/model.pt`, SHA-256 `f5ea1fafc826ae524c8d335a5e32019243c58dcd0bda19ef0e9722823ca82736`.

## Data adequacy and class imbalance

- **Run scope:** `STANDARD_INTERNAL_EVALUATION`; validation-ready: `true`.
- **Training loss:** inverse-frequency weighted cross-entropy (`w_c = N_train / (K * n_train,c)`), computed from training counts only.
- The source audit did not flag any class for insufficient samples.

## Held-out test results (internal, evaluated once)

- Accuracy 0.807 (95% CI 0.659-0.894); macro-F1 0.790 (95% CI 0.626-0.877); balanced accuracy 0.794 (95% CI 0.657-0.871).
- Macro one-vs-rest AUROC 0.867. ECE 0.138 uncalibrated, 0.020 after temperature scaling (T = 3.191).
- n = 1867 test images in 28 subject clusters (bootstrap unit).

## Limitations

- Training used inverse-frequency weighted cross-entropy computed from the training split only. Weighting changes optimisation but does not create rare-class evidence or correct evaluation uncertainty.
- Subject ids come from the publisher's file names. Identical images occur under different subject ids, so subjects sharing an image were joined into clusters, training subjects linked to the test set were removed, and the bootstrap resamples clusters; whether an id denotes one patient cannot be verified.
- Internal held-out test from the same source distribution; no external validation.
- Temperature scaling was fitted on the internal validation split; probabilities are not calibrated for any clinical population.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/hematology_cnmc_all_classifier.json`.
