"""Multi-file DICOM series assembly: ordering by patient position and fail-closed geometry checks.

Every DICOM object here is generated in the test (4x4 synthetic pixels, no patient data).
"""

import io
import random

import numpy as np
import pytest
import pydicom
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from app.models.entities import Case
from app.services.dicom_series import assemble_series, uid_reference
from tests.conftest import get_auth_headers

AXIAL = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]


def _slice(series_uid, z, instance, orientation=AXIAL, spacing=(0.8, 0.7), value=0, patient_name="", trigger_time=None, modality="CT"):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = pydicom.Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.SeriesInstanceUID = series_uid
    ds.StudyInstanceUID = "1.2.826.0.1.3680043.10.1.1"
    ds.Modality = modality
    if trigger_time is not None:
        ds.TriggerTime = trigger_time
    ds.PatientName = patient_name
    ds.InstanceNumber = instance
    ds.ImageOrientationPatient = orientation
    normal = np.cross(orientation[:3], orientation[3:])
    ds.ImagePositionPatient = [float(v) for v in (np.array([-10.0, 20.0, 0.0]) + normal * z)]
    ds.PixelSpacing = list(spacing)
    ds.Rows, ds.Columns = 4, 4
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
    ds.RescaleSlope, ds.RescaleIntercept = 1, -1024
    ds.PixelData = np.full((4, 4), value, dtype=np.uint16).tobytes()
    return ds


def _write(tmp_path, datasets):
    paths = []
    for number, ds in enumerate(datasets):
        path = tmp_path / f"slice-{number}.dcm"
        ds.save_as(path, enforce_file_format=True)
        paths.append(path)
    return paths


def test_slices_are_ordered_by_position_not_instance_number(tmp_path):
    series = generate_uid()
    positions = [0.0, 2.5, 5.0, 7.5, 10.0]
    datasets = [_slice(series, z, instance=len(positions) - index, value=index * 10 + 1024) for index, z in enumerate(positions)]
    random.Random(7).shuffle(datasets)
    paths = _write(tmp_path, datasets)
    report = assemble_series(paths, load_pixels=True)
    assert report["status"] == "ASSEMBLED", report
    assert report["shape_slices_rows_columns"] == [5, 4, 4]
    assert report["spacing_mm"] == {"row": 0.8, "column": 0.7, "slice": 2.5}
    assert report["volume"][:, 0, 0].tolist() == [0.0, 10.0, 20.0, 30.0, 40.0], "rescaled values in position order"
    assert report["affine_lps_mm"][2][2] == 2.5 and report["affine_lps_mm"][0][3] == -10.0


def test_oblique_series_affine_follows_the_orientation_cosines(tmp_path):
    c, s = np.cos(np.pi / 6), np.sin(np.pi / 6)
    oblique = [c, s, 0.0, -s, c, 0.0]
    series = generate_uid()
    report = assemble_series(_write(tmp_path, [_slice(series, z, i, orientation=oblique) for i, z in enumerate([0, 3, 6])]))
    assert report["status"] == "ASSEMBLED"
    affine = np.array(report["affine_lps_mm"])
    assert np.allclose(affine[:3, 0], np.array(oblique[:3]) * 0.7, atol=1e-6)
    assert np.allclose(affine[:3, 1], np.array(oblique[3:]) * 0.8, atol=1e-6)


def test_geometry_problems_reject_the_series(tmp_path):
    series = generate_uid()
    (tmp_path / "gap").mkdir()
    gap = assemble_series(_write(tmp_path / "gap", [_slice(series, z, i) for i, z in enumerate([0, 2.5, 7.5, 10])]))
    assert (gap["status"], gap["issues"]) == ("REJECTED", ["MISSING_SLICES"])
    (tmp_path / "dup").mkdir()
    duplicate = assemble_series(_write(tmp_path / "dup", [_slice(series, z, i) for i, z in enumerate([0, 2.5, 2.5, 5])]))
    assert duplicate["issues"] == ["DUPLICATE_SLICE_POSITION"]
    (tmp_path / "tilt").mkdir()
    tilted = [_slice(series, 0, 1), _slice(series, 2.5, 2, orientation=[1.0, 0.0, 0.0, 0.0, 0.99, 0.141])]
    assert assemble_series(_write(tmp_path / "tilt", tilted))["issues"] == ["INCONSISTENT_ORIENTATION"]
    (tmp_path / "one").mkdir()
    assert assemble_series(_write(tmp_path / "one", [_slice(series, 0, 1)]))["issues"] == ["SINGLE_SLICE"]


