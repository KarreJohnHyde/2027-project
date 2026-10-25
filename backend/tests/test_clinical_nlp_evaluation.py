"""Clinical NLP span evaluation without a fabricated gold corpus or metrics."""

from __future__ import annotations

import hashlib
import json

import pytest

from app.services.clinical_nlp_evaluation import SCHEMA_VERSION, evaluate_clinical_nlp
from app.services.evaluation_metrics import EvaluationInputError
from tests.conftest import get_auth_headers


DOCUMENTS = [
    {"document_id": "doc-001", "character_count": 50, "document_sha256": "a" * 64},
    {"document_id": "doc-002", "character_count": 40, "document_sha256": "b" * 64},
]


def _span(
    document_id: str,
    start: int,
    end: int,
    label: str,
    *,
    assertion: str = "CERTAIN",
    negation: str = "AFFIRMED",
    temporality: str = "CURRENT",
    code_system: str | None = None,
    concept_id: str | None = None,
) -> dict:
    span = {
        "document_id": document_id,
        "start": start,
        "end": end,
        "label": label,
        "assertion": assertion,
        "negation": negation,
        "temporality": temporality,
    }
    if code_system is not None:
        span["code_system"] = code_system
    if concept_id is not None:
        span["concept_id"] = concept_id
    return span


def _artifact(role: str, spans: list[dict], documents: list[dict] | None = None) -> bytes:
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "artifact_role": role,
            "documents": DOCUMENTS if documents is None else documents,
            "spans": spans,
        }
    ).encode("utf-8")


def _files(gold: bytes, predictions: bytes) -> dict:
    return {
        "gold": ("sensitive-gold-name.json", gold, "application/json"),
        "predictions": ("sensitive-prediction-name.json", predictions, "application/json"),
    }


def _attestations(**extra: str) -> dict[str, str]:
    return {"deidentified": "true", "independently_annotated": "true", **extra}


def test_exact_overlap_label_errors_and_sample_provenance():
    gold = [
        _span("doc-001", 0, 5, "CONDITION"),
        _span("doc-001", 10, 15, "MEDICATION"),
        _span("doc-002", 0, 4, "CONDITION", temporality="HISTORICAL"),
    ]
    predictions = [
        _span("doc-001", 0, 5, "CONDITION"),
        _span("doc-001", 11, 16, "MEDICATION"),
        _span("doc-002", 0, 4, "SYMPTOM", temporality="HISTORICAL"),
    ]

    result = evaluate_clinical_nlp(_artifact("gold", gold), _artifact("prediction", predictions))

    assert result["exact_span"] == {
        "tp": 1,
        "fp": 2,
        "fn": 2,
        "precision": pytest.approx(1 / 3),
        "recall": pytest.approx(1 / 3),
        "f1": pytest.approx(1 / 3),
    }
    assert result["overlap"] == {
        "tp": 2,
        "fp": 1,
        "fn": 1,
        "precision": pytest.approx(2 / 3),
        "recall": pytest.approx(2 / 3),
        "f1": pytest.approx(2 / 3),
    }
    assert result["error_counts"]["boundary_mismatches_on_label_matched_overlaps"] == 1
    assert result["error_counts"]["label_mismatches_on_geometric_overlaps"] == 1
    medication = next(row for row in result["per_label"] if row["label"] == "MEDICATION")
    assert medication["exact_span"]["tp"] == 0
    assert medication["overlap"]["tp"] == 1
    assert {row["document_id_sha256"] for row in result["documents"]} == {
        hashlib.sha256(b"doc-001").hexdigest(),
        hashlib.sha256(b"doc-002").hexdigest(),
    }
    assert result["provenance"]["document_count"] == 2
    assert result["provenance"]["document_manifests_identical"] is True
    assert "doc-001" not in json.dumps(result)  # raw document identifiers are never persisted


