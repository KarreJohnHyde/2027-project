"""Upload inference for the 12-lead ECG classifier and the cardiac-MRI volume segmenter:
exact input readers, fail-closed contract checks, and the gated research-inference route.

Every signal, volume, checkpoint and report here is a synthetic fixture created inside the
test (randomly initialised networks); none of it is patient evidence or a model result."""

import hashlib
import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")
nib = pytest.importorskip("nibabel")
pytest.importorskip("monai")

from app.services import ecg_inference, model_inference, model_registry, volume_inference  # noqa: E402
from app.services.ecg_inference import PTBXL_LEADS, EcgInputError  # noqa: E402
from app.services.volume_inference import VolumeInputError  # noqa: E402
from tests.conftest import get_auth_headers  # noqa: E402

CONTRACT = ecg_inference.CONTRACTS["wfdb16-100hz-10s-leadstd-v1"]
ENVELOPE = {"dataset_version": "fixture", "in_plane_spacing_mm": {"min": 1.0, "max": 2.0}, "slice_spacing_mm": {"min": 5.0, "max": 10.0},
            "matrix": {"i": {"min": 8, "max": 64}, "j": {"min": 8, "max": 64}, "k": {"min": 4, "max": 12}}}


def _signal(seed=3, samples=1000, leads=12):
    return np.random.default_rng(seed).normal(0.0, 0.2, size=(samples, leads))


def _wfdb(signal_mv, leads, fs=100, gain=1000.0, unit="mV", fmt="16", with_checksums=True):
    """A WFDB header and format-16 signal file, with the checksums a WFDB writer records."""
    digital = np.round(signal_mv * gain * (1000.0 if unit == "uV" else 1.0)).astype("<i2")
    lines = [f"rec {len(leads)} {fs:g} {digital.shape[0]}"]
    for column, lead in enumerate(leads):
        checksum = int(digital[:, column].astype(np.int64).sum()) % 65536
        checksum = checksum - 65536 if checksum > 32767 else checksum
        base = f"rec.dat {fmt} {gain:g}(0)/{unit} 16 0"
        lines.append(f"{base} {int(digital[0, column])} {checksum} 0 {lead}" if with_checksums else base)
    return ("\n".join(lines) + "\n").encode("ascii"), digital.tobytes()


def test_wfdb_reader_returns_physical_millivolts_in_ptbxl_lead_order():
    signal = _signal()
    shuffled = [PTBXL_LEADS[index] for index in (11, 0, 5, 1, 2, 3, 4, 6, 7, 8, 9, 10)]
    names = [{"AVR": "aVR", "AVL": "aVL", "AVF": "aVF"}.get(lead, lead) for lead in shuffled]  # vendor spelling
    header, data = _wfdb(signal, names)
    record = ecg_inference.check_record(ecg_inference.read_wfdb(header, data), CONTRACT)
    assert record.leads == PTBXL_LEADS
    expected = np.round(signal * 1000) / 1000
    for column, lead in enumerate(shuffled):
        assert np.allclose(record.signal_mv[:, PTBXL_LEADS.index(lead)], expected[:, column], atol=1e-6)
    assert any("reordered" in note for note in record.notes)

    micro_header, micro_data = _wfdb(signal[:, :12], PTBXL_LEADS, gain=1.0, unit="uV")
    micro = ecg_inference.read_wfdb(micro_header, micro_data)
    assert np.allclose(micro.signal_mv, np.round(signal * 1000) / 1000, atol=1e-6), "uV records are converted to mV"


def test_header_checksums_prove_the_signal_file_belongs_to_the_header():
    header, _ = _wfdb(_signal(seed=1), PTBXL_LEADS)
    _, other = _wfdb(_signal(seed=2), PTBXL_LEADS)
    with pytest.raises(EcgInputError) as error:
        ecg_inference.read_wfdb(header, other)
    assert error.value.code == "WFDB_CHECKSUM_MISMATCH"
    bare, data = _wfdb(_signal(), PTBXL_LEADS, with_checksums=False)
    with pytest.raises(EcgInputError) as error:
        ecg_inference.read_wfdb(bare, data)
    assert error.value.code == "WFDB_HEADER_INCOMPLETE"


