# Spatial completion API and coordinate contract

This extends the original [native imaging contract](imaging.md). The new code uses the already-installed SimpleITK, SciPy, nibabel, NumPy, Pillow and existing application/auth/storage stack. No new package, data download or external patient-data transfer is required.

## Explicit frame selection

`GET /uploads/{id}/spatial/metadata?frame_kind=channel|time&frame_index=N&view_space=source|anatomical`

Omitting selectors on a four-dimensional NIfTI returns `status=REFUSED`, `refusal.code=FRAME_SELECTION_REQUIRED` and `frame_selection={required:true,axis:3,count,index,kind,header_temporal_units,...}`. Both interpretation and index must be explicitly chosen. Channel/time identity is user-declared; the software does not infer DWI, ADC or a clinical timepoint from intensities. Missing, negative, out-of-range or unexpected selectors refuse. Higher-dimensional and unsupported fourth-axis container formats remain explicitly unsupported; they are never flattened.

Three-dimensional sources require no selector. `original_dimensions` retains the uploaded shape, and `native_geometry` retains the selected frame's original spatial grid. Frame viewing does not create or rerun a model. A stored multichannel spatial mask is identified as the existing full-source run's mask, not an independent channel-specific prediction. Timepoint overlays require a recorded run-to-timepoint binding and are otherwise refused.

## Physically mapped source and anatomical planes

`view_space=source` preserves original voxel-index planes. `view_space=anatomical` constructs an axis-aligned RAS-mm grid from the exact coded source affine, converted from LPS when applicable. Known source units and invertible source geometry are mandatory. Unknown units, fallback uncoded transforms and unsuitable source grids receive explicit refusals rather than invented physical coordinates.

New metadata fields:

- `view_space`, `available_view_spaces`.
- `native_geometry` containing the original selected frame's dimensions, spacing, affine and frame.
- `view_to_native_voxel` and `native_to_view_voxel`, inverse homogeneous matrices.
- Anatomical display dimensions/spacing/affine in the existing top-level grid fields. The source identity/hash never changes.

The anatomical target includes the source field of view. Its spacing increases as necessary to bound the grid to 1024 voxels per axis and 32 million target voxels; this is display resampling, not increased native resolution. The service samples only the requested two-dimensional plane. Empty parts of an oblique bounding grid remain explicitly outside the source and render black. `valid_source_fraction` accompanies every rendered plane.

`GET /uploads/{id}/spatial/render` accepts the same selectors plus `axis`, `index`, `center`, `width`, `layer=image|prediction|reviewer`, and `run_id` for a mask. It returns PNG plus `X-MedTwin-Render` describing frame selection, source/view mapping and interpolation. Intensities use linear interpolation; categorical masks and reviewer annotations use nearest-neighbour sampling. A mask must match the same upload, native grid and source hash; it cannot be borrowed from another source/run. Stored predictions and original bytes are not overwritten.

`POST /cases/{id}/spatial/series-metadata?view_space=...` accepts the existing DICOM upload/series/phase selection body. `POST /cases/{id}/spatial/series-render` accepts that selection plus axis/index/window/view-space. Both reuse canonical ordering/assembly; source DICOM planes preserve their existing nonflipped slice direction, whereas anatomical planes use the explicit RAS target mapping.

The viewer reports continuous native voxel coordinates separately from anatomical display voxels. Crosshairs, physical positions and real source planes remain synchronized. The 3D source box follows the original affine, including oblique/LPS sources. Brush/eraser/polygon/undo editing remains anchored to original native axial voxels; the anatomical view displays remapped masks and directs the reviewer back to native planes to edit.

## Bounded source-to-source rigid candidates

`POST /cases/{id}/spatial/registration`

```json
{
  "fixed": {"upload_id": 18},
  "moving": {"upload_id": 19},
  "same_subject_attested": true,
  "same_anatomical_region_attested": true,
  "metric": "mean_squares",
  "landmarks": [
    {"fixed_ras_mm": [1, 2, 3], "moving_ras_mm": [2, 2, 3]},
    {"fixed_ras_mm": [5, 7, 3], "moving_ras_mm": [6, 7, 3]},
    {"fixed_ras_mm": [2, 3, 9], "moving_ras_mm": [3, 3, 9]}
  ],
  "landmark_source": "REVIEWER_SUPPLIED_UNVERIFIED"
}
```

Each source may also specify explicit `frame_index` and `frame_kind`. Both must be current, associated imaging evidence in this authorized case. Case membership alone does not establish subject/anatomical correspondence; both attestations are required. Known-unit coded physical geometry, orthogonal directions, finite nonconstant intensities and at most 32 million voxels per source are required. Registration uses native physical coordinates, bounded grids up to 96 per axis, two ITK threads/work units, a seeded similarity sampler, at most 120 optimizer iterations per level and an optimization runtime budget. One registration runs per API process; another receives `REGISTRATION_RESOURCE_BUSY`.

The response has `status=CANDIDATE_UNVALIDATED`, both `fixed_to_moving_ras_mm` and `moving_to_fixed_ras_mm`, source IDs/hashes/selectors, actual optimizer status/timing and optional held-out landmark TRE. SimpleITK's optimizer transform maps fixed output physical points to moving source points; its inverse is explicitly supplied. Similarity is evaluated on the same full bounded grids before/after optimization and is not substituted for TRE.

Landmarks are optional or a set of 3–100 finite, noncollinear paired RAS-mm locations inside the corresponding sources. They are evaluated after intensity-based optimization and never initialize or fit the transform. Landmark-source labels are provenance declarations, not automatic expert verification. The response always states `independent_clinical_validation=false`, `atlas_registration=false`, `clinical_activation=false`. Candidates are audited but not applied to original data, model outputs or atlas activation. Changing UI inputs invalidates the previous candidate.

The native metadata's patient-to-atlas status remains unavailable after this source-to-source computation. Independent expert localization, external patient-to-atlas validation and clinical acceptance still require their own evidence and cannot be obtained by installing a repository.

Official algorithm/direction references: [SimpleITK registration overview](https://simpleitk.readthedocs.io/en/master/registrationOverview.html), [ITK/SimpleITK registration errors and held-out target error](https://insightsoftwareconsortium.github.io/SimpleITK-Notebooks/Python_html/68_Registration_Errors.html).
