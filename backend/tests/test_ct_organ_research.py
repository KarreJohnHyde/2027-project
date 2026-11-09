"""CT organ segmentation (TotalSegmentator, third-party): applicability, stored output, surfaces, refusals.

The CT is a synthetic phantom (air at -1000 HU, a 40 HU sphere) and the segmenter is a fixture that labels
the sphere; the real network is exercised by the LUNA16 check (scripts/evaluate_totalseg_luna16.py)."""

import nibabel as nib
import numpy as np
import pytest

from app.services import ct_organ_research
from tests.conftest import get_auth_headers

pytest.importorskip("totalsegmentator")

SPACING = (1.5, 1.5, 3.0)
CENTRE, RADIUS = np.array([32, 30, 12]), 9


def _sphere(shape=(64, 60, 24)) -> np.ndarray:
    grid = np.indices(shape).transpose(1, 2, 3, 0)
    return np.linalg.norm((grid - CENTRE) * np.array(SPACING) / np.array(SPACING[0]), axis=-1) <= RADIUS


def _nifti(path, values: np.ndarray):
    image = nib.Nifti1Image(values.astype(np.int16), np.diag([*SPACING, 1.0]))
    nib.save(image, str(path))
    return path.read_bytes()


def _fake_segmenter(image, fast):
    labels = np.zeros(image.shape[:3], dtype=np.uint8)
    labels[_sphere(image.shape[:3])] = 5  # class 5 of TotalSegmentator's "total" map
    return nib.Nifti1Image(labels, image.affine)


