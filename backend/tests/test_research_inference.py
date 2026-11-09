"""Research-only model inference: registry gate, applicability gate, determinism,
provenance labelling, and source-geometry mapping of boxes and masks.

Checkpoints, reports and images here are synthetic fixtures created inside the
test (a randomly initialised network); none of it is patient evidence."""

import hashlib
import io
import json

import numpy as np
import pytest
from PIL import Image

torch = pytest.importorskip("torch")
models = pytest.importorskip("torchvision.models")

from app.models.entities import Finding, InferenceRun  # noqa: E402
from app.services import model_inference, model_registry  # noqa: E402
from tests.conftest import get_auth_headers  # noqa: E402

MODEL_ID = "test_research_classifier"


def _bundle(tmp_path, checkpoint, sha):
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"test_n": 10, "metrics": {"accuracy": 0.5, "macro_f1": 0.5}, "confidence_intervals_95": {}}), encoding="utf-8")
    card = tmp_path / "card.md"
    card.write_text("# Synthetic test fixture\n", encoding="utf-8")
    return {
        "dataset_version": "fixture", "dataset_license": "CC0 (synthetic test fixture)", "split_manifest_path": str(report),
        "task_definition": "fixture", "label_definition": {"classes": ["a", "b", "c"]}, "preprocessing_version": "fixture-v1",
        "checkpoint_path": str(checkpoint), "checkpoint_sha256": sha, "calibration": None, "decision_thresholds": None,
        "abstention_thresholds": None, "held_out_predictions_path": str(report), "evaluation_report_path": str(report), "model_card_path": str(card),
        "ood_reference_path": None, "ood_reference_sha256": None,
    }


@pytest.fixture
def research_registry(tmp_path, monkeypatch):
    torch.manual_seed(0)
    network = models.resnet18(weights=None)
    network.fc = torch.nn.Linear(network.fc.in_features, 3)
    checkpoint = tmp_path / "model.pt"
    torch.save({"kind": "image_classifier", "arch": "resnet18", "state_dict": network.state_dict(), "classes": ["a", "b", "c"], "image_size": 64,
                # A NumPy scalar, as trainers often save; weights_only loading must still accept it.
                "normalization": {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}, "temperature": np.float64(1.5)}, checkpoint)
    sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    entry = {"model_id": MODEL_ID, "display_name": "Synthetic test classifier", "task": "image_classification", "status": "READY_UNVALIDATED",
             "validated": False, "research_inference": True, "anatomy": "intestines", "supported_modalities": ["ENDOSCOPY"],
             "supported_classes": ["a", "b", "c"], "limitations": [], "artifact_bundle": _bundle(tmp_path, checkpoint, sha)}
    hidden = {**entry, "model_id": "not_for_research", "research_inference": False}
    path = tmp_path / "models.json"

    def write(**changes):
        model = json.loads(json.dumps(entry))
        for key, value in changes.items():
            target = model["artifact_bundle"] if key in model["artifact_bundle"] else model
            target[key] = value
        path.write_text(json.dumps({"schema_version": "1.0.0", "models": [model, hidden]}), encoding="utf-8")
        model_registry._load_registry.cache_clear()

    monkeypatch.setattr(model_registry, "REGISTRY_PATH", path)
    write()
    # The applicability reference is fitted on varied synthetic frames through the served network.
    reference_path, reference_sha = _fit_reference(tmp_path, model_inference.load_model(model_inference._load_registry()["models"][0]), sha)
    entry["artifact_bundle"].update(ood_reference_path=str(reference_path), ood_reference_sha256=reference_sha)
    write()
    model_inference._load.cache_clear()  # later tests must load (and re-verify) the checkpoint themselves
    yield {"write": write, "checkpoint": checkpoint, "sha": sha, "reference": reference_path, "reference_sha": reference_sha}
    model_registry._load_registry.cache_clear()
    model_inference._load.cache_clear()


def _frame(seed):
    rng = np.random.default_rng(seed)
    pixels = rng.integers(0, 255, size=(80, 96, 3)) * rng.uniform(0.3, 1.0, size=3) + rng.uniform(0, 60)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def _frame_bytes(seed):
    buffer = io.BytesIO()
    _frame(seed).save(buffer, format="PNG")
    return buffer.getvalue()


def _fit_reference(tmp_path, loaded, sha, scale=3.0, quantile=1.0):
    from app.services import image_ood

    network, payload, device = loaded
    rows = [model_inference.image_features(network, payload, device, _frame(seed)) for seed in range(100, 140)]
    stages = [np.vstack([row[index] for row in rows]) for index in range(len(rows[0]))]
    reference = image_ood.fit_reference([stage[:30] for stage in stages], [stage[30:] for stage in stages], quantile=quantile,
                                        metadata={"checkpoint_sha256": sha, "feature_version": model_inference.FEATURE_VERSION})
    reference["threshold"] *= scale
    path = tmp_path / "ood_reference.npz"
    return path, image_ood.save_reference(path, reference)


