import json
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.routers import research_readiness as routes
from app.services import research_readiness as readiness
from tests.conftest import get_auth_headers


@pytest.fixture(autouse=True)
def safe_live_counts(monkeypatch):
    # Stable committed fixture; production uses the new finalization evidence file.
    monkeypatch.setattr(readiness, "EVIDENCE_PATH", Path(readiness.PROJECT_ROOT)/"docs/universal/evidence/expansion-2026-11-13.json")
    monkeypatch.setattr(readiness, "_live_counts", lambda: ({"registry_models": 19, "research_allowed": 2, "research_blocked": 17, "upload_runnable": 2, "clinical_activated": 0}, "b"*64))
    # Deliberately distinct from the committed 2163 to prove live and historical denominators stay separate.
    monkeypatch.setattr(readiness, "_matched_cohort", lambda: {"status": "SOURCE_BOUND_CURRENT_COHORT", "records": 1900, "patients": 1700, "snapshot_sha256": "c"*64})
    monkeypatch.delenv("MEDTWIN_INDEPENDENT_REPORT_EVALUATION", raising=False)


def _independent(tmp_path, *, synthetic=False):
    data = {"schema_version": "medtwin.independent-report-evaluation.v1", "status": "SYNTHETIC_SOFTWARE_CONTROL" if synthetic else "EVALUATED_INDEPENDENT_REPORTS", "evidence_type": "SYNTHETIC" if synthetic else "REAL_PERMITTED", "clinical_activation": False,
        "counts": {"documents": 1, "pages": 2, "readable_pages": 1, "unreadable_pages": 1, "independent_real_documents": 0 if synthetic else 1, "independent_real_pages": 0 if synthetic else 2, "independent_real_readable_pages": 0 if synthetic else 1},
        "references": {key: True for key in ["all_readable_pages_independently_checked", "full_page_text_available", "permissions_verified", "full_report_page_coverage_verified", "unexposed_reference_attested"]},
        "metrics": {"ocr": {"character_error_rate": .1, "word_error_rate": .2, "exact_page_rate": 0.}, "lab": {"precision": .9, "recall": .8, "f1": .847}, "raw_report": "SECRET_PATIENT_NAME"},
        "provenance": {**{key: "d"*64 for key in ["inventory_sha256", "annotations_sha256", "permissions_sha256", "source_manifest_sha256", "predictions_sha256", "pipeline_sha256"]}, "verified_source_bindings": True, "raw_text_persisted": False, "raw_identifiers_persisted": False, "source_pdf_sha256s": ["e"*64], "source_page_sha256s": ["f"*64], "raw_source_path": "C:/private/SECRET_PATIENT_NAME/report.pdf"},
        "raw_text": "SECRET_PATIENT_NAME", "publication_scope": "PRIVATE_OPERATOR_EVALUATION"}
    path = tmp_path/"private-aggregate.json"; path.write_text(json.dumps(data), encoding="utf-8")
    return path, data


def test_committed_counts_and_current_bindings_are_exact_and_separate():
    payload = json.loads(readiness.EVIDENCE_PATH.read_text(encoding="utf-8-sig"))
    result = readiness.readiness_summary()
    metrics = {metric["metric_id"]: metric["value"] for metric in result["metrics"]}
    assert metrics["backend_passed"] == payload["backend"]["passed"]
    assert metrics["matched_records"] == payload["matched_records"]["records"]
    assert result["live_matched_cohort"]["records"] == 1900
    assert result["live_model_counts"]["registry_models"] == 19
    assert result["independent_reports"]["status"] == "PENDING_REFERENCE_IMPORT"
    assert result["independent_reports"]["metrics"] == [] and result["independent_reports"]["documents"] is None
    assert not result["clinical_activation"] and not result["new_inference"]


def test_nonadmin_never_reads_private_artifact_or_discloses_its_counts_hashes_or_text(monkeypatch, tmp_path):
    path, _ = _independent(tmp_path)
    monkeypatch.setenv("MEDTWIN_INDEPENDENT_REPORT_EVALUATION", str(path))
    monkeypatch.setattr(readiness, "_json", lambda *_: (_ for _ in ()).throw(AssertionError("Private artifact must not be opened for nonadmin")))
    result = readiness.independent_reports(False)
    assert result["status"] == "PRIVATE_OPERATOR_EVALUATION" and result["visibility"] == "ADMIN_ONLY"
    assert not result["sources"] and not result["metrics"] and result["documents"] is None
    assert "SECRET_PATIENT_NAME" not in json.dumps(result) and str(path) not in json.dumps(result)


