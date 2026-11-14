"""Typed-value inference for the registered UCI tabular research models: contract, envelope checks and refusals.

Uses the registered checkpoints and envelopes when they exist in this checkout; values are generated from the envelope."""

import json

import pytest

# Running a tabular model needs pandas, scikit-learn and joblib; the CI backend environment has none of them.
for _module in ("pandas", "sklearn", "joblib"):
    pytest.importorskip(_module)

from app.models.entities import AuditEvent
from app.services import model_inference
from tests.conftest import get_auth_headers

RESEARCH_MODEL = "tabular_heart_disease_uci"
EXPLORATORY_MODEL = "tabular_cervical_biopsy_uci"


def _registered(model_id):
    model = next((m for m in model_inference._load_registry()["models"] if m["model_id"] == model_id), None)
    if model is None or not model["artifact_bundle"].get("input_envelope_path"):
        pytest.skip(f"{model_id} or its envelope is not registered in this checkout")
    try:
        model_inference.get_model(model_id)
    except model_inference.InferenceNotPermitted:
        pytest.skip(f"{model_id} checkpoint is not available in this checkout")
    return model


def _valid_values(contract):
    def value(field):
        if field["type"] != "number":
            return field["categories"][0]
        return field["allowed_values"][0] if field.get("allowed_values") else (field["min"] + field["max"]) / 2
    return {field["name"]: value(field) for field in contract["fields"]}


def test_contract_and_a_valid_run(client, db_session, test_users):
    _registered(RESEARCH_MODEL)
    headers = get_auth_headers(test_users["clinician_a"])
    contract = client.get(f"/api/v1/research-models/{RESEARCH_MODEL}/tabular-contract", headers=headers)
    assert contract.status_code == 200, contract.text
    body = contract.json()
    assert body["runnable"] is True and len(body["fields"]) == 13 and body["output_status"] == "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED"
    values = _valid_values(body)
    run = client.post(f"/api/v1/research-models/{RESEARCH_MODEL}/tabular-inference", json={"values": values}, headers=headers)
    assert run.status_code == 200, run.text
    result = run.json()
    assert 0.0 <= result["probability"] <= 1.0 and result["stored"] is False
    assert result["at_or_above_threshold"] == (result["probability"] >= result["threshold"])
    events = db_session.query(AuditEvent).filter(AuditEvent.action == "TABULAR_RESEARCH_INFERENCE").all()
    assert events and all(str(values["age"]) not in json.dumps(event.details) for event in events)  # values never logged


def test_refusals_name_the_reason(client, test_users):
    _registered(RESEARCH_MODEL)
    headers = get_auth_headers(test_users["clinician_a"])
    url = f"/api/v1/research-models/{RESEARCH_MODEL}/tabular-inference"
    contract = client.get(f"/api/v1/research-models/{RESEARCH_MODEL}/tabular-contract", headers=headers).json()
    values = _valid_values(contract)
    age = next(field for field in contract["fields"] if field["name"] == "age")
    cases = [
        ({**values, "age": age["max"] * 10}, "OUT_OF_DEVELOPMENT_RANGE"),
        ({**values, "not_a_field": 1}, "UNKNOWN_FIELD"),
        ({**values, "age": "abc"}, "NOT_A_NUMBER"),
        ({**values, "sex": 0.5}, "NOT_AN_ALLOWED_CODE"),  # sex is coded 0/1 in the source table
        ({name: None for name in values}, None),  # all blank: required-field or too-many-blank refusal
    ]
    for payload, code in cases:
        response = client.post(url, json={"values": payload}, headers=headers)
        assert response.status_code == 400, payload
        detail = response.json()["detail"]
        assert (code in detail) if code else ("MISSING_REQUIRED_FIELD" in detail or "TOO_MANY_BLANK_FIELDS" in detail)


def test_exploratory_and_non_tabular_models_are_refused(client, test_users):
    _registered(EXPLORATORY_MODEL)
    headers = get_auth_headers(test_users["clinician_a"])
    contract = client.get(f"/api/v1/research-models/{EXPLORATORY_MODEL}/tabular-contract", headers=headers).json()
    assert contract["runnable"] is False
    refused = client.post(f"/api/v1/research-models/{EXPLORATORY_MODEL}/tabular-inference", json={"values": _valid_values(contract)}, headers=headers)
    assert refused.status_code == 400 and "EXPLORATORY_ONLY" in refused.json()["detail"]
    image = client.post("/api/v1/research-models/brain_ct_rsna_ich_classifier/tabular-inference", json={"values": {}}, headers=headers)
    assert image.status_code == 400 and ("MODEL_NOT_TABULAR" in image.json()["detail"] or "not runnable" in image.json()["detail"])


def test_an_unauthenticated_request_is_rejected(client):
    assert client.post(f"/api/v1/research-models/{RESEARCH_MODEL}/tabular-inference", json={"values": {}}).status_code in (401, 403)