def _png(width=96, height=80, seed=1):
    pixels = np.random.default_rng(seed).integers(0, 255, size=(height, width, 3), dtype=np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(client, headers, name="frame.png", body=None, mime="image/png", pseudonym="CASE-RESEARCH"):
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": pseudonym}, headers=headers).json()["id"]
    response = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (name, body if body is not None else _png(), mime)},
                           data={"deidentified": "true"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_listing_shows_only_research_models_with_gate_and_metrics(client, test_users, research_registry):
    listed = client.get("/api/v1/research-models", headers=get_auth_headers(test_users["clinician_a"])).json()
    assert [model["model_id"] for model in listed["models"]] == [MODEL_ID]
    model = listed["models"][0]
    assert model["gate"] == {"allowed": True, "blockers": []}
    assert model["output_status"] == "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED" and model["validated"] is False
    assert model["held_out_evaluation"]["test_n"] == 10


def test_ecg_volume_and_survival_models_are_listed_and_survival_never_runs_on_uploads(client, test_users, tmp_path, monkeypatch):
    checkpoint = tmp_path / "evidence.pt"
    checkpoint.write_bytes(b"synthetic checkpoint fixture")
    sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    reports = {
        "ecg": {"test_n": 20, "metrics": {"macro_auroc": 0.8, "macro_auprc": 0.6, "macro_f1_at_validation_thresholds": 0.5},
                "confidence_intervals_95": {"macro_auroc": {"status": "COMPUTED", "low": 0.7, "high": 0.9}}},
        "survival": {"test_n": 30, "metrics": {"harrell_c": 0.7, "integrated_brier_model": 0.1, "integrated_brier_kaplan_meier": 0.12, "integrated_brier_skill": 0.17},
                     "confidence_intervals_95": {"harrell_c": {"status": "COMPUTED", "low": 0.6, "high": 0.8}}},
        "volume": {"test_n": 4, "test_patients": 2, "metrics": {"mean_case_macro_dice": 0.8, "per_structure": {
                       "left_ventricular_cavity": {"mean_dice": 0.9}, "myocardium": {"mean_dice": 0.8}, "right_ventricular_cavity": {"mean_dice": 0.7}}},
                   "clinical_indices": {"lv_ef_percent": {"mean_absolute_error": 4.0}}},
    }
    models = []
    for kind, task, inference_input in (("ecg", "multilabel_ecg_classification", "ecg_12lead"), ("survival", "survival_prediction", "tabular_survival"),
                                        ("volume", "volumetric_semantic_segmentation", "volume_nifti")):
        report = tmp_path / f"{kind}.json"
        report.write_text(json.dumps(reports[kind]), encoding="utf-8")
        bundle = _bundle(tmp_path, checkpoint, sha)
        bundle["evaluation_report_path"] = str(report)
        models.append({"model_id": f"evidence_{kind}", "display_name": kind, "task": task, "status": "READY_UNVALIDATED", "validated": False,
                       "research_inference": True, "inference_input": inference_input, "supported_modalities": ["ENDOSCOPY"], "supported_classes": [],
                       "limitations": [], "artifact_bundle": bundle})
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"schema_version": "1.0.0", "models": models}), encoding="utf-8")
    monkeypatch.setattr(model_registry, "REGISTRY_PATH", path)
    model_registry._load_registry.cache_clear()
    try:
        headers = get_auth_headers(test_users["clinician_a"])
        listed = {item["model_id"]: item for item in client.get("/api/v1/research-models", headers=headers).json()["models"]}
        assert listed["evidence_ecg"]["held_out_evaluation"]["macro_auroc"] == 0.8
        assert listed["evidence_survival"]["held_out_evaluation"]["harrell_c"] == 0.7
        assert listed["evidence_volume"]["held_out_evaluation"]["lv_cavity_dice"] == 0.9
        assert listed["evidence_volume"]["held_out_evaluation"]["lv_ef_mean_absolute_error"] == 4.0
        assert {item["inference_input"] for item in listed.values()} == {"ecg_12lead", "tabular_survival", "volume_nifti"}
        assert client.get("/api/v1/models", headers=headers).status_code == 200
        upload_id = _upload(client, headers, pseudonym="CASE-RESEARCH-EVIDENCE")
        refused = client.post(f"/api/v1/uploads/{upload_id}/research-inference", json={"model_id": "evidence_survival", "declared_input_type": "ENDOSCOPY"}, headers=headers)
        assert refused.status_code == 400 and "no upload inference path" in refused.json()["detail"]
    finally:
        model_registry._load_registry.cache_clear()


def test_inference_reports_the_numeric_precision_it_used():
    import torch

    from app.services.model_inference import evaluated_precision

    context, note = evaluated_precision(torch.device("cpu"))
    with context:
        value = torch.ones(2, 2) @ torch.ones(2, 2)
    # CPU inference runs float32 and says that it differs from the evaluated CUDA bfloat16 configuration.
    assert value.dtype == torch.float32 and "differs from the evaluated" in note


