# Model card: Malaria parasite in a thin-smear red blood cell (NIH/NLM, research)

- **Model id:** `blood_smear_malaria_cell_classifier` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** nih-malaria-cell-classification — parasitized, uninfected
- **Data:** NIH/NLM malaria thin blood smear cell images (NLM public research release (free public use; cite the dataset paper); source https://lhncbc.nlm.nih.gov/LHC-research/LHC-projects/image-processing/malaria-datasheet.html). Dataset version `d217c6dceca42d7d`.
- **Split:** patients (slide code prefix) split 70/15/15, stratified by each patient's majority label, seed 20261024; counts {'train': 19156, 'val': 4012, 'test': 4390}.
- **Architecture:** efficientnet_b0 (selected by validation macro-F1 from resnet18, efficientnet_b0), ImageNet-pretrained torchvision weights.
- **Checkpoint:** `artifacts/training/blood_smear_malaria_cell_classifier-20261114T071802Z/model.pt`, SHA-256 `aa6216e57bc92be33ad3702e06487906c624099e98567937cc02f2f6b874b085`.

## Data adequacy and class imbalance

- **Run scope:** `STANDARD_INTERNAL_EVALUATION`; validation-ready: `true`.
- **Training loss:** inverse-frequency weighted cross-entropy (`w_c = N_train / (K * n_train,c)`), computed from training counts only.
- The source audit did not flag any class for insufficient samples.

## Held-out test results (internal, evaluated once)

- Accuracy 0.965 (95% CI 0.948-0.982); macro-F1 0.965 (95% CI 0.947-0.981); balanced accuracy 0.964 (95% CI 0.950-0.981).
- Macro one-vs-rest AUROC 0.987. ECE 0.020 uncalibrated, 0.014 after temperature scaling (T = 1.418).
- n = 4390 test images in 34 patients (bootstrap unit).

## Limitations

- Training used inverse-frequency weighted cross-entropy computed from the training split only. Weighting changes optimisation but does not create rare-class evidence or correct evaluation uncertainty.
- Pseudonymous patient ids come from the publisher's folders. The publisher's validation split, used as the test set, shares no patient with its training split; training patients were divided into train and validation, and the bootstrap resamples patients.
- Internal held-out test from the same source distribution; no external validation.
- Temperature scaling was fitted on the internal validation split; probabilities are not calibrated for any clinical population.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/blood_smear_malaria_cell_classifier.json`.