def test_admin_allowlist_contains_only_aggregate_metrics_and_global_bindings(monkeypatch, tmp_path):
    path, _ = _independent(tmp_path); monkeypatch.setenv("MEDTWIN_INDEPENDENT_REPORT_EVALUATION", str(path))
    result = readiness.independent_reports(True)
    assert result["status"] == "RECORDED_INDEPENDENT_EVALUATION"
    assert result["readable_pages"] == 1 and result["independent_real_pages"] == 2
    assert result["full_report_validation"] == "RECORDED_FULL_REFERENCE_COVERAGE_RESEARCH_ONLY"
    text = json.dumps(result)
    for private in ["SECRET_PATIENT_NAME", str(path), "source_pdf_sha256s", "source_page_sha256s", "e"*64, "f"*64]: assert private not in text
    assert any(metric["value"] == .1 for metric in result["metrics"])


@pytest.mark.parametrize("mutation", ["missing_bindings", "missing_references", "invalid_denominator", "nonfinite_metric", "invalid_schema", "mixed_reference", "privacy_state"])
def test_malformed_or_incomplete_independent_evidence_never_becomes_accuracy(monkeypatch, tmp_path, mutation):
    path, data = _independent(tmp_path)
    if mutation == "missing_bindings": data["provenance"]["verified_source_bindings"] = False
    elif mutation == "missing_references": data["references"]["permissions_verified"] = False
    elif mutation == "invalid_denominator": data["counts"]["independent_real_readable_pages"] = 0
    elif mutation == "nonfinite_metric": data["metrics"]["ocr"]["character_error_rate"] = float("nan")
    elif mutation == "mixed_reference": data["counts"]["documents"] = 2
    elif mutation == "privacy_state": data["provenance"]["raw_text_persisted"] = True
    else: data["schema_version"] = "arbitrary-client-json"
    path.write_text(json.dumps(data), encoding="utf-8"); monkeypatch.setenv("MEDTWIN_INDEPENDENT_REPORT_EVALUATION", str(path))
    result = readiness.independent_reports(True)
    assert result["status"] == "EVALUATION_UNVERIFIED" and result["metrics"] == []


def test_synthetic_result_is_explicitly_not_independent_real_accuracy(monkeypatch, tmp_path):
    path, _ = _independent(tmp_path, synthetic=True); monkeypatch.setenv("MEDTWIN_INDEPENDENT_REPORT_EVALUATION", str(path))
    result = readiness.independent_reports(True)
    assert result["status"] == "SYNTHETIC_SOFTWARE_CONTROL" and result["independent_real_documents"] == 0
    assert result["full_report_validation"] == "SYNTHETIC_ONLY"


def test_undefined_metrics_are_omitted_instead_of_zero_or_rejecting_other_measures(monkeypatch, tmp_path):
    path, data = _independent(tmp_path)
    data["metrics"]["lab"] = {"precision": None, "recall": None, "f1": None}
    path.write_text(json.dumps(data), encoding="utf-8"); monkeypatch.setenv("MEDTWIN_INDEPENDENT_REPORT_EVALUATION", str(path))
    result = readiness.independent_reports(True)
    assert result["status"] == "RECORDED_INDEPENDENT_EVALUATION"
    assert len(result["metrics"]) == 3 and all(row["metric_id"].startswith("ocr.") for row in result["metrics"])


def test_missing_configured_artifact_is_unverified_for_admin_but_private_for_others(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDTWIN_INDEPENDENT_REPORT_EVALUATION", str(tmp_path/"not-imported-yet.json"))
    assert readiness.independent_reports(True)["status"] == "EVALUATION_UNVERIFIED"
    assert readiness.independent_reports(False)["status"] == "PRIVATE_OPERATOR_EVALUATION"


def test_authentication_and_private_operator_visibility(db_session, test_users, monkeypatch, tmp_path):
    app = FastAPI(); app.include_router(routes.router, prefix="/api/v1"); app.dependency_overrides[get_db] = lambda: db_session
    path, _ = _independent(tmp_path); monkeypatch.setenv("MEDTWIN_INDEPENDENT_REPORT_EVALUATION", str(path))
    with TestClient(app) as client:
        assert client.get("/api/v1/universal/research/readiness").status_code == 401
        clinician = client.get("/api/v1/universal/research/readiness", headers=get_auth_headers(test_users["clinician_a"]))
        admin = client.get("/api/v1/universal/research/readiness", headers=get_auth_headers(test_users["admin"]))
    assert clinician.status_code == 200 and admin.status_code == 200
    assert clinician.json()["independent_reports"]["status"] == "PRIVATE_OPERATOR_EVALUATION"
    assert admin.json()["independent_reports"]["status"] == "RECORDED_INDEPENDENT_EVALUATION"
    assert "SECRET_PATIENT_NAME" not in clinician.text+admin.text
