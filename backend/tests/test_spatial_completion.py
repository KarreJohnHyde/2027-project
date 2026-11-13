"""Explicit frame selection and independent coordinate/label-resampling checks.

All generated images and known transforms are synthetic engineering controls.
"""
import io
import json

import nibabel as nib
import numpy as np
import pytest
from PIL import Image

from app.models.entities import Case, EvidenceStatus, Finding, InferenceRun, ModalityType
from app.services.reference_annotations import encode
from app.services.universal_geometry import GeometryRefusal, transform_point
from app.services.universal_spatial_io import read_selected_volume, sample_plane, source_metadata, view_contract
from tests.conftest import get_auth_headers
from tests.test_universal_geometry import SOURCE, _upload, spatial_client  # noqa: F401


def _nifti(path, array, affine=None, *, units="mm"):
    image = nib.Nifti1Image(array.astype(np.float32), np.eye(4) if affine is None else affine)
    if units:
        image.header.set_xyzt_units(units)
    nib.save(image, path)
    return path


def test_fourth_axis_never_selects_or_interprets_itself(tmp_path):
    data = np.stack([np.indices((7, 9, 5))[0], 1000 + np.indices((7, 9, 5))[1]], axis=3)
    path = _nifti(tmp_path / "channels.nii.gz", data)
    for index, kind in [(None, None), (0, None), (None, "channel"), (0, "automatic")]:
        metadata = source_metadata(path, index, kind)
        contract = view_contract(metadata, SOURCE)
        assert contract["refusal"]["code"] == "FRAME_SELECTION_REQUIRED"
        with pytest.raises(GeometryRefusal):
            read_selected_volume(path, metadata)
    selected = source_metadata(path, 1, "channel")
    assert selected["dimensions"] == [7, 9, 5] and selected["original_dimensions"] == [7, 9, 5, 2]
    assert np.array_equal(read_selected_volume(path, selected), data[..., 1])
    assert source_metadata(path, 2, "channel")["selection_refusal"]["code"] == "FRAME_OUT_OF_RANGE"
    assert source_metadata(path, -1, "time")["selection_refusal"]["code"] == "FRAME_OUT_OF_RANGE"
    simple = _nifti(tmp_path / "simple.nii.gz", data[..., 0])
    assert source_metadata(simple, 0, "channel")["selection_refusal"]["code"] == "UNEXPECTED_FRAME_SELECTION"


