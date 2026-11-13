# Checkpoint-specific results

The user's original model registry SHA-256 remains `b56979e0591788b1d588fa11c590e0378a1f98db1114612df702f816aa5b65b7`. Original weights and registered statuses were not replaced. Existing user fracture-model changes were preserved.

Current new worker checks:

| Model | Checkpoint SHA-256 | New execution evidence |
| --- | --- | --- |
| `acdc_cardiac_mri_3d_unet` | `b18afcf66effbfd8c8db515958e798cb7b03f322b4a1da354d41edb5edc2d60e` | Public ACDC input, actual persisted mask/run11,3 structures/surfaces and source-grid publisher comparison |
| `brain_mri_stroke_lesion_segresnet` | `058be494f9b04b603fa47bfc7425707bb6802408eac37d5ce8daa910a86d14ca` | Public ISLES input, actual persisted lesion mask/run12,1 surface and source-grid publisher comparison |

Exact new per-input Dice/IoU and hashes are in `IMPLEMENTATION_STATUS.md` and `native-workflows/publisher-reference-comparisons.json`. One input per checkpoint is not a new aggregate model evaluation. No training, calibration fitting, threshold selection or accuracy improvement occurred.

The preserved prior same-day checkpoint inventory/result reconciliation is `docs/review-2026-11-13/MEDTWIN_MODEL_RESULTS_2026-11-13.csv` and `MEDTWIN_MODEL_EVIDENCE_2026-11-13.json`. They distinguish historic saved cohort metrics from runtime/checkpoint evidence. The failed renal tumour target remains blocked; historical weak fracture/stenosis/skin/GastroVision evidence remains visible. Registry count and historical scores do not substitute for inference or clinical validation.

Arena shows current evaluation-file and checkpoint identities and independently verifies declared report model/dataset/checkpoint/prediction-path binding. Unsupported/missing declarations remain unverified. Matched cohorts are checked using actual record/patient/ground-truth tuples; equal sample counts do not establish comparability.
