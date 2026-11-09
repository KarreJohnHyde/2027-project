# Cardiac MRI from scanner series: choosing the axis convention

`acdc_cardiac_mri_3d_unet` was trained on ACDC NIfTI frames whose affines are placeholders (`diag(-1, -1, 1)`, spacing
1). The frames carry no patient orientation, so DICOM tags alone cannot put a scanner series into the network's voxel
convention. These measurements were made on 2026-11-06 with
`scripts/calibrate_cardiac_orientation_consistency.py`. The prior and the results are stored in the model's input
envelope (`axis_convention`).

## What the convention changes

Each held-out test frame was segmented under all 16 conventions (a row/column transpose times flips of each axis), and
each prediction was mapped back. Mean macro Dice (RV, myocardium, LV cavity) on 98 frames:

| Convention | Mean macro Dice |
| --- | --- |
| Publisher's convention | 0.748 |
| Flips only (training augmentations), range | 0.742–0.755 |
| Row/column transposed, range | 0.704–0.723 |

Flips cost nothing because the network was trained with random flips. A transpose costs 0.025–0.044. The network
localises real anatomy under every convention, but it can also place a false right ventricle where it expects one.

A first check, the agreement of the 16 predictions with each other, was the wrong measure. The median Dice between
conventions was about 0.62 on six held-out frames, while their accuracy against the ground truth was similar. That
check was dropped.

## The rule

The development ground truth (168 training frames) has a consistent layout:

- The right-ventricle centroid lies at 171° from the left-ventricle centroid in voxel space (resultant length 0.88;
  median offset 19°; 99th percentile 70°).
- The left-ventricle area shrinks along k in 98.8 % of frames (base to apex).

For a scanner series:

1. The model runs under all 16 conventions, and each prediction is mapped back to the series grid.
2. A convention is eligible only if:
   - its right ventricle lies anterior-right of the left ventricle in the series' DICOM patient coordinates (normal anatomy), and
   - its left-ventricle area shrinks along the slices.
3. Of the eligible conventions, the one whose RV direction is closest to 171° is used. A series is refused when no
   convention is eligible, or when the best one is more than 71° from 171°.
4. Before any of this, the series must be MR with a slice normal at least 15° from every body axis (short-axis stacks
   are double-oblique), at least 6 slices, and the requester's attestation of view and phase. A cine series is assembled
   for one chosen phase (the p-th image by trigger time at every position).

## Held-out evaluation

ACDC has no patient orientation, so each held-out frame was given a simulated scanner geometry:

- a random double-oblique slice normal;
- in-plane axes that put its ground-truth right ventricle anterior-right of the left ventricle, within 60°.

By symmetry, the 16 candidates are the same whatever the stored convention, so this covers every unknown convention.

| Rule | Accepted (of 98) | Mean macro Dice, chosen | Publisher's convention, same frames |
| --- | --- | --- | --- |
| With the patient-coordinate check | 91 | 0.750 | 0.753 |
| Content only (no geometry) | 96 | 0.743 | 0.751 |

Refusals with the check:

| Reason | Frames |
| --- | --- |
| RV not anterior-right under any convention | 3 |
| LV area never shrinking | 2 |
| Layout outside the development range | 2 |

Two further frames are outside the input envelope (in-plane spacing).

An end-to-end run on one held-out frame showed why the anatomical side matters. The frame was stored transposed and
flipped. Without the patient-coordinate check, the content-only rule chose a convention with a false right ventricle
(RV Dice 0.18). With the check, that convention was ineligible.

## Limits

- The geometry is simulated; no real scanner series with reference masks has been evaluated.
- The patient-coordinate check assumes normal cardiac position (it refuses dextrocardia and situs inversus).
- The rule cannot tell a short-axis stack from another oblique stack; the requester attests the view.
- Output volumes are research estimates for one frame, not ejection fraction.
