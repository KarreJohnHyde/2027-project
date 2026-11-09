# Model card: CT kidney and renal-tumour segmenter, 3-D (research)

- **Model id:** `ct_kidney_tumour_segresnet` (registry status `FAILED`; research evidence only when FAILED; no clinical authorization)
- **Task:** Patient-separated kidney and renal-tumour segmentation on the 210 labelled KiTS19 contrast CT volumes.
- **Data:** CC BY-NC-SA 4.0 (KiTS19 data); local non-commercial research only; dataset version `455cfd7c06b0a16e`; patients split {'train': 146, 'val': 32, 'test': 32} (train/val/test) by `sha256(seed:patient_id)`. Citation: Heller N et al. The KiTS19 Challenge Data: 300 Kidney Tumor Cases with Clinical Context, CT Semantic Segmentations, and Surgical Outcomes. arXiv:1904.00445.
- **Input:** channels CT; in-plane spacing 0.4375-5 mm, slice spacing 0.4375-1.041 mm; voxel axes IPL; 1st/99th intensity percentiles -3028 to -1009 and 159 to 561 HU (margin 100 HU). Held-out cases accepted by the gate: 32 of 32.
- **Preprocessing:** clip to -73 to 296 HU (0.5-99.5 percentiles of training foreground voxels), z-score with mean 101.95 and SD 72.4723 HU (training foreground), resampling to 3 x 3 x 3 mm and back (trilinear); sliding window [96, 96, 96] with overlap 0.5 (gaussian).
- **Architecture:** MONAI SegResNet (init filters 8, blocks [1, 2, 2, 4]/[1, 1, 1]), trained from scratch; best validation epoch 20 of 20 (validation mean case Dice 0.412).
- **Checkpoint:** `artifacts/training/ct_kidney_tumour_segresnet-20261109/best.pt`, SHA-256 `9acfa4f810ff7eb7be0e35c9ff465f1dee9385f7dc4ce9141ee54ae6e58651a2`.

## Held-out test results (32 patients, evaluated once through the serving function)

- Mean case macro Dice 0.416 (95% CI 0.402-0.429).
- kidney: Dice 0.833 (95% CI 0.804-0.858) over 32 cases (0 with neither reference nor prediction excluded).
- renal tumour: Dice 0.000 (95% CI 0.000-0.000) over 32 cases (0 with neither reference nor prediction excluded).
- kidney volume ml vs reference: bias +99.15 mL, limits of agreement -17.00 to 215.30 mL, MAE 100.55 (n = 32).
- renal tumour volume ml vs reference: bias -144.77 mL, limits of agreement -689.19 to 399.64 mL, MAE 144.77 (n = 32).

## Limitations

- Internal held-out patients only; no independent external or clinical validation.
- Renal-surgery cohort; healthy kidneys and incidental lesions in general populations are not established use cases.
- Tumour masks do not determine histology, malignancy, stage or treatment.
- One contrast abdominal CT volume in Hounsfield units within the recorded development geometry and intensity envelope.
- Initial bounded training experiment; measured results must be assessed before proposing further research use.
- FAILED TARGET: zero held-out Dice for renal_tumour. Upload inference is blocked; a zero mask must not imply absence of disease.
- Research-only output; not clinically validated and not for diagnosis or treatment decisions.
- Evaluation and serving use float16 autocast on CUDA with cuDNN autotuning; a rerun of training can differ slightly.

Full report: `docs/validation/models/ct_kidney_tumour_segresnet.json`; input envelope: `docs/validation/models/ct_kidney_tumour_segresnet_input_envelope.json`.