@pytest.mark.parametrize("change, code", [
    ({"fs": 500}, "SAMPLING_RATE_OUT_OF_SCOPE"),
    ({"samples": 900}, "DURATION_OUT_OF_SCOPE"),
    ({"leads": PTBXL_LEADS[:11]}, "LEAD_SET_OUT_OF_SCOPE"),
    ({"leads": PTBXL_LEADS[:11] + ["V7"]}, "LEAD_SET_OUT_OF_SCOPE"),
    ({"scale": 60.0}, "SIGNAL_QUALITY_AMPLITUDE"),
    ({"flat": 4}, "SIGNAL_QUALITY_FLATLINE"),
])
def test_records_outside_the_trained_contract_are_refused(change, code):
    leads = change.get("leads", PTBXL_LEADS)
    signal = _signal(samples=change.get("samples", 1000), leads=len(leads)) * change.get("scale", 1.0)
    if "flat" in change:
        signal[:, change["flat"]] = 0.0
    header, data = _wfdb(signal, leads, fs=change.get("fs", 100), gain=200.0 if "scale" in change else 1000.0)
    with pytest.raises(EcgInputError) as error:
        ecg_inference.check_record(ecg_inference.read_wfdb(header, data), CONTRACT)
    assert error.value.code == code


def test_invalid_samples_and_unsupported_formats_are_refused():
    signal = _signal()
    header, data = _wfdb(signal, PTBXL_LEADS)
    digital = np.frombuffer(data, dtype="<i2").copy().reshape(1000, 12)
    digital[10, 3] = -32768
    lines = header.decode().splitlines()
    checksum = int(digital[:, 3].astype(np.int64).sum()) % 65536
    fields = lines[4].split()
    fields[6] = str(checksum - 65536 if checksum > 32767 else checksum)
    lines[4] = " ".join(fields)
    with pytest.raises(EcgInputError) as error:
        ecg_inference.read_wfdb(("\n".join(lines) + "\n").encode(), digital.tobytes())
    assert error.value.code == "MISSING_SAMPLES"
    packed, data = _wfdb(signal, PTBXL_LEADS, fmt="212")
    with pytest.raises(EcgInputError) as error:
        ecg_inference.read_wfdb(packed, data)
    assert error.value.code == "UNSUPPORTED_WFDB_FORMAT"


