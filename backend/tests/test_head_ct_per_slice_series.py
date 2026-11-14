"""A single-slice head CT model registered with series_inference "head_ct_per_slice" runs slice by slice over an assembled
axial head CT series, with the same images as its external series evaluation; without the opt-in it refuses series.

The network, its applicability reference and the DICOM slices are synthetic fixtures generated in the test (a randomly
initialised ResNet-18 and small Hounsfield arrays); none of it is patient evidence."""

import hashlib
import json

import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch")
models = pytest.importorskip("torchvision.models")

from app.models.entities import Case  # noqa: E402
from app.services import image_ood, model_inference, model_registry  # noqa: E402
from tests.conftest import get_auth_headers  # noqa: E402
from tests.test_head_ct_series import KEYS, NAMES, WINDOW, _head, _upload_series  # noqa: E402

MODEL_ID = "test_head_ct_single_slice_model"


@pytest.fixture
def per_slice_registry(tmp_path, monkeypatch):
    torch.manual_seed(1)
    network = models.resnet18(weights=None)
    network.fc = torch.nn.Linear(network.fc.in_features, len(KEYS))
    checkpoint = tmp_path / "model.pt"
    torch.save({"kind": "image_multilabel_classifier", "arch": "resnet18", "state_dict": network.state_dict(), "classes": NAMES,
                "label_keys": list(KEYS), "image_size": 48, "normalization": {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]},
                "thresholds": {key: 0.5 for key in KEYS}}, checkpoint)
    sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"test_n": 10, "mean_auroc": 0.5}), encoding="utf-8")
    entry = {"model_id": MODEL_ID, "display_name": "Synthetic single-slice head CT model", "task": "multilabel_image_classification",
             "status": "READY_UNVALIDATED", "validated": False, "research_inference": True, "anatomy": "brain", "inference_input": "image_2d",
             "supported_modalities": ["HEAD_CT"], "supported_classes": NAMES, "limitations": [], "dicom_window": WINDOW,
             "series_inference": "head_ct_per_slice",
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
    # The reference is fitted on single windowed synthetic head slices through the served network, as the model reads them.
    rows = [model_inference.image_features(*loaded, model_inference.series_model_images(entry, _head(seed)[None])[0]) for seed in range(60)]
    stages = [np.vstack([row[index] for row in rows]) for index in range(len(rows[0]))]
    reference = image_ood.fit_reference([stage[:40] for stage in stages], [stage[40:] for stage in stages], quantile=1.0,
                                        metadata={"checkpoint_sha256": sha, "feature_version": model_inference.FEATURE_VERSION})
    reference["threshold"] *= 3.0
    reference_path = tmp_path / "ood_reference.npz"
    entry["artifact_bundle"].update(ood_reference_path=str(reference_path), ood_reference_sha256=image_ood.save_reference(reference_path, reference))
    write()
    model_inference._load.cache_clear()
    yield {"entry": entry, "write": write}
    model_registry._load_registry.cache_clear()
    model_inference._load.cache_clear()


def _case(db_session, owner, name):
    case = Case(pseudonymous_id=name, created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()
    return case


def test_per_slice_images_match_the_external_series_evaluation():
    model = {"inference_input": "image_2d", "series_inference": "head_ct_per_slice", "dicom_window": WINDOW}
    hu = np.stack([_head(seed) for seed in (1, 2, 3)]).astype(np.float32)
    served = model_inference.series_model_images(model, hu)
    # scripts/evaluate_head_ct_cq500.py: the middle channel of the windowed stack, read as grey and converted to RGB.
    evaluated = [Image.fromarray(plane, mode="L").convert("RGB") for plane in np.asarray(model_inference.series_slice_images(hu, WINDOW))[..., 1]]
    assert all(np.array_equal(np.asarray(a), np.asarray(b)) for a, b in zip(served, evaluated))
    assert all(np.array_equal(np.asarray(image)[..., 0], np.asarray(image)[..., 2]) for image in served)  # no neighbours in the channels


def test_only_an_explicit_opt_in_with_a_window_reads_series():
    assert model_inference.head_ct_series_mode({"inference_input": "head_ct_series"}) == "neighbours"
    assert model_inference.head_ct_series_mode({"inference_input": "image_2d", "series_inference": "head_ct_per_slice", "dicom_window": WINDOW}) == "per_slice"
    assert model_inference.head_ct_series_mode({"inference_input": "image_2d", "dicom_window": WINDOW}) is None
    assert model_inference.head_ct_series_mode({"inference_input": "image_2d", "series_inference": "head_ct_per_slice"}) is None


def test_a_single_slice_model_reads_a_series_slice_by_slice(client, db_session, test_users, per_slice_registry):
    owner = test_users["clinician_a"]
    headers = get_auth_headers(owner)
    case = _case(db_session, owner, "HEAD-CT-PER-SLICE")
    ids = _upload_series(client, headers, case.id, [_head(700 + index) for index in range(4)])
    response = client.post(f"/api/v1/cases/{case.id}/dicom-series/research-inference", headers=headers,
                           json={"upload_ids": ids, "model_id": MODEL_ID, "declared_input_type": "HEAD_CT_SERIES"})
    assert response.status_code == 201, response.text
    output = response.json()["research_output"]
    assert output["type"] == "series_slice_multilabel" and "alone" in output["slice_input"]
    assert [item["upload_id"] for item in output["slices"]] == ids and output["slices_analysed"] >= 2
    analysed = [item for item in output["slices"] if item["status"] == "ANALYSED"]
    assert [entry["label"] for entry in output["label_maxima"]] == NAMES
    for entry in output["label_maxima"]:
        best = max(next(label["probability"] for label in item["labels"] if label["label"] == entry["label"]) for item in analysed)
        assert entry["probability"] == best and entry["at_or_above_threshold"] == (best >= entry["threshold"])
    assert "read alone" in output["input_content_check"]["checks"]
    assert output["series_pipeline_external_evaluation"] is None  # no saved evaluation of this fixture checkpoint
    listed = next(item for item in client.get("/api/v1/research-models", headers=headers).json()["models"] if item["model_id"] == MODEL_ID)
    assert listed["head_ct_series_mode"] == "per_slice"


def test_series_refusals_for_single_slice_models(client, db_session, test_users, per_slice_registry):
    owner = test_users["clinician_a"]
    headers = get_auth_headers(owner)
    case = _case(db_session, owner, "HEAD-CT-PER-SLICE-REFUSED")
    url = f"/api/v1/cases/{case.id}/dicom-series/research-inference"
    ids = _upload_series(client, headers, case.id, [_head(800 + index) for index in range(4)])
    wrong_type = client.post(url, headers=headers, json={"upload_ids": ids, "model_id": MODEL_ID, "declared_input_type": "MRI"})
    assert wrong_type.status_code == 400 and "head CT series" in wrong_type.json()["detail"]
    coronal = _upload_series(client, headers, case.id, [_head(900 + index) for index in range(4)], normal_tilt=80.0)
    tilted = client.post(url, headers=headers, json={"upload_ids": coronal, "model_id": MODEL_ID, "declared_input_type": "HEAD_CT_SERIES"})
    assert tilted.status_code == 400 and "NOT_AN_AXIAL_STACK" in tilted.json()["detail"]
    per_slice_registry["entry"].pop("series_inference")
    per_slice_registry["write"]()
    without = client.post(url, headers=headers, json={"upload_ids": ids, "model_id": MODEL_ID, "declared_input_type": "HEAD_CT_SERIES"})
    assert without.status_code == 400 and "does not take volumes" in without.json()["detail"]


def test_the_registered_haemorrhage_classifier_opts_in():
    registry = json.loads((model_registry.REGISTRY_PATH).read_text(encoding="utf-8"))
    entry = next((item for item in registry["models"] if item["model_id"] == "brain_ct_rsna_ich_classifier"), None)
    if entry is None:
        pytest.skip("haemorrhage classifier not registered in this checkout")
    assert model_inference.head_ct_series_mode(entry) == "per_slice"
