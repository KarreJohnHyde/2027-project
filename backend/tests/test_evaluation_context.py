"""Focused tests for the registry-backed Validation Center reporting gate."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import PROJECT_ROOT
from app.routers.evaluation import _stored_context
from app.services import evaluation_context
from conftest import get_auth_headers


MODEL_ID = "gi_kvasir_v2_classifier"
DATASET_ID = "kvasir-v2"
DATASET_VERSION = "f3eedd730fe4a33d30048a69e1cfe9af3aeae4804b5c20f552bda11450c22cf5"
CHECKPOINT = "sha256:6d7494d19e52c0b5462f90637e35f474d9db1950217e5a40e95cda4bec27a8e4"
OTHER_REGISTERED_CHECKPOINT = "sha256:e9267f9a6e9fb36cc08fd27a888096209febf023ce2f140c5f7d38f6839b9fcb"
INPUT_SHA256 = "23a9c7439914170a466925b700c7f726da49a41eb3adde6fba9edd02eda3456a"
INPUT_PATH = PROJECT_ROOT / "artifacts" / "training" / "gi_kvasir_v2_classifier-20261024T151359Z" / "predictions_test.csv"


def _registered_input_bytes() -> bytes:
    """Skip artifact-backed assertions only when the local artifact is absent."""
    try:
        return INPUT_PATH.read_bytes()
    except FileNotFoundError:
        pytest.skip(
            "requires the untracked registered held-out prediction artifact: "
            f"{INPUT_PATH}"
        )


@pytest.fixture(autouse=True)
def stable_revision(monkeypatch):
    monkeypatch.setattr(
        evaluation_context,
        "code_revision",
        lambda: {
            "commit": "a" * 40,
            "source": "test",
            "working_tree_clean": True,
        },
    )


def _resolve(**overrides):
    values = {
        "evaluation_task": "multiclass",
        "model_id": MODEL_ID,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "split": "test",
        "checkpoint": CHECKPOINT,
        "input_sha256": INPUT_SHA256,
        "input_digest_scheme": evaluation_context.RAW_INPUT_DIGEST_SCHEME,
    }
    values.update(overrides)
    return evaluation_context.resolve_evaluation_context(**values)


def _assert_exploratory(context, blocker):
    assert context["reporting_status"] == "EXPLORATORY"
    assert blocker in context["reporting_blockers"]
    assert context["registry_resolution"]["exact_match"] is False


def test_model_id_is_required_even_when_checkpoint_resolves():
    _assert_exploratory(_resolve(model_id=None), "model_id")


def test_unknown_model_is_not_resolved_from_user_supplied_text():
    _assert_exploratory(_resolve(model_id="unregistered-model"), "model_not_registered")


@pytest.mark.parametrize(
    ("checkpoint", "blocker"),
    [
        (CHECKPOINT.removeprefix("sha256:"), "checkpoint_sha256_format"),
        ("sha256:" + "0" * 64, "checkpoint_sha256_zero"),
        ("sha256:" + "1" * 64, "checkpoint_not_registered"),
    ],
)
def test_malformed_zero_and_unresolved_checkpoint_hashes_are_blocked(
    checkpoint, blocker
):
    _assert_exploratory(_resolve(checkpoint=checkpoint), blocker)


def test_checkpoint_registered_to_another_model_is_a_mismatch():
    _assert_exploratory(
        _resolve(checkpoint=OTHER_REGISTERED_CHECKPOINT),
        "model_checkpoint_mismatch",
    )


def test_missing_uploaded_input_digest_is_blocked():
    _assert_exploratory(
        _resolve(input_sha256=None),
        "evaluation_input_sha256",
    )


def test_model_without_registered_input_binding_stays_exploratory(monkeypatch):
    registry = deepcopy(evaluation_context._load_registry())
    model = next(item for item in registry["models"] if item["model_id"] == MODEL_ID)
    del model["artifact_bundle"]["evaluation_input"]
    monkeypatch.setattr(evaluation_context, "_load_registry", lambda: registry)

    _assert_exploratory(_resolve(), "evaluation_input_not_registered")


def test_uploaded_input_digest_must_match_registered_held_out_bytes():
    _assert_exploratory(
        _resolve(input_sha256="1" * 64),
        "evaluation_input_hash_mismatch",
    )


def test_legacy_metadata_only_eligible_run_is_read_back_as_exploratory():
    run = SimpleNamespace(
        input_sha256="2" * 64,
        metrics={
            "evaluation_context": {
                "reporting_status": "ELIGIBLE_FOR_REPORTING",
                "reporting_blockers": [],
            }
        },
    )

    context = _stored_context(run)

    assert context["reporting_status"] == "EXPLORATORY"
    assert context["reporting_blockers"] == [
        "evaluation_input_binding_not_recorded"
    ]


@pytest.mark.parametrize(
    ("changes", "blocker"),
    [
        ({"dataset_id": "unknown-dataset"}, "dataset_not_registered"),
        ({"dataset_version": "frozen-v1"}, "dataset_version_not_registered"),
    ],
)
def test_unknown_dataset_or_version_is_blocked(changes, blocker):
    _assert_exploratory(_resolve(**changes), blocker)


def test_validation_split_never_qualifies_as_held_out_reporting_evidence():
    context = _resolve(split="validation")
    _assert_exploratory(context, "held_out_test_split")
    assert context["registry_resolution"]["split"] is None


def test_evaluator_must_match_the_registered_model_label_contract():
    _assert_exploratory(
        _resolve(evaluation_task="classification"),
        "evaluation_task_model_label_contract_mismatch",
    )


def test_exact_registered_tuple_is_internal_research_reporting_evidence_only():
    _registered_input_bytes()
    context = _resolve()

    assert context["reporting_status"] == "ELIGIBLE_FOR_REPORTING"
    assert context["reporting_blockers"] == []
    assert context["reporting_scope"] == (
        "RESEARCH_EVIDENCE_ONLY_NOT_CLINICAL_ACTIVATION"
    )
    assert context["registry_resolution"] == {
        "model_id": MODEL_ID,
        "checkpoint_sha256": CHECKPOINT,
        "checkpoint_artifact_verified": True,
        "evaluation_input_sha256": INPUT_SHA256,
        "evaluation_input_artifact_verified": True,
        "evaluation_input_format": "MEDTWIN_MULTICLASS_CSV_V1",
        "evaluation_input_digest_scheme": evaluation_context.RAW_INPUT_DIGEST_SCHEME,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "task_id": "kvasir-v2-8class",
        "task_type": "CLASSIFICATION",
        "split": "test",
        "split_n": 1202,
        "exact_match": True,
    }


def test_multiclass_endpoint_binds_reportability_to_exact_registered_bytes(
    client, test_users
):
    headers = get_auth_headers(test_users["clinician_a"])
    form = {
        "model_id": MODEL_ID,
        "dataset_label": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "split": "test",
        "checkpoint": CHECKPOINT,
    }
    registered_bytes = _registered_input_bytes()

    exact = client.post(
        "/api/v1/evaluation/multiclass",
        files={"file": ("predictions_test.csv", registered_bytes, "text/csv")},
        data=form,
        headers=headers,
    )
    assert exact.status_code == 200, exact.text
    exact_run = exact.json()
    assert exact_run["input_sha256"] == INPUT_SHA256
    assert exact_run["evaluation_context"]["reporting_status"] == (
        "ELIGIBLE_FOR_REPORTING"
    )
    assert exact_run["evaluation_context"]["reporting_scope"] == (
        "RESEARCH_EVIDENCE_ONLY_NOT_CLINICAL_ACTIVATION"
    )
    assert exact_run["evaluation_context"]["registry_resolution"][
        "evaluation_input_artifact_verified"
    ] is True

    altered = client.post(
        "/api/v1/evaluation/multiclass",
        files={"file": ("predictions_test.csv", registered_bytes + b"\n", "text/csv")},
        data=form,
        headers=headers,
    )
    assert altered.status_code == 200, altered.text
    altered_context = altered.json()["evaluation_context"]
    assert altered_context["reporting_status"] == "EXPLORATORY"
    assert "evaluation_input_hash_mismatch" in altered_context["reporting_blockers"]
