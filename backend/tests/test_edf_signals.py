"""EDF/EDF+/BDF reading. Every recording here is synthesised in the test (sine waves, a ramp and
annotations); the patient field carries a marker that must never be returned."""

import math

import numpy as np
import pytest

from app.services import edf_reader
from tests.conftest import get_auth_headers

MARKER = "SYNTHETIC-PATIENT-FIELD-MARKER"


def _field(value, width):
    data = str(value).encode("ascii")
    assert len(data) <= width
    return data.ljust(width, b" ")


def build(signals, records=3, record_duration=1.0, patient=MARKER, reserved="", bdf=False, annotation_records=None, records_field=None):
    """signals: list of dicts with label, samples (per record), physical/digital ranges, unit, values (all samples, digital)."""
    count = len(signals) + (1 if annotation_records else 0)
    head = (b"\xffBIOSEMI" if bdf else _field("0", 8)) + _field(patient, 80) + _field("Startdate X X X X", 80)
    head += _field("03.02.26", 8) + _field("09.15.00", 8) + _field(256 * (count + 1), 8) + _field(reserved, 44)
    head += _field(records if records_field is None else records_field, 8) + _field(record_duration, 8) + _field(count, 4)
    entries = list(signals)
    if annotation_records:
        entries.append({"label": "BDF Annotations" if bdf else "EDF Annotations", "samples": 30, "unit": "", "pmin": -1, "pmax": 1,
                        "dmin": -32768, "dmax": 32767})
    for key, width in (("label", 16), ("transducer", 80), ("unit", 8), ("pmin", 8), ("pmax", 8), ("dmin", 8), ("dmax", 8),
                       ("prefilter", 80), ("samples", 8), ("reserved", 32)):
        head += b"".join(_field(entry.get(key, ""), width) for entry in entries)
    width = 3 if bdf else 2
    body = b""
    for record in range(records):
        for signal in signals:
            chunk = signal["values"][record * signal["samples"]:(record + 1) * signal["samples"]]
            if bdf:
                body += b"".join(int(v).to_bytes(3, "little", signed=True) for v in chunk)
            else:
                body += np.asarray(chunk, dtype="<i2").tobytes()
        if annotation_records:
            body += annotation_records[record].ljust(30 * width, b"\x00")
    return head + body


def _sine_signal(rate=256, records=3):
    t = np.arange(rate * records) / rate
    physical = 100.0 * np.sin(2 * math.pi * 10 * t)  # µV
    digital = np.round((physical + 200.0) / 400.0 * 65535 - 32768).astype(int)
    return {"label": "EEG Fp1-REF", "samples": rate, "unit": "uV", "pmin": -200, "pmax": 200, "dmin": -32768, "dmax": 32767,
            "transducer": "AgAgCl electrode", "prefilter": "HP:0.1Hz LP:70Hz", "values": digital.tolist()}, physical


def test_header_preview_and_physical_values(tmp_path):
    sine, physical = _sine_signal()
    ramp = {"label": "Temp", "samples": 4, "unit": "degC", "pmin": 30, "pmax": 40, "dmin": 0, "dmax": 1000, "values": list(range(0, 1200, 100))}
    path = tmp_path / "rec.edf"
    path.write_bytes(build([sine, ramp]))
    header = edf_reader.read_file_header(path)
    assert (header.format, header.records, header.record_duration_s, header.patient_field) == ("EDF", 3, 1.0, "FILLED_NOT_SHOWN")
    assert [(s.label, s.sampling_rate_hz) for s in header.data_signals] == [("EEG Fp1-REF", 256.0), ("Temp", 4.0)]
    assert header.start.isoformat() == "2026-02-03T09:15:00"
    window = edf_reader.preview(path, header, start_s=0.5, duration_s=1.0, max_points=5000)
    eeg = window["channels"][0]
    assert eeg["points"] == 256 and eeg["unit"] == "uV"
    np.testing.assert_allclose(eeg["min"], physical[128:384], atol=400 / 65535 + 1e-3)
    temperature = window["channels"][1]
    np.testing.assert_allclose(temperature["min"], [30 + v / 100 for v in range(200, 600, 100)], atol=1e-6)
    reduced = edf_reader.preview(path, header, start_s=0.0, duration_s=3.0, channels=[0], max_points=100)
    assert reduced["channels"][0]["points"] <= 100 and reduced["channels"][0]["window_max"] == pytest.approx(100.0, abs=0.01)