def test_context_mismatches_are_counted_without_changing_span_matches():
    gold = [_span("doc-001", 3, 9, "CONDITION")]
    predictions = [
        _span(
            "doc-001",
            3,
            9,
            "CONDITION",
            assertion="UNCERTAIN",
            negation="NEGATED",
            temporality="HISTORICAL",
        )
    ]

    result = evaluate_clinical_nlp(_artifact("gold", gold), _artifact("prediction", predictions))

    assert result["exact_span"]["f1"] == 1.0
    for field in ("assertion", "negation", "temporality"):
        summary = result["context_confusion"]["exact_span"][field]
        assert summary["evaluated"] == 1
        assert summary["correct"] == 0
        assert summary["errors"] == 1
        assert summary["accuracy"] == 0.0
    condition = result["per_label"][0]
    assert condition["context_errors"]["exact_span"] == {
        "assertion": 1,
        "negation": 1,
        "temporality": 1,
    }


def test_normalized_concept_links_report_correct_missing_and_wrong_counts():
    gold = [
        _span("doc-001", 0, 2, "CONDITION", code_system="SNOMED_CT", concept_id="111"),
        _span("doc-001", 3, 5, "CONDITION", code_system="SNOMED_CT", concept_id="222"),
        _span("doc-001", 6, 8, "CONDITION", code_system="SNOMED_CT", concept_id="333"),
        _span("doc-001", 9, 11, "CONDITION"),
    ]
    predictions = [
        _span("doc-001", 0, 2, "CONDITION", code_system="SNOMED_CT", concept_id="111"),
        _span("doc-001", 3, 5, "CONDITION"),
        _span("doc-001", 6, 8, "CONDITION", code_system="SNOMED_CT", concept_id="999"),
        _span("doc-001", 9, 11, "CONDITION", code_system="SNOMED_CT", concept_id="444"),
    ]

    result = evaluate_clinical_nlp(_artifact("gold", gold), _artifact("prediction", predictions))

    links = result["concept_linking"]["exact_span"]
    assert links == {
        "evaluated": 3,
        "correct": 1,
        "missing": 1,
        "wrong": 1,
        "errors": 2,
        "accuracy": pytest.approx(1 / 3),
        "confusion": [
            {"gold": "SNOMED_CT:111", "predicted": "SNOMED_CT:111", "count": 1},
            {"gold": "SNOMED_CT:222", "predicted": "__MISSING__", "count": 1},
            {"gold": "SNOMED_CT:333", "predicted": "SNOMED_CT:999", "count": 1},
        ],
    }
    assert result["metrics"]["exact_concept_link_accuracy"] == pytest.approx(1 / 3)
    assert result["per_label"][0]["concept_link_errors"]["exact_span"] == 2


@pytest.mark.parametrize(
    ("spans", "message"),
    [
        ([_span("doc-001", 1, 3, "CONDITION"), _span("doc-001", 1, 3, "CONDITION")], "Duplicate entity span"),
        ([_span("doc-001", -1, 3, "CONDITION")], "0 <= start < end"),
        ([_span("doc-001", 3, 3, "CONDITION")], "0 <= start < end"),
        ([_span("doc-001", 3, 51, "CONDITION")], "exceeds the declared document"),
        ([_span("missing-doc", 1, 3, "CONDITION")], "must reference a document"),
        ([_span("doc-001", 1, 3, "not_normalized")], "normalized uppercase token"),
        ([_span("doc-001", 1, 3, "CONDITION", negation="BANANA")], "must be one of"),
    ],
)
def test_strict_schema_rejects_duplicates_and_invalid_spans(spans, message):
    with pytest.raises(EvaluationInputError, match=message):
        evaluate_clinical_nlp(_artifact("gold", spans), _artifact("prediction", []))


