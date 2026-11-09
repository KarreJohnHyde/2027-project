"""Neighbouring-slice head CT models on an assembled DICOM series: windowing, stacking, per-slice applicability.

The network, its applicability reference and the DICOM slices are synthetic fixtures generated in the test
(a randomly initialised ResNet-18 and small Hounsfield arrays); none of it is patient evidence."""

import hashlib
import io
import json

import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

torch = pytest.importorskip("torch")
models = pytest.importorskip("torchvision.models")

from app.models.entities import Case  # noqa: E402
from app.services import image_ood, model_inference, model_registry  # noqa: E402
from tests.conftest import get_auth_headers  # noqa: E402

MODEL_ID = "test_head_ct_series_model"
KEYS = ("edh", "sdh", "iph", "ivh", "sah", "any")
NAMES = ["epidural", "subdural", "intraparenchymal", "intraventricular", "subarachnoid", "any intracranial haemorrhage"]
WINDOW = {"center": 40, "width": 80, "function": "LINEAR_EXACT", "rounding": "floor", "source": "test fixture"}


def _head(seed: int, size: int = 48) -> np.ndarray:
    """A synthetic head slice in HU: air, a skull ring and brain tissue around 30 HU with noise."""
    rng = np.random.default_rng(seed)
    grid = np.hypot(*(np.indices((size, size)) - (size - 1) / 2))
    hu = np.full((size, size), -1000.0)
    hu[grid < 0.45 * size] = 900.0
    hu[grid < 0.40 * size] = 30.0 + rng.normal(0, 6, (size, size))[grid < 0.40 * size]
    return hu


@pytest.fixture
def series_registry(tmp_path, monkeypatch):
    torch.manual_seed(0)
    network = models.resnet18(weights=None)
    network.fc = torch.nn.Linear(network.fc.in_features, len(KEYS))
    checkpoint = tmp_path / "model.pt"
    torch.save({"kind": "image_multilabel_classifier", "arch": "resnet18", "state_dict": network.state_dict(), "classes": NAMES,
                "label_keys": list(KEYS), "image_size": 48, "normalization": {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]},
                "thresholds": {key: 0.5 for key in KEYS}}, checkpoint)
    sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"test_n": 10, "mean_auroc": 0.5}), encoding="utf-8")
    entry = {"model_id": MODEL_ID, "display_name": "Synthetic head CT series model", "task": "multilabel_image_classification",
             "status": "READY_UNVALIDATED", "validated": False, "research_inference": True, "anatomy": "brain", "inference_input": "head_ct_series",
             "supported_modalities": ["HEAD_CT_SERIES"], "supported_classes": NAMES, "limitations": [], "dicom_window": WINDOW,
             "artifact_bundle": {"dataset_version": "fixture", "dataset_license": "CC0 (synthetic test fixture)", "split_manifest_path": str(report),
                                 "task_definition": "fixture", "label_definition": {"classes": NAMES}, "preprocessing_version": "fixture-v1",
                                 "checkpoint_path": str(checkpoint), "checkpoint_sha256": sha, "calibration": None, "decision_thresholds": None,
                                 "abstention_thresholds": None, "held_out_predictions_path": str(report), "evaluation_report_path": str(report),
                                 "model_card_path": str(report), "ood_reference_path": None, "ood_reference_sha256": None}}
    path = tmp_path / "models.json"

    def write():
        path.write_text(json.dumps({"schema_version": "1.0.0", "models": [entry]}), encoding="utf-8")
        model_registry._load_registry.cache_clear()

    monkeypatch.setattr(model_registry, "REGISTRY_PATH", path)
    write()
    loaded = model_inference.load_model(model_inference._load_registry()["models"][0])
    # The reference is fitted on stacked, windowed synthetic head slices through the served network.
    rows = []
    for seed in range(60):
        images = model_inference.series_slice_images(np.stack([_head(seed * 3 + offset) for offset in range(3)]), WINDOW)
        rows.append(model_inference.image_features(*loaded, images[1]))
    stages = [np.vstack([row[index] for row in rows]) for index in range(len(rows[0]))]
    reference = image_ood.fit_reference([stage[:40] for stage in stages], [stage[40:] for stage in stages], quantile=1.0,
                                        metadata={"checkpoint_sha256": sha, "feature_version": model_inference.FEATURE_VERSION})
    reference["threshold"] *= 3.0
    reference_path = tmp_path / "ood_reference.npz"
    entry["artifact_bundle"].update(ood_reference_path=str(reference_path), ood_reference_sha256=image_ood.save_reference(reference_path, reference))
    write()
    model_inference._load.cache_clear()
    yield entry
    model_registry._load_registry.cache_clear()
    model_inference._load.cache_clear()


