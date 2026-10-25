# Model card: ARCADE coronary stenosis detector (research)

- **Model id:** `angiography_stenosis_detector` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** stenosis regions (COCO boxes, category 'stenosis')
- **Data:** ARCADE coronary X-ray angiography (CC0 1.0; https://zenodo.org/records/10390295); dataset version `2b1fbdaf7fe5431f`; publisher splits kept.
- **Architecture:** Faster R-CNN ResNet-50 FPN v2 (COCO-pretrained torchvision weights); best validation epoch 4.
- **Checkpoint:** `artifacts/training/angiography_stenosis_detector-20261024T152607Z/model.pt`, SHA-256 `d06224b406d7e9104f25c03921fcbe78c2aedae0752ce74e9bcbfefae49c05b8`.

## Held-out test results (internal, evaluated once)

- COCO mAP@[.50:.95] 0.062; AP50 0.203; AR@100 0.359 on 300 images.
- After excluding all 10 test images belonging to any transitive near-duplicate component spanning publisher splits (290 retained): mAP 0.061, AP50 0.198.
- At the validation-chosen score threshold 0.75: precision 0.215, recall 0.381 (IoU 0.5).

## Limitations

- The registry found no identifiers in sampled metadata, but source patient IDs are unavailable; patient-level independence cannot be verified. The recorded split and near-duplicate audit are reported above.
- Internal test split from the same source; no external validation.
- Detection scores are not probabilities and are not calibrated.
- Research-only output; not validated for clinical use.
- The conservative duplicate sensitivity analysis excludes every test image in a transitive near-duplicate component spanning publisher splits; it is a post-hoc subset analysis, while the official publisher test result remains unchanged.

Full report: `docs/validation/models/angiography_stenosis_detector.json`.
Conservative rescore evidence: `docs/validation/models/angiography_stenosis_detector.component_rescore.json`.
