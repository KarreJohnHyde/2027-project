# Model card: GastroVision 27-class GI endoscopy classifier (exploratory research)

- **Model id:** `gi_gastrovision_27class_classifier` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** gastrovision-27class — Accessory tools, Angiectasia, Barretts esophagus, Blood in lumen, Cecum, Colon diverticula, Colon polyps, Colorectal cancer, Duodenal bulb, Dyed-lifted-polyps, Dyed-resection-margins, Erythema, Esophageal varices, Esophagitis, Gastric polyps, Gastroesophageal_junction_normal z-line, Ileocecal valve, Mucosal inflammation large bowel, Normal esophagus, Normal mucosa and vascular pattern in the large bowel, Normal stomach, Pylorus, Resected polyps, Resection margins, Retroflex rectum, Small bowel_terminal ileum, Ulcer
- **Data:** GastroVision (GI endoscopy, 27 classes) (CC BY 4.0; source https://api.osf.io/v2/nodes/84e7f/ (OSF project 84e7f, license field)). Dataset version `1f2d40f8aa2a284d`.
- **Split:** group-aware stratified split, seed 20261024, fractions {'train': 0.7, 'val': 0.15, 'test': 0.15}, dHash threshold 4; counts {'train': 5587, 'val': 1188, 'test': 1225}.
- **Architecture:** efficientnet_b0 (selected by validation macro-F1 from resnet18, efficientnet_b0), ImageNet-pretrained torchvision weights.
- **Checkpoint:** `artifacts/training/gi_gastrovision_27class_classifier-20261024T173442Z/model.pt`, SHA-256 `464986a86033a6415af2870ac26a75d06c787e86caf3b9f74b865e4f5ba757f9`.

## Data adequacy and class imbalance

- **Run scope:** `EXPLORATORY_ONLY`; validation-ready: `false`.
- **Training loss:** inverse-frequency weighted cross-entropy (`w_c = N_train / (K * n_train,c)`), computed from training counts only.
- **Minimum samples per class:** 20.
- **Rare class:** Angiectasia — total 17 (train 11, validation 2, test 4).
- **Rare class:** Erythema — total 15 (train 10, validation 2, test 3).
- **Rare class:** Esophageal varices — total 7 (train 4, validation 1, test 2).
- **Rare class:** Ulcer — total 6 (train 4, validation 1, test 1).

## Held-out test results (internal, evaluated once)

- Accuracy 0.737 (95% CI 0.713-0.761); macro-F1 0.553 (95% CI 0.507-0.589); balanced accuracy 0.622 (95% CI 0.574-0.693).
- Macro one-vs-rest AUROC 0.979. ECE 0.047 uncalibrated, 0.035 after temperature scaling (T = 1.117).
- n = 1225 test images in 1223 near-duplicate groups (bootstrap unit).

## Limitations

- INSUFFICIENT_SAMPLES: classes below the declared minimum of 20: Angiectasia (total=17, train=11, val=2, test=4); Erythema (total=15, train=10, val=2, test=3); Esophageal varices (total=7, train=4, val=1, test=2); Ulcer (total=6, train=4, val=1, test=1). This run was explicitly exploratory; rare-class estimates are unstable and are not validation-ready.
- Training used inverse-frequency weighted cross-entropy computed from the training split only. Weighting changes optimisation but does not create rare-class evidence or correct evaluation uncertainty.
- The registry found no identifiers in sampled metadata, but the source provides no patient IDs; patient-level separation cannot be verified. Splits keep confirmed near-duplicate groups together.
- Internal held-out test from the same source distribution; no external validation.
- Temperature scaling was fitted on the internal validation split; probabilities are not calibrated for any clinical population.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/gi_gastrovision_27class_classifier.json`.
