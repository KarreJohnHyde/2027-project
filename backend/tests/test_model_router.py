"""Routing ambiguity, execution guard delegation and per-case access control."""
from types import SimpleNamespace
from copy import deepcopy
import io
from PIL import Image
import pytest
from app.services import model_router
from app.models.entities import ModalityType
from tests.conftest import get_auth_headers


@pytest.fixture
def routing(tmp_path, monkeypatch):
    path = tmp_path / "image.png"
    path.write_bytes(b"fixture")
    upload = SimpleNamespace(id=1, is_associated=True, withdrawn_at=None, superseded_by_file_id=None,
                             file_path=str(path), stored_filename="image.png", modality=ModalityType.IMAGE)
    entries = [{"model_id": "fixture", "display_name": "Fixture", "research_inference": True,
                "task": "image_classification", "anatomy": "blood", "supported_modalities": ["MICROSCOPY"],
                "supported_classes": ["a", "b"], "artifact_bundle": {"checkpoint_sha256": "fixture"}}]
    monkeypatch.setattr(model_router.model_inference, "_load_registry", lambda: {"models": entries})
    monkeypatch.setattr(model_router.model_inference, "research_gate", lambda _: {"allowed": True, "blockers": []})
    monkeypatch.setattr(model_router.model_inference, "check_input", lambda *args: None)
    return upload, entries


def test_source_cannot_be_guessed_from_filename(routing):
    upload, _ = routing
    upload.stored_filename = "blood-leukemia.png"
    assert model_router.plan_upload(upload)["status"] == "NEEDS_CONTEXT"


def test_generic_ct_tag_is_not_kidney_stone_anatomy(routing, monkeypatch):
    from contextlib import contextmanager
    upload, _ = routing
    upload.stored_filename = "scan.dcm"
    @contextmanager
    def materialize(path):
        yield path
    monkeypatch.setattr(model_router.upload_store, "materialize", materialize)
    monkeypatch.setattr(model_router, "read_metadata", lambda _: {"modality_tag": "CT", "body_part": None})
    assert model_router.plan_upload(upload)["status"] == "NEEDS_CONTEXT"


def test_unique_and_ambiguous_task_selection(routing):
    upload, entries = routing
    plan = model_router.plan_upload(upload, declared_input_type="MICROSCOPY")
    assert plan["selected_model_id"] == "fixture"
    entries.append({**deepcopy(entries[0]), "model_id": "other", "task": "semantic_segmentation"})
    assert model_router.plan_upload(upload, declared_input_type="MICROSCOPY")["status"] == "AMBIGUOUS"
    assert model_router.plan_upload(upload, declared_input_type="MICROSCOPY", task="segmentation")["selected_model_id"] == "other"
    assert model_router.plan_upload(upload, declared_input_type="MICROSCOPY", target="unseen disease")["status"] == "ABSTAIN"


def test_blocked_model_never_selected(routing, monkeypatch):
    upload, _ = routing
    monkeypatch.setattr(model_router.model_inference, "research_gate", lambda _: {"allowed": False, "blockers": ["CHECKPOINT_HASH_MISMATCH"]})
    plan = model_router.plan_upload(upload, declared_input_type="MICROSCOPY")
    assert plan["selected_model_id"] is None
    assert plan["rejected"][0]["reasons"] == ["CHECKPOINT_HASH_MISMATCH"]


def test_adapter_refusal_is_preserved(routing, monkeypatch):
    upload, _ = routing
    def refuse(*args):
        raise model_router.model_inference.InferenceNotPermitted("WRONG_CONTAINER")
    monkeypatch.setattr(model_router.model_inference, "check_input", refuse)
    plan = model_router.plan_upload(upload, declared_input_type="MICROSCOPY")
    assert plan["status"] == "ABSTAIN" and plan["rejected"][0]["reasons"] == ["WRONG_CONTAINER"]


def test_inactive_forecast_and_generic_csv_are_refused(routing):
    upload, _ = routing
    assert model_router.plan_upload(upload, task="forecast")["reason"] == "NO_VALIDATED_UPLOAD_FORECAST_MODEL"
    upload.modality = ModalityType.REPORT
    assert model_router.plan_upload(upload)["diagnostic_predictions"] is False
    assert model_router.plan_upload(upload, task="classification")["status"] == "ABSTAIN"
    upload.withdrawn_at = "withdrawn"
    assert model_router.plan_upload(upload)["reason"] == "UPLOAD_NOT_ACTIVE_EVIDENCE"


def _upload(client, headers):
    case = client.post("/api/v1/cases", json={"pseudonymous_id": "ROUTER-SYNTHETIC"}, headers=headers).json()["id"]
    body = io.BytesIO()
    Image.new("RGB", (48, 48), (120, 130, 140)).save(body, format="PNG")
    response = client.post(f"/api/v1/cases/{case}/uploads", files={"file": ("frame.png", body.getvalue(), "image/png")},
                           data={"deidentified": "true"}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.private_workspace
def test_routes_require_access_and_ambiguity_does_not_execute(client, test_users, monkeypatch):
    from app.routers import research_models
    headers = get_auth_headers(test_users["clinician_a"])
    file_id = _upload(client, headers)
    endpoint = f"/api/v1/uploads/{file_id}/model-selection"
    assert client.post(endpoint, json={}).status_code in (401, 403)
    other = get_auth_headers(test_users["clinician_b"])
    assert client.post(endpoint, json={}, headers=other).status_code == 403
    monkeypatch.setattr(model_router, "plan_upload", lambda *args, **kwargs: {"status": "AMBIGUOUS", "candidates": []})
    def forbidden(*args, **kwargs):
        pytest.fail("Ambiguous selection executed inference")
    monkeypatch.setattr(research_models, "run_research_inference", forbidden)
    assert client.post(endpoint, json={}, headers=headers).json()["status"] == "AMBIGUOUS"
    assert client.post(f"/api/v1/uploads/{file_id}/automatic-inference", json={}, headers=headers).status_code == 409


def test_automatic_execution_requires_attestation_and_delegates(client, test_users, monkeypatch):
    from app.routers import research_models
    headers = get_auth_headers(test_users["clinician_a"])
    file_id = _upload(client, headers)
    monkeypatch.setattr(model_router, "plan_upload", lambda *args, **kwargs: {
        "status": "SELECTED", "selected_model_id": "fixture", "handler": "registered_research", "declared_input_type": "MICROSCOPY"})
    seen = []
    def execute(file_id, request, key, db, user):
        seen.append((request.model_id, request.declared_input_type, key))
        return {"delegated": True}
    monkeypatch.setattr(research_models, "run_research_inference", execute)
    endpoint = f"/api/v1/uploads/{file_id}/automatic-inference"
    assert client.post(endpoint, json={}, headers=headers).status_code == 400
    assert not seen
    assert client.post(endpoint, json={"attest_source_input": True}, headers={**headers, "Idempotency-Key": "routing-fixture"}).json() == {"delegated": True}
    assert seen == [("fixture", "MICROSCOPY", "routing-fixture")]
