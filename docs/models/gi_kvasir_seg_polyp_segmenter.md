# Model card: Kvasir-SEG polyp segmenter (research)

- **Model id:** `gi_kvasir_seg_polyp_segmenter` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** binary polyp masks (1 segment classes + background)
- **Data:** Kvasir-SEG (GI polyp segmentation) (Kvasir-SEG terms of use: research and educational purposes only; commercial use forbidden without prior written permission; cite the dataset paper; https://datasets.simula.no/kvasir-seg/); dataset version `4c97d0496ca08a60`; publisher lists: train.txt split group-aware into train/validation (85/15, seed 20261024); val.txt is the frozen test set.
- **Architecture:** MONAI 2D U-Net (32-512 channels, residual units), trained from scratch; best validation epoch 54.
- **Checkpoint:** `artifacts/training/gi_kvasir_seg_polyp_segmenter-20261025T080312Z/model.pt`, SHA-256 `a5a2c88dc5af67a8993210ca8a3d40ea79b9cd5e0a7cd5f422c1356828115c36`.

## Held-out test results (internal, evaluated once)

- Mean foreground Dice per image 0.768 (95% CI 0.725-0.809); macro segment Dice 0.768.
- Whole-polyp Dice 0.768 (95% CI 0.725-0.809), IoU 0.670, HD95 73.6 px at 352 px.
- Without test images that have a near-duplicate in another split (n = 120): mean Dice 0.768.

## Limitations

- Evaluated at the model's 352x352 working resolution; distances are in those pixels, not millimetres.
- The registry found no identifiers in sampled metadata, but source patient IDs are unavailable; patient-level independence cannot be verified. The recorded split and near-duplicate audit are reported above.
- Internal test split from the same source; no external validation.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/gi_kvasir_seg_polyp_segmenter.json`.
