"""Coordinate proof uses labelled synthetic voxels, not claims of diagnostic accuracy."""
import io
from datetime import datetime, timezone

import nibabel as nib
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.database import get_db
from app.models.entities import Case, ModalityType, UploadedFile
from app.routers import modalities, universal_imaging
from app.services.universal_geometry import GeometryRefusal, lps_to_ras, spatial_contract, transform_point, validate_affine
from tests.conftest import get_auth_headers


SOURCE = {"upload_id": 1, "case_id": 1, "sha256": "test", "kind": "UPLOAD"}


def _metadata(affine=None, **overrides):
    return {"container": "NIFTI", "dimensions": [7, 9, 5], "spacing_mm": [1, 2, 3],
            "affine": np.diag([1, 2, 3, 1]).tolist() if affine is None else affine,
            "qform_code": 1, "sform_code": 1, "spatial_units": "mm", **overrides}


@pytest.mark.parametrize("angle,reflection", [(0, 1), (.7, 1), (.9, -1)])
def test_unequal_spacing_oblique_reflected_affines_roundtrip(angle, reflection):
    c, s = np.cos(angle), np.sin(angle)
    affine = np.array([[c, -s, 0, 51], [s, c, 0, -12], [0, 0, reflection, 4], [0, 0, 0, 1.]]) @ np.diag([1.2, 2.4, 5.5, 1])
    point = [2.25, 4.5, .75]
    world = transform_point(affine, point)
    assert np.allclose(transform_point(affine, world, inverse=True), point, atol=1e-10)
    result = spatial_contract(_metadata(affine.tolist()), SOURCE)
    assert result["world_available"] and result["coordinate_frame"] == "RAS_MM"
    assert result["oblique_or_non_axis_aligned"] is (angle != 0)


def test_lps_ras_preserves_superior_and_reverses_left_anterior_axes():
    lps = np.array([[2, 0, 0, 40], [0, 3, 0, -20], [0, 0, 4, 8], [0, 0, 0, 1]])
    assert transform_point(lps_to_ras(lps), [1, 2, 3]) == [-42, 14, 20]
    assert np.allclose(lps_to_ras(lps_to_ras(lps)), lps)


@pytest.mark.parametrize("matrix,code", [([[0]*4]*4, "MALFORMED_GEOMETRY"), (np.diag([0, 1, 1, 1]).tolist(), "NONINVERTIBLE_GEOMETRY"), (np.diag([float("nan"), 1, 1, 1]).tolist(), "MALFORMED_GEOMETRY")])
def test_invalid_affine_has_typed_refusal(matrix, code):
    with pytest.raises(GeometryRefusal) as exc:
        validate_affine(matrix)
    assert exc.value.code == code
    assert spatial_contract(_metadata(matrix), SOURCE)["refusal"]["code"] == code


def test_uncoded_nifti_never_promotes_fallback_affine_to_patient_world():
    result = spatial_contract(_metadata(qform_code=0, sform_code=0), SOURCE)
    assert result["status"] == "AVAILABLE"
    assert result["affine_voxel_to_world"] is None and not result["world_available"]
    assert result["coordinate_frame"] is None and result["display_frame"] == "SOURCE_GRID_MM"
    assert result["registration"]["atlas_transform"] is None


def test_unknown_units_and_four_dimensions_are_explicit():
    unknown = spatial_contract(_metadata(spatial_units="unknown"), SOURCE)
    assert not unknown["world_available"] and unknown["spacing_xyz_mm"] is None
    assert unknown["display_frame"] == "SOURCE_GRID_UNSPECIFIED_UNITS"
    assert spatial_contract(_metadata(dimensions=[7, 9, 5, 2]), SOURCE)["refusal"]["code"] == "EXPLICIT_3D_VOLUME_REQUIRED"
    assert spatial_contract({"container": "PNG", "dimensions": [100, 50]}, SOURCE)["refusal"]["code"] == "NATIVE_VOLUME_REQUIRED"


def test_itk_direction_spacing_and_origin_form_lps_affine():
    result = spatial_contract({"container": "NRRD", "dimensions": [3, 4, 5], "spacing_mm": [.7, .8, 2.5], "origin_mm": [10, -20, 3], "direction": [0, -1, 0, 1, 0, 0, 0, 0, 1]}, SOURCE)
    assert result["coordinate_frame"] == "LPS_MM"
    assert np.allclose(transform_point(result["affine_voxel_to_world"], [2, 3, 4]), [7.6, -18.6, 13])


@pytest.mark.parametrize("units,scale", [("mm", 1), ("meter", 1000), ("micron", .001)])
def test_nifti_spatial_unit_conversion_includes_translation(units, scale):
    affine = np.diag([1., 2., 3., 1.]); affine[:3, 3] = [10, 20, 30]
    result = spatial_contract(_metadata(affine.tolist(), spatial_units=units), SOURCE)
    assert np.allclose(transform_point(result["affine_voxel_to_world"], [1, 1, 1]), np.array([11, 22, 33]) * scale)


def test_dicom_renderer_mapping_is_distinct_from_native_flip():
    report = {"status": "ASSEMBLED", "shape_slices_rows_columns": [5, 9, 7], "affine_lps_mm": np.diag([1, 2, 3, 1]).tolist()}
    result = spatial_contract(report, SOURCE, series=True)
    assert result["dimensions_xyz"] == [7, 9, 5]
    assert result["coordinate_frame"] == "LPS_MM" and not result["non_axial_vertical_flip"]
    assert result["plane_mapping"]["coronal"] == "(u,j,v)"
    assert spatial_contract({"status": "REJECTED"}, SOURCE, series=True)["refusal"]["code"] == "DICOM_SERIES_NOT_ASSEMBLED"


