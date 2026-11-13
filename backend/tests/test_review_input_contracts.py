"""Synthetic technical input contracts, independent of checkpoints and application state.

These tests establish refusal/reader behavior, not clinical model accuracy.
They may also run with --noconftest --confcutdir=backend/tests to isolate the
pure readers when the full application runtime is unavailable.
"""
from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from app.models.entities import ModalityType
from app.services import ecg_inference as ecg, model_router
from app.services.imaging_readers import open_raster, read_metadata

CONTRACT = ecg.CONTRACTS["wfdb16-100hz-10s-leadstd-v1"]


def _csv(*, unit="mV", times=None, signal=None, leads=None):
    leads = leads or ecg.PTBXL_LEADS
    times = np.arange(1000, dtype=float) / 100 if times is None else times
    if signal is None:
        signal = np.stack([0.2 * np.sin(np.arange(len(times)) / (7 + lead)) for lead in range(len(leads))], axis=1)
    values = signal * (1000 if unit == "uV" else 1)
    lines = ["time_s," + ",".join(leads)]
    lines.extend(str(time) + "," + ",".join(str(value) for value in row) for time, row in zip(times, values))
    return ("\n".join(lines) + "\n").encode(), signal


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_csv_time_is_refused_before_frequency_inference(bad):
    times = np.arange(1000, dtype=float) / 100
    times[29] = bad
    content, _ = _csv(times=times)
    with pytest.raises(ecg.EcgInputError, match="NON_FINITE_TIMESTAMPS"):
        ecg.read_csv(content, "mV")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 1e300])
def test_nonfinite_or_unrepresentable_csv_signal_is_refused(bad):
    signal = np.ones((1000, 12))
    signal[3, 2] = bad
    content, _ = _csv(signal=signal)
    with pytest.raises(ecg.EcgInputError, match="NON_FINITE_SAMPLES"):
        ecg.read_csv(content, "mV")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 0.0, -100.0])
def test_nonfinite_or_nonpositive_record_frequency_is_refused(bad):
    _, signal = _csv()
    record = ecg.EcgRecord(signal, ecg.PTBXL_LEADS, bad, "CONTROL")
    with pytest.raises(ecg.EcgInputError, match="INVALID_SAMPLING_RATE"):
        ecg.check_record(record, CONTRACT)


@pytest.mark.parametrize("shape", [(1000,), (1000, 11), (1000, 12, 1)])
def test_signal_dimensions_must_match_named_leads(shape):
    record = ecg.EcgRecord(np.ones(shape), ecg.PTBXL_LEADS, 100.0, "CONTROL")
    with pytest.raises(ecg.EcgInputError, match="SIGNAL_SHAPE_MISMATCH"):
        ecg.check_record(record, CONTRACT)


@pytest.mark.parametrize("change, code", [
    ("extra_cell", "CSV_COLUMN_COUNT_MISMATCH"),
    ("missing_cell", "CSV_COLUMN_COUNT_MISMATCH"),
    ("duplicate_time", "TIME_NOT_INCREASING"),
    ("irregular_time", "IRREGULAR_SAMPLING"),
])
def test_malformed_csv_and_time_grids_have_typed_refusals(change, code):
    content, _ = _csv()
    rows = content.decode().splitlines()
    fields = rows[8].split(",")
    if change == "extra_cell":
        fields.append("123")
    elif change == "missing_cell":
        fields.pop()
    elif change == "duplicate_time":
        fields[0] = rows[7].split(",")[0]
    else:
        fields[0] = "0.075"
    rows[8] = ",".join(fields)
    with pytest.raises(ecg.EcgInputError, match=code):
        ecg.read_csv("\n".join(rows).encode(), "mV")


def test_physical_units_and_shuffled_leads_preserve_samples():
    leads = list(reversed(ecg.PTBXL_LEADS))
    content, signal = _csv(unit="uV", leads=leads)
    record = ecg.check_record(ecg.read_csv(content, " uV "), CONTRACT)
    assert record.sampling_rate_hz == pytest.approx(100)
    assert record.signal_mv.shape == (1000, 12)
    assert record.leads == ecg.PTBXL_LEADS
    assert np.allclose(record.signal_mv, signal[:, ::-1], atol=1e-7)


@pytest.mark.parametrize("rate", ["nan", "inf", "0", "-100"])
def test_wfdb_nonphysical_frequency_is_typed(rate):
    header = f"record 1 {rate} 2\nrecord.dat 16 1000/mV 16 0 0 0 0 I\n".encode()
    with pytest.raises(ecg.EcgInputError, match="INVALID_SAMPLING_RATE"):
        ecg.read_wfdb(header, b"\x00\x00" * 2)


def _dicom(path, modality="CT", body="HEAD"):
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.Modality = modality
    dataset.BodyPartExamined = body
    dataset.Rows, dataset.Columns = 2, 3
    dataset.SOPClassUID, dataset.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    dataset.SamplesPerPixel, dataset.PhotometricInterpretation = 1, "MONOCHROME2"
    dataset.BitsAllocated, dataset.BitsStored, dataset.HighBit, dataset.PixelRepresentation = 16, 16, 15, 0
    dataset.PixelData = np.arange(6, dtype="<u2").tobytes()
    dataset.save_as(path, enforce_file_format=True)
    return path


