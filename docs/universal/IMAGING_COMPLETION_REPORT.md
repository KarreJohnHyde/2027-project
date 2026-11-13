# Spatial completion evidence — 13 November 2026

The previously partial native imaging engineering is implemented: explicit four-dimensional NIfTI channel/time selection, physically checked anatomical-plane resampling, native/view coordinate inverses, correctly remapped categorical masks, and bounded source-to-source rigid registration with optional held-out landmark TRE. These changes are additive and preserve original sources, predictions, datasets, checkpoints and prior artifacts.

The current interface contract is [imaging-completion.md](contracts/imaging-completion.md). No paid dependency, new dependency, GitHub/Kaggle code execution, patient-data transfer or third-party benchmark download was necessary. Existing SimpleITK/NumPy/SciPy/nibabel/Pillow supply the engineering primitives. The registration benchmark's original Gaussian phantoms and known physical transforms introduce no third-party data-use restriction. Existing public brain data are used only for authorized research viewer QA; this is not a new commercial-data clearance or a new model inference claim.

## Executed evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Targeted source geometry, selection, resampling, registration, isolation and DICOM tests | 41 passed in 8.73 s | `backend/tests/test_universal_geometry.py`, `test_spatial_completion.py`, `test_spatial_registration.py`, `test_dicom_series.py` |
| Three original anisotropic/rigid/oblique known-transform controls | Mean held-out TRE below 0.02 mm in all three; engineering thresholds 1 mm mean / 2 mm max | `artifacts/completion-2026-11-13/imaging/registration-benchmark-final.json` |
| Actual public brain source case 7/upload 12 | Explicit channels 0/1: six real native PNGs; distinct channel pixels; anatomical RAS rendering available; existing run 12 mask reused without inference | `artifacts/completion-2026-11-13/imaging/qa-proof.json` and PNGs |
| Actual canonical API rigid candidate | Original synthetic case 10, uploads 18/19, mean held-out TRE about 0.00667 mm; remains unvalidated/no activation | Same `qa-proof.json` |
| Actual browser UI | 15 checks passed, no uncaught page or backend-500 errors; 390 px document width fits viewport | `artifacts/completion-2026-11-13/imaging/browser/proof.json` and screenshots |

Tests independently encode synthetic world-coordinate linear fields and labelled native voxels to verify oblique/reflected affine resampling, inverse transforms and nearest-neighbour categorical remapping. They test explicit missing/out-of-range frame refusals, source/run/hash binding, native editing restrictions, cross-case access denial, unknown units, shear/constant-source/landmark/runtime refusals and preservation of unavailable atlas activation after a source-to-source candidate.

Browser evidence verifies that selecting the two actual brain channels yields different PNG hashes, original run masks appear on all three native/anatomical planes, native coordinates remain visible, anatomical edits are blocked in favour of native axial editing, registration requires source correspondence attestations, both transform directions/source identities/TRE are inspectable, and changing controls invalidates the candidate. The stored brain mask remains the output of its original full multichannel research run. It is not an independent channel-specific evaluation.

Reproduce with the repository virtual environment:

```text
python -m pytest backend/tests/test_universal_geometry.py backend/tests/test_spatial_completion.py backend/tests/test_spatial_registration.py backend/tests/test_dicom_series.py -q
python scripts/benchmark_spatial_registration.py --output artifacts/completion-2026-11-13/imaging/registration-benchmark-final.json
python scripts/qa_spatial_completion.py
node tools/browser-qa/spatial-completion.mjs
```

QA scripts use the existing isolated stack and read local credentials without exporting them. They do not start services or rerun inference. The API script creates/reuses only its named synthetic QA case; candidate computation writes an audit event, not an accepted transform. The browser script uses existing uploads and computes another unapproved synthetic candidate.

## Honest limits

Synthetic submillimetre TRE demonstrates known-transform engineering, not clinical registration accuracy. No independently annotated clinical landmark corpus, expert agreement, external patient-to-atlas registration or clinical acceptance was fabricated. Those requirements remain unavailable until appropriately cleared data and independent expert review exist. No atlas/disease localization or L2/L3 clinical activation is enabled by these changes.

Timepoint viewing is implemented, but an old run without explicit timepoint provenance cannot be displayed as a time-specific prediction. Higher-than-four-dimensional inputs and unsupported four-dimensional containers refuse rather than flatten. Native DICOM cine phases continue to require canonical series/phase selection. Source headers with unknown physical units remain viewable only in their source grid.

The initial loaded-environment registration test hit its runtime budget because limiting ITK thread count alone did not cap internal work units. The implementation now caps both at two; the five registration tests reran in 2.61 s without relaxing the runtime budget. The failed attempt and initial benchmark artifacts are preserved under the same artifact directory.
