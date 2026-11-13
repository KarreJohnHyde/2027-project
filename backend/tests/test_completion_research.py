"""Actual-prediction metrics and read-only source/chronological research controls."""
import csv
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.database import get_db
from app.models.entities import Case, Examination, ForecastRecord, HumanReview, MedicalMeasurement, ModalityType, InferenceRun, Finding, EvidenceStatus
from app.routers.completion_research import router
from app.services import universal_arena as arena
from tests.conftest import get_auth_headers
from tests.test_universal_intelligence import evidence_case


@pytest.fixture
def research_client(db_session):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client:
        yield client


@pytest.fixture
def prediction_models(tmp_path, monkeypatch):
    models = []
    def make(mid, n=40, reverse=False, fusion=False, patient_keys=True):
        path = tmp_path / f"{mid}.csv"
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["record_id", "patient_id", "y_A", *(["ecg_only_p_A", "fusion_p_A"] if fusion else ["p_A"])])
            for i in range(n):
                p = .9 if i % 2 else .1
                writer.writerow([f"record{i}", f"patient{i}" if patient_keys else "", i % 2, *([1-p, p] if fusion else [1-p if reverse else p])])
        report = tmp_path / f"{mid}.json"
        report.write_text(json.dumps({"model_id": mid, "dataset_version": "frozen", "checkpoint_sha256": "abc", "held_out_predictions": str(path), "test_n": n, "test_patients": n}))
        model = {"model_id": mid, "task": "multilabel_ecg_classification", "research_inference": True,
            "supported_classes": ["A"], "artifact_bundle": {"held_out_predictions_path": str(path), "evaluation_report_path": str(report),
                "checkpoint_sha256": "abc", "dataset_version": "frozen", "label_definition": {"classes": ["A"]},
                "decision_thresholds": {"values": {"A": .5}}}}
        models.append(model)
        return model
    monkeypatch.setattr(arena.model_inference, "_load_registry", lambda: {"models": models})
    monkeypatch.setattr(arena.model_inference, "research_gate", lambda m: {"allowed": False})
    monkeypatch.setattr(arena.model_inference, "evaluation_summary", lambda m: {})
    monkeypatch.setattr(arena, "_evaluation_rights", lambda m: {"allowed": True, "reason": "EXPLICIT_SYNTHETIC_TEST_FIXTURE"})
    arena._prediction_matrix.cache_clear(); arena._paired_cached.cache_clear(); arena._csv_units.cache_clear()
    return make


def test_diagnostics_are_from_actual_predictions_and_include_probability_one(prediction_models):
    model = prediction_models("test")
    result = arena.diagnostics("test")
    assert result["status"] == "COMPUTED_FROM_SAVED_PREDICTIONS"
    entry = result["per_class"][0]
    assert entry["curves"]["auroc"] == 1.
    assert entry["curves"]["average_precision"] == 1.
    assert entry["binary_confusion"]["tp"] == 20 and entry["binary_confusion"]["tn"] == 20
    assert sum(bin["count"] for bin in entry["reliability"]["bins"]) == 40
    reliability = arena._reliability(np.array([0, 1]), np.array([0., 1.]))
    assert reliability["bins"][-1]["count"] == 1
    assert reliability["ece"] == reliability["brier"] == 0.


def test_fusion_diagnostics_select_fused_columns_not_ecg_only(prediction_models):
    prediction_models("ptbxl_ecg_demographic_fusion", fusion=True)
    fused = arena.diagnostics("ptbxl_ecg_demographic_fusion")
    alone = arena.diagnostics("ptbxl_ecg_demographic_fusion", arm="ecg_only")
    assert fused["probability_prefix"] == "fusion_p_"
    assert fused["per_class"][0]["curves"]["auroc"] == 1.
    assert alone["per_class"][0]["curves"]["auroc"] == 0.


def test_paired_patient_bootstrap_recomputes_difference_and_no_difference(prediction_models):
    prediction_models("left", reverse=True)
    prediction_models("right")
    result = arena.compare_models("left", "right")
    paired = result["paired_statistics"]
    assert paired["status"] == "COMPUTED_PAIRED_PATIENT_BOOTSTRAP"
    assert paired["right_minus_left"] == 1.
    assert paired["ci95"] == [1., 1.]
    assert paired["patient_count"] == 40
    assert paired["seed"] == 20261113
    prediction_models("same")
    equal = arena.compare_models("right", "same")["paired_statistics"]
    assert equal["ci95"] == [0., 0.]
    assert equal["conclusion"] == "NO_DIFFERENCE_SHOWN"


