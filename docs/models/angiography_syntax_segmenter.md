# Model card: ARCADE SYNTAX coronary segment segmenter (research)

- **Model id:** `angiography_syntax_segmenter` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** 25 SYNTAX coronary segments (COCO polygons) (25 segment classes + background)
- **Data:** ARCADE coronary X-ray angiography (CC0 1.0; https://zenodo.org/records/10390295); dataset version `c21bee6dc5bd0a4e`; publisher splits kept.
- **Architecture:** MONAI 2D U-Net (32-512 channels, residual units), trained from scratch; best validation epoch 18.
- **Checkpoint:** `artifacts/training/angiography_syntax_segmenter-20261024T170738Z/model.pt`, SHA-256 `3a3882071f72192edaec39a3cfd2449faf6d93f367d11dccf3455ba8824ab0a0`.

## Held-out test results (internal, evaluated once)

- Mean foreground Dice per image 0.307 (95% CI 0.291-0.322); macro segment Dice 0.201.
- Whole-vessel Dice 0.683 (95% CI 0.665-0.699), IoU 0.535, HD95 80.5 px at 512 px.
- After excluding all 2 test images belonging to any transitive near-duplicate component spanning publisher splits (298 retained): mean foreground Dice per image 0.308; whole-vessel Dice 0.683.

## Limitations

- Evaluated at the model's 512x512 working resolution; distances are in those pixels, not millimetres.
- The registry found no identifiers in sampled metadata, but source patient IDs are unavailable; patient-level independence cannot be verified. The recorded split and near-duplicate audit are reported above.
- Internal test split from the same source; no external validation.
- Research-only output; not validated for clinical use.
- The conservative duplicate sensitivity analysis excludes every test image in a transitive near-duplicate component spanning publisher splits; it is a post-hoc subset analysis, while the official publisher test result remains unchanged.
- No held-out reference mask exists for segment 10a; its per-segment Dice is undefined.
- Held-out support is below 20 images for segment 10; its per-segment estimate is unstable.

Full report: `docs/validation/models/angiography_syntax_segmenter.json`.
Conservative rescore evidence: `docs/validation/models/angiography_syntax_segmenter.component_rescore.json`.