def test_edf_plus_annotations_and_bdf_24_bit(tmp_path):
    sine, _ = _sine_signal(rate=128)
    tals = [b"+0\x14\x14\x00", b"+1\x14\x14\x00+1.5\x150.5\x14Eyes closed\x14\x00", b"+2\x14\x14\x00"]
    path = tmp_path / "rec.edf"
    path.write_bytes(build([sine], reserved="EDF+C", annotation_records=tals))
    header = edf_reader.read_file_header(path)
    assert header.format == "EDF+C" and len(header.data_signals) == 1
    assert edf_reader.annotations(path, header) == [{"onset_s": 1.5, "duration_s": 0.5, "text": "Eyes closed"}]
    values = [-8388608, -1, 0, 1, 8388607, -5000] * 2
    bdf = {"label": "EEG Cz", "samples": 6, "unit": "uV", "pmin": -262144, "pmax": 262143, "dmin": -8388608, "dmax": 8388607, "values": values}
    path = tmp_path / "rec.bdf"
    path.write_bytes(build([bdf], records=2, bdf=True))
    header = edf_reader.read_file_header(path)
    assert header.format == "BDF" and header.bytes_per_sample == 3
    window = edf_reader.preview(path, header, start_s=0.0, duration_s=1.0, max_points=5000)
    gain = (262143 + 262144) / (8388607 + 8388608)
    np.testing.assert_allclose(window["channels"][0]["min"], [(v + 8388608) * gain - 262144 for v in values[:6]], rtol=1e-5, atol=1e-6)


@pytest.mark.parametrize("mutate, code", [
    (lambda data: data[:-10], "EDF_SIZE_MISMATCH"),
    (lambda data: data[:184] + b"999     " + data[192:], "EDF_HEADER_LENGTH_MISMATCH"),
    (lambda data: b"9       " + data[8:], "EDF_SIGNATURE_INVALID"),
])
def test_structural_errors_are_refused(tmp_path, mutate, code):
    sine, _ = _sine_signal()
    with pytest.raises(edf_reader.EdfError, match=code):
        edf_reader.read_header(mutate(build([sine])))


def test_upload_analysis_and_api_never_return_the_patient_field(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-EDF"}, headers=headers).json()["id"]
    sine, _ = _sine_signal()
    tals = [b"+0\x14\x14\x00+0.2\x14Photic stimulation\x14\x00", b"+1\x14\x14\x00", b"+2\x14\x14\x00"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("rec.edf", build([sine], reserved="EDF+C", annotation_records=tals), "application/octet-stream")},
                         data={"deidentified": "true"}, headers=headers)
    assert upload.status_code == 201, upload.text
    assert upload.json()["modality"] == "SIGNAL"
    upload_id = upload.json()["id"]
    info = client.get(f"/api/v1/uploads/{upload_id}/signal", headers=headers)
    assert info.status_code == 200, info.text
    body = info.text
    assert MARKER not in body
    data = info.json()
    assert data["format"] == "EDF+C" and data["patient_identification_field"] == "FILLED_NOT_SHOWN" and data["warnings"]
    assert data["annotations"] == [{"onset_s": 0.2, "duration_s": None, "text": "Photic stimulation"}]
    preview = client.get(f"/api/v1/uploads/{upload_id}/signal/preview", params={"start": 1, "duration": 2, "max_points": 200}, headers=headers)
    assert preview.status_code == 200 and preview.json()["channels"][0]["label"] == "EEG Fp1-REF"
    assert client.post(f"/api/v1/uploads/{upload_id}/analysis-jobs", headers=headers).status_code == 201
    findings = client.get(f"/api/v1/cases/{case_id}/findings", headers=headers).json()
    finding = next(item for item in findings if item.get("modality") == "SIGNAL")
    assert finding["label"] == "READ_NO_MODEL" and MARKER not in str(finding)


def test_edf_upload_with_a_broken_structure_is_refused(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-EDF-BAD"}, headers=headers).json()["id"]
    sine, _ = _sine_signal()
    for body in (build([sine])[:-7], b"not an edf file at all" * 20):
        refused = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("rec.edf", body, "application/octet-stream")},
                              data={"deidentified": "true"}, headers=headers)
        assert refused.status_code == 415, refused.text
