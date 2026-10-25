# Model card: TEZ kidney stone detector on CT slices (research)

- **Model id:** `kidney_stone_detector` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** kidney stone boxes (class Tas_Var)
- **Data:** TEZ_ROI_AUG kidney stone detection (Roboflow) (CC BY 4.0; in-archive README.dataset.txt and data.yaml (Roboflow Universe tez-nwkf5/tez_roi_aug v3)); dataset version `5085472ca7ecf856`; re-split by acquisition session joined with pixel near-duplicate groups; stratified by stone present, seed 20261024, fractions {'train': 0.7, 'val': 0.15, 'test': 0.15} (publisher split kept as publisher_split).
- **Architecture:** Faster R-CNN ResNet-50 FPN v2 (COCO-pretrained torchvision weights); best validation epoch 1.
- **Checkpoint:** `artifacts/training/kidney_stone_detector-20261024T161540Z/model.pt`, SHA-256 `e9267f9a6e9fb36cc08fd27a888096209febf023ce2f140c5f7d38f6839b9fcb`.

## Held-out test results (internal, evaluated once)

- COCO mAP@[.50:.95] 0.231; AP50 0.629; AR@100 0.360 on 196 images.
- Without the 0 test images that have a near-duplicate in another split: mAP 0.231, AP50 0.629.
- At the validation-chosen score threshold 0.85: precision 0.742, recall 0.550 (IoU 0.5).

## Limitations

- The registry found no identifiers in sampled metadata, but source patient IDs are unavailable; patient-level independence cannot be verified. The recorded split and near-duplicate audit are reported above.
- Internal test split from the same source; no external validation.
- Detection scores are not probabilities and are not calibrated.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/kidney_stone_detector.json`.
