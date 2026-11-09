# Window of the RSNA ICH PNG archive (for DICOM input to the head-CT model)

The head-CT haemorrhage model (`brain_ct_rsna_ich_classifier`) was trained on `RSNA_PNG/rsna-ich-png.zip`: a
third-party conversion of the RSNA 2019 training DICOMs to one 8-bit greyscale PNG per slice. The archive does not
say how Hounsfield units were mapped to grey levels. A DICOM slice sent to the model has to be mapped the same way,
so the mapping was measured from the PNGs. Measured on 2026-11-06; the scripts sit outside the repository and print
summary numbers only.

## Width: measured exactly

RSNA DICOMs store integers with rescale slope 1, so their HU values are integers. A linear window of width W maps
integers onto at most about W − 1 of the inner grey levels 1–254, spaced 255 / W apart. On 300 random slices with
a large brain area:

| Measure | Value |
| --- | --- |
| Inner grey levels that occur (all slices together) | 79 |
| Inner grey levels that occur (median per slice) | 79 |
| Spacing between occupied levels | 3 (64 times) or 4 (14 times); 255 / 80 = 3.19 |
| Best fit over W = 40–400 HU, lower bound offset and rounding | W = 80, integer lower bound, truncation (floor): 0 unexplained and 0 unused levels |
| Next-best fit | W = 80 with a shifted offset: 20 mismatched levels |

The export window is therefore **80 HU wide, with truncation** (`floor`, not `round`).

## Level: estimated

Quantisation fixes only the fractional part of the window's lower bound, not the level. The level comes from anatomy:

- The brain-tissue peak (per-slice mode, median of 1,500 slices) is grey level 96, IQR 93–106. That is 96 × 80 / 255 ≈ 30 HU above the lower bound.
- Smaller peaks at grey levels 13–29 sit 4–9 HU above the lower bound, as expected for CSF.

With a lower bound of 0 HU (level 40), brain tissue sits at about 30 HU and CSF at 4–9 HU. Both are textbook values.
A level of 30 would put brain tissue at about 20 HU, and a level of 50 at about 40 HU. **Level 40 HU**, the standard
brain level, is used. It is an estimate, not a measurement.

## How it is used

The model's registry entry declares `dicom_window = {center 40, width 80, LINEAR_EXACT, floor}`. The source is
`ml_training/rsna_ich.py` `DICOM_WINDOW`. `app/services/dicom_raster.py` applies it to the DICOM slice's HU values
instead of the file's own VOI, and records the window and its basis with every run. The converted slice must still
pass the model's applicability reference. The declared window does not bypass that gate, and the gate threshold was
not changed.

## Not verified

- `Brain_Stroke_CT_Dataset` has DICOMs, but its licence is unverified and its tasks are `LICENSE_BLOCKED`, so it was
  not used. CQ500 (490 head-CT DICOM scans with three radiologists' reads, CC BY-NC-SA 4.0) was approved and
  downloaded for evaluation on 2026-11-06. `scripts/evaluate_head_ct_cq500.py` measures the gate pass rate of real
  DICOM slices windowed this way and the scan-level agreement with the reads. On the first 5 scans every slice passed
  the gate. Results for all scans go to `docs/validation/models/head_ct_cq500_external.json`.
- Slices whose DICOM rescale is wrong would be mapped wrongly. The PNG converter may have corrected these; this is
  unknown.
