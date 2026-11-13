"""Controlled tuples, source hashes, privacy and no-read rights refusals."""
import csv
import hashlib
import json
import os
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.database import get_db
from app.routers.matched_model_explorer import router
from app.schemas.matched_model_explorer import MatchedRecordsQuery
from app.services import matched_model_explorer as explorer
from app.services import universal_arena as arena
from tests.conftest import get_auth_headers


@pytest.fixture
def controlled(tmp_path, monkeypatch):
    records, sums, missingness, models = {}, {}, {}, []
    for index in range(1, 5):
        identity = str(index)
        record = {"file": f"record{index}", "patient_id": f"PRIVATE-PATIENT-{index}", "labels": ["STTC"] + (["NORM"] if index % 2 else [])}
        records[identity] = record
        missingness[identity] = {"age_missing": index == 1, "sex_missing": index == 2}
        for suffix in (".hea", ".dat"):
            p = tmp_path / (record["file"] + suffix); p.write_bytes(f"controlled-source-{index}{suffix}".encode())
            sums[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    for mid, fusion in ((explorer.BASELINE, False), (explorer.FUSION, True)):
        prediction = tmp_path / f"{mid}.csv"
        prefixes = ["ecg_only_p_", "fusion_p_"] if fusion else ["p_"]
        with prediction.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["record_id", "patient_id", *["y_" + label for label in explorer.LABELS], *[prefix + label for prefix in prefixes for label in explorer.LABELS]])
            for identity, record in records.items():
                truth = [int(label in record["labels"]) for label in explorer.LABELS]
                if fusion:
                    scores = [(.6 if truth[0] else .4), .1, .8, .1, .1, (.9 if truth[0] else .1), .1, .8, .1, .1]
                else:
                    scores = [(.2 if truth[0] else .8), .1, .8, .1, .1]
                writer.writerow([identity, record["patient_id"], *truth, *scores])
        checkpoint = tmp_path / f"{mid}.pt"; checkpoint.write_bytes(mid.encode())
        checksum = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        report = tmp_path / f"{mid}.json"
        report.write_text(json.dumps({"model_id": mid, "dataset_version": "controlled-version", "checkpoint_sha256": checksum,
            "held_out_predictions": str(prediction), "test_n": 4,
            "arms": {"ecg_only": {"per_class": [{"class": label, "threshold_from_validation": .6} for label in explorer.LABELS]}}}))
        models.append({"model_id": mid, "task": "multilabel_ecg_classification", "research_inference": True,
            "supported_classes": explorer.LABELS.copy(), "artifact_bundle": {"dataset_version": "controlled-version",
                "label_definition": {"classes": explorer.LABELS.copy()}, "held_out_predictions_path": str(prediction),
                "checkpoint_path": str(checkpoint), "checkpoint_sha256": checksum, "evaluation_report_path": str(report),
                "decision_thresholds": {"values": {label: .5 for label in explorer.LABELS}}}})
    publisher = {"root": tmp_path, "records": records, "sums": sums, "missingness": missingness,
        "dataset_version": "controlled-version", "metadata_sha256": "1" * 64, "label_table_sha256": "2" * 64, "checksum_manifest_sha256": "3" * 64}
    monkeypatch.setattr(arena.model_inference, "_load_registry", lambda: {"models": models})
    monkeypatch.setattr(arena, "_evaluation_rights", lambda model: {"allowed": True, "reason": "EXPLICIT_CONTROLLED_SYNTHETIC_FIXTURE"})
    monkeypatch.setattr(explorer, "_publisher_data", lambda: publisher)
    arena._prediction_matrix.cache_clear()
    return models, publisher


@pytest.fixture
def explorer_client(db_session):
    app = FastAPI(); app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        yield client


def test_actual_controlled_reference_errors_and_private_keys_withheld(controlled):
    result = explorer.query_records(MatchedRecordsQuery(limit=2))
    assert result["status"] == "MATCHED_RECORDS_AVAILABLE"
    assert result["total"] == result["total_filtered"] == 4
    assert len(result["rows"]) == 2
    assert all(row["decision_disagreement"] for row in result["rows"])
    for row in result["rows"]:
        assert row["record_pseudonym"].startswith("ptb-")
        assert row["left"]["error_type"].startswith("FALSE_")
        assert row["right"]["error_type"].startswith("TRUE_")
        assert row["input_provenance"]["status"] == "MATCHED_PUBLISHER_RECORD_AND_CURRENT_SOURCE_BYTES"
    serialized = json.dumps(result)
    assert "PRIVATE-PATIENT" not in serialized
    assert '"patient_id"' not in serialized and '"record_id"' not in serialized
    assert str(controlled[1]["root"]) not in serialized
    assert result["never_writes"] is True


def test_stable_pagination_pseudonym_search_and_snapshot_binding(controlled):
    first = explorer.query_records(MatchedRecordsQuery(limit=2))
    second = explorer.query_records(MatchedRecordsQuery(offset=2, limit=2, expected_snapshot_id=first["snapshot_id"]))
    assert second["snapshot_id"] == first["snapshot_id"]
    assert not {row["record_pseudonym"] for row in first["rows"]} & {row["record_pseudonym"] for row in second["rows"]}
    pseudonym = first["rows"][0]["record_pseudonym"]
    search = explorer.query_records(MatchedRecordsQuery(search=pseudonym, order="errors", errors_only=True))
    assert search["total_filtered"] == 1 and search["rows"][0]["record_pseudonym"] == pseudonym
    stale = explorer.query_records(MatchedRecordsQuery(expected_snapshot_id="0" * 64))
    assert stale["status"] == "SNAPSHOT_CHANGED" and stale["rows"] == []