def test_csv_records_need_a_time_column_and_a_declared_unit():
    signal = _signal()
    rows = ["time_s," + ",".join(f"Lead_{lead}" for lead in ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"])]
    rows += [f"{index / 100:.2f}," + ",".join(f"{value * 1000:.1f}" for value in sample) for index, sample in enumerate(signal)]
    content = ("\n".join(rows) + "\n").encode()
    record = ecg_inference.check_record(ecg_inference.read_csv(content, "uV"), CONTRACT)
    assert record.sampling_rate_hz == pytest.approx(100.0) and np.allclose(record.signal_mv, np.round(signal * 1000, 1) / 1000, atol=1e-6)
    with pytest.raises(EcgInputError) as error:
        ecg_inference.read_csv(content.replace(b"time_s,", b"sample_no,"), "mV")
    assert error.value.code == "SAMPLING_RATE_NOT_DOCUMENTED", "the sampling rate is never assumed"


def _nifti(path, shape=(24, 20, 6), zooms=(1.5, 1.5, 8.0), unit="mm", seed=0):
    data = np.random.default_rng(seed).normal(100.0, 20.0, size=shape).astype(np.float32)
    image = nib.Nifti1Image(data, np.diag([-1.0, -1.0, 1.0, 1.0]))
    image.header.set_zooms(zooms)
    image.header.set_xyzt_units(xyz=unit)
    nib.save(image, str(path))
    return path


@pytest.mark.parametrize("kwargs, code", [
    ({"shape": (24, 20, 6, 3), "zooms": (1.5, 1.5, 8.0, 1.0)}, "FOUR_D_VOLUME"),
    ({"zooms": (1.5, 1.2, 8.0)}, "NONSQUARE_IN_PLANE_PIXELS"),
    ({"zooms": (8.0, 8.0, 1.5)}, "SLICE_AXIS_NOT_LAST"),
    ({"zooms": (2.5, 2.5, 8.0)}, "IN_PLANE_SPACING_OUTSIDE_DEVELOPMENT_RANGE"),
    ({"zooms": (1.5, 1.5, 3.0)}, "SLICE_SPACING_OUTSIDE_DEVELOPMENT_RANGE"),
])
def test_volumes_outside_the_development_envelope_are_refused(tmp_path, kwargs, code):
    path = _nifti(tmp_path / "frame.nii.gz", **kwargs)
    with pytest.raises(VolumeInputError) as error:
        volume_inference.read_volume(path, ENVELOPE)
    assert code in error.value.codes


def test_spatial_units_are_converted_and_undeclared_units_are_flagged(tmp_path):
    metres = volume_inference.read_volume(_nifti(tmp_path / "m.nii.gz", zooms=(0.0015, 0.0015, 0.008), unit="meter"), ENVELOPE)
    assert metres.spacing_mm == pytest.approx((1.5, 1.5, 8.0)) and metres.warnings == []
    unknown = volume_inference.read_volume(_nifti(tmp_path / "u.nii.gz", unit="unknown"), ENVELOPE)
    assert unknown.warnings and unknown.warnings[0].startswith("SPATIAL_UNIT_NOT_DECLARED")


def test_slice_masks_are_in_the_viewers_axial_display_pixels():
    from pycocotools import mask as coco_mask

    mask = np.zeros((6, 5, 3), dtype=np.uint8)  # (i, j, k)
    mask[2:4, 1, 1] = 3
    payload = {"labels": [{"id": 0, "name": "background"}, {"id": 1, "name": "a"}, {"id": 2, "name": "b"}, {"id": 3, "name": "c"}]}
    volume = volume_inference.VolumeInput(np.zeros((6, 5, 3), np.float32), (1.5, 1.5, 8.0))
    output = volume_inference.segmentation_output(mask, payload, volume, {}, torch.device("cpu"))
    assert [item["voxels"] for item in output["structures"]] == [0, 0, 2]
    assert output["structures"][2]["volume_ml"] == pytest.approx(2 * 1.5 * 1.5 * 8.0 / 1000, abs=1e-3)
    segment = output["slices"][1]["segments"][0]
    decoded = coco_mask.decode({"size": segment["rle"]["size"], "counts": segment["rle"]["counts"].encode("ascii")})
    assert decoded.shape == (5, 6), "rows are j and columns are i, as the viewer renders axial index planes"
    assert decoded[1, 2] == 1 and decoded[1, 3] == 1 and decoded.sum() == 2


def _report(path, body):
    path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


@pytest.fixture
def signal_volume_registry(tmp_path, monkeypatch):
    from monai.networks.nets import UNet

    torch.manual_seed(0)
    ecg_network = ecg_inference.build_network(5)
    ecg_checkpoint = tmp_path / "ecg.pt"
    torch.save({"kind": "ecg_classifier", "arch": "resnet1d_compact", "state_dict": ecg_network.state_dict(), "classes": ["NORM", "MI", "STTC", "CD", "HYP"],
                "leads": PTBXL_LEADS, "sampling_rate_hz": 100, "samples": 1000, "lead_mean_mv": [0.0] * 12, "lead_std_mv": [0.2] * 12,
                "platt": [[1.0, 0.0]] * 5, "thresholds": [0.5] * 5}, ecg_checkpoint)
    architecture = {"name": "monai.networks.nets.UNet", "spatial_dims": 3, "in_channels": 1, "out_channels": 4, "channels": [4, 8], "strides": [2], "num_res_units": 1}
    volume_network = UNet(spatial_dims=3, in_channels=1, out_channels=4, channels=(4, 8), strides=(2,), num_res_units=1, norm="batch")
    volume_checkpoint = tmp_path / "volume.pt"
    torch.save({"kind": "volumetric_semantic_segmenter", "trainer_version": "volumetric-monai-unet-v1", "state_dict": volume_network.state_dict(),
                "best_state_dict": volume_network.state_dict(), "optimizer_state_dict": {}, "architecture": architecture, "patch_size": [16, 16, 8],
                "labels": [{"id": 0, "name": "background"}, {"id": 1, "name": "right_ventricular_cavity"}, {"id": 2, "name": "myocardium"},
                           {"id": 3, "name": "left_ventricular_cavity"}]}, volume_checkpoint)
    card = tmp_path / "card.md"
    card.write_text("# Synthetic test fixture\n", encoding="utf-8")
    envelope = _report(tmp_path / "envelope.json", ENVELOPE)
    reports = {
        "ecg": _report(tmp_path / "ecg.json", {"test_n": 20, "metrics": {"macro_auroc": 0.8, "macro_auprc": 0.6, "macro_f1_at_validation_thresholds": 0.5}}),
        "volume": _report(tmp_path / "volume.json", {"test_n": 4, "test_patients": 2, "metrics": {"mean_case_macro_dice": 0.8, "per_structure": {
            "left_ventricular_cavity": {"mean_dice": 0.9}, "myocardium": {"mean_dice": 0.8}, "right_ventricular_cavity": {"mean_dice": 0.7}}},
            "clinical_indices": {"lv_ef_percent": {"mean_absolute_error": 4.0}, "lv_edv_ml": {"n_patients": 2, "bias": 5.0, "limits_of_agreement": [-1.0, 11.0]}}}),
    }

    def entry(model_id, task, kind, modality, checkpoint, report, preprocessing, **bundle_extra):
        return {"model_id": model_id, "display_name": model_id, "task": task, "status": "READY_UNVALIDATED", "validated": False, "research_inference": True,
                "inference_input": kind, "anatomy": "heart", "supported_modalities": [modality], "supported_classes": [], "limitations": [],
                "artifact_bundle": {"dataset_version": "fixture", "dataset_license": "CC0 (synthetic test fixture)", "split_manifest_path": report,
                                    "task_definition": "fixture", "label_definition": {}, "preprocessing_version": preprocessing,
                                    "checkpoint_path": str(checkpoint), "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                                    "calibration": None, "decision_thresholds": None, "abstention_thresholds": None, "held_out_predictions_path": report,
                                    "evaluation_report_path": report, "model_card_path": str(card), **bundle_extra}}

    models = [entry("fixture_ecg", "multilabel_ecg_classification", "ecg_12lead", "ECG", ecg_checkpoint, reports["ecg"], "wfdb16-100hz-10s-leadstd-v1"),
              entry("fixture_volume", "volumetric_semantic_segmentation", "volume_nifti", "MRI", volume_checkpoint, reports["volume"],
                    "nifti-native-grid-nonzero-zscore-v1", input_envelope_path=envelope)]
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"schema_version": "1.0.0", "models": models}), encoding="utf-8")
    monkeypatch.setattr(model_registry, "REGISTRY_PATH", path)
    model_registry._load_registry.cache_clear()
    model_inference._load.cache_clear()
    yield {"path": path, "models": models}
    model_registry._load_registry.cache_clear()
    model_inference._load.cache_clear()


