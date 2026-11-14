"""Contract tests for the authenticated, read-only dataset registry API."""

import json
from pathlib import Path

from tests.conftest import get_auth_headers


REGISTRY_PATH = Path(__file__).resolve().parents[2] / "dataset_registry" / "datasets.json"
TASK_AUDIT_PATH = Path(__file__).resolve().parents[2] / "dataset_registry" / "tasks.json"
# Registered by their own scripts once an approved download completes (2026-11-06).
SCRIPT_REGISTERED = {"msd-task07-pancreas", "msd-task03-liver", "nlm-tb-cxr", "lidc-idri-subset",
                     # Downloads approved by the owner on 2026-11-14 (scripts/acquire_approved_public_datasets.py), each
                     # registered with its download receipt by ml_training/tabular.py or its own registration script.
                     "uci-heart-disease", "uci-chronic-kidney-disease", "uci-diabetes-130-hospitals", "uci-breast-cancer-wisconsin-diagnostic",
                     "uci-thyroid-hypothyroid", "uci-indian-liver-patient", "uci-hepatitis", "uci-parkinsons",
                     "uci-cervical-cancer-risk-factors", "nih-malaria-cell-images", "fetal-planes-db",
                     "msd-task09-spleen", "msd-task05-prostate", "msd-task04-hippocampus", "msd-task07-pancreas", "hc18-fetal-head"}


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
    datasets = response.json()["datasets"]
    # Datasets downloaded with the owner's approval on 2026-11-06 are added by their own registration scripts
    # (scripts/register_msd_ct_dataset.py, register_nlm_tb_dataset.py, prepare_lidc_dataset.py --register) as each
    # download finishes. Research source authorization must not overwrite a
    # recorded hold for the newly declared commercial training purpose.
    script_registered = [item for item in datasets if item["id"] in SCRIPT_REGISTERED]
    for item in script_registered:
        assert item["license"]["authorization_status"] == "VERIFIED" and item["license"].get("citation")
        assert len(item["tasks"]) == 1
        task = item["tasks"][0]
        if task["readiness"] == "RIGHTS_REVIEW_REQUIRED_FOR_DECLARED_PURPOSE":
            assert task["training_eligible"] is False and task["commercial_development_eligible"] is False
            assert "rights" in task["training_blocker"].lower()
        else:
            assert (task["training_eligible"], task["readiness"]) == (True, "READY_FOR_TRAINING")
    extra = len(script_registered)
    extra_trainable = sum(item["tasks"][0]["training_eligible"] for item in script_registered)
    # KiTS19's existing record becomes trainable only after CT/mask matching and
    # voxel/geometry inspection; it is not an additional dataset or task unit.
    kits = next(item for item in datasets if item["id"] == "kits19-labels")
    kits_ready = int(bool(kits["tasks"][0]["training_eligible"]))
    if kits_ready:
        assert kits["labels"] == "PAIRED_CT_AND_MASKS"
        assert kits["tasks"][0]["preparation"]["cases"] == 210
        assert kits["license"]["authorization_status"] == "VERIFIED"
    task_units = [task for dataset in datasets for task in dataset["tasks"]]
    assert len(datasets) == 64 + extra
    # The audit source defines 35 task units; cardiac MRI became READY_FOR_TRAINING on
    # 2026-10-25 and MURA on 2026-10-31, each after the repository owner's recorded authorization.
    # ISLES 2022 (CC BY 4.0) and MSD BrainTumour (CC BY-SA 4.0) were added on 2026-11-05 under their
    # published licences, and NIH ChestX-ray14 for evaluation only (no training). On 2026-11-06 the owner
    # defined the fracture target (one class, the 'humerus' anatomy class excluded) and confirmed the
    # EchoNet-Dynamic agreement, so both tasks became READY_FOR_TRAINING.
    assert len(task_units) == 35 + extra
    assert sum(task["training_eligible"] for task in task_units) == 16 + extra_trainable + kits_ready
    assert {task["readiness"] for task in task_units} == {
        "READY_FOR_TRAINING",
        "EXPLORATORY_TRAINING_ONLY",
        "BLOCKED",
        "EVALUATED",
    } | ({"RIGHTS_REVIEW_REQUIRED_FOR_DECLARED_PURPOSE"} if extra_trainable < extra else set())
    assert sum(task["readiness"] == "EVALUATED" and not task["training_eligible"] for task in task_units) == 1
    assert sum(task["readiness"] == "READY_FOR_TRAINING" for task in task_units) == 15 + extra_trainable + kits_ready
    assert sum(task["readiness"] == "EXPLORATORY_TRAINING_ONLY" for task in task_units) == 1
    assert sum(task["readiness"] == "BLOCKED" for task in task_units) == 18 - kits_ready
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
