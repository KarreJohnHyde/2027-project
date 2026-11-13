# Matched temporal image comparison

This is a working source-to-source research comparison, not an automatic disease-progression assessment. It reuses the canonical authenticated upload reader, coded source geometry and bounded SimpleITK rigid registration. No inference model is run or activated.

`POST /api/v1/cases/{case_id}/temporal-comparisons` accepts:

```json
{
  "previous": {"upload_id": 18, "sha256": "64-lowercase-hex-characters"},
  "current": {"upload_id": 19, "sha256": "64-lowercase-hex-characters"},
  "previous_region": "synthetic phantom",
  "current_region": "synthetic phantom",
  "same_subject_attested": true,
  "same_region_attested": true,
  "comparable_intensity_attested": false,
  "alignment": "compute_rigid"
}
```

Each source additionally supports explicit `frame_kind=channel|time` and zero-based `frame_index`. Missing fourth-axis selection refuses. Identical content/frame pairs cannot establish temporal change. Different channels of one source cannot be disguised as separate timepoints. Selected channels of different studies must have matching selector semantics. Previous/current order and anatomy are explicitly declared; upload creation time is not presented as a scan date.

Sources must be current, associated imaging uploads in this authorized case. Each supplied hash must match the upload record and SHA-256 recomputed from the actual materialized bytes. Coded transforms, known physical units, valid geometry and bounded native volumes are mandatory. Missing units, unknown geometry, withdrawn/superseded evidence, hash changes, cross-case sources and mismatching declared regions receive typed refusals.

Alignment choices:

- `compute_rigid` reuses the existing bounded registration optimizer. Its transform remains `CANDIDATE_UNVALIDATED`.
- `shared_physical_space` requires the additional `shared_physical_space_attested=true`. Valid coded affines alone do not establish anatomical alignment.
- `provided_rigid` requires `provided_rigid.previous/current` to bind the exact source IDs, hashes and frame selectors, plus `previous_to_current_ras_mm`. The server validates a finite homogeneous proper rigid matrix: no scaling, shear or reflection, and bounded translation. It accepts no client-supplied quality or clinical-verification fields. This remains an unverified supplied candidate.

The response includes an opaque comparison ID, ten-minute expiry, both RAS-mm transform directions, source/hash/frame provenance, anatomical reference-grid geometry, actual intensity compatibility evidence, resource bounds and explicit false clinical/atlas/progression claims. The in-memory session stores small metadata/transforms only, is scoped to the current user and case, expires after 600 seconds, and is capped at 32 live sessions. A server restart invalidates sessions. Rendering independently reauthorizes and rehashes both sources; expiry or source changes require recreation.

`POST /cases/{case_id}/temporal-comparisons/{comparison_id}/render` accepts `axis`, `index`, `mode=previous|current|blend|checkerboard|difference`, optional shared `center`/`width`, blend opacity and optional positive `difference_scale`. It returns PNG and `X-MedTwin-Comparison` metadata. The current source is sampled through the previous-to-current physical transform onto the previous source's anatomical grid. Both views share one pooled valid-overlap window, or one explicitly requested window. No input image is overwritten. The browser displays synchronized previous/current and blend/checkerboard/difference planes, slice controls and overlap statistics.

Raw numeric differences require both an attestation and compatible actual source metadata. An attestation alone cannot certify MRI/NIfTI intensity comparability. Unknown raw MRI units permit geometrical side-by-side/blend/checkerboard inspection but refuse numeric differences and numeric change statistics. Explicit original synthetic-control header metadata permit engineering tests in matched arbitrary units; they are not clinical calibration. CT-HU metadata have a compatibility branch, but ordinary single-slice DICOM remains outside the native-volume temporal workflow; no unsupported CT-volume claim is made.

Difference is current-minus-previous raw intensity only on finite shared source pixels. Red means greater raw intensity, blue means lower, and black means zero. Invalid/out-of-field-of-view areas are hatched and excluded from differences/statistics, never displayed as zero change. No-valid-overlap planes explicitly refuse. Native sources are bounded to 32 million voxels each and anatomical display planes to 1024×1024; plane requests are debounced and serialized in the UI, with aborted/stale responses and blob resources cleaned up.

`TemporalImageComparison` is a modular component embedded in `UniversalImagingWorkbench`. The latter additionally accepts optional `findingId`: omitted preserves standalone eligible-run selection; a number selects only the exact finding's run; explicit null yields plain source viewing. A selected source/finding never silently falls back to an unrelated prediction.

Evidence scripts and outputs are under `artifacts/expansion-2026-11-13/imaging`. Unit tests independently verify identity and a known physical translation/change, invalid overlap exclusion, transform restrictions, source binding, units, intensity refusal, session isolation and expiry. Synthetic engineering evidence is not independent clinical longitudinal validation, treatment-response validation or patient-to-atlas activation.

Executed verification on 13 November 2026:

- `python -m pytest backend/tests/test_temporal_comparison.py -q`: 9 passed in 2.33 seconds. CT compatibility specifically refuses missing, `US` and `OTHER` rescale units; explicit `RescaleType=HU` is required.
- `python scripts/qa_temporal_comparison.py`: canonical isolated QA case 14, uploads 31/32, five PNG modes verified. The original synthetic control's independently specified mean change was 0.21875 matched arbitrary units, and the actual API result was exactly 0.21875. Existing synthetic case 10's rigid/checkerboard comparison worked while unverified intensity metadata correctly disabled differences.
- `node tools/browser-qa/temporal-comparison.mjs`: 15 actual UI checks passed, including source/alignment attestations, synchronized images/planes, exact numeric-control difference, explicit anatomy mismatch, source hashes and stale-comparison invalidation. No uncaught page errors or backend 500 responses occurred. Automated axe-core WCAG A/AA runs at 1500 px and 390 px reported zero violations; automated checks do not constitute full manual conformance certification.
- The first axe pass found one inaccessible scrolling hash block. Adding keyboard focus and an accessible label fixed it; failed evidence is preserved as `browser/failed-axe-attempt.*` alongside the final `browser/proof.json` and screenshot.

No inference, data download, original checkpoint change, clinical progression claim or clinical activation occurred in this verification.