def _upload(client, headers, case_id, name, body):
    response = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (name, body, "application/gzip")},
                           data={"deidentified": "true"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_ct_volume_is_segmented_stored_listed_and_surfaced(client, test_users, tmp_path, monkeypatch):
    monkeypatch.setattr(ct_organ_research, "_segment", _fake_segmenter)
    monkeypatch.setattr(ct_organ_research, "availability", lambda: {"available": True, "fast": True, "full_resolution": True})
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CT-ORGAN-PHANTOM"}, headers=headers).json()["id"]
    ct = np.full((64, 60, 24), -1000, dtype=np.int16)
    ct[_sphere()] = 40
    upload_id = _upload(client, headers, case_id, "phantom_ct.nii.gz", _nifti(tmp_path / "ct.nii.gz", ct))

    response = client.post(f"/api/v1/uploads/{upload_id}/ct-organ-segmentation", json={"attest_ct_volume": True, "fast": True}, headers=headers)
    assert response.status_code == 201, response.text
    run = response.json()
    output = run["research_output"]
    assert output["type"] == "volume_segmentation" and output["volume_shape_ijk"] == [64, 60, 24]
    [structure] = output["structures"]
    expected_ml = int(_sphere().sum()) * np.prod(SPACING) / 1000
    assert structure["class_index"] == 5 and structure["volume_ml"] == pytest.approx(expected_ml, abs=0.0005)  # stored to 3 decimals
    assert run["research_provenance"]["model_id"] == "ct_totalsegmentator_v2" and run["finding_id"]
    assert output["input_checks"]["intensity_p1_p99"][0] <= -500

    listed = client.get(f"/api/v1/uploads/{upload_id}/research-inference", headers=headers).json()["runs"]
    assert [item["id"] for item in listed] == [run["id"]]
    surfaces = client.get(f"/api/v1/research-inference/{run['id']}/surfaces", headers=headers).json()
    assert [item["class_index"] for item in surfaces["surfaces"]] == [5] and surfaces["marching_cubes_step_voxels"] == 1


def test_non_ct_values_are_refused_before_the_network(client, test_users, tmp_path, monkeypatch):
    def must_not_run(image, fast):
        raise AssertionError("the network must not run on a refused input")

    monkeypatch.setattr(ct_organ_research, "_segment", must_not_run)
    monkeypatch.setattr(ct_organ_research, "availability", lambda: {"available": True, "fast": True, "full_resolution": True})
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CT-ORGAN-MRI"}, headers=headers).json()["id"]
    mri_like = np.random.default_rng(0).integers(0, 1200, size=(64, 60, 24))  # MRI-like: no values near -1000
    upload_id = _upload(client, headers, case_id, "mri_like.nii.gz", _nifti(tmp_path / "mri.nii.gz", mri_like))
    response = client.post(f"/api/v1/uploads/{upload_id}/ct-organ-segmentation", json={"attest_ct_volume": True}, headers=headers)
    assert response.status_code == 400 and "Hounsfield" in response.json()["detail"]


def test_attestation_is_required(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    response = client.post("/api/v1/uploads/1/ct-organ-segmentation", json={"fast": True}, headers=headers)
    assert response.status_code == 422


def _phantom_case(client, headers, tmp_path, name, spacing_unit="mm", scale=1.0):
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": f"CT-{name}"}, headers=headers).json()["id"]
    ct = np.full((64, 60, 24), -1000, dtype=np.int16)
    ct[_sphere()] = 40
    image = nib.Nifti1Image(ct, np.diag([*(value * scale for value in SPACING), 1.0]))
    image.header.set_xyzt_units(spacing_unit)
    path = tmp_path / f"{name}.nii.gz"
    nib.save(image, str(path))
    return case_id, _upload(client, headers, case_id, f"{name}.nii.gz", path.read_bytes())


def test_metre_headers_are_converted_and_withdrawn_uploads_refused(client, test_users, tmp_path, monkeypatch, db_session):
    from app.models.entities import UploadedFile

    seen = {}

    def recording_segmenter(image, fast):
        seen["zooms"] = [round(float(value), 6) for value in image.header.get_zooms()[:3]]
        return _fake_segmenter(image, fast)

    monkeypatch.setattr(ct_organ_research, "_segment", recording_segmenter)
    monkeypatch.setattr(ct_organ_research, "availability", lambda: {"available": True, "fast": True, "full_resolution": True})
    headers = get_auth_headers(test_users["clinician_a"])
    _, upload_id = _phantom_case(client, headers, tmp_path, "metres", spacing_unit="meter", scale=0.001)
    run = client.post(f"/api/v1/uploads/{upload_id}/ct-organ-segmentation", json={"attest_ct_volume": True}, headers=headers).json()
    assert run["research_output"]["voxel_spacing_mm"] == list(SPACING) and seen["zooms"] == list(SPACING)
    expected_ml = int(_sphere().sum()) * np.prod(SPACING) / 1000
    assert run["research_output"]["structures"][0]["volume_ml"] == pytest.approx(expected_ml, abs=0.0005)

    _, withdrawn_id = _phantom_case(client, headers, tmp_path, "withdrawn")
    record = db_session.get(UploadedFile, withdrawn_id)
    record.is_associated = False
    db_session.commit()
    response = client.post(f"/api/v1/uploads/{withdrawn_id}/ct-organ-segmentation", json={"attest_ct_volume": True}, headers=headers)
    assert response.status_code == 400 and "withdrawn or not associated" in response.json()["detail"]


def test_volumes_over_the_voxel_budget_are_refused_before_reading(client, test_users, tmp_path, monkeypatch):
    monkeypatch.setattr(ct_organ_research, "MAX_VOXELS", 1000)
    monkeypatch.setattr(ct_organ_research, "availability", lambda: {"available": True, "fast": True, "full_resolution": True})
    headers = get_auth_headers(test_users["clinician_a"])
    _, upload_id = _phantom_case(client, headers, tmp_path, "budget")
    response = client.post(f"/api/v1/uploads/{upload_id}/ct-organ-segmentation", json={"attest_ct_volume": True}, headers=headers)
    assert response.status_code == 400 and "voxels" in response.json()["detail"]


def _watertight(faces: np.ndarray) -> bool:
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool(np.all(counts == 2))


def test_thin_and_off_lattice_structures_get_closed_surfaces_on_large_grids():
    from app.services import volume_inference

    labels = np.zeros((520, 40, 30), dtype=np.uint8)
    labels[100:200, 5:15, 10] = 1    # one voxel thick: the step falls back to 1
    labels[300:407, 20:27, 3:11] = 2  # 107 x 7 x 8: sizes off the step-3 lattice
    surfaces = volume_inference.structure_surfaces(ct_organ_research.label_output(labels, {1: "sheet", 2: "bar"}, [1.0, 1.0, 1.0], {}, True))
    by_class = {item["class_index"]: item for item in surfaces["surfaces"]}
    assert set(by_class) == {1, 2} and surfaces["structures_without_surface"] == []
    assert by_class[1]["step_voxels"] == 1 and by_class[2]["step_voxels"] == 3
    for item in by_class.values():
        assert _watertight(np.array(item["faces"]).reshape(-1, 3))
    vertices = np.array(by_class[2]["vertices_mm"]).reshape(-1, 3)
    assert vertices[:, 0].min() >= 298 and vertices[:, 0].max() <= 408


def test_large_grids_get_a_coarser_surface_step():
    from app.services import volume_inference

    labels = np.zeros((520, 20, 10), dtype=np.uint8)
    labels[100:400, 5:15, 2:8] = 3
    output = ct_organ_research.label_output(labels, {3: "block"}, [1.0, 1.0, 1.0], {}, True)
    surfaces = volume_inference.structure_surfaces(output)
    assert surfaces["marching_cubes_step_voxels"] == 3
    vertices = np.array(surfaces["surfaces"][0]["vertices_mm"]).reshape(-1, 3)
    assert vertices[:, 0].min() >= 98 and vertices[:, 0].max() <= 401, "cropped coordinates stay in the scan frame"