def test_same_run_arm_threshold_equality_and_unarchived_control_checkpoint(controlled):
    result = explorer.query_records(MatchedRecordsQuery(mode="same_run"))
    assert result["status"] == "MATCHED_RECORDS_AVAILABLE"
    assert result["models"]["left"]["probability_prefix"] == "ecg_only_p_"
    assert result["models"]["right"]["probability_prefix"] == "fusion_p_"
    assert result["models"]["left"]["checkpoint_sha256"] is None
    assert result["models"]["left"]["checkpoint_binding_status"] == "CONTROL_ARM_CHECKPOINT_NOT_ARCHIVED"
    equality = next(row for row in result["rows"] if row["reference_label"] == 1)
    assert equality["left"]["probability"] == .6
    assert equality["left"]["predicted_label"] == 1


def test_rights_refusal_precedes_prediction_and_publisher_reads(controlled, monkeypatch):
    monkeypatch.setattr(arena, "_evaluation_rights", lambda model: {"allowed": False})
    monkeypatch.setattr(arena, "_prediction_spec", lambda *args: pytest.fail("Prediction access before rights"))
    monkeypatch.setattr(explorer, "_publisher_data", lambda: pytest.fail("Publisher access before rights"))
    result = explorer.query_records(MatchedRecordsQuery())
    assert result["status"] == "RIGHTS_BLOCKED" and result["rows"] == []


@pytest.mark.parametrize("change,reason", [("labels", "TASK_OR_ORDERED_LABEL_DEFINITION_MISMATCH"), ("version", "DATASET_OR_TARGET_DEFINITION_MISMATCH")])
def test_model_label_or_dataset_mismatch_fails_before_reads(controlled, monkeypatch, change, reason):
    models, publisher = controlled
    if change == "labels": models[1]["supported_classes"] = ["OTHER"]
    else: models[1]["artifact_bundle"]["dataset_version"] = "different"
    monkeypatch.setattr(arena, "_prediction_spec", lambda *args: pytest.fail("Mismatched prediction read"))
    result = explorer.query_records(MatchedRecordsQuery())
    assert result["status"] == "UNAVAILABLE" and result["reason"] == reason


def test_changed_reference_tuple_and_current_source_hash_refuse(controlled):
    models, publisher = controlled
    publisher["records"]["1"]["patient_id"] = "OTHER-PRIVATE-PATIENT"
    result = explorer.query_records(MatchedRecordsQuery())
    assert result["reason"] == "PUBLISHER_HELD_OUT_RECORD_OR_REFERENCE_TUPLE_MISMATCH"
    publisher["records"]["1"]["patient_id"] = "PRIVATE-PATIENT-1"
    for record in publisher["records"].values(): (publisher["root"] / (record["file"] + ".dat")).write_bytes(b"changed")
    assert explorer.query_records(MatchedRecordsQuery())["reason"] == "SELECTED_INPUT_PUBLISHER_HASH_MISMATCH"


def test_changed_checkpoint_and_cached_prediction_bytes_refuse(controlled):
    models, publisher = controlled
    model = models[0]
    prediction = Path(model["artifact_bundle"]["held_out_predictions_path"])
    spec = arena._prediction_spec(model); arena._prediction_matrix(*spec)
    stat = prediction.stat()
    content = prediction.read_bytes().replace(b"0.8", b"0.9")
    assert len(content) == stat.st_size
    prediction.write_bytes(content)
    # Preserve size and timestamp to exercise independent byte hashing beyond stat cache keys.
    os.utime(prediction, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert explorer.query_records(MatchedRecordsQuery())["reason"] == "PREDICTION_BYTES_CHANGED_DURING_READ_OR_CACHE"
    Path(model["artifact_bundle"]["checkpoint_path"]).write_bytes(b"changed")
    assert explorer.query_records(MatchedRecordsQuery())["reason"] == "CHECKPOINT_BYTES_HASH_MISMATCH"


@pytest.mark.parametrize("body", [{"mode": "unknown"}, {"label": "UNKNOWN"}, {"order": "diagnose"}, {"offset": -1}, {"limit": 51}, {"limit": "2"}, {"search": "patient id"}, {"unexpected": True}, {"expected_snapshot_id": "abc"}])
def test_strict_endpoint_params(explorer_client, test_users, body):
    response = explorer_client.post("/api/v1/universal/research/matched-records/query", json=body, headers=get_auth_headers(test_users["clinician_a"]))
    assert response.status_code == 422


def test_authenticated_endpoint_returns_controlled_rows(explorer_client, test_users, controlled):
    path = "/api/v1/universal/research/matched-records/query"
    assert explorer_client.post(path, json={}).status_code == 401
    response = explorer_client.post(path, json={"limit": 2}, headers=get_auth_headers(test_users["clinician_a"]))
    assert response.status_code == 200
    assert response.json()["status"] == "MATCHED_RECORDS_AVAILABLE"
