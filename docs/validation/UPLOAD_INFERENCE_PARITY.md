# Upload inference parity: ECG and cardiac MRI (2026-10-28)

The ECG classifier (`ptbxl_ecg_baseline`) and the cardiac cine-MRI segmenter
(`acdc_cardiac_mri_3d_unet`) now have research-only upload inference. Before relying on
it, the server code path was run on each model's public held-out test set and compared
with the predictions its trainer saved. Inputs went through the same readers and gates an
upload goes through (`backend/app/services/ecg_inference.py`, `volume_inference.py`) and
the registered checkpoints behind the SHA-256 gate.

Reproduce with `.venv\Scripts\python.exe scripts/verify_upload_inference_parity.py`; the
machine-readable result is `docs/validation/UPLOAD_INFERENCE_PARITY.json`.

| Model | Held-out set | Refused by the input gate | Compared | Agreement with saved predictions |
| --- | --- | --- | --- | --- |
| PTB-XL ECG | 2,163 records (strat_fold 10) | 2 (`SIGNAL_QUALITY_AMPLITUDE`, peak above 10 mV) | 2,161 | Max probability difference 0.0024, mean 0.00022; 2 of 10,805 threshold decisions differ |
| ACDC cardiac MRI | 100 frames (publisher test set) | 2 (`IN_PLANE_SPACING_OUTSIDE_DEVELOPMENT_RANGE`, 1.95 mm) | 98 | 98 of 98 masks identical voxel for voxel |

Both paths reproduce their trainers' preprocessing and numeric precision: bfloat16 autocast
for the ECG network and float16 autocast for the 3-D U-Net, as in each held-out evaluation.
The small ECG differences are consistent with bfloat16 arithmetic on single records rather
than batches of 256. The saved probabilities are also rounded to six decimals.

## What the gates cost

- **ECG.** The 10 mV amplitude limit is shared with the ECG preview validator. It refuses
  2 genuine PTB-XL test records (0.09%). Nothing is resampled, cropped or padded, so only
  100 Hz, 10-second, 12-lead records are accepted.
- **Cardiac MRI.** The spacing envelope is the range over the 198 development cases,
  recorded in `docs/validation/models/acdc_cardiac_mri_3d_unet_input_envelope.json` by
  `scripts/build_acdc_input_envelope.py`. It refuses 2 of the 100 publisher test frames,
  both with 1.95 mm in-plane spacing (the development maximum is 1.92 mm). Six accepted test
  frames have a matrix outside the development range; that produces a warning, not a refusal.

## What this does and does not show

It shows that an uploaded record or frame inside the contract gets the prediction that
was scored in the held-out evaluation. It is not new evidence of accuracy, and it is not
external or clinical validation. The input gates check format, geometry and signal
quality. They cannot verify the ECG acquisition conditions, the MRI sequence or view, or
the cardiac phase. A photograph or scan of a printed ECG is an image, not a signal, and is
never accepted by the ECG model.