def test_oblique_physical_resampling_matches_independent_world_linear_field(tmp_path):
    angle = .4; c, s = np.cos(angle), np.sin(angle)
    affine = np.array([[c, -s, 0, -18], [s, c, 0, 23], [0, 0, -1, 48], [0, 0, 0, 1.]]) @ np.diag([1.2, 1.8, 2.1, 1])
    shape = (15, 17, 9)
    indices = np.indices(shape).reshape(3, -1)
    world = affine[:3, :3] @ indices + affine[:3, 3, None]
    values = (world[0] + 2*world[1] + 3*world[2]).reshape(shape).astype(np.float32)
    path = _nifti(tmp_path / "oblique.nii.gz", values, affine)
    metadata = source_metadata(path)
    contract = view_contract(metadata, SOURCE, "anatomical")
    assert contract["status"] == "AVAILABLE" and contract["coordinate_frame"] == "RAS_MM"
    assert np.allclose(np.asarray(contract["native_to_view_voxel"]) @ contract["view_to_native_voxel"], np.eye(4))
    assert contract["native_geometry"]["dimensions_xyz"] == list(shape)
    dims = contract["dimensions_xyz"]
    for axis, fixed in [("axial", 2), ("coronal", 1), ("sagittal", 0)]:
        selected = dims[fixed]//2
        plane, info = sample_plane(values, contract, axis, selected)
        height, width = plane.shape
        for row, column in [(r, col) for r in range(height) for col in range(width) if np.isfinite(plane[r, col])][::max(1, width//3)]:
            voxel = {"axial": [column, row, selected], "coronal": [column, selected, dims[2]-1-row], "sagittal": [selected, column, dims[2]-1-row]}[axis]
            physical = transform_point(contract["affine_voxel_to_world"], voxel)
            expected = physical[0] + 2*physical[1] + 3*physical[2]
            assert plane[row, column] == pytest.approx(expected, abs=3e-5)
        assert 0 < info["valid_source_fraction"] <= 1


def test_categorical_resampling_never_interpolates_class_ids(tmp_path):
    c, s = np.cos(.25), np.sin(.25)
    affine = np.array([[c, -s, 0, 10], [s, c, 0, -20], [0, 0, 2, 5], [0, 0, 0, 1]])
    labels = np.where(np.indices((12, 14, 8))[0] < 6, 1, 2).astype(np.uint8)
    path = _nifti(tmp_path / "labels.nii.gz", labels, affine)
    contract = view_contract(source_metadata(path), SOURCE, "anatomical")
    index = contract["dimensions_xyz"][2]//2
    plane, info = sample_plane(labels, contract, "axial", index, categorical=True)
    assert set(np.unique(plane)) <= {0, 1, 2} and info["interpolation"] == "NEAREST_NEIGHBOUR"
    transform = np.asarray(contract["view_to_native_voxel"])
    for row, column in np.ndindex(plane.shape):
        point = (transform @ [column, row, index, 1])[:3]
        if (point >= 0).all() and (point <= np.asarray(labels.shape)-1).all():
            expected = labels[tuple(np.floor(point + .5).astype(int))]
        else:
            expected = 0
        assert plane[row, column] == expected


def test_anatomical_resampling_refuses_unknown_units_and_uncoded_source(tmp_path):
    path = _nifti(tmp_path / "unknown.nii.gz", np.ones((5, 6, 7)), units=None)
    result = view_contract(source_metadata(path), SOURCE, "anatomical")
    assert result["status"] == "REFUSED" and result["refusal"]["code"] == "PATIENT_WORLD_UNAVAILABLE"
    assert result["native_geometry"]["dimensions_xyz"] == [5, 6, 7]
    path = tmp_path / "uncoded.nii.gz"
    image = nib.Nifti1Image(np.ones((5, 6, 7)), None); image.header.set_xyzt_units("mm"); nib.save(image, path)
    result = view_contract(source_metadata(path), SOURCE, "anatomical")
    assert result["refusal"]["code"] == "PATIENT_WORLD_UNAVAILABLE"


def test_selected_frame_api_metadata_render_and_refusal(spatial_client, db_session, test_users, tmp_path):
    data = np.stack([np.indices((7, 9, 5))[0], 1000 + np.indices((7, 9, 5))[1]], axis=3)
    record = _upload(db_session, test_users["clinician_a"], _nifti(tmp_path / "channels.nii.gz", data))
    headers = get_auth_headers(test_users["clinician_a"]); route = f"/api/v1/uploads/{record.id}/spatial"
    result = spatial_client.get(route + "/metadata", headers=headers)
    assert result.json()["refusal"]["code"] == "FRAME_SELECTION_REQUIRED"
    assert spatial_client.get(route + "/render", headers=headers).status_code == 422
    means = []
    for frame in (0, 1):
        query = f"frame_index={frame}&frame_kind=channel"
        metadata = spatial_client.get(route + "/metadata?" + query, headers=headers).json()
        assert metadata["status"] == "AVAILABLE" and metadata["frame_selection"]["index"] == frame
        result = spatial_client.get(route + f"/render?{query}&axis=axial&index=2&center=500&width=2000", headers=headers)
        assert result.status_code == 200, result.text
        means.append(np.asarray(Image.open(io.BytesIO(result.content))).mean())
        assert json.loads(result.headers["X-MedTwin-Render"])["frame_selection"]["index"] == frame
    assert means[1]-means[0] > 100
    assert spatial_client.get(route + "/render?frame_index=2&frame_kind=channel", headers=headers).status_code == 422


def test_prediction_mask_is_remapped_from_native_grid_and_bound_to_source(spatial_client, db_session, test_users, tmp_path):
    values = np.indices((7, 9, 5)).sum(axis=0)
    record = _upload(db_session, test_users["clinician_a"], _nifti(tmp_path / "frame.nii.gz", values))
    run = InferenceRun(case_id=record.case_id, file_id=record.id, modality=ModalityType.IMAGE, model_name="synthetic-control", model_version="1", preprocessing_version="test", status=EvidenceStatus.COMPLETED)
    db_session.add(run); db_session.flush()
    mask = np.zeros((9, 7), dtype=bool); mask[2:4, 4:6] = True
    output = {"type": "volume_segmentation", "volume_shape_ijk": [7, 9, 5], "structures": [{"class_index": 1, "structure": "synthetic_label", "voxels": 4}], "slices": [{"slice_index": 2, "segments": [{"class_index": 1, "rle": encode(mask)}]}]}
    finding = Finding(case_id=record.case_id, inference_run_id=run.id, modality=ModalityType.IMAGE, category="Synthetic control", label="synthetic", mapping_status="L1", evidence_provenance={"output": output, "source_file_sha256": record.file_hash})
    db_session.add(finding); db_session.commit()
    headers = get_auth_headers(test_users["clinician_a"])
    route = f"/api/v1/uploads/{record.id}/spatial/render?layer=prediction&run_id={run.id}&axis=axial&index=2&view_space=anatomical"
    result = spatial_client.get(route, headers=headers)
    assert result.status_code == 200, result.text
    rgba = np.asarray(Image.open(io.BytesIO(result.content)))
    assert np.array_equal(rgba[:, :, 3] > 0, mask)
    assert json.loads(result.headers["X-MedTwin-Render"])["interpolation"] == "NEAREST_NEIGHBOUR"
    finding.evidence_provenance = {"output": output, "source_file_sha256": "wrong"}; db_session.commit()
    assert spatial_client.get(route, headers=headers).status_code == 409
    assert output["slices"][0]["segments"][0]["rle"] == encode(mask)


@pytest.mark.private_workspace
def test_registration_refuses_foreign_sources_unknown_physical_units_and_missing_attestation(spatial_client, db_session, test_users, tmp_path):
    owner = test_users["clinician_a"]
    record = _upload(db_session, owner, _nifti(tmp_path / "known.nii.gz", np.indices((5, 6, 7)).sum(axis=0)))
    same_case = db_session.get(Case, record.case_id)
    second = _upload(db_session, owner, _nifti(tmp_path / "unknown.nii.gz", np.indices((5, 6, 7)).sum(axis=0), units=None), case=same_case)
    headers = get_auth_headers(owner); route = f"/api/v1/cases/{record.case_id}/spatial/registration"
    request = {"fixed": {"upload_id": record.id}, "moving": {"upload_id": second.id}}
    result = spatial_client.post(route, json=request, headers=headers)
    assert result.status_code == 422 and result.json()["detail"]["code"] == "SOURCE_CORRESPONDENCE_ATTESTATION_REQUIRED"
    request.update(same_subject_attested=True, same_anatomical_region_attested=True)
    result = spatial_client.post(route, json=request, headers=headers)
    assert result.status_code == 422 and result.json()["detail"]["code"] == "PATIENT_WORLD_UNAVAILABLE"
    result = spatial_client.post(route, json=request, headers=get_auth_headers(test_users["clinician_b"]))
    assert result.status_code in (403, 404)