def test_bootstrap_missing_patient_keys_and_single_class_fail_closed(prediction_models):
    left = prediction_models("left", patient_keys=False)
    right = prediction_models("right", patient_keys=False)
    assert arena.paired_comparison(left, right)["reason"] == "EXPLICIT_PATIENT_KEYS_REQUIRED"
    curve = arena._curve(np.array([1, 1]), np.array([.2, .8]))
    assert curve["status"] == "UNAVAILABLE"
    assert curve["roc"] == curve["pr"] == []


def test_invalid_probabilities_refused_and_curve_limits_explicit(prediction_models):
    model = prediction_models("bad")
    path = Path(model["artifact_bundle"]["held_out_predictions_path"])
    path.write_text(path.read_text().replace("0.1", "NaN", 1))
    assert arena.diagnostics("bad")["status"] == "UNAVAILABLE"
    y = np.array([i % 2 for i in range(1000)])
    curve = arena._curve(y, np.linspace(0, 1, 1000))
    assert len(curve["roc"]) <= 201 and len(curve["pr"]) <= 201
    assert curve["display_downsampled"] is True


def test_rights_block_precedes_any_prediction_read(prediction_models, monkeypatch):
    prediction_models("blocked")
    monkeypatch.setattr(arena, "_evaluation_rights", lambda m: {"allowed": False, "reason": "COMMERCIAL_REVIEW_REQUIRED"})
    monkeypatch.setattr(arena, "_prediction_matrix", lambda *args: pytest.fail("A blocked source must never be loaded"))
    assert arena.diagnostics("blocked")["status"] == "RIGHTS_BLOCKED"
    prediction_models("also-blocked")
    result = arena.compare_models("blocked", "also-blocked")
    assert result["status"] == "COMPARISON_UNAVAILABLE"
    assert "FRESH_COMPUTATION_RIGHTS_GATE_NOT_PASSED" in result["reasons"]


def test_noncommercial_source_is_rejected_for_declared_commercial_purpose(tmp_path, monkeypatch):
    directory = tmp_path / "dataset_registry"
    directory.mkdir()
    (directory / "release_context.json").write_text(json.dumps({"training_purpose": "commercial_development"}))
    monkeypatch.setattr(arena, "PROJECT_ROOT", tmp_path)
    result = arena._evaluation_rights({"model_id": "gi_kvasir_seg_polyp_segmenter", "artifact_bundle": {"dataset_license": "research and educational purposes only"}})
    assert result["allowed"] is False
    assert result["reason"] == "SOURCE_TERMS_EXCLUDE_COMMERCIAL_USE"


def test_matched_sources_require_same_exam_identity_and_no_missing_modality_imputation(research_client, db_session, test_users, evidence_case):
    case, exam, source, primary = evidence_case
    image = source()
    image[0].modality = image[1].modality = image[2].modality = ModalityType.IMAGE
    old_exam = Examination(case_id=case.id, modality=ModalityType.ECG, exam_date=datetime(2026, 1, 1))
    db_session.add(old_exam); db_session.flush()
    ecg = source(examination=old_exam)
    ecg[0].modality = ecg[1].modality = ecg[2].modality = ModalityType.ECG
    db_session.commit()
    url = f"/api/v1/cases/{case.id}/research/paired-evidence"
    headers = get_auth_headers(test_users["clinician_a"])
    unconfirmed = research_client.get(url, headers=headers).json()
    group = next(g for g in unconfirmed["groups"] if g["examination_id"] == exam.id)
    assert group["status"] == "IDENTITY_CONFIRMATION_REQUIRED"
    confirmed = research_client.get(url, params={"exam_id": exam.id, "confirmed_same_patient": True}, headers=headers).json()
    assert len(confirmed["groups"]) == 1
    group = confirmed["groups"][0]
    assert group["present_modalities"] == ["IMAGE", "REPORT"]
    assert group["missing_modalities"] == ["ECG"]
    assert ecg[0].id not in group["source_ids"]
    assert confirmed["learned_fusion_eligible"] is False