@pytest.mark.parametrize("modality, body, declared, expected", [
    ("CT", "HEAD", "HEAD_CT", None),
    ("MR", "HEAD", "HEAD_CT", "DICOM_MODALITY_CONTRADICTS_DECLARATION"),
    ("CT", "KNEE", "HEAD_CT", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
    ("DX", "HAND", "CHEST_XRAY", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
    ("DX", "CHEST", "CHEST_XRAY", None),
    ("CT", "CHEST", "CT_ABDOMEN_VOLUME", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
    ("MR", "BRAIN", "BRAIN_MRI_MULTISEQUENCE", None),
    ("MR", "BRAIN", "MRI", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
    ("XA", "HEAD", "ANGIOGRAPHY", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
    ("CT", "", "HEAD_CT", None),
])
def test_real_dicom_headers_detect_known_declaration_contradictions(tmp_path, modality, body, declared, expected):
    metadata = read_metadata(_dicom(tmp_path / "source.dcm", modality, body))
    assert model_router.metadata_conflicts(declared, metadata) == expected


def test_explicit_declaration_cannot_skip_metadata_before_model_selection(tmp_path, monkeypatch):
    path = _dicom(tmp_path / "source.dcm", "MR", "HEAD")
    upload = SimpleNamespace(id=1, stored_filename=path.name, file_path=str(path), modality=ModalityType.IMAGE,
                             is_associated=True, withdrawn_at=None, superseded_by_file_id=None)
    @contextmanager
    def materialize(source):
        yield source
    monkeypatch.setattr(model_router.upload_store, "materialize", materialize)
    monkeypatch.setattr(model_router.upload_store, "available", lambda _: True)
    def cannot_select():
        pytest.fail("contradictory metadata reached checkpoint selection")
    monkeypatch.setattr(model_router.model_inference, "_load_registry", cannot_select)
    result = model_router.plan_upload(upload, declared_input_type="HEAD_CT")
    assert result["status"] == "ABSTAIN"
    assert result["selected_model_id"] is None
    assert result["reason"] == "DICOM_MODALITY_CONTRADICTS_DECLARATION"


def test_raster_source_still_needs_context_and_never_guesses_filename(tmp_path, monkeypatch):
    path = tmp_path / "head-ct-brain.png"
    Image.new("L", (8, 8), 100).save(path)
    upload = SimpleNamespace(id=1, stored_filename=path.name, file_path=str(path), modality=ModalityType.IMAGE,
                             is_associated=True, withdrawn_at=None, superseded_by_file_id=None)
    monkeypatch.setattr(model_router.upload_store, "available", lambda _: True)
    assert model_router.plan_upload(upload)["reason"] == "SOURCE_INPUT_TYPE_REQUIRED"


def test_exif_quarter_turn_has_known_source_pixel_mapping(tmp_path):
    path = tmp_path / "orientation.png"
    image = Image.new("RGB", (5, 7), "black")
    image.putpixel((0, 0), (255, 0, 0))
    exif = image.getexif()
    exif[0x0112] = 6
    image.save(path, exif=exif)
    upright, applied = open_raster(path)
    assert applied == 6 and upright.size == (7, 5)
    assert upright.getpixel((6, 0)) == (255, 0, 0)
    assert read_metadata(path)["dimensions"] == [7, 5]


def test_direct_model_endpoint_cannot_bypass_body_tag_guard(client, test_users, db_session, tmp_path, monkeypatch):
    from app.models.entities import InferenceRun
    from tests.conftest import get_auth_headers
    headers = get_auth_headers(test_users["clinician_a"])
    case = client.post("/api/v1/cases", json={"pseudonymous_id": "REVIEW-SYNTHETIC-METADATA"}, headers=headers).json()["id"]
    path = _dicom(tmp_path / "wrong-body.dcm", "CT", "KNEE")
    uploaded = client.post(f"/api/v1/cases/{case}/uploads", files={"file": (path.name, path.read_bytes(), "application/dicom")},
                           data={"deidentified": "true"}, headers=headers)
    assert uploaded.status_code == 201, uploaded.text
    upload_id = uploaded.json()["id"]
    # The registry is a synthetic contract control; no checkpoint inference is claimed.
    monkeypatch.setattr(model_router.model_inference, "get_model", lambda _: {
        "display_name": "Synthetic head input contract", "inference_input": "image_2d", "supported_modalities": ["HEAD_CT"]})
    def cannot_execute(*args, **kwargs):
        pytest.fail("wrong-anatomy source reached preparation or inference")
    monkeypatch.setattr(model_router.model_inference, "prepare_input", cannot_execute)
    response = client.post(f"/api/v1/uploads/{upload_id}/research-inference",
                           json={"model_id": "synthetic-head-contract", "declared_input_type": "HEAD_CT"}, headers=headers)
    assert response.status_code == 400, response.text
    assert "DICOM_BODY_PART_CONTRADICTS_DECLARATION" in response.json()["detail"]
    assert db_session.query(InferenceRun).filter(InferenceRun.file_id == upload_id).count() == 0
