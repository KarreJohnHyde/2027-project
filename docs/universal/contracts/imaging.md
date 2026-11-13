# Native spatial evidence contract

The later [spatial completion contract](imaging-completion.md) extends this initial contract with explicit fourth-axis selection, anatomical resampling and unapproved source-to-source registration. Statements below describing those features as pending are preserved as first-pass history.

`UniversalImagingWorkbench` default export accepts `{ caseId: number | null, uploadId?: number | null, onSelectUpload?: (id: number) => void }`. Root owns mounting. Existing authorization, case association, encrypted upload materialization, native readers, DICOM assembly, research runs, mask correction storage and mask-derived surfaces are reused.

## Metadata API

- `GET /api/v1/uploads/{id}/spatial/metadata` authorizes the upload's case and requires a current, associated imaging upload. Its schema is `medtwin.spatial.v1`.
- `POST /api/v1/cases/{id}/spatial/series-metadata` accepts canonical `{ upload_ids: number[], series_reference?: string|null, phase?: number|null }`. Each upload must belong to this case and be current and associated. Canonical DICOM assembly is reused; the report contains no volume array or identifying tag values.

Successful responses carry `status: AVAILABLE`, `source` identity with SHA-256 (individual hashes for DICOM), `dimensions_xyz`, `spacing_xyz_mm` or null, `affine_voxel_to_world` or null, `coordinate_frame: RAS_MM | LPS_MM | null`, `world_available`, `world_refusal`, `affine_voxel_to_display`, `display_frame`, `geometry_provenance`, `non_axial_vertical_flip`, `plane_definition`, `plane_mapping`, `capabilities`, `warnings`, `registration` and `render_input`.

`render_input` for a native source is `{kind: UPLOAD, upload_id, path: /uploads/{id}/imaging/render}`. For DICOM it is `{kind: DICOM_SERIES, path: /cases/{id}/dicom-series/render, body: {upload_ids,series_reference,phase}}`. The viewer requests PNGs from those existing authenticated endpoints. No raw volume is returned to JavaScript. Its requests are debounced, aborted when stale, serialized to avoid multiplying native decode allocations, and blob/GPU resources are released.

Refused spatial capabilities return `status: REFUSED` and `{refusal:{code,reason}}`, without fabricated geometry. Raster/photographed film, single-slice DICOM, 4D/channel volumes, degenerate axes, unreadable/singular/nonfinite geometry and oversized geometry have explicit refusal behavior. Current viewer bounds are 2–4096 voxels per axis and at most 134,217,728 voxels, in addition to canonical readers' allocation bounds. General source preview and inference eligibility are separate capabilities.

## Coordinate proof and limits

The three views are **voxel-index MPR**, not patient-anatomical resampling. All views share `(i,j,k)`. Native reader PNGs flip the vertical direction for coronal/sagittal planes; canonical DICOM series PNGs do not. `non_axial_vertical_flip` makes this distinction explicit. The frontend mapping and tests preserve it. Physical aspect ratios use affine column lengths when a world transform is available and source-grid spacing ratios otherwise. Crosshair clicks are inverted through the actual SVG screen transform, including zoom.

NIfTI uses its selected affine in RAS coordinates only with positive qform/sform coding and known spatial units. Metres/microns are converted to millimetres, including translation. Zero qform/sform codes retain only a spacing-based source grid. Unknown units never acquire an mm label. NRRD/MetaImage use ITK direction × spacing plus origin in LPS; DICOM series use the canonical column/row/slice-to-LPS affine. Matrix validation rejects singular and ill-conditioned transforms. Source headers do not constitute independently verified patient registration.

The 3D panel renders the actual three PNG planes at their affine source positions, the source bounds and the selected voxel. It does not invent a tissue or lesion surface. Stored native-volume masks may be shown only for the same upload and matching grid, with matching verified physical spacing when available. Actual mask-derived surfaces reuse `VolumeSurfaceView` in its separately labelled voxel-grid frame. When source units are unknown, an adjacent warning explicitly limits the legacy panel's mm convention. Original predictions, saved orange reviewer masks and publisher/expert ground truth remain separate.

Saved native axial corrections reuse `/research-inference/{run}/volume-slice-corrections` and `/uploads/{id}/reference-annotations`; latest per-slice/per-structure annotation IDs are restored as an optional orange overlay after reload. Editing starts from the original model mask, as the existing editor states. Brush, eraser, polygon and undo reuse the existing editor. Saving does not alter model output or trigger training.

`registration.status` remains `REGISTRATION_UNAVAILABLE`, `atlas_transform` is null and `atlas_overlay` is false. No L2/L3 patient-to-atlas registration, clinical accuracy improvement, 4D channel selector or resampled anatomical-plane MPR is claimed.