def test_backtest_reuses_reviewed_chronological_engine_without_write(research_client, db_session, test_users, evidence_case):
    case, exam, source, (upload, run, finding, statement) = evidence_case
    for index, value in enumerate([40., 42., 44., 46., 48., 50.]):
        db_session.add(MedicalMeasurement(case_id=case.id, source_file_id=upload.id, finding_id=finding.id,
            name="hdl_cholesterol", display_name="HDL cholesterol", value=value, unit="mg/dL", raw_value=str(value), raw_unit="mg/dL",
            source_span=f"HDL {value} mg/dL", source_span_start=0, source_span_end=15,
            documented_date=f"2026-{index + 1:02d}-01", specimen="Serum", laboratory_method="Enzymatic"))
    db_session.add(HumanReview(finding_id=finding.id, reviewer_id=test_users["clinician_a"].id,
        review_status="CONFIRMED", original_output_preserved=True))
    db_session.commit()
    before = db_session.query(ForecastRecord).count()
    response = research_client.get(f"/api/v1/cases/{case.id}/research/backtest",
        params={"metric": "hdl_cholesterol", "unit": "mg/dL", "horizon_days": 7}, headers=get_auth_headers(test_users["clinician_a"]))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "CHRONOLOGICAL_BASELINES_EVALUATED"
    assert result["matched_comparison"]["n"] == 3
    assert result["matched_comparison"]["linear_mae"] < result["matched_comparison"]["persistence_mae"]
    assert result["models"]["persistence"]["id"] is None
    assert result["never_writes"] is True
    assert db_session.query(ForecastRecord).count() == before
    assert not db_session.new and not db_session.dirty
    for method in ("persistence", "linear"):
        folds = result["models"][method]["baseline_analysis"]["backtest"]["folds"]
        assert all(fold["train_count"] < result["models"][method]["observations_count"] for fold in folds)


@pytest.mark.private_workspace
def test_research_case_auth_cross_exam_and_bad_horizon(research_client, db_session, test_users, evidence_case):
    case, exam, source, primary = evidence_case
    url = f"/api/v1/cases/{case.id}/research/paired-evidence"
    assert research_client.get(url).status_code == 401
    assert research_client.get(url, headers=get_auth_headers(test_users["clinician_b"])).status_code == 403
    other = Case(pseudonymous_id="other-research-case", created_by_id=test_users["admin"].id)
    db_session.add(other); db_session.flush()
    other_exam = Examination(case_id=other.id, exam_date=datetime(2026, 1, 1), modality=ModalityType.REPORT)
    db_session.add(other_exam); db_session.commit()
    assert research_client.get(url, params={"exam_id": other_exam.id}, headers=get_auth_headers(test_users["admin"])).status_code == 404
    bad = research_client.get(f"/api/v1/cases/{case.id}/research/backtest", params={"metric": "hdl", "unit": "mg/dL", "horizon_days": 0}, headers=get_auth_headers(test_users["admin"]))
    assert bad.status_code == 422


def test_sparse_unreviewed_series_remain_ineligible(research_client, test_users, evidence_case):
    case, *_ = evidence_case
    result = research_client.get(f"/api/v1/cases/{case.id}/research/backtest", params={"metric": "hdl", "unit": "mg/dL"}, headers=get_auth_headers(test_users["clinician_a"])).json()
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["matched_comparison"] is None
    assert all(output["predicted_value"] is None for output in result["models"].values())


def test_superseded_report_measurements_remain_history_and_cannot_forecast(research_client, db_session, test_users, evidence_case):
    case, exam, source, (upload, run, finding, statement) = evidence_case
    for index in range(5):
        db_session.add(MedicalMeasurement(case_id=case.id, source_file_id=upload.id, finding_id=finding.id,
            name="hdl_cholesterol", display_name="HDL cholesterol", value=40. + index, unit="mg/dL", raw_value=str(40 + index), raw_unit="mg/dL",
            source_span="Documented HDL result", source_span_start=0, source_span_end=21,
            documented_date=f"2026-{index + 1:02d}-01", specimen="Serum", laboratory_method="Enzymatic"))
    db_session.add(HumanReview(finding_id=finding.id, reviewer_id=test_users["clinician_a"].id, review_status="CONFIRMED", original_output_preserved=True))
    db_session.commit()
    params = {"metric": "hdl_cholesterol", "unit": "mg/dL", "horizon_days": 7}
    url = f"/api/v1/cases/{case.id}/research/backtest"
    headers = get_auth_headers(test_users["clinician_a"])
    assert research_client.get(url, params=params, headers=headers).json()["status"] == "CHRONOLOGICAL_BASELINES_EVALUATED"
    latest = InferenceRun(case_id=case.id, file_id=upload.id, modality=ModalityType.REPORT, model_name="new-analysis",
        model_version="new", preprocessing_version="new", status=EvidenceStatus.COMPLETED)
    db_session.add(latest); db_session.flush()
    db_session.add(Finding(case_id=case.id, inference_run_id=latest.id, modality=ModalityType.REPORT,
        category="REPORT", label="Current analysis has no HDL observations", mapping_status="NOT_MAPPED"))
    db_session.commit()
    result = research_client.get(url, params=params, headers=headers).json()
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert all(output["observations_count"] == 0 and output["predicted_value"] is None for output in result["models"].values())
    assert db_session.query(MedicalMeasurement).filter(MedicalMeasurement.case_id == case.id).count() == 5
    assert db_session.query(ForecastRecord).filter(ForecastRecord.case_id == case.id).count() == 0