def _slice_bytes(series_uid: str, z: float, hu: np.ndarray, instance: int, modality: str = "CT", normal_tilt: float = 0.0) -> bytes:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = pydicom.Dataset()
    ds.file_meta = meta
    ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    ds.SeriesInstanceUID, ds.StudyInstanceUID, ds.Modality, ds.InstanceNumber = series_uid, "1.2.826.0.1.3680043.10.1.2", modality, instance
    c, s = np.cos(np.radians(normal_tilt)), np.sin(np.radians(normal_tilt))
    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, c, -s]
    normal = np.cross([1.0, 0.0, 0.0], [0.0, c, -s])
    ds.ImagePositionPatient = [float(value) for value in normal * z]
    ds.PixelSpacing = [0.5, 0.5]
    ds.Rows, ds.Columns = hu.shape
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
    ds.RescaleSlope, ds.RescaleIntercept = 1, -1024
    ds.PixelData = (np.round(hu) + 1024).astype(np.uint16).tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def _upload_series(client, headers, case_id, slices, **kwargs):
    series = generate_uid()
    ids = []
    for index, hu in enumerate(slices):
        response = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"},
                               files={"file": (f"h{index}.dcm", _slice_bytes(series, 5.0 * index, hu, index + 1, **kwargs), "application/dicom")})
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    return ids


def test_slices_are_windowed_and_stacked_with_their_neighbours():
    hu = np.stack([np.full((2, 2), value, np.float32) for value in (0.0, 40.0, 80.0)])
    images = model_inference.series_slice_images(hu, WINDOW)
    # Channels: slice below, the slice, slice above; the ends repeat the slice itself. 40 HU -> floor(127.5) = 127.
    assert [list(np.asarray(image)[0, 0]) for image in images] == [[0, 0, 127], [0, 127, 255], [127, 255, 255]]


def test_a_head_ct_series_is_analysed_slice_by_slice(client, db_session, test_users, series_registry):
    owner = test_users["clinician_a"]
    case = Case(pseudonymous_id="HEAD-CT-SERIES", created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()
    headers = get_auth_headers(owner)
    ids = _upload_series(client, headers, case.id, [_head(500 + index) for index in range(4)])
    single = client.post(f"/api/v1/uploads/{ids[0]}/research-inference", json={"model_id": MODEL_ID, "declared_input_type": "HEAD_CT_SERIES"},
                         headers=headers)
    assert single.status_code == 400 and "assembled DICOM series" in single.json()["detail"]
    response = client.post(f"/api/v1/cases/{case.id}/dicom-series/research-inference", headers=headers,
                           json={"upload_ids": ids, "model_id": MODEL_ID, "declared_input_type": "HEAD_CT_SERIES"})
    assert response.status_code == 201, response.text
    output = response.json()["research_output"]
    assert output["type"] == "series_slice_multilabel" and len(output["slices"]) == 4
    assert output["slices_analysed"] + output["slices_refused"] == 4 and output["slices_analysed"] >= 2
    assert [item["upload_id"] for item in output["slices"]] == ids
    series_level = output["series_level"]
    assert series_level["label"] == "any intracranial haemorrhage" and output["window"]["width"] == 80
    assert series_level["complete_coverage"] == (output["slices_refused"] == 0) and series_level["coverage"].endswith("of 4 slices")
    check = output["input_content_check"]
    assert check["series_geometry"]["status"] == "PASSED" and check["distribution"]["status"] == "PASSED"


def test_slices_are_put_in_ascending_patient_z_as_in_training():
    model = {"dicom_window": WINDOW}
    volume = np.stack([np.full((4, 4), value, np.float32) for value in (10.0, 20.0, 30.0)])
    report = {"modality_tags": ["CT"], "shape_slices_rows_columns": [3, 4, 4], "volume": volume, "ordered_upload_ids": [7, 8, 9],
              "slice_normal_lps": [0.0, 0.0, -1.0]}  # the series runs down the body
    prepared = model_inference.prepare_head_ct_series(model, report)
    assert prepared.ordered_upload_ids == [9, 8, 7] and prepared.hounsfield[:, 0, 0].tolist() == [30.0, 20.0, 10.0]
    assert "reversed" in prepared.checks["slice_order"]
    upward = model_inference.prepare_head_ct_series(model, {**report, "slice_normal_lps": [0.0, 0.0, 1.0]})
    assert upward.ordered_upload_ids == [7, 8, 9]


def test_head_ct_series_refusals(client, db_session, test_users, series_registry):
    owner = test_users["clinician_a"]
    case = Case(pseudonymous_id="HEAD-CT-SERIES-REFUSED", created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()
    headers = get_auth_headers(owner)
    url = f"/api/v1/cases/{case.id}/dicom-series/research-inference"
    coronal = _upload_series(client, headers, case.id, [_head(600 + index) for index in range(4)], normal_tilt=80.0)
    refused = client.post(url, headers=headers, json={"upload_ids": coronal, "model_id": MODEL_ID, "declared_input_type": "HEAD_CT_SERIES"})
    assert refused.status_code == 400 and "NOT_AN_AXIAL_STACK" in refused.json()["detail"]
    # Constant-brightness slices (no anatomy) are outside the reference: the series is refused, not analysed. (Checked on the
    # service: the refusal happens inside the queued job, and this test database cannot roll back a failed job's transaction.)
    model = model_inference.get_model(MODEL_ID)
    flat = model_inference.HeadCtSeries(np.full((4, 48, 48), 2000.0, np.float32), [1, 2, 3, 4], {"status": "PASSED"})
    with pytest.raises(model_inference.InferenceNotPermitted, match="MODEL_INPUT_OUT_OF_DISTRIBUTION: 4 of 4 slices"):
        model_inference.run_head_ct_series(model, flat)
