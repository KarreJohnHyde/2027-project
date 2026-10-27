"""Multi-file DICOM series assembly: ordering by patient position and fail-closed geometry checks.

Every DICOM object here is generated in the test (4x4 synthetic pixels, no patient data).
"""

import io
import random

import numpy as np
import pydicom
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from app.models.entities import Case
from app.services.dicom_series import assemble_series, uid_reference
from tests.conftest import get_auth_headers

AXIAL = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]


def _slice(series_uid, z, instance, orientation=AXIAL, spacing=(0.8, 0.7), value=0, patient_name=""):
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
    ds.Modality = "CT"
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
