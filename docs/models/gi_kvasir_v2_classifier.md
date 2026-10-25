# Model card: Kvasir v2 8-class GI endoscopy classifier (research)

- **Model id:** `gi_kvasir_v2_classifier` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** kvasir-v2-8class — dyed-lifted-polyps, dyed-resection-margins, esophagitis, normal-cecum, normal-pylorus, normal-z-line, polyps, ulcerative-colitis
- **Data:** Kvasir v2 (GI endoscopy) (Kvasir terms of use: research and educational purposes only; commercial use requires written permission; cite the dataset paper; source https://datasets.simula.no/kvasir/). Dataset version `f3eedd730fe4a33d`.
- **Split:** group-aware stratified split, seed 20261024, fractions {'train': 0.7, 'val': 0.15, 'test': 0.15}, dHash threshold 4; counts {'train': 5599, 'val': 1199, 'test': 1202}.
- **Architecture:** resnet18 (selected by validation macro-F1 from resnet18, efficientnet_b0), ImageNet-pretrained torchvision weights.
- **Checkpoint:** `artifacts/training/gi_kvasir_v2_classifier-20261024T151359Z/model.pt`, SHA-256 `6d7494d19e52c0b5462f90637e35f474d9db1950217e5a40e95cda4bec27a8e4`.

## Held-out test results (internal, evaluated once)

- Accuracy 0.926 (95% CI 0.911-0.940); macro-F1 0.926 (95% CI 0.911-0.940); balanced accuracy 0.926 (95% CI 0.912-0.940).
- Macro one-vs-rest AUROC 0.995. ECE 0.020 uncalibrated, 0.019 after temperature scaling (T = 1.078).
- n = 1202 test images in 1194 near-duplicate groups (bootstrap unit).

## Limitations

- The registry found no identifiers in sampled metadata, but the source provides no patient IDs; patient-level separation cannot be verified. Splits keep confirmed near-duplicate groups together.
- Internal held-out test from the same source distribution; no external validation.
- Temperature scaling was fitted on the internal validation split; probabilities are not calibrated for any clinical population.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/gi_kvasir_v2_classifier.json`.