def test_strict_schema_rejects_unknown_fields_and_manifest_mismatch():
    span = _span("doc-001", 1, 3, "CONDITION")
    span["surface_text"] = "must not be uploaded"
    with pytest.raises(EvaluationInputError, match="unexpected field"):
        evaluate_clinical_nlp(_artifact("gold", [span]), _artifact("prediction", []))

    changed = [*DOCUMENTS]
    changed[0] = {**changed[0], "character_count": 49}
    with pytest.raises(EvaluationInputError, match="document manifests"):
        evaluate_clinical_nlp(_artifact("gold", []), _artifact("prediction", [], changed))

    missing_hash = [{"document_id": "doc-001", "character_count": 50}]
    with pytest.raises(EvaluationInputError, match="document_sha256"):
        evaluate_clinical_nlp(
            _artifact("gold", [], missing_hash), _artifact("prediction", [], missing_hash)
        )

    concept_without_system = _span("doc-001", 1, 3, "CONDITION")
    concept_without_system["concept_id"] = "123"
    with pytest.raises(EvaluationInputError, match="must be supplied together"):
        evaluate_clinical_nlp(
            _artifact("gold", [concept_without_system]), _artifact("prediction", [])
        )


@pytest.mark.parametrize(
    ("gold", "predictions", "expected"),
    [
        ([], [], {"precision": None, "recall": None, "f1": None}),
        ([_span("doc-001", 1, 3, "CONDITION")], [], {"precision": None, "recall": 0.0, "f1": 0.0}),
        ([], [_span("doc-001", 1, 3, "CONDITION")], {"precision": 0.0, "recall": None, "f1": 0.0}),
    ],
)
def test_empty_span_cases_have_explicit_undefined_metrics(gold, predictions, expected):
    result = evaluate_clinical_nlp(_artifact("gold", gold), _artifact("prediction", predictions))
    assert {key: result["exact_span"][key] for key in expected} == expected
    assert {key: result["overlap"][key] for key in expected} == expected


def test_overlap_matching_maximizes_cardinality_and_is_order_invariant():
    gold = [_span("doc-001", 0, 10, "CONDITION"), _span("doc-001", 0, 2, "CONDITION")]
    predictions = [_span("doc-001", 0, 10, "CONDITION"), _span("doc-001", 8, 9, "CONDITION")]
    forward = evaluate_clinical_nlp(_artifact("gold", gold), _artifact("prediction", predictions))
    reversed_rows = evaluate_clinical_nlp(
        _artifact("gold", list(reversed(gold))),
        _artifact("prediction", list(reversed(predictions))),
    )
    assert forward["overlap"]["tp"] == 2
    assert forward["overlap"]["f1"] == 1.0
    assert forward["overlap"] == reversed_rows["overlap"]
    assert forward["context_confusion"] == reversed_rows["context_confusion"]


def test_endpoint_requires_auth_and_research_attestations(client, test_users):
    gold = _artifact("gold", [])
    predictions = _artifact("prediction", [])
    assert client.post(
        "/api/v1/evaluation/clinical_nlp",
        files=_files(gold, predictions),
        data=_attestations(),
    ).status_code == 401

    headers = get_auth_headers(test_users["clinician_a"])
    response = client.post(
        "/api/v1/evaluation/clinical_nlp",
        files=_files(gold, predictions),
        data={"deidentified": "false", "independently_annotated": "true"},
        headers=headers,
    )
    assert response.status_code == 400
    response = client.post(
        "/api/v1/evaluation/clinical_nlp",
        files=_files(gold, predictions),
        data={"deidentified": "true", "independently_annotated": "false"},
        headers=headers,
    )
    assert response.status_code == 400


