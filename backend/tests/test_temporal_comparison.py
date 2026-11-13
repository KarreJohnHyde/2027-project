import hashlib
import io
import json
import numpy as np
import nibabel as nib
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.database import get_db
from app.models.entities import Case
from app.routers import temporal_comparison as routes
from app.schemas.temporal_comparison import TemporalRenderRequest
from app.services import temporal_comparison as temporal
from app.services.universal_geometry import GeometryRefusal
from app.services.universal_spatial_io import source_metadata, view_contract, configure_view
from tests.test_universal_geometry import _upload
from tests.conftest import get_auth_headers


def _file(path, values, *, units="mm", synthetic=True):
    image = nib.Nifti1Image(np.asarray(values, dtype=np.float32), np.eye(4))
    if units: image.header.set_xyzt_units(units)
    if synthetic:
        image.header["intent_name"] = b"MT_SYNTHETIC"
        image.header["descrip"] = b"MedTwin original synthetic control;unit=matched_arbitrary"
    nib.save(image, path)
    return path


def _contract(path):
    return view_contract(source_metadata(path), {"upload_id": 1, "sha256": "test"})


@pytest.mark.parametrize("matrix", [np.diag([2, 1, 1, 1]), np.diag([-1, 1, 1, 1]), [[1, .1, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], np.diag([float("nan"), 1, 1, 1])])
def test_invalid_rigid_transform_refuses(matrix):
    with pytest.raises(GeometryRefusal): temporal.validate_rigid(matrix)


def test_exact_identity_and_known_mapping_change_excludes_invalid_source_field(tmp_path):
    indices = np.indices((10, 12, 8)); previous = (indices[0]+10*indices[1]+100*indices[2]).astype(np.float32)
    contract = _contract(_file(tmp_path/"control.nii.gz", previous))
    reference = configure_view(contract, "anatomical")
    a, b, valid, _ = temporal.comparison_planes(previous, previous, reference, contract, np.eye(4), "axial", 3)
    assert np.array_equal(a, b) and valid.all()
    current = previous + 4  # current(x+1) = previous(x)+5 under the known physical mapping.
    transform = np.eye(4); transform[0, 3] = 1
    a, b, valid, _ = temporal.comparison_planes(previous, current, reference, contract, transform, "axial", 3)
    assert np.allclose((b-a)[valid], 5) and valid.mean() == pytest.approx(.9)
    session = {"reference": reference, "current_contract": contract, "transform": transform.tolist(), "public": {"intensity": {"difference_allowed": True, "semantics": "synthetic only"}}}
    png, info = temporal.render_comparison(previous, current, session, TemporalRenderRequest(mode="difference", axis="axial", index=3))
    rgb = np.asarray(Image.open(io.BytesIO(png)))
    assert (rgb[valid, 0] == 255).all() and (rgb[valid, 2] == 0).all()
    assert info["statistics"]["mean_current_minus_previous"] == pytest.approx(5)
    assert np.all(rgb[~valid, 0] == rgb[~valid, 1]-10) and info["statistics"]["invalid_pixels_excluded"]
    assert not info["clinical_progression_claim"]


def test_session_user_case_expiry_and_unknown_intensity_refusals(monkeypatch):
    session = temporal.put_session(100, 200, {"public": {"status": "CANDIDATE_UNVALIDATED"}})
    token = session["comparison_id"]
    with pytest.raises(GeometryRefusal): temporal.get_session(token, 101, 200)
    with pytest.raises(GeometryRefusal): temporal.get_session(token, 100, 201)
    assert temporal.get_session(token, 100, 200)
    monkeypatch.setattr(temporal.time, "monotonic", lambda: 1e15)
    with pytest.raises(GeometryRefusal) as error: temporal.get_session(token, 100, 200)
    assert error.value.code == "COMPARISON_EXPIRED"
    unknown = {"modality": "UNSPECIFIED", "unit": None, "metadata_verified": False}
    assert not temporal.compatibility(unknown, unknown, True)["difference_allowed"]


def test_ct_rescale_requires_explicit_hounsfield_units():
    tags = {"Modality": "CT", "RescaleSlope": 1., "RescaleIntercept": -1024.}
    for unit in [None, "US", "OTHER"]:
        result = temporal.intensity_evidence(None, {"container": "DICOM", "technical_tags": {**tags, "RescaleType": unit}})
        assert not result["metadata_verified"] and result["unit"] is None
    result = temporal.intensity_evidence(None, {"container": "DICOM", "technical_tags": {**tags, "RescaleType": "HU"}})
    assert result["metadata_verified"] and result["unit"] == "HU"


@pytest.fixture
def temporal_client(db_session):
    app = FastAPI(); app.include_router(routes.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client: yield client


def _pair(db, owner, tmp_path, *, units="mm", synthetic=True):
    previous = np.indices((10, 12, 8)).sum(axis=0).astype(np.float32)
    first = _upload(db, owner, _file(tmp_path/"previous.nii.gz", previous, units=units, synthetic=synthetic))
    second = _upload(db, owner, _file(tmp_path/"current.nii.gz", previous+2, units=units, synthetic=synthetic), case=db.get(Case, first.case_id))
    for record in [first, second]: record.file_hash = hashlib.sha256(open(record.file_path, "rb").read()).hexdigest()
    db.commit()
    def identity(record): return {"upload_id": record.id, "sha256": record.file_hash}
    return first, second, {"previous": identity(first), "current": identity(second), "previous_region": "synthetic phantom", "current_region": "synthetic phantom", "same_subject_attested": True, "same_region_attested": True, "comparable_intensity_attested": True, "alignment": "shared_physical_space", "shared_physical_space_attested": True}


def test_actual_bound_api_difference_source_hash_and_refusals(temporal_client, db_session, test_users, tmp_path):
    first, second, body = _pair(db_session, test_users["clinician_a"], tmp_path)
    headers = get_auth_headers(test_users["clinician_a"]); route = f"/api/v1/cases/{first.case_id}/temporal-comparisons"
    response = temporal_client.post(route, headers=headers, json=body)
    assert response.status_code == 200, response.text
    comparison = response.json(); token = comparison["comparison_id"]
    assert comparison["status"] == "CANDIDATE_UNVALIDATED" and comparison["intensity"]["difference_allowed"]
    rendered = temporal_client.post(route+f"/{token}/render", headers=headers, json={"mode": "difference", "index": 3})
    assert rendered.status_code == 200, rendered.text
    stats = json.loads(rendered.headers["X-MedTwin-Comparison"])["statistics"]
    assert stats["mean_current_minus_previous"] == pytest.approx(2) and stats["valid_fraction"] == 1
    mismatch = {**body, "current_region": "heart"}
    assert temporal_client.post(route, headers=headers, json=mismatch).json()["detail"]["code"] == "ANATOMICAL_REGION_MISMATCH"
    assert temporal_client.post(route, headers=headers, json={**body, "current": body["previous"]}).status_code == 422
    changed = {**body, "current": {**body["current"], "sha256": "b"*64}}
    assert temporal_client.post(route, headers=headers, json=changed).json()["detail"]["code"] == "SOURCE_HASH_CHANGED"
    second.file_hash = "c"*64; db_session.commit()
    assert temporal_client.post(route+f"/{token}/render", headers=headers, json={}).status_code == 422


@pytest.mark.private_workspace
def test_unknown_units_intensity_transform_binding_and_case_isolation(temporal_client, db_session, test_users, tmp_path):
    first, second, body = _pair(db_session, test_users["clinician_a"], tmp_path, synthetic=False)
    headers = get_auth_headers(test_users["clinician_a"]); route = f"/api/v1/cases/{first.case_id}/temporal-comparisons"
    result = temporal_client.post(route, headers=headers, json=body).json()
    assert not result["intensity"]["difference_allowed"]
    rendered = temporal_client.post(route+f"/{result['comparison_id']}/render", headers=headers, json={"mode": "difference"})
    assert rendered.status_code == 422 and rendered.json()["detail"]["code"] == "INTENSITY_COMPATIBILITY_UNVERIFIED"
    assert temporal_client.post(route, headers=get_auth_headers(test_users["clinician_b"]), json=body).status_code in (403, 404)
    transform = {"previous": body["previous"], "current": {**body["current"], "sha256": "e"*64}, "previous_to_current_ras_mm": np.eye(4).tolist()}
    refusal = temporal_client.post(route, headers=headers, json={**body, "alignment": "provided_rigid", "provided_rigid": transform})
    assert refusal.status_code == 422 and refusal.json()["detail"]["code"] == "TRANSFORM_SOURCE_BINDING_MISMATCH"
    path = tmp_path/"unknown-units.nii.gz"; _file(path, np.indices((10, 12, 8)).sum(axis=0), units=None)
    second.file_path = str(path); second.file_hash = hashlib.sha256(path.read_bytes()).hexdigest(); db_session.commit()
    body["current"]["sha256"] = second.file_hash
    refusal = temporal_client.post(route, headers=headers, json=body)
    assert refusal.status_code == 422 and refusal.json()["detail"]["code"] == "PATIENT_WORLD_UNAVAILABLE"
