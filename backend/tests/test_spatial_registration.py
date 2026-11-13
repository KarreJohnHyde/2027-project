"""Held-out known-transform engineering checks; no clinical/expert validation."""
import numpy as np
import pytest

from app.models.entities import Case
from app.services import universal_registration
from app.services.universal_geometry import GeometryRefusal
from scripts.benchmark_spatial_registration import synthetic_case
from tests.conftest import get_auth_headers
from tests.test_universal_geometry import _upload, spatial_client  # noqa: F401
from tests.test_spatial_completion import _nifti


@pytest.mark.parametrize("metric", ["mattes", "mean_squares"])
def test_optimizer_transform_direction_and_held_out_tre(metric):
    fixed, moving, contract, landmarks, known = synthetic_case(.04, np.array([2., -1., 1.5]), .2)
    result = universal_registration.register_rigid(fixed, contract, moving, contract, landmarks=landmarks, landmark_source="SYNTHETIC_KNOWN_TRANSFORM", metric=metric)
    tre = result["landmark_evaluation"]
    assert tre["before_mean_mm"] > 1 and tre["after_mean_mm"] < .75
    assert not tre["used_for_optimization"] and not tre["independent_clinical_validation"]
    assert result["status"] == "CANDIDATE_UNVALIDATED" and not result["clinical_activation"] and not result["atlas_registration"]
    assert np.allclose(np.asarray(result["fixed_to_moving_ras_mm"]) @ result["moving_to_fixed_ras_mm"], np.eye(4))
    # Deliberately checking the wrong direction would miss the known physical transform by several mm.
    assert np.linalg.norm(np.asarray(result["moving_to_fixed_ras_mm"])[:3, 3]-known[:3, 3]) < .75
    assert max(result["sampled_dimensions"]["fixed"]) <= 96


def test_registration_refuses_unknown_sheared_constant_and_out_of_source_landmarks():
    fixed, moving, contract, landmarks, _ = synthetic_case(0., np.array([2., -1., 1.5]))
    invalid = {**contract, "world_available": False}
    with pytest.raises(GeometryRefusal, match="coded source affine"):
        universal_registration.register_rigid(fixed, invalid, moving, contract)
    affine = np.array(contract["affine_voxel_to_world"]); affine[0, 1] += .5
    with pytest.raises(GeometryRefusal) as exc:
        universal_registration.register_rigid(fixed, {**contract, "affine_voxel_to_world": affine.tolist()}, moving, contract)
    assert exc.value.code == "SHEARED_REGISTRATION_GRID"
    with pytest.raises(GeometryRefusal) as exc:
        universal_registration.register_rigid(np.zeros_like(fixed), contract, moving, contract)
    assert exc.value.code == "REGISTRATION_INTENSITIES_INVALID"
    outside = [dict(p) for p in landmarks]; outside[0] = {**outside[0], "moving_ras_mm": [999., 999., 999.]}
    with pytest.raises(GeometryRefusal) as exc:
        universal_registration.register_rigid(fixed, contract, moving, contract, landmarks=outside)
    assert exc.value.code == "LANDMARK_OUTSIDE_SOURCE"


def test_landmark_tre_and_runtime_refusals_are_typed(monkeypatch):
    with pytest.raises(GeometryRefusal) as exc:
        universal_registration.landmark_tre(np.eye(4).tolist(), [{"fixed_ras_mm": [0, 0, 0], "moving_ras_mm": [0, 0, 0]}], source="SYNTHETIC_KNOWN_TRANSFORM")
    assert exc.value.code == "LANDMARK_COUNT_INVALID"
    collinear = [{"fixed_ras_mm": [i, 0, 0], "moving_ras_mm": [i, 0, 0]} for i in range(3)]
    with pytest.raises(GeometryRefusal) as exc:
        universal_registration.landmark_tre(np.eye(4).tolist(), collinear, source="SYNTHETIC_KNOWN_TRANSFORM")
    assert exc.value.code == "LANDMARK_GEOMETRY_DEGENERATE"
    fixed, moving, contract, _, _ = synthetic_case(.04, np.array([2., -1., 1.5]))
    monkeypatch.setattr(universal_registration, "MAX_RUNTIME_SECONDS", 0.)
    with pytest.raises(GeometryRefusal) as exc:
        universal_registration.register_rigid(fixed, contract, moving, contract)
    assert exc.value.code == "REGISTRATION_RUNTIME_BUDGET"


def test_authorized_candidate_api_is_source_bound_and_never_activates_registration(spatial_client, db_session, test_users, tmp_path):
    owner = test_users["clinician_a"]
    fixed, moving, contract, landmarks, _ = synthetic_case(.04, np.array([2., -1., 1.5]))
    first = _upload(db_session, owner, _nifti(tmp_path / "fixed.nii.gz", fixed, np.asarray(contract["affine_voxel_to_world"])))
    case = db_session.get(Case, first.case_id)
    second = _upload(db_session, owner, _nifti(tmp_path / "moving.nii.gz", moving, np.asarray(contract["affine_voxel_to_world"])), case=case)
    request = {"fixed": {"upload_id": first.id}, "moving": {"upload_id": second.id}, "same_subject_attested": True, "same_anatomical_region_attested": True, "metric": "mean_squares", "landmarks": landmarks, "landmark_source": "SYNTHETIC_KNOWN_TRANSFORM"}
    response = spatial_client.post(f"/api/v1/cases/{case.id}/spatial/registration", json=request, headers=get_auth_headers(owner))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["sources"]["fixed"]["upload_id"] == first.id and result["sources"]["moving"]["upload_id"] == second.id
    assert result["landmark_evaluation"]["after_mean_mm"] < .75
    assert result["status"] == "CANDIDATE_UNVALIDATED" and not result["clinical_activation"]
    result = spatial_client.get(f"/api/v1/uploads/{first.id}/spatial/metadata", headers=get_auth_headers(owner)).json()
    assert result["registration"]["status"] == "REGISTRATION_UNAVAILABLE" and result["registration"]["atlas_transform"] is None