def _case(client, headers, pseudonym):
    return client.post("/api/v1/cases", json={"pseudonymous_id": pseudonym}, headers=headers).json()["id"]


def _upload(client, headers, case_id, name, body, mime="application/octet-stream"):
    response = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (name, body, mime)}, data={"deidentified": "true"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_ecg_research_inference_runs_on_a_wfdb_pair_and_refuses_out_of_contract_records(client, test_users, signal_volume_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = _case(client, headers, "CASE-ECG-FIXTURE")
    header, data = _wfdb(_signal(), PTBXL_LEADS)
    header_id = _upload(client, headers, case_id, "rec.hea", header, "text/plain")
    signal_id = _upload(client, headers, case_id, "rec.dat", data)
    url = f"/api/v1/uploads/{header_id}/research-inference"

    missing = client.post(url, json={"model_id": "fixture_ecg", "declared_input_type": "ECG"}, headers=headers)
    assert missing.status_code == 400 and "WFDB_SIGNAL_FILE_REQUIRED" in missing.json()["detail"]
    run = client.post(url, json={"model_id": "fixture_ecg", "declared_input_type": "ECG", "companion_upload_id": signal_id}, headers=headers)
    assert run.status_code == 201, run.text
    output = run.json()["research_output"]
    assert output["type"] == "ecg_multilabel" and [item["class"] for item in output["classes"]] == ["NORM", "MI", "STTC", "CD", "HYP"]
    assert all(0.0 <= item["probability"] <= 1.0 for item in output["classes"])
    assert output["input"]["sampling_rate_hz"] == 100 and output["input"]["samples"] == 1000
    provenance = run.json()["research_provenance"]
    assert provenance["companion_file_id"] == signal_id and provenance["output_status"] == "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED"
    again = client.post(url, json={"model_id": "fixture_ecg", "declared_input_type": "ECG", "companion_upload_id": signal_id}, headers=headers)
    assert again.json()["research_output"]["classes"] == output["classes"], "deterministic for the same input"

    fast_header, fast_data = _wfdb(_signal(samples=5000), PTBXL_LEADS, fs=500)
    fast_id = _upload(client, headers, case_id, "fast.hea", fast_header, "text/plain")
    fast_signal = _upload(client, headers, case_id, "fast.dat", fast_data)
    refused = client.post(f"/api/v1/uploads/{fast_id}/research-inference",
                          json={"model_id": "fixture_ecg", "declared_input_type": "ECG", "companion_upload_id": fast_signal}, headers=headers)
    assert refused.status_code == 400 and "SAMPLING_RATE_OUT_OF_SCOPE" in refused.json()["detail"]

    other_case = _case(client, headers, "CASE-ECG-OTHER")
    foreign = _upload(client, headers, other_case, "rec.dat", data)
    cross = client.post(url, json={"model_id": "fixture_ecg", "declared_input_type": "ECG", "companion_upload_id": foreign}, headers=headers)
    assert cross.status_code == 400, "a signal file from another case is never paired"


def test_volume_research_inference_segments_one_frame_inside_the_envelope(client, test_users, signal_volume_registry, tmp_path):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = _case(client, headers, "CASE-MRI-FIXTURE")
    frame = _nifti(tmp_path / "frame.nii.gz").read_bytes()
    upload_id = _upload(client, headers, case_id, "frame.nii.gz", frame, "application/gzip")
    url = f"/api/v1/uploads/{upload_id}/research-inference"

    run = client.post(url, json={"model_id": "fixture_volume", "declared_input_type": "MRI"}, headers=headers)
    assert run.status_code == 201, run.text
    output = run.json()["research_output"]
    assert output["type"] == "volume_segmentation" and output["volume_shape_ijk"] == [24, 20, 6]
    assert len(output["slices"]) == 6 and output["voxel_spacing_mm"] == [1.5, 1.5, 8.0]
    for structure in output["structures"]:
        per_slice = sum(segment["area_px"] for item in output["slices"] for segment in item["segments"] if segment["class_index"] == structure["class_index"])
        assert per_slice == structure["voxels"]
        assert structure["volume_ml"] == pytest.approx(structure["voxels"] * 1.5 * 1.5 * 8.0 / 1000, abs=1e-3)
    assert output["held_out_volume_agreement"]["lv_edv_ml"]["bias_ml"] == 5.0
    assert run.json()["research_provenance"]["output_status"] == "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED"

    wide = _upload(client, headers, case_id, "wide.nii.gz", _nifti(tmp_path / "wide.nii.gz", zooms=(3.0, 3.0, 8.0)).read_bytes(), "application/gzip")
    refused = client.post(f"/api/v1/uploads/{wide}/research-inference", json={"model_id": "fixture_volume", "declared_input_type": "MRI"}, headers=headers)
    assert refused.status_code == 400 and "IN_PLANE_SPACING_OUTSIDE_DEVELOPMENT_RANGE" in refused.json()["detail"]
    wrong_type = client.post(url, json={"model_id": "fixture_volume", "declared_input_type": "CT"}, headers=headers)
    assert wrong_type.status_code == 400 and "trained only on" in wrong_type.json()["detail"]


def test_volume_inference_is_refused_without_a_recorded_envelope(client, test_users, signal_volume_registry, tmp_path):
    registry = json.loads(signal_volume_registry["path"].read_text(encoding="utf-8"))
    registry["models"][1]["artifact_bundle"].pop("input_envelope_path")
    signal_volume_registry["path"].write_text(json.dumps(registry), encoding="utf-8")
    model_registry._load_registry.cache_clear()
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = _case(client, headers, "CASE-MRI-NOENVELOPE")
    upload_id = _upload(client, headers, case_id, "frame.nii.gz", _nifti(tmp_path / "frame.nii.gz").read_bytes(), "application/gzip")
    refused = client.post(f"/api/v1/uploads/{upload_id}/research-inference", json={"model_id": "fixture_volume", "declared_input_type": "MRI"}, headers=headers)
    assert refused.status_code == 400 and "INPUT_ENVELOPE_MISSING" in refused.json()["detail"]
