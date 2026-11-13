# Model card: Upper-limb radiograph fracture detector (Roboflow v4, research)

- **Model id:** `bone_fracture_detector` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** fracture boxes: the six region-specific fracture classes merged into one 'fracture' class; the non-fracture 'humerus' class (index 4) excluded (owner decision, 2026-11-06)
- **Data:** Bone fracture detection v4 (Roboflow) (CC BY 4.0; in-archive README.dataset.txt and data.yaml (Roboflow Universe veda/bone-fracture-detection-daoon v4)); dataset version `7ea36477f94704c9`; publisher splits kept.
- **Architecture:** Faster R-CNN ResNet-50 FPN v2 (COCO-pretrained torchvision weights); best validation epoch 10.
- **Checkpoint:** `artifacts/training/bone_fracture_detector-20261110T020213Z/model.pt`, SHA-256 `902e43ba2d7f0cf38dc2f56def3c2fa4dfef85bb5dccc8e4d61c01b20c213ff1`.

## Held-out test results (internal, evaluated once)

- COCO mAP@[.50:.95] 0.047; AP50 0.155; AR@100 0.123 on 169 images.
- Without the 0 test images that have a near-duplicate in another split: mAP 0.047, AP50 0.155.
- At the validation-chosen score threshold 0.55: precision 0.400, recall 0.222 (IoU 0.5).

## Limitations

- The registry found no identifiers in sampled metadata, but source patient IDs are unavailable; patient-level independence cannot be verified. The recorded split and near-duplicate audit are reported above.
- Internal test split from the same source; no external validation.
- Detection scores are not probabilities and are not calibrated.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/bone_fracture_detector.json`.