@pytest.fixture
def spatial_client(db_session):
    application = FastAPI()
    application.include_router(universal_imaging.router, prefix="/api/v1")
    application.include_router(modalities.router, prefix="/api/v1")
    application.dependency_overrides[get_db] = lambda: db_session
    with TestClient(application) as client:
        yield client


def _upload(db, owner, path, case=None, **overrides):
    if case is None:
        case = Case(pseudonymous_id="SYNTHETIC-COORDINATE-PROOF", created_by_id=owner.id)
        db.add(case); db.flush()
    record = UploadedFile(case_id=case.id, filename=path.name, stored_filename=path.name, file_path=str(path), file_hash="a"*64, file_size_bytes=path.stat().st_size, mime_type="application/octet-stream", modality=ModalityType.IMAGE, is_associated=True, **overrides)
    db.add(record); db.commit()
    return record


def test_authenticated_native_metadata_and_all_three_rendered_index_mappings(spatial_client, db_session, test_users, tmp_path):
    # Label each voxel with its coordinate: display flips cannot pass accidentally on a constant image.
    x, y, z = np.indices((7, 9, 5)); values = (x + 10*y + 100*z).astype(np.float32)
    path = tmp_path / "proof.nii.gz"
    image = nib.Nifti1Image(values, np.diag([1., 2., 3., 1.])); image.header.set_xyzt_units("mm"); nib.save(image, path)
    record = _upload(db_session, test_users["clinician_a"], path)
    headers = get_auth_headers(test_users["clinician_a"])
    endpoint = f"/api/v1/uploads/{record.id}"
    assert spatial_client.get(endpoint + "/spatial/metadata").status_code == 401
    result = spatial_client.get(endpoint + "/spatial/metadata", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["world_available"] and result.json()["dimensions_xyz"] == [7, 9, 5]
    for axis, index, expected in [("axial", 2, values[:, :, 2].T), ("coronal", 3, np.flipud(values[:, 3, :].T)), ("sagittal", 4, np.flipud(values[4, :, :].T))]:
        rendered = spatial_client.get(endpoint + f"/imaging/render?axis={axis}&index={index}&center=250&width=500", headers=headers)
        assert rendered.status_code == 200, rendered.text
        actual = np.asarray(Image.open(io.BytesIO(rendered.content)))
        expected8 = (np.clip(expected / 500, 0, 1)*255).astype(np.uint8)
        assert np.max(np.abs(actual.astype(int) - expected8.astype(int))) <= 1
    record.withdrawn_at = datetime.now(timezone.utc); db_session.commit()
    assert spatial_client.get(endpoint + "/spatial/metadata", headers=headers).status_code == 409


@pytest.mark.private_workspace
def test_spatial_metadata_denies_cross_case_user(spatial_client, db_session, test_users, tmp_path):
    path = tmp_path / "proof.nii.gz"; image = nib.Nifti1Image(np.zeros((2, 3, 4)), np.eye(4)); nib.save(image, path)
    record = _upload(db_session, test_users["clinician_a"], path)
    result = spatial_client.get(f"/api/v1/uploads/{record.id}/spatial/metadata", headers=get_auth_headers(test_users["clinician_b"]))
    assert result.status_code in (403, 404)


def test_dicom_series_spatial_route_uses_canonical_order_and_current_upload_boundary(spatial_client, db_session, test_users, tmp_path):
    from pydicom.uid import generate_uid
    from tests.test_dicom_series import _slice
    owner = test_users["clinician_a"]
    case = Case(pseudonymous_id="SPATIAL-DICOM-PROOF", created_by_id=owner.id)
    db_session.add(case); db_session.commit()
    series = generate_uid(); records = []
    for number, position in enumerate([5., 0., 2.5]):
        path = tmp_path / f"source-{number}.dcm"
        _slice(series, position, number, value=1000 + number*100, patient_name="Synthetic^NotReturned").save_as(path, enforce_file_format=True)
        records.append(_upload(db_session, owner, path, case=case))
    headers = get_auth_headers(owner)
    route = f"/api/v1/cases/{case.id}/spatial/series-metadata"
    body = {"upload_ids": [r.id for r in records]}
    response = spatial_client.post(route, headers=headers, json=body)
    assert response.status_code == 200, response.text
    contract = response.json()
    assert contract["status"] == "AVAILABLE" and contract["coordinate_frame"] == "LPS_MM"
    assert contract["dimensions_xyz"] == [4, 4, 3] and not contract["non_axial_vertical_flip"]
    assert contract["series_report"]["ordered_upload_ids"] == [records[1].id, records[2].id, records[0].id]
    assert "Synthetic" not in response.text and "NotReturned" not in response.text
    assert "volume" not in contract["series_report"]
    assert transform_point(contract["affine_voxel_to_world"], [0, 0, 0]) == [-10., 20., 0.]
    records[0].superseded_by_file_id = records[1].id; db_session.commit()
    assert spatial_client.post(route, headers=headers, json=body).status_code == 409
    assert spatial_client.post(route, headers=headers, json={"upload_ids": [records[1].id, 99999]}).status_code == 404