def test_endpoint_persists_aggregate_run_and_applies_reportability_gate(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    gold = _artifact("gold", [_span("doc-001", 1, 4, "CONDITION")])
    predictions = _artifact("prediction", [_span("doc-001", 1, 4, "CONDITION")])

    exploratory = client.post(
        "/api/v1/evaluation/clinical_nlp",
        files=_files(gold, predictions),
        data=_attestations(dataset_label="lawful fixture only"),
        headers=headers,
    )
    assert exploratory.status_code == 200, exploratory.text
    exploratory_run = exploratory.json()
    assert exploratory_run["evaluation_context"]["reporting_status"] == "EXPLORATORY"
    assert {
        "model_id",
        "dataset_version",
        "split",
        "checkpoint",
        "dataset_not_registered",
    }.issubset(exploratory_run["evaluation_context"]["reporting_blockers"])
    assert exploratory_run["input_artifacts"]["gold"].keys() == {"role", "sha256"}
    expected_input_digest = hashlib.sha256(
        hashlib.sha256(gold).digest() + hashlib.sha256(predictions).digest()
    ).hexdigest()
    assert exploratory_run["input_sha256"] == expected_input_digest
    assert exploratory_run["evaluation_context"]["evaluation_input_sha256"] == (
        expected_input_digest
    )
    assert exploratory_run["evaluation_context"]["evaluation_input_digest_scheme"] == (
        "SHA256_ORDERED_PART_DIGESTS_V1"
    )
    assert "doc-001" not in exploratory.text

    context = {
        "dataset_label": "lawfully supplied annotated corpus",
        "dataset_version": "frozen-v1",
        "split": "test",
        "checkpoint": "sha256:" + "0" * 64,
        "model_id": "rules-v2",
    }
    unregistered_context = client.post(
        "/api/v1/evaluation/clinical_nlp",
        files=_files(gold, predictions),
        data=_attestations(**context),
        headers=headers,
    )
    assert unregistered_context.status_code == 200, unregistered_context.text
    unregistered_run = unregistered_context.json()
    assert unregistered_run["evaluation_context"]["reporting_status"] == "EXPLORATORY"
    assert {
        "model_not_registered",
        "checkpoint_sha256_zero",
        "dataset_not_registered",
    }.issubset(unregistered_run["evaluation_context"]["reporting_blockers"])
    persisted = client.get(
        f"/api/v1/evaluation/runs/{unregistered_run['run_id']}", headers=headers
    ).json()
    assert persisted["task_type"] == "clinical_nlp"
    assert persisted["input_filename"] == "gold.json|predictions.json"
    assert persisted["config"]["deidentified_attested"] is True
    assert persisted["config"]["independently_annotated_attested"] is True

    validation = client.post(
        "/api/v1/evaluation/clinical_nlp",
        files=_files(gold, predictions),
        data=_attestations(**{**context, "split": "validation"}),
        headers=headers,
    ).json()
    assert validation["evaluation_context"]["reporting_status"] == "EXPLORATORY"
    assert "held_out_test_split" in validation["evaluation_context"]["reporting_blockers"]

    mutable_checkpoint = client.post(
        "/api/v1/evaluation/clinical_nlp",
        files=_files(gold, predictions),
        data=_attestations(**{**context, "checkpoint": "rules-v2-latest"}),
        headers=headers,
    ).json()
    assert mutable_checkpoint["evaluation_context"]["reporting_status"] == "EXPLORATORY"
    assert "checkpoint_sha256_format" in mutable_checkpoint["evaluation_context"]["reporting_blockers"]

    empty = client.post(
        "/api/v1/evaluation/clinical_nlp",
        files=_files(_artifact("gold", []), _artifact("prediction", [])),
        data=_attestations(**context),
        headers=headers,
    ).json()
    assert empty["evaluation_context"]["reporting_status"] == "EXPLORATORY"
    assert "nonempty_gold_standard" in empty["evaluation_context"]["reporting_blockers"]

    other_headers = get_auth_headers(test_users["clinician_b"])
    other_runs = client.get("/api/v1/evaluation/runs", headers=other_headers)
    assert other_runs.status_code == 200
    assert all(run["run_id"] != unregistered_run["run_id"] for run in other_runs.json())
    assert client.get(
        f"/api/v1/evaluation/runs/{unregistered_run['run_id']}", headers=other_headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/evaluation/runs/{unregistered_run['run_id']}",
        headers=get_auth_headers(test_users["admin"]),
    ).status_code == 200