def test_mixed_series_need_an_explicit_choice_and_identifiers_are_reported_by_name_only(tmp_path):
    first, second = generate_uid(), generate_uid()
    datasets = [_slice(first, z, i, patient_name="Synthetic^Fixture") for i, z in enumerate([0, 2, 4])] + [_slice(second, z, i) for i, z in enumerate([0, 5])]
    paths = _write(tmp_path, datasets)
    mixed = assemble_series(paths)
    assert mixed["issues"] == ["MULTIPLE_SERIES"] and len(mixed["series"]) == 2
    assert all(first not in str(item) for item in mixed["series"]), "UIDs are not returned"
    chosen = assemble_series(paths, series_reference=uid_reference(first))
    assert chosen["status"] == "ASSEMBLED"
    assert chosen["identifying_tags_present"] == ["PatientName"]
    assert "IDENTIFYING_TAGS_PRESENT" in chosen["warnings"]
    assert "Synthetic" not in str(chosen)


def test_assembly_endpoint_uses_only_case_bound_uploads(client, db_session, test_users, tmp_path):
    owner = test_users["clinician_a"]
    case = Case(pseudonymous_id="DICOM-SERIES-TEST", created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()
    series = generate_uid()
    upload_ids = []
    for index, z in enumerate([5.0, 0.0, 2.5]):
        buffer = io.BytesIO()
        _slice(series, z, index + 1).save_as(buffer, enforce_file_format=True)
        response = client.post(f"/api/v1/cases/{case.id}/uploads", headers=get_auth_headers(owner),
                               files={"file": (f"s{index}.dcm", buffer.getvalue(), "application/dicom")}, data={"deidentified": "true"})
        assert response.status_code == 201, response.text
        upload_ids.append(response.json()["id"])

    response = client.post(f"/api/v1/cases/{case.id}/dicom-series/assemble", headers=get_auth_headers(owner), json={"upload_ids": upload_ids})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["status"] == "ASSEMBLED"
    assert report["ordered_upload_ids"] == [upload_ids[1], upload_ids[2], upload_ids[0]]
    assert report["inference"]["status"] == "NOT_RUN"

    foreign = client.post(f"/api/v1/cases/{case.id}/dicom-series/assemble", headers=get_auth_headers(owner), json={"upload_ids": [upload_ids[0], 999999]})
    assert foreign.status_code == 404


def _upload_series(client, owner, case, values_by_z):
    series = generate_uid()
    upload_ids = []
    for index, (z, value) in enumerate(values_by_z):
        buffer = io.BytesIO()
        _slice(series, z, index + 1, value=value).save_as(buffer, enforce_file_format=True)
        response = client.post(f"/api/v1/cases/{case.id}/uploads", headers=get_auth_headers(owner),
                               files={"file": (f"r{index}.dcm", buffer.getvalue(), "application/dicom")}, data={"deidentified": "true"})
        assert response.status_code == 201, response.text
        upload_ids.append(response.json()["id"])
    return upload_ids


def test_assembled_series_renders_every_plane_in_slice_order(client, db_session, test_users):
    import json as jsonlib

    from PIL import Image

    owner = test_users["clinician_a"]
    case = Case(pseudonymous_id="DICOM-SERIES-RENDER", created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()
    # Stored values 1000, 1100, 1200 by position (rescaled -24, 76, 176); uploaded out of order.
    upload_ids = _upload_series(client, owner, case, [(5.0, 1200), (0.0, 1000), (2.5, 1100)])
    url = f"/api/v1/cases/{case.id}/dicom-series/render"
    axial = client.post(url, headers=get_auth_headers(owner), json={"upload_ids": upload_ids, "axis": "axial", "index": 2, "center": 76, "width": 200})
    assert axial.status_code == 200 and axial.headers["content-type"] == "image/png"
    info = jsonlib.loads(axial.headers["X-MedTwin-Render"])
    assert (info["index"], info["count"], info["shape"]) == (2, 3, [4, 4])
    assert info["ordered_upload_ids"] == [upload_ids[1], upload_ids[2], upload_ids[0]]
    assert np.asarray(Image.open(io.BytesIO(axial.content))).max() == 255  # the last slice (176) is at the top of the window
    coronal = client.post(url, headers=get_auth_headers(owner), json={"upload_ids": upload_ids, "axis": "coronal", "index": 1, "center": 76, "width": 200})
    rows = np.asarray(Image.open(io.BytesIO(coronal.content)))
    assert rows.shape == (3, 4) and rows[0, 0] < rows[1, 0] < rows[2, 0]  # slice 0 at the top
    info = jsonlib.loads(coronal.headers["X-MedTwin-Render"])
    assert info["pixel_spacing_mm"] == {"vertical": 2.5, "horizontal": 0.7}
    rejected = _upload_series(client, owner, case, [(0.0, 1000), (2.5, 1000), (5.0, 1000), (12.5, 1000)])
    refused = client.post(url, headers=get_auth_headers(owner), json={"upload_ids": rejected})
    assert refused.status_code == 422 and refused.json()["detail"]["issues"] == ["MISSING_SLICES"]


def test_series_volume_matches_the_nifti_voxel_order(tmp_path):
    import nibabel as nib

    from app.services import volume_inference

    rng = np.random.default_rng(0)
    image = rng.integers(0, 400, size=(5, 4, 3)).astype(np.float32)  # (i, j, k)
    nifti = tmp_path / "frame.nii.gz"
    affine = np.diag([1.5, 1.5, 8.0, 1.0])
    nib.save(nib.Nifti1Image(image, affine), str(nifti))
    envelope = {"in_plane_spacing_mm": {"min": 1.0, "max": 2.0}, "slice_spacing_mm": {"min": 5.0, "max": 10.0},
                "matrix": {axis: {"min": 1, "max": 512} for axis in ("i", "j", "k")}}
    from_nifti = volume_inference.read_volume(nifti, envelope)
    series = np.stack([image[:, :, k].T for k in range(3)])  # slices x rows (j) x columns (i), as dicom_series assembles
    from_series = volume_inference.from_series(series, {"row": 1.5, "column": 1.5, "slice": 8.0}, envelope)
    assert np.array_equal(from_series.image, from_nifti.image) and from_series.spacing_mm == from_nifti.spacing_mm
    assert any(warning.startswith("ORIENTATION_CONVENTION") for warning in from_series.warnings)
    with pytest.raises(volume_inference.VolumeInputError, match="NONSQUARE_IN_PLANE_PIXELS"):
        volume_inference.from_series(series, {"row": 1.5, "column": 1.9, "slice": 8.0}, envelope)


def test_cine_series_are_assembled_for_one_chosen_phase(tmp_path):
    series = generate_uid()
    # Three positions, two phases each (trigger times differ slightly between positions, as on scanners).
    datasets = [_slice(series, z, index * 2 + phase + 1, value=1000 + 100 * phase + index, trigger_time=time + index, modality="MR")
                for index, z in enumerate([0.0, 8.0, 16.0]) for phase, time in enumerate([0.0, 310.0])]
    random.Random(3).shuffle(datasets)
    paths = _write(tmp_path, datasets)
    unchosen = assemble_series(paths)
    assert unchosen["issues"] == ["CARDIAC_PHASE_REQUIRED"] and unchosen["cardiac_phases"] == 2
    assert unchosen["phase_trigger_times_ms"] == [1.0, 311.0]
    late = assemble_series(paths, phase=1, load_pixels=True)
    assert late["status"] == "ASSEMBLED" and late["phase"] == 1 and late["modality_tags"] == ["MR"]
    assert late["volume"][:, 0, 0].tolist() == [76.0, 77.0, 78.0]  # stored 1100 + index, rescaled by -1024, in position order
    assert assemble_series(paths, phase=2)["issues"] == ["CARDIAC_PHASE_OUT_OF_RANGE"]
    (tmp_path / "untimed").mkdir()
    untimed = [_slice(series, z, i) for i, z in enumerate([0.0, 0.0, 8.0, 8.0])]
    assert assemble_series(_write(tmp_path / "untimed", untimed))["issues"] == ["DUPLICATE_SLICE_POSITION"]


def _short_axis_report(normal, slices=8, tags=("MR",)):
    return {"slice_normal_lps": list(normal), "shape_slices_rows_columns": [slices, 4, 4], "modality_tags": list(tags)}


def test_short_axis_plausibility_refuses_body_axis_stacks():
    from app.services import volume_inference

    oblique = np.array([0.6, 0.5, -0.62])
    assert volume_inference.short_axis_plausibility(_short_axis_report(oblique))["status"] == "PASSED"
    with pytest.raises(volume_inference.VolumeInputError, match="SLICE_NORMAL_ALIGNED_WITH_BODY_AXIS") as refused:
        volume_inference.short_axis_plausibility(_short_axis_report([0.0, 0.05, 1.0]))
    assert "axial" in str(refused.value)
    with pytest.raises(volume_inference.VolumeInputError, match="TOO_FEW_SLICES_FOR_SHORT_AXIS_STACK"):
        volume_inference.short_axis_plausibility(_short_axis_report(oblique, slices=4))
    with pytest.raises(volume_inference.VolumeInputError, match="SERIES_MODALITY_NOT_MR"):
        volume_inference.short_axis_plausibility(_short_axis_report(oblique, tags=("CT",)))


def _phantom_heart(shape=(40, 36, 8)):
    """Labels on the development layout: LV (3) a disc shrinking along k, RV (1) a disc at -i of the LV, myocardium (2) a ring."""
    grid_i, grid_j = np.indices(shape[:2])
    labels = np.zeros(shape, np.uint8)
    for k in range(shape[2]):
        radius = 7 - 0.6 * k
        lv = (grid_i - 22) ** 2 + (grid_j - 18) ** 2
        labels[..., k][lv <= (radius + 2) ** 2] = 2
        labels[..., k][lv <= radius ** 2] = 3
        labels[..., k][((grid_i - 9) ** 2 + (grid_j - 18) ** 2) <= 16] = 1
    return labels


def test_the_axis_convention_is_chosen_from_the_ventricle_layout(monkeypatch):
    from app.services import volume_inference as vi

    truth = _phantom_heart()
    prior = {"rv_label": 1, "lv_label": 3, "rv_direction_deg": vi.ventricle_direction_deg(truth, (1.0, 1.0, 8.0), 1, 3),
             "rv_direction_limit_deg": 45.0}
    # The "model" segments the image it is given exactly (labels are stored in the image), so a series stored in any
    # of the 16 conventions must come back on its own grid with the development layout recovered.
    monkeypatch.setattr(vi, "predict", lambda network, payload, device, item: item.image.astype(np.uint8))
    for variant in (vi.ORIENTATION_VARIANTS[0], (True, False, True, False), (False, True, False, True), (True, True, True, True)):
        series = vi._orient(truth.astype(np.float32), variant)
        mask, report = vi.choose_convention(None, {}, None, vi.VolumeInput(series, (1.0, 1.0, 8.0)), prior)
        assert np.array_equal(mask, series), variant
        assert abs(report["chosen"]["rv_direction_offset_deg"]) < 1 and report["chosen"]["lv_area_trend"] < 0
    # Without a shrinking left ventricle in any convention the series is refused.
    flat = np.where(truth == 3, 3, np.where(truth == 1, 1, 0)).astype(np.float32)
    flat[..., :] = flat[..., :1]
    with pytest.raises(vi.VolumeInputError, match="SLICE_ORDER_NOT_BASE_TO_APEX_IN_ANY_CONVENTION"):
        vi.choose_convention(None, {}, None, vi.VolumeInput(flat, (1.0, 1.0, 8.0)), prior)


def test_the_right_ventricle_must_be_anterior_right_in_patient_coordinates():
    from app.services import volume_inference as vi

    labels = _phantom_heart()  # RV at lower i than the LV
    # i runs to the patient's left (+x in LPS), j posterior (+y): the RV at lower i, same j, is to the patient's right.
    affine = np.diag([1.0, 1.0, 8.0, 1.0])
    assert vi.right_ventricle_is_right_anterior(labels, affine, 1, 3)["status"] == "PASSED"
    mirrored = np.diag([-1.0, 1.0, 8.0, 1.0])  # i runs to the patient's right: the same labels put the RV on the left
    with pytest.raises(vi.VolumeInputError, match="RIGHT_VENTRICLE_NOT_RIGHT_ANTERIOR"):
        vi.right_ventricle_is_right_anterior(labels, mirrored, 1, 3)


def test_series_inference_refuses_models_that_do_not_take_volumes(client, db_session, test_users, monkeypatch):
    from app.services import model_inference

    owner = test_users["clinician_a"]
    case = Case(pseudonymous_id="DICOM-SERIES-MODEL", created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()
    upload_ids = _upload_series(client, owner, case, [(0.0, 1000), (2.5, 1100), (5.0, 1200)])
    monkeypatch.setattr(model_inference, "get_model", lambda model_id: {"model_id": model_id, "display_name": "Image classifier",
                                                                          "inference_input": "image_2d", "supported_modalities": ["MRI"]})
    response = client.post(f"/api/v1/cases/{case.id}/dicom-series/research-inference", headers=get_auth_headers(owner),
                           json={"upload_ids": upload_ids, "model_id": "image_classifier"})
    assert response.status_code == 400 and "only volumetric and series models" in response.json()["detail"]
