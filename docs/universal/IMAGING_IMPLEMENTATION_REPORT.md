# Native imaging implementation evidence

Historical first-pass report. The later completion work and current remaining limits are recorded in [IMAGING_COMPLETION_REPORT.md](IMAGING_COMPLETION_REPORT.md) and [the completion contract](contracts/imaging-completion.md).

2026-11-13. Additive imaging work covers the native spatial portions of supplied Universal requirements U-003, U-004 and U-017. Source requirements are distinguished from verified functionality in the contract.

Implemented: authenticated source geometry metadata; native NIfTI/ITK and validated multi-file DICOM contracts; synchronized three index-plane views and real source-plane 3D view; crosshairs, voxel/source-world coordinates when available, affine-derived laterality labels, scrolling, sliders, shared explicit windowing, zoom and reset; original stored mask display, actual mask-derived surfaces and separately persisted/restored reviewer correction layers. Raster and 4D inputs are explicitly refused for native 3D. Existing source readers and review paths are reused.

Verification:

- `python -m pytest backend/tests/test_universal_geometry.py backend/tests/test_dicom_series.py -q`: 29 passed (17 new geometry/API tests plus 12 existing DICOM tests). Tests include rotated/reflected anisotropic affine/inverse round trips, LPS/RAS laterality, NIfTI units, uncoded/unknown transforms, malformed/singular geometry, ITK origin/direction, actual labelled voxel PNG mapping in all three views, upload authorization/withdrawal, DICOM source ordering and supersession.
- `node --test scripts/universal-geometry.test.mjs`: 3 passed. Includes exact display/voxel inverses for both renderers and laterality/reflection checks.
- Typecheck and production/check builds pass. Owned frontend files have no lint errors; advisory React state-in-effect warnings remain for clearing asynchronous source/case resource state.
- `python scripts/qa_universal_imaging.py`: actual public ACDC `database/testing/patient101/patient101_frame01.nii` uploaded through the canonical isolated QA API, case 6, upload 11, dimensions 232 × 256 × 10. All three actual source PNGs returned successfully. Source SHA-256 and render hashes/metadata are in `artifacts/universal-2026-11-13/imaging-native-proof/proof.json` with the PNGs.
- `node tools/browser-qa/universal-imaging.mjs`: 11 actual browser checks passed on case 6/upload 11, including the real stored run's surface panel, unknown physical scale warning, shared source voxel, crosshairs, auto-window reset and three PNG planes. No uncaught page/server errors or horizontal overflow at 1500px. Screenshot and machine-readable results: `artifacts/universal-2026-11-13/imaging-browser/`.

The sample header has unknown spatial units (`qform_code=0`, `sform_code=2`). It therefore proves source-grid display and refusal of millimetre patient coordinates; it does not prove native patient-world localization. Uncoded qform/sform fallback refusal is separately covered by synthetic tests. Root independently executed actual ACDC inference (run 11) and owns those inference/model claims and artifacts. Geometry tests use synthetic independently labelled voxel coordinates to test the coordinate pipeline; they are not clinical data or diagnostic evaluations.

Pending capabilities remain explicit: anatomical-plane resampling, verified patient-to-atlas registration, multi-channel/time selection, DICOM-series segmentation correction UI and longitudinal registered overlays. Existing canonical DICOM-series inference remains available separately. No source datasets, original model weights or registry entries were modified by this imaging track. No research model improvement or clinical deployment success is claimed.
