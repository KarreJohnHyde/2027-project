# Model card: Cardiac cine-MRI ventricular segmenter, 3-D (research)

- **Model id:** `acdc_cardiac_mri_3d_unet` (registry status `READY_UNVALIDATED`; research-only; no upload inference path)
- **Task:** segmentation of the right-ventricular cavity, myocardium and left-ventricular cavity at end-diastole and end-systole.
- **Data:** dataset version `c0fa24d113128f2d`; publisher test patients frozen; development patients split by patient (seed 20261024); development patients whose images duplicate a test patient are excluded. Sources and terms: Data sources and licences.
- **Architecture:** 3-D U-Net, channels [32, 64, 128, 256], patch [128, 128, 16], trained from scratch; best validation epoch 41 of 60.
- **Checkpoint:** `artifacts/training/acdc_cardiac_mri_3d_unet-20261025T132755Z/best.pt`, SHA-256 `b18afcf66effbfd8c8db515958e798cb7b03f322b4a1da354d41edb5edc2d60e`.

## Held-out test results (50 patients, 100 ED/ES volumes, evaluated once)

- Mean case macro Dice 0.750 (95% CI 0.719-0.778).
- right ventricular cavity: Dice 0.707 (95% CI 0.672-0.742); HD95 81.6 mm.
- myocardium: Dice 0.731 (95% CI 0.698-0.758); HD95 58.6 mm.
- left ventricular cavity: Dice 0.812 (95% CI 0.771-0.848); HD95 53.7 mm.
- LV ejection fraction vs reference masks: bias -5.8 points, limits of agreement -29.6 to +17.9, MAE 9.1 (n = 50).

## Limitations

- Internal held-out evaluation on the publisher's test patients from one centre; no external or clinical validation.
- Cardiac indices are compared with indices from the publisher's reference masks, not with clinically reported values.
- Native acquisition grid without resampling; slice thickness (5-10 mm) limits through-plane accuracy, and HD95 is dominated by it.
- No connected-component post-processing was prespecified; predicted regions away from the heart inflate volumes and HD95, so volumes, ejection fractions and myocardial mass carry large biases and wide limits of agreement.
- Evaluation and training used float16 autocast on CUDA; CUDA cross-entropy is not deterministic, so a rerun can differ slightly.
- Research-only output; there is no upload inference path, and nothing here is a patient measurement.

Full report: `docs/validation/models/acdc_cardiac_mri_3d_unet.json`.
