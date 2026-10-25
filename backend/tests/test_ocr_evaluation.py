"""OCR CER/WER evaluation contracts and privacy boundaries."""

from __future__ import annotations

import hashlib
import json

import pytest

from app.models.entities import EvaluationRun
from app.services.evaluation_metrics import EvaluationInputError
from app.services.ocr_evaluation import SCHEMA_VERSION, evaluate_ocr
from conftest import get_auth_headers


IMAGE_HASH = hashlib.sha256(b"deidentified-rendered-page").hexdigest()


def _artifact(role: str, text: str, *, image_hash: str = IMAGE_HASH, document_id: str = "doc-001") -> bytes:
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_role": role,
            "pages": [
                {
                    "document_id": document_id,
                    "page": 1,
                    "source_image_sha256": image_hash,
                    "text": text,
                }
            ],
        }
    ).encode("utf-8")


def test_ocr_evaluator_computes_cer_wer_without_returning_text_or_raw_ids():
    gold = _artifact("gold", "Glucose 5.2\nNormal")
    prediction = _artifact("prediction", "Glocose 5.2\r\nNormal")

    result = evaluate_ocr(gold, prediction)

    assert result["n"] == 1
    assert result["n_groups"] == 1
    assert result["metrics"]["character_edits"] == 1
    assert result["metrics"]["word_edits"] == 1
    assert result["metrics"]["character_error_rate"] == pytest.approx(1 / len("Glucose 5.2\nNormal"))
    assert result["metrics"]["word_error_rate"] == pytest.approx(1 / 3)
    assert result["metrics"]["exact_page_rate"] == 0
    assert result["per_page"][0]["document_id_sha256"] == hashlib.sha256(b"doc-001").hexdigest()
    serialized = json.dumps(result)
    assert "Glucose" not in serialized
    assert "Glocose" not in serialized
    assert "doc-001" not in serialized


def test_ocr_evaluator_requires_the_same_source_page_manifest():
    with pytest.raises(EvaluationInputError, match="source-image hash"):
        evaluate_ocr(
            _artifact("gold", "text"),
            _artifact("prediction", "text", image_hash="a" * 64),
        )


def test_ocr_evaluator_rejects_empty_or_non_strict_artifacts():
    empty = json.dumps(
        {"schema_version": SCHEMA_VERSION, "artifact_role": "gold", "pages": []}
    ).encode()
    with pytest.raises(EvaluationInputError, match="at least one page"):
        evaluate_ocr(empty, _artifact("prediction", "text"))

    unexpected = json.loads(_artifact("gold", "text"))
    unexpected["pages"][0]["engine"] = "untrusted"
    with pytest.raises(EvaluationInputError, match="must contain exactly"):
        evaluate_ocr(json.dumps(unexpected).encode(), _artifact("prediction", "text"))


def test_ocr_api_requires_attestations_and_persists_only_aggregate_metrics(
    client, db_session, test_users
):
    user = test_users["clinician_a"]
    headers = get_auth_headers(user)
    gold = _artifact("gold", "PRIVATE_TEST_MARKER reference")
    prediction = _artifact("prediction", "PRIVATE_TEST_MARKER prediction")
    files = {
        "gold": ("gold.json", gold, "application/json"),
        "predictions": ("prediction.json", prediction, "application/json"),
    }

    rejected = client.post(
        "/api/v1/evaluation/ocr",
        headers=headers,
        files=files,
        data={"deidentified": "false", "independently_transcribed": "true"},
    )
    assert rejected.status_code == 400

    response = client.post(
        "/api/v1/evaluation/ocr",
        headers=headers,
        files=files,
        data={"deidentified": "true", "independently_transcribed": "true"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["task_type"] == "ocr"
    expected_input_digest = hashlib.sha256(
        hashlib.sha256(gold).digest() + hashlib.sha256(prediction).digest()
    ).hexdigest()
    assert body["input_sha256"] == expected_input_digest
    assert body["evaluation_context"]["evaluation_input_sha256"] == (
        expected_input_digest
    )
    assert body["evaluation_context"]["evaluation_input_digest_scheme"] == (
        "SHA256_ORDERED_PART_DIGESTS_V1"
    )
    assert body["evaluation_context"]["reporting_status"] == "EXPLORATORY"
    assert "model_id" in body["evaluation_context"]["reporting_blockers"]
    assert "PRIVATE_TEST_MARKER" not in response.text
    run = db_session.query(EvaluationRun).filter(EvaluationRun.id == body["run_id"]).one()
    assert "PRIVATE_TEST_MARKER" not in json.dumps(run.metrics)
    assert run.config["deidentified_attested"] is True
    assert run.config["independently_transcribed_attested"] is True