def test_evaluation_report_is_served_for_research_models_only(client, test_users, research_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    served = client.get(f"/api/v1/research-models/{MODEL_ID}/evaluation", headers=headers)
    assert served.status_code == 200 and served.json()["report"]["test_n"] == 10
    assert client.get("/api/v1/research-models/not_for_research/evaluation", headers=headers).status_code == 404
    assert client.get(f"/api/v1/research-models/{MODEL_ID}/evaluation").status_code == 401


def test_classifier_output_is_deterministic_labelled_and_pending_review(client, test_users, db_session, research_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    upload_id = _upload(client, headers)
    request = {"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"}
    first = client.post(f"/api/v1/uploads/{upload_id}/research-inference", json=request, headers=headers)
    second = client.post(f"/api/v1/uploads/{upload_id}/research-inference", json=request, headers=headers)
    assert first.status_code == second.status_code == 201, first.text
    one, two = first.json(), second.json()
    assert one["id"] != two["id"]
    assert one["status"] == "COMPLETED" and one["model_name"] == MODEL_ID and one["model_version"] == research_registry["sha"][:16]
    probabilities = [item["probability"] for item in one["research_output"]["classes"]]
    assert abs(sum(probabilities) - 1) < 1e-5
    assert one["research_output"] == two["research_output"], "the same checkpoint and input must give the same output"
    finding = db_session.query(Finding).filter(Finding.inference_run_id == one["id"]).one()
    assert finding.review_status.value == "PENDING_HUMAN_REVIEW" and finding.anatomical_region is None
    assert finding.evidence_provenance["output_status"] == "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED"
    assert finding.evidence_provenance["checkpoint_sha256"] == research_registry["sha"]
    assert client.get(f"/api/v1/research-inference/{one['id']}", headers=headers).json()["research_output"] == one["research_output"]


def test_research_finding_maps_only_to_confirmed_schematic_organ(client, test_users, db_session, research_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    upload_id = _upload(client, headers, pseudonym="CASE-RESEARCH-ANATOMY")
    run = client.post(
        f"/api/v1/uploads/{upload_id}/research-inference",
        json={"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"},
        headers=headers,
    )
    assert run.status_code == 201, run.text
    finding = db_session.query(Finding).filter(Finding.inference_run_id == run.json()["id"]).one()

    before = client.get(f"/api/v1/cases/{finding.case_id}/anatomy-evidence", headers=headers).json()
    item = next(item for item in before["systems"]["intestines"]["items"] if item["kind"] == "MODEL_FINDING")
    assert item["mapping_state"] == "NOT_MAPPABLE"
    assert item["mapping_category"] == "UNSUPPORTED_MAPPING", "legacy clients keep the compatibility category"
    assert item["atlas_structure_id"] is None and item["candidate_atlas_structure_id"] is None
    assert item["source_file_id"] == upload_id
    assert item["source_hash"] == finding.evidence_provenance["source_file_sha256"]
    assert item["checkpoint_sha256"] == research_registry["sha"]
    assert item["evidence_status"] == "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED"
    assert before["systems"]["intestines"]["highlight"] == {
        "organ_schematic": False,
        "verified_structures": [],
        "spatially_registered": [],
        "documented_structures": [],
        "verified_structure_names": [],
        "documented_structure_names": [],
    }

    review = client.post(f"/api/v1/reviews/{finding.id}", json={"review_status": "CONFIRMED"}, headers=headers)
    assert review.status_code == 201, review.text
    after = client.get(f"/api/v1/cases/{finding.case_id}/anatomy-evidence", headers=headers).json()
    item = next(item for item in after["systems"]["intestines"]["items"] if item["kind"] == "MODEL_FINDING")
    assert item["mapping_state"] == "SCHEMATIC_ORGAN_ONLY"
    assert item["mapping_category"] == "SCHEMATIC_ORGAN_ASSOCIATION"
    assert item["clinician_confirmation"]["status"] == "CONFIRMED"
    assert item["clinician_confirmation"]["scope"] == "FINDING_LEVEL"
    assert item["atlas_structure_id"] is None and item["source_coordinate_space"] is None
    assert after["systems"]["intestines"]["highlight"] == {
        "organ_schematic": True,
        "verified_structures": [],
        "spatially_registered": [],
        "documented_structures": [],
        "verified_structure_names": [],
        "documented_structure_names": [],
    }


@pytest.mark.parametrize("change, blocker", [
    ("tamper", "CHECKPOINT_HASH_MISMATCH"),
    ({"dataset_license": "UNVERIFIED"}, "DATASET_LICENSE_UNVERIFIED"),
    ({"evaluation_report_path": "missing/report.json"}, "EVALUATION_REPORT_MISSING"),
    ({"research_inference": False}, "NOT_REGISTERED_FOR_RESEARCH_INFERENCE"),
    ({"status": "WEIGHTS_MISSING"}, "STATUS_WEIGHTS_MISSING"),
    ({"ood_reference_path": None}, "OOD_REFERENCE_MISSING"),
    ({"ood_reference_sha256": "0" * 64}, "OOD_REFERENCE_HASH_MISMATCH"),
])
def test_gate_refuses_models_without_a_verified_bundle(client, test_users, db_session, research_registry, change, blocker):
    headers = get_auth_headers(test_users["clinician_a"])
    upload_id = _upload(client, headers)
    if change == "tamper":
        with research_registry["checkpoint"].open("ab") as handle:
            handle.write(b"\0")
    else:
        research_registry["write"](**change)
    response = client.post(f"/api/v1/uploads/{upload_id}/research-inference", json={"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"}, headers=headers)
    assert response.status_code == 400 and blocker in response.json()["detail"]
    assert db_session.query(InferenceRun).filter(InferenceRun.file_id == upload_id).count() == 0, "no output may be recorded"


def test_tampered_bytes_are_refused_even_after_the_gate(research_registry):
    model = model_inference.get_model(MODEL_ID)
    with research_registry["checkpoint"].open("ab") as handle:
        handle.write(b"\0")
    with pytest.raises(model_inference.InferenceNotPermitted):
        model_inference._load(MODEL_ID, str(research_registry["checkpoint"]), model["artifact_bundle"]["checkpoint_sha256"])


def test_serving_cache_releases_replaced_network_and_duplicate_weights(research_registry):
    import gc
    import weakref

    model = model_inference.get_model(MODEL_ID)
    first, metadata, device = model_inference.load_model(model)
    assert MODEL_ID in model_inference.resident_model_ids()
    assert "state_dict" not in metadata, "cached metadata must not retain a second full copy of network weights"
    assert metadata["classes"] == ["a", "b", "c"] and metadata["temperature"] == 1.5
    assert sum(parameter.numel() for parameter in first.parameters()) > 0
    first_reference = weakref.ref(first)
    # A different registry identity replaces the resident model. Checkpoints
    # are synthetic fixtures; this exercises release, without downloading data.
    model_inference.load_model({**model, "model_id": "replacement_test_classifier"})
    del first
    gc.collect()
    assert first_reference() is None, "an evicted network must not stay resident through the serving cache"
    assert MODEL_ID not in model_inference.resident_model_ids()
    assert "replacement_test_classifier" in model_inference.resident_model_ids()
    model_inference._load.cache_clear()
    gc.collect()
    assert "replacement_test_classifier" not in model_inference.resident_model_ids()


def test_gpu_telemetry_reports_actual_process_residency(client, test_users, monkeypatch):
    monkeypatch.setattr(model_inference, "resident_model_ids", lambda: ["fixture_live_network"])
    response = client.get("/api/v1/system/gpu", headers=get_auth_headers(test_users["clinician_a"]))
    assert response.status_code == 200
    assert response.json()["loaded_models"] == ["fixture_live_network"]
    assert response.json()["telemetry_scope"] == "API_PROCESS_ONLY"


def test_applicability_gate_rejects_unsupported_inputs(client, test_users, research_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    image_id = _upload(client, headers, pseudonym="CASE-RESEARCH-IMG")
    report_id = _upload(client, headers, name="note.txt", body=b"Synthetic note. Creatinine 1.0 mg/dL.", mime="text/plain", pseudonym="CASE-RESEARCH-TXT")
    url = "/api/v1/uploads/{}/research-inference"
    wrong_type = client.post(url.format(image_id), json={"model_id": MODEL_ID, "declared_input_type": "ANGIOGRAPHY"}, headers=headers)
    assert wrong_type.status_code == 400 and "trained only on" in wrong_type.json()["detail"]
    microscopy_type = client.post(url.format(image_id), json={"model_id": MODEL_ID, "declared_input_type": "MICROSCOPY"}, headers=headers)
    assert microscopy_type.status_code == 400 and "trained only on" in microscopy_type.json()["detail"]
    assert client.post(url.format(report_id), json={"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"}, headers=headers).status_code == 400
    assert client.post(url.format(image_id), json={"model_id": "unknown", "declared_input_type": "ENDOSCOPY"}, headers=headers).status_code == 400
    mri_type = client.post(url.format(image_id), json={"model_id": MODEL_ID, "declared_input_type": "MRI"}, headers=headers)
    assert mri_type.status_code == 400 and "trained only on" in mri_type.json()["detail"]
    assert client.post(url.format(image_id), json={"model_id": MODEL_ID, "declared_input_type": "ULTRASOUND"}, headers=headers).status_code == 422


def test_detection_boxes_are_clipped_to_source_pixels():
    class Detector:
        def __call__(self, images):
            assert images[0].shape == (3, 80, 100)
            return [{"boxes": torch.tensor([[-5.0, 10.0, 50.0, 400.0], [20.0, 20.0, 30.0, 30.0]]), "scores": torch.tensor([0.9, 0.2])}]

    output = model_inference.detect(Detector(), {"classes": ["stenosis"], "score_threshold": 0.5}, torch.device("cpu"), Image.new("RGB", (100, 80)))
    assert output["image_size"] == [100, 80]
    assert output["boxes"][0]["bbox_xyxy"] == [0.0, 10.0, 50.0, 80.0]
    assert [box["above_display_threshold"] for box in output["boxes"]] == [True, False]


def test_segmentation_mask_maps_back_to_source_geometry():
    from pycocotools import mask as coco_mask

    class Segmenter:
        def __call__(self, batch):
            size = batch.shape[-1]
            logits = torch.zeros((1, 3, size, size))
            logits[0, 0] = 1.0
            logits[0, 1, :, : size // 2] = 5.0  # class 1 on the left half of the model grid
            return logits

    output = model_inference.segment(Segmenter(), {"input_size": 64, "classes": ["left", "unused"]}, torch.device("cpu"), Image.new("L", (300, 200)))
    assert output["image_size"] == [300, 200] and [s["segment"] for s in output["segments"]] == ["left"]
    segment = output["segments"][0]
    decoded = coco_mask.decode({"size": segment["rle"]["size"], "counts": segment["rle"]["counts"].encode("ascii")})
    assert decoded.shape == (200, 300)
    columns = np.flatnonzero(decoded.any(axis=0))
    assert columns.min() == 0 and abs(columns.max() - 149) <= 3, "the left half of the model grid is the left half of the source image"
    assert segment["area_px"] == int(decoded.sum())


@pytest.mark.private_workspace
def test_runs_are_listed_per_upload_with_their_latest_review(client, test_users, research_registry):
    """A stored run comes back after a reload; a review is shown with it and never changes the output."""
    headers = get_auth_headers(test_users["clinician_a"])
    upload_id = _upload(client, headers, pseudonym="CASE-RESEARCH-LIST")
    run = client.post(f"/api/v1/uploads/{upload_id}/research-inference", json={"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"}, headers=headers)
    assert run.status_code == 201, run.text
    [listed] = client.get(f"/api/v1/uploads/{upload_id}/research-inference", headers=headers).json()["runs"]
    assert listed["id"] == run.json()["id"] and listed["research_output"] == run.json()["research_output"]
    assert listed["finding_id"] and listed["latest_review"] is None
    review = client.post(f"/api/v1/reviews/{listed['finding_id']}", json={"review_status": "REJECTED", "reviewer_comments": "fixture"}, headers=headers)
    assert review.status_code == 201, review.text
    [reviewed] = client.get(f"/api/v1/uploads/{upload_id}/research-inference", headers=headers).json()["runs"]
    assert reviewed["latest_review"]["review_status"] == "REJECTED" and reviewed["latest_review"]["original_output_preserved"] is True
    assert reviewed["research_output"] == run.json()["research_output"]
    assert client.get(f"/api/v1/uploads/{upload_id}/research-inference", headers=get_auth_headers(test_users["clinician_b"])).status_code == 403


def _stored_segmentation_run(db_session, upload_id: int, mask: np.ndarray) -> int:
    """A stored segmentation run with a known mask (fixture; the model path itself is tested above)."""
    from app.models.entities import EvidenceStatus, UploadedFile
    from app.services.reference_annotations import encode

    upload = db_session.get(UploadedFile, upload_id)
    run = InferenceRun(case_id=upload.case_id, file_id=upload.id, modality=upload.modality, model_name=MODEL_ID, model_version="fixture",
                       preprocessing_version="fixture", status=EvidenceStatus.COMPLETED)
    db_session.add(run)
    db_session.flush()
    output = {"type": "segmentation", "coordinate_space": "source image pixels", "image_size": [mask.shape[1], mask.shape[0]],
              "segments": [{"class_index": 1, "segment": "polyp", "area_px": int(mask.sum()), "rle": encode(mask)}],
              "vessel_area_px": int(mask.sum()), "foreground_label": "polyp"}
    db_session.add(Finding(inference_run_id=run.id, case_id=upload.case_id, modality=upload.modality, category="fixture", label="fixture",
                           mapping_status="NOT_MAPPABLE", evidence_provenance={"source": "MODEL_INFERENCE", "output": output}, is_demo=False))
    db_session.commit()
    return run.id


def _mask_png(mask: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray((mask * 255).astype(np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.private_workspace
def test_reference_mask_is_compared_per_image_without_touching_the_run(client, test_users, db_session):
    headers = get_auth_headers(test_users["clinician_a"])
    upload_id = _upload(client, headers, pseudonym="CASE-RESEARCH-REFERENCE")  # a 96x80 frame
    predicted = np.zeros((80, 96), dtype=bool)
    predicted[10:50, 10:50] = True  # 1600 px
    reference = np.zeros((80, 96), dtype=bool)
    reference[30:70, 10:50] = True  # 1600 px, 800 px shared
    run_id = _stored_segmentation_run(db_session, upload_id, predicted)
    form = {"source": "DATASET_PUBLISHER_ANNOTATION", "source_detail": "fixture dataset, test split", "class_name": "polyp"}

    wrong_size = client.post(f"/api/v1/uploads/{upload_id}/reference-annotations", files={"mask": ("m.png", _mask_png(reference[:40]), "image/png")}, data=form, headers=headers)
    assert wrong_size.status_code == 400 and wrong_size.json()["detail"].startswith("MASK_SIZE_MISMATCH")
    unknown_source = client.post(f"/api/v1/uploads/{upload_id}/reference-annotations", files={"mask": ("m.png", _mask_png(reference), "image/png")},
                                 data={**form, "source": "MODEL_OUTPUT"}, headers=headers)
    assert unknown_source.status_code == 400 and unknown_source.json()["detail"].startswith("SOURCE_UNSUPPORTED")
    created = client.post(f"/api/v1/uploads/{upload_id}/reference-annotations", files={"mask": ("m.png", _mask_png(reference), "image/png")}, data=form, headers=headers)
    assert created.status_code == 201, created.text
    annotation = created.json()
    assert annotation["layer"] == "GROUND_TRUTH" and annotation["area_px"] == 1600 and annotation["image_size"] == [96, 80]

    comparison = client.get(f"/api/v1/research-inference/{run_id}/reference-comparison/{annotation['id']}", headers=headers)
    assert comparison.status_code == 200, comparison.text
    result = comparison.json()
    assert result["comparison"] == "PER_IMAGE_AGREEMENT" and result["compared"] == "segment 'polyp'"
    assert result["dice"] == 0.5 and result["iou"] == round(800 / 2400, 4)
    assert result["pixel_precision"] == 0.5 and result["pixel_recall"] == 0.5
    from app.services.reference_annotations import decode
    assert decode(result["regions"]["model_only"]).sum() == 800 and decode(result["regions"]["reference_only"]).sum() == 800
    stored = client.get(f"/api/v1/research-inference/{run_id}", headers=headers).json()["research_output"]
    assert stored["segments"][0]["area_px"] == 1600, "the run's own mask is unchanged"
    assert [item["id"] for item in client.get(f"/api/v1/uploads/{upload_id}/reference-annotations", headers=headers).json()["annotations"]] == [annotation["id"]]
    assert client.get(f"/api/v1/research-inference/{run_id}/reference-comparison/{annotation['id']}", headers=get_auth_headers(test_users["clinician_b"])).status_code == 403


def test_a_reviewer_correction_is_stored_beside_the_run_and_says_what_changed(client, test_users, db_session):
    headers = get_auth_headers(test_users["clinician_a"])
    upload_id = _upload(client, headers, pseudonym="CASE-RESEARCH-CORRECTION")  # a 96x80 frame
    predicted = np.zeros((80, 96), dtype=bool)
    predicted[10:50, 10:50] = True  # 1600 px
    corrected = predicted.copy()
    corrected[10:20, 10:50] = False  # the reviewer erases 400 px
    corrected[50:60, 10:50] = True  # and paints 400 px
    run_id = _stored_segmentation_run(db_session, upload_id, predicted)
    url = f"/api/v1/research-inference/{run_id}/mask-corrections"

    disguised = client.post(f"/api/v1/uploads/{upload_id}/reference-annotations", files={"mask": ("m.png", _mask_png(corrected), "image/png")},
                            data={"source": "REVIEWER_CORRECTION_OF_MODEL_OUTPUT", "source_detail": "edited", "class_name": "polyp"}, headers=headers)
    assert disguised.status_code == 400 and disguised.json()["detail"].startswith("SOURCE_UNSUPPORTED"), "corrections come only from a run"
    wrong_size = client.post(url, files={"mask": ("c.png", _mask_png(corrected[:40]), "image/png")}, data={"class_name": "polyp"}, headers=headers)
    assert wrong_size.status_code == 400 and wrong_size.json()["detail"].startswith("MASK_SIZE_MISMATCH")

    saved = client.post(url, files={"mask": ("c.png", _mask_png(corrected), "image/png")}, data={"class_name": "polyp", "note": "edge redrawn"}, headers=headers)
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["layer"] == "REVIEWER_CORRECTION" and body["derived_from_run_id"] == run_id and body["area_px"] == 1600
    assert body["source_detail"].startswith(f"Reviewer correction of run {run_id}") and "edge redrawn" in body["source_detail"]
    change = body["comparison_with_run"]
    assert change["dice"] == 0.75 and "not independent ground truth" in change["semantics"]
    from app.services.reference_annotations import decode
    assert decode(change["regions"]["model_only"]).sum() == 400 and decode(change["regions"]["reference_only"]).sum() == 400
    stored = client.get(f"/api/v1/research-inference/{run_id}", headers=headers).json()["research_output"]
    assert stored["segments"][0]["area_px"] == 1600, "the run's own mask is unchanged"

    assert change["correction_of_this_run"] is True

    db_session.expire_all()
    from app.models.entities import AuditEvent
    assert db_session.query(AuditEvent).filter(AuditEvent.action == "MODEL_MASK_CORRECTED").count() == 1

    other_run = _stored_segmentation_run(db_session, upload_id, predicted)
    across = client.get(f"/api/v1/research-inference/{other_run}/reference-comparison/{body['id']}", headers=headers).json()
    assert across["correction_of_this_run"] is False and "not edits of this run" in across["semantics"]

    missed = np.zeros((80, 96), dtype=bool)
    missed[60:70, 60:70] = True
    painted = client.post(url, files={"mask": ("c.png", _mask_png(missed), "image/png")}, data={"class_name": "adenoma"}, headers=headers)
    assert painted.status_code == 201, painted.text
    assert painted.json()["comparison_with_run"]["predicted_area_px"] == 0, "a class the run never predicted has an empty model mask"


def test_a_label_mask_holding_only_0_and_1_is_not_read_as_empty(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    upload_id = _upload(client, headers, pseudonym="CASE-RESEARCH-LABEL-MASK")
    labels = np.zeros((80, 96), dtype=np.uint8)
    labels[10:30, 10:30] = 1
    buffer = io.BytesIO()
    Image.fromarray(labels).save(buffer, format="PNG")
    created = client.post(f"/api/v1/uploads/{upload_id}/reference-annotations", files={"mask": ("labels.png", buffer.getvalue(), "image/png")},
                          data={"source": "DATASET_PUBLISHER_ANNOTATION", "source_detail": "fixture label map", "class_name": "polyp"}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["area_px"] == 400 and created.json()["empty"] is False and created.json()["binarize_threshold"] == 0


@pytest.mark.private_workspace
def test_any_account_can_attach_reference_masks_to_its_own_images(client, test_users, db_session):
    from app.models.entities import User, UserRole, VerificationStatus
    from app.services.auth import get_password_hash

    public = User(username="public_ref", email="public_ref@test.medtwin", hashed_password=get_password_hash("PublicPass1!"), role=UserRole.PUBLIC,
                  verification_status=VerificationStatus.UNVERIFIED, is_active=True)
    db_session.add(public)
    db_session.commit()
    headers = get_auth_headers(public)
    upload_id = _upload(client, headers, pseudonym="CASE-PUBLIC-REFERENCE")
    response = client.post(f"/api/v1/uploads/{upload_id}/reference-annotations", files={"mask": ("m.png", _mask_png(np.ones((80, 96), bool)), "image/png")},
                           data={"source": "DATASET_PUBLISHER_ANNOTATION", "source_detail": "fixture dataset", "class_name": "polyp"}, headers=headers)
    assert response.status_code == 201, response.text
    elsewhere = client.post(f"/api/v1/uploads/{upload_id}/reference-annotations", files={"mask": ("m.png", _mask_png(np.ones((80, 96), bool)), "image/png")},
                            data={"source": "DATASET_PUBLISHER_ANNOTATION", "source_detail": "fixture dataset", "class_name": "polyp"},
                            headers=get_auth_headers(test_users["clinician_b"]))
    assert elsewhere.status_code == 403, "another account's image stays closed"


def _exif_rotated_phantom(path, orientation: int):
    """Synthetic geometry phantom (TEST data only): a 120x80 stored frame, black except a bright
    block in its top-left corner, saved as JPEG with the given EXIF orientation tag."""
    stored = np.zeros((80, 120, 3), dtype=np.uint8)
    stored[:20, :30] = 255
    exif = Image.Exif()
    exif[0x0112] = orientation
    Image.fromarray(stored).save(path, format="JPEG", quality=95, exif=exif.tobytes())


def test_exif_orientation_is_applied_before_inference_so_overlays_match_the_displayed_image(monkeypatch, tmp_path):
    """Browsers display a JPEG upright using its EXIF tag; masks must use that same pixel grid."""
    from pycocotools import mask as coco_mask
    from app.services import imaging_readers

    path = tmp_path / "phantom.jpg"
    _exif_rotated_phantom(path, 6)  # 6: displayed after a 90° clockwise turn
    metadata = imaging_readers.read_metadata(path)
    assert metadata["dimensions"] == [80, 120] and metadata["exif_orientation"] == 6
    upright, orientation = imaging_readers.open_raster(path)
    assert orientation == 6 and upright.size == (80, 120)
    bright = np.asarray(upright.convert("L")) > 128
    rows, columns = np.flatnonzero(bright.any(axis=1)), np.flatnonzero(bright.any(axis=0))
    assert rows.max() < 35 and columns.min() > 55, "the stored top-left block is displayed top-right"

    class BrightnessSegmenter:  # class 1 wherever the model input is bright
        def __call__(self, batch):
            score = batch.mean(dim=1)
            return torch.stack([torch.zeros_like(score), score * 10], dim=1)

    payload = {"kind": "semantic_segmenter", "input_size": 64, "classes": ["bright"], "color": "rgb"}
    monkeypatch.setattr(model_inference, "load_model", lambda model: (BrightnessSegmenter(), payload, torch.device("cpu")))
    output = model_inference.run_model({"model_id": "phantom"}, path)
    assert output["image_size"] == [80, 120] and output["exif_orientation_applied"] == 6
    segment = output["segments"][0]
    mask = coco_mask.decode({"size": segment["rle"]["size"], "counts": segment["rle"]["counts"].encode("ascii")}) > 0
    overlap = (mask & bright).sum() / max(1, (mask | bright).sum())
    assert overlap > 0.7, f"mask and displayed bright block disagree (IoU {overlap:.2f})"


def test_document_photograph_gate_refuses_printed_pages_before_any_model(monkeypatch, tmp_path):
    """The content gate is independent of the declared modality and fails closed on printed pages."""
    image_path = tmp_path / "upload.png"
    Image.new("RGB", (64, 64), "white").save(image_path)

    monkeypatch.setattr(model_inference, "printed_text_lines", lambda path: 12)
    with pytest.raises(model_inference.InferenceNotPermitted, match="MODEL_INPUT_INCOMPATIBLE"):
        model_inference.check_document_photograph(image_path)

    monkeypatch.setattr(model_inference, "printed_text_lines", lambda path: 2)
    assert model_inference.check_document_photograph(image_path)["status"] == "PASSED"

    monkeypatch.setattr(model_inference, "printed_text_lines", lambda path: None)
    assert model_inference.check_document_photograph(image_path)["status"] == "NOT_CHECKED_OCR_UNAVAILABLE"


def test_out_of_distribution_image_is_refused_before_the_model_runs(client, test_users, db_session, research_registry, tmp_path):
    from app.services import image_ood

    headers = get_auth_headers(test_users["clinician_a"])
    upload_id = _upload(client, headers, pseudonym="CASE-RESEARCH-OOD")
    reference = image_ood.load_reference(research_registry["reference"], research_registry["reference_sha"], research_registry["sha"])
    reference["threshold"] = 0.0  # every image is outside this reference
    strict = tmp_path / "strict_reference.npz"
    research_registry["write"](ood_reference_path=str(strict), ood_reference_sha256=image_ood.save_reference(strict, reference))
    response = client.post(f"/api/v1/uploads/{upload_id}/research-inference", json={"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"}, headers=headers)
    assert response.status_code == 400 and response.json()["detail"].startswith("MODEL_INPUT_OUT_OF_DISTRIBUTION")
    assert db_session.query(Finding).join(InferenceRun, Finding.inference_run_id == InferenceRun.id).filter(InferenceRun.file_id == upload_id).count() == 0


def test_in_distribution_run_records_the_applicability_check(client, test_users, research_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    upload_id = _upload(client, headers, body=_frame_bytes(7), pseudonym="CASE-RESEARCH-IN")
    run = client.post(f"/api/v1/uploads/{upload_id}/research-inference", json={"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"}, headers=headers)
    assert run.status_code == 201, run.text
    check = run.json()["research_output"]["input_content_check"]["distribution"]
    assert check["status"] == "PASSED" and check["applicability_score"] <= check["applicability_limit"]


def _rgb_dicom_bytes(image: Image.Image, modality="ES", frames=1) -> bytes:
    import pydicom
    from pydicom.dataset import FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.77.1.1"  # VL Endoscopic Image Storage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = pydicom.Dataset()
    ds.file_meta = meta
    ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    ds.Modality = modality
    ds.Rows, ds.Columns = pixels.shape[:2]
    ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    if frames > 1:
        ds.NumberOfFrames = frames
    ds.PixelData = np.concatenate([pixels.ravel()] * frames).tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def test_a_dicom_frame_runs_like_the_same_pixels_as_png(client, test_users, research_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    png_id = _upload(client, headers, body=_frame_bytes(7), pseudonym="CASE-RESEARCH-PNG")
    dicom_id = _upload(client, headers, name="frame.dcm", body=_rgb_dicom_bytes(_frame(7)), mime="application/dicom",
                       pseudonym="CASE-RESEARCH-DCM")
    request = {"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"}
    from_png = client.post(f"/api/v1/uploads/{png_id}/research-inference", json=request, headers=headers)
    from_dicom = client.post(f"/api/v1/uploads/{dicom_id}/research-inference", json=request, headers=headers)
    assert from_png.status_code == 201 and from_dicom.status_code == 201, from_dicom.text
    png_output, dicom_output = from_png.json()["research_output"], from_dicom.json()["research_output"]
    assert dicom_output["classes"] == png_output["classes"]
    assert dicom_output["input_content_check"]["distribution"] == png_output["input_content_check"]["distribution"]
    assert dicom_output["dicom_frame"]["frame_index"] == 0 and dicom_output["dicom_frame"]["photometric_interpretation"] == "RGB"
    assert dicom_output["input_content_check"]["dicom_frame"]["modality_tag"] == "ES"
    assert "DICOM frame 0 converted" in from_dicom.json()["research_provenance"]["applicability"]


def test_dicom_frame_choice_and_modality_tag_are_checked_before_queueing(client, test_users, db_session, research_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    request = {"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"}
    cine = _upload(client, headers, name="cine.dcm", body=_rgb_dicom_bytes(_frame(7), frames=3), mime="application/dicom",
                   pseudonym="CASE-RESEARCH-CINE")
    refused = client.post(f"/api/v1/uploads/{cine}/research-inference", json=request, headers=headers)
    assert refused.status_code == 400 and refused.json()["detail"].startswith("FRAME_INDEX_REQUIRED")
    # A missing frame choice is a request error: no abstention is recorded against the image.
    assert db_session.query(InferenceRun).filter(InferenceRun.file_id == cine).count() == 0
    chosen = client.post(f"/api/v1/uploads/{cine}/research-inference", json={**request, "frame_index": 2}, headers=headers)
    assert chosen.status_code == 201, chosen.text
    assert chosen.json()["research_output"]["dicom_frame"]["frame_index"] == 2
    angiogram = _upload(client, headers, name="xa.dcm", body=_rgb_dicom_bytes(_frame(7), modality="XA"), mime="application/dicom",
                        pseudonym="CASE-RESEARCH-XA")
    mismatch = client.post(f"/api/v1/uploads/{angiogram}/research-inference", json=request, headers=headers)
    assert mismatch.status_code == 400 and "DICOM_MODALITY_MISMATCH" in mismatch.json()["detail"]


def test_applicability_reference_math_and_binding(tmp_path):
    from app.services import image_ood

    rng = np.random.default_rng(3)
    mixing = rng.normal(size=(40, 40))

    def sample(n, shift=0.0):
        return [rng.normal(size=(n, 40)) @ mixing + shift, rng.normal(size=(n, 12)) + shift]

    reference = image_ood.fit_reference(sample(2000), sample(2000), quantile=0.99, metadata={"checkpoint_sha256": "a" * 64})
    in_distribution = (image_ood.score(reference, sample(4000)) > reference["threshold"]).mean()
    shifted = (image_ood.score(reference, sample(500, shift=3.0)) > reference["threshold"]).mean()
    assert 0.003 <= in_distribution <= 0.03 and shifted > 0.99
    path = tmp_path / "reference.npz"
    digest = image_ood.save_reference(path, reference)
    loaded = image_ood.load_reference(path, digest, "a" * 64)
    probe = sample(5)
    np.testing.assert_allclose(image_ood.score(loaded, probe), image_ood.score(reference, probe))
    for sha, checkpoint, code in ((digest, "b" * 64, "OOD_REFERENCE_FOR_ANOTHER_CHECKPOINT"), ("0" * 64, "a" * 64, "OOD_REFERENCE_HASH_MISMATCH")):
        with pytest.raises(image_ood.OodReferenceError, match=code):
            image_ood.load_reference(path, sha, checkpoint)
    with pytest.raises(image_ood.OodReferenceError, match="OOD_REFERENCE_MISSING"):
        image_ood.load_reference(tmp_path / "absent.npz", digest, "a" * 64)
