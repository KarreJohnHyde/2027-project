"""Contract tests for the authenticated, read-only dataset registry API."""

import json
from pathlib import Path

from tests.conftest import get_auth_headers


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "dataset_registry" / "datasets.json"
TASK_AUDIT_PATH = Path(__file__).resolve().parents[2] / "dataset_registry" / "tasks.json"


def _source_registry():
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _source_task_audit():
    return json.loads(TASK_AUDIT_PATH.read_text(encoding="utf-8"))


def test_dataset_registry_requires_authentication(client):
    assert client.get("/api/v1/datasets").status_code == 401
    assert client.get("/api/v1/datasets/task-audit").status_code == 401
    assert client.get("/api/v1/datasets/data").status_code == 401


def test_dataset_registry_list_preserves_generated_evidence(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    response = client.get("/api/v1/datasets", headers=headers)

    assert response.status_code == 200
    assert response.json() == _source_registry()
    assert len(response.json()["datasets"]) == 33
    assert response.json()["global_readiness"] == "CATALOG_ONLY_NOT_TRAINING_READY"
    assert all(item["training_eligible"] is False for item in response.json()["datasets"])
    assert all(item["validation_eligible"] is False for item in response.json()["datasets"])


def test_dataset_registry_detail_and_not_found(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    source = _source_registry()
    expected = next(item for item in source["datasets"] if item["dataset_id"] == "data")

    response = client.get("/api/v1/datasets/data", headers=headers)
    assert response.status_code == 200
    assert response.json() == expected
    assert response.json()["annotation_format"] == "COCO_JSON"
    assert response.json()["license_status"] == "unknown"
    assert response.json()["training_eligible"] is False

    missing = client.get("/api/v1/datasets/not-registered", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Dataset 'not-registered' is not registered."


def test_dataset_task_audit_preserves_generated_task_evidence(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])

    response = client.get("/api/v1/datasets/task-audit", headers=headers)

    assert response.status_code == 200
    assert response.json() == _source_task_audit()
    task_units = [task for dataset in response.json()["datasets"] for task in dataset["tasks"]]
    assert len(response.json()["datasets"]) == 61
    # The audit source defines 32 task units; cardiac MRI became READY_FOR_TRAINING on
    # 2026-10-25 after the repository owner's recorded authorization.
    assert len(task_units) == 32
    assert sum(task["training_eligible"] for task in task_units) == 11
    assert {task["readiness"] for task in task_units} == {
        "READY_FOR_TRAINING",
        "EXPLORATORY_TRAINING_ONLY",
        "BLOCKED",
    }
    assert sum(task["readiness"] == "READY_FOR_TRAINING" for task in task_units) == 10
    assert sum(task["readiness"] == "EXPLORATORY_TRAINING_ONLY" for task in task_units) == 1
    assert sum(task["readiness"] == "BLOCKED" for task in task_units) == 21
    assert sum(task["readiness"] == "NOT_STARTED" for task in task_units) == 0
    assert all("flags" in task for task in task_units)


def test_dataset_registry_exposes_no_mutation_routes(client, test_users):
    headers = get_auth_headers(test_users["admin"])

    assert client.post("/api/v1/datasets", json={}, headers=headers).status_code == 405
    assert client.post("/api/v1/datasets/task-audit", json={}, headers=headers).status_code == 405
    assert client.patch("/api/v1/datasets/task-audit", json={}, headers=headers).status_code == 405
    assert client.delete("/api/v1/datasets/task-audit", headers=headers).status_code == 405
    assert client.patch("/api/v1/datasets/data", json={}, headers=headers).status_code == 405
    assert client.delete("/api/v1/datasets/data", headers=headers).status_code == 405


def test_dataset_registry_fails_closed_when_artifact_is_unavailable(
    client, test_users, monkeypatch, tmp_path
):
    headers = get_auth_headers(test_users["clinician_a"])
    missing_path = tmp_path / "not-generated.json"
    monkeypatch.setenv("DATASET_REGISTRY_PATH", str(missing_path))

    response = client.get("/api/v1/datasets", headers=headers)

    assert response.status_code == 503
    assert response.json() == {"detail": "The generated dataset registry is unavailable."}
    assert str(missing_path) not in response.text


def test_dataset_task_audit_fails_closed_when_artifact_is_unavailable(
    client, test_users, monkeypatch, tmp_path
):
    headers = get_auth_headers(test_users["clinician_a"])
    missing_path = tmp_path / "not-generated.json"
    monkeypatch.setenv("DATASET_TASK_AUDIT_PATH", str(missing_path))

    response = client.get("/api/v1/datasets/task-audit", headers=headers)

    assert response.status_code == 503
    assert response.json() == {"detail": "The generated dataset task audit is unavailable."}
    assert str(missing_path) not in response.text
