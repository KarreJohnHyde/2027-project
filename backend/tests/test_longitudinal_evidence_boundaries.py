"""Synthetic longitudinal acceptance checks for source and correction boundaries."""
from datetime import datetime
import json

import pytest

from app.models.entities import HumanReview, MedicalMeasurement, UploadedFile
from app.services.research_baselines import evaluate
from tests.conftest import get_auth_headers
from tests.test_heterogeneous_evidence import add_measurements, case_and_upload


def pair(client, test_users):
    owner, reviewer = test_users["clinician_a"], test_users["clinician_b"]
    headers = get_auth_headers(owner)
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-COMPARISON-BOUNDARIES"}).json()["id"]
    client.post(f"/api/v1/cases/{case_id}/members", headers=headers, json={"username": reviewer.username, "role": "EDITOR"})
    uploads, exams = [], []
    for date, value, statement in [("2024-01-01", 70, "No pleural effusion is seen."), ("2024-02-01", 80, "Pleural effusion is present.")]:
        exam = client.post(f"/api/v1/cases/{case_id}/examinations", headers=headers, json={"exam_date": date + "T00:00:00", "modality": "REPORT"}).json()
        response = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers,
            data={"deidentified": "true", "examination_id": str(exam["id"])},
            files={"file": (date + ".txt", f"SYNTHETIC SOFTWARE FIXTURE\nReport date: {date}\nHeart rate {value} bpm.\n{statement}".encode(), "text/plain")})
        assert response.status_code == 201
        upload = response.json()
        assert client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=headers).status_code == 201
        uploads.append(upload); exams.append(exam)
    body = {"prior_exam_id": exams[0]["id"], "current_exam_id": exams[1]["id"], "same_patient_confirmed": True}
    return case_id, headers, uploads, body


def test_comparison_applies_approved_values_and_assertions_without_mutating_sources(client, db_session, test_users):
    case_id, headers, uploads, body = pair(client, test_users)
    measurements = client.get(f"/api/v1/cases/{case_id}/measurements", headers=headers).json()
    current = next(m for m in measurements if m["source_file_id"] == uploads[1]["id"])
    statements = client.get(f"/api/v1/cases/{case_id}/statements", headers=headers).json()
    statement = next(s for s in statements if int(s["source_file_id"]) == uploads[1]["id"] and s["entity"] == "Pleural effusion")
    review = client.post(f"/api/v1/reviews/{current['finding_id']}", headers=headers, json={"review_status": "MODIFIED", "reviewer_comments": "Corrected against the synthetic source fixture.",
        "correction_payload": {
            "measurement_corrections": [{"target_measurement_id": current["id"], "action": "AMEND", "corrected_value": 75}],
            "entity_corrections": [{"target_statement_id": int(statement["id"]), "action": "AMEND", "corrected_assertion": "NEGATED"}]}})
    assert review.status_code == 201, review.text
    review_id = review.json()["id"]
    approval = client.post(f"/api/v1/reviews/corrections/{review_id}/decision", headers=get_auth_headers(test_users["clinician_b"]), json={"decision": "APPROVED", "rationale": "Verified synthetic fixture values."})
    assert approval.status_code == 201, approval.text
    response = client.post(f"/api/v1/cases/{case_id}/compare", headers=headers, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    delta = next(d for d in result["numeric_deltas"] if d["name"] == "heart_rate")
    assert delta["absolute_delta"] == 5
    assert delta["current"]["value"] == 75 and delta["current"]["original_value"] == 80
    assert delta["current"]["correction_review_id"] == review_id
    assert db_session.get(MedicalMeasurement, current["id"]).value == 80
    change = next(d for d in result["semantic_report_diff"] if d["entity"] == "Pleural effusion")
    assert change["current"]["assertion"] == "NEGATED"
    assert change["current"]["original_values"]["negation"] == "AFFIRMED"


@pytest.mark.parametrize("state", ["withdrawn", "superseded", "unassociated", "rejected"])
def test_inactive_or_rejected_sources_do_not_drive_comparison(client, db_session, test_users, state):
    case_id, headers, uploads, body = pair(client, test_users)
    upload = db_session.get(UploadedFile, uploads[1]["id"])
    if state == "withdrawn": upload.withdrawn_at = datetime(2026, 1, 1)
    elif state == "superseded": upload.superseded_by_file_id = uploads[0]["id"]
    elif state == "unassociated": upload.is_associated = False
    else:
        measurement = db_session.query(MedicalMeasurement).filter_by(source_file_id=upload.id).first()
        db_session.add(HumanReview(finding_id=measurement.finding_id, reviewer_id=test_users["clinician_a"].id, review_status="REJECTED"))
    db_session.commit()
    response = client.post(f"/api/v1/cases/{case_id}/compare", headers=headers, json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["numeric_deltas"] == []
    assert result["semantic_report_diff"] == []
    assert result["excluded_evidence"]
    assert result["semantic_comparison_blockers"][0]["reason"] == "EXCLUDED_EVIDENCE_PREVENTS_ABSENCE_INFERENCE"


@pytest.mark.parametrize("kind", ["duplicate_context", "lesion", "missing_lab_context", "overflow"])
def test_baselines_refuse_unpaired_contexts_lesions_and_overflow(db_session, test_users, tmp_path, kind):
    user = test_users["clinician_a"]
    case, upload, finding = case_and_upload(db_session, user, tmp_path)
    add_measurements(db_session, case, upload, finding, user, 3)
    rows = db_session.query(MedicalMeasurement).filter_by(case_id=case.id).order_by(MedicalMeasurement.id).all()
    metric, unit = "synthetic_metric", "mm"
    if kind == "duplicate_context":
        original = rows[0]
        db_session.add(MedicalMeasurement(case_id=case.id, source_file_id=upload.id, finding_id=finding.id, name=metric,
            display_name=metric, value=original.value, unit=unit, raw_value=str(original.value), raw_unit=unit,
            source_span="Synthetic duplicate", source_span_start=0, source_span_end=19, documented_date=original.documented_date,
            specimen="OTHER", laboratory_method="OTHER"))
        expected = "INCOMPATIBLE_MEASUREMENT_CONTEXTS"
    elif kind == "lesion":
        metric = "lesion_size"
        for row in rows: row.name = metric
        expected = "LESION_IDENTITY_NOT_ESTABLISHED"
    elif kind == "missing_lab_context":
        metric, unit = "creatinine", "mg/dL"
        for row in rows: row.name = metric; row.unit = unit; row.specimen = row.laboratory_method = None
        expected = "MEASUREMENT_CONTEXT_NOT_ESTABLISHED"
    else:
        for row, value in zip(rows, (1e308, -1e308, 1e308)): row.value = value
        expected = "NUMERICAL_RANGE_UNSUPPORTED"
    db_session.commit()
    result = evaluate(case.id, db_session, metric, unit, 30, "persistence")
    assert result["predicted_value"] is None
    assert result["ineligibility_reason"].startswith(expected)
    assert result["baseline_analysis"]["observed_change"] is None
    json.dumps(result, default=str, allow_nan=False)
