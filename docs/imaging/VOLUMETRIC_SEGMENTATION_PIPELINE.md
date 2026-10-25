# Volumetric NIfTI segmentation pipeline

## Evidence boundary

MedTwin now has an executable, reusable 3-D segmentation training/evaluation path.
It has **not** trained on the local ACDC volumes. The ACDC archive contains a mandatory
citation file but no explicit licence grant, so the live registry records
`license.authorization_status = UNVERIFIED`. The trainer checks that exact field before
loading any real volume and refuses unless its value is `VERIFIED`.

`SOURCE_AND_CITATION_VERIFIED_TERMS_NOT_FOUND` describes what was inspected. It is not
permission. A generated synthetic fixture has a separate, explicit test-only gate and
cannot become model-registry evidence.

## Components

- `ml_training.volumetric_manifest` discovers ACDC ED/ES pairs or reads a generic pairs
  CSV for later KiTS/BTCV/TotalSegmentator use.
- It requires one `patient_id` per case and assigns whole patients to deterministic
  SHA-256-ordered train/validation/test splits.
- It verifies that image and mask are 3-D, their shapes and affines agree, voxel spacing
  is valid, image values are finite, masks contain finite integer labels from a declared
  contiguous vocabulary, and required paths remain inside the dataset root.
- It records SHA-256 for every image and mask, label voxel counts by split, orientation,
  spacing, geometry, and a stable dataset version. Identical content and patients may not
  cross splits. Training revalidates the files and hashes.
- `ml_training.volumetric` trains a configurable MONAI 3-D U-Net from deterministic,
  foreground-biased patches. It supports CPU/CUDA selection, optional CUDA AMP,
  deterministic seeds, checkpoints, resume, and native-grid sliding-window inference.
- Validation selects a checkpoint by mean case-level macro foreground Dice. The frozen
  checkpoint is evaluated once per complete held-out case. Reports include case-level
  and per-class Dice/IoU; both-empty class/case pairs are explicitly undefined and
  excluded rather than scored as perfect.
- The trainer writes an execution record and checkpoint only after the licence and
  manifest gates pass. It never edits the model registry.

## Executed ACDC readiness audit

Command:

```powershell
.venv\Scripts\python.exe -m ml_training.volumetric_manifest acdc `
  --dataset-root database --output $env:TEMP\medtwin-acdc-volumetric-manifest.json
.venv\Scripts\python.exe -m ml_training.volumetric_manifest validate `
  --manifest $env:TEMP\medtwin-acdc-volumetric-manifest.json
```

Observed on 2026-10-25:

| Check | Result |
| --- | --- |
| Labelled patients / phase cases discovered | 150 / 300 |
| Publisher cohort | 100 training patients / 50 frozen test patients, all with local masks |
| Retained patient split | 84 train / 15 validation / 50 test |
| Retained phase-case split | 168 / 30 / 100 (298 total) |
| Leakage exclusion | complete development patient055 (both phases byte-identical to frozen-test patient118; masks differ) |
| Patient overlap | 0 |
| Identical image or mask content across splits | 0 |
| Geometry/affine failures | 0 |
| Observed labels | 0 background, 1 right-ventricular cavity, 2 myocardium, 3 left-ventricular cavity |
| Dataset version | `c0fa24d113128f2d33975747fa82c3d13eea27577c08de895346094544afebcd` |
| Training eligibility | false (`LICENSE_AUTHORIZATION_UNVERIFIED`) |

The 50 publisher test patients are labelled locally and remain frozen for evaluation.
Hash inspection found that both ED/ES images for development patient055 are byte-identical
to publisher-test patient118, while the associated masks differ. The complete development
patient055 (two cases) is excluded; no publisher-test case is moved or removed. After that
exclusion, no patient or identical image/mask content crosses splits. The readiness
manifest was written to a temporary path because it contains per-case
pseudonymous identifiers and absolute local storage metadata; it can be regenerated from
the verified local files using the command above.

The real-data refusal was also executed through the train CLI. It exited non-zero before
creating the requested output directory. No ACDC patient volume was loaded for training.

## Synthetic execution verification

```powershell
.venv\Scripts\python.exe -m ml_training.volumetric smoke --work-dir <empty-temp-directory>
.venv\Scripts\python.exe -m pytest backend/tests/test_training_volumetric.py -q -p no:cacheprovider
```

The smoke command generates six isolated 12x12x12 NIfTI image/mask pairs, builds and
revalidates a patient-grouped manifest, trains one CPU epoch, selects a checkpoint,
evaluates the held-out case with sliding-window inference, saves a prediction, and emits
per-class/case Dice and IoU. Tests also continue from the saved checkpoint for a second
epoch and verify that an affine mismatch and an unauthorized real ACDC request fail.
These generated results establish software execution only; their metrics are not medical
performance evidence and are intentionally omitted from the model registry.

## Remaining gates before a real experiment

1. Record independently reviewed ACDC licence/terms evidence and authorization in the
   dataset registry. Do not change the gate merely to make a run start.
2. Have a qualified reviewer confirm the integer-label semantics and experiment scope.
3. Pre-register an ACDC-specific spacing/resampling, normalization, augmentation,
   architecture, stopping, and uncertainty protocol. The current generic native-grid
   defaults are a runnable baseline, not an approved ACDC protocol.
4. Persist the immutable manifest, execute training, preserve checkpoint and held-out
   predictions, independently re-score them, and only then update the registry.
5. Obtain external-site validation and build a separately tested application inference
   adapter before exposing any patient-facing output.

KiTS19 still lacks its paired CT volumes locally. BTCV and TotalSegmentator training data
are absent. Their labels, rights, patient grouping and geometry must pass this manifest
contract after authorized acquisition; code/repository files alone are not datasets.
