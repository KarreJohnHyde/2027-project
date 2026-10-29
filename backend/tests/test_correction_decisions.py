"""Four-eyes approval of proposed corrections and the effective (reviewed) evidence view.

Synthetic, de-identified fixtures only.
"""

from app.models.entities import Case, CaseMembership, ClinicalReportStatement, Finding, InferenceRun, MedicalMeasurement, ModalityType, UploadedFile
from app.services.biomarker_trends import build_series
from tests.conftest import get_auth_headers


def _case_with_measurements(db_session, owner, member):
    case = Case(pseudonymous_id="CORRECTION-TEST", created_by_id=owner.id)
    db_session.add(case)
    db_session.flush()
    db_session.add(CaseMembership(case_id=case.id, user_id=member.id, role="EDITOR", granted_by_id=owner.id))
    upload = UploadedFile(case_id=case.id, filename="lab.pdf", stored_filename="lab.pdf", file_path="/fixture/lab.pdf",
                          file_hash="c" * 64, file_size_bytes=1, mime_type="application/pdf", modality=ModalityType.REPORT)
    db_session.add(upload)
    db_session.flush()
    run = InferenceRun(case_id=case.id, file_id=upload.id, modality=ModalityType.REPORT, model_name="fixture",
                       model_version="1", preprocessing_version="1")
    db_session.add(run)
    db_session.flush()
    finding = Finding(inference_run_id=run.id, case_id=case.id, modality=ModalityType.REPORT, category="Clinical report",
                      label="fixture", mapping_status="NOT_MAPPED")
    db_session.add(finding)
    db_session.flush()

    def measurement(value, date):
        row = MedicalMeasurement(case_id=case.id, source_file_id=upload.id, finding_id=finding.id, name="hdl_cholesterol",
                                 display_name="HDL cholesterol", value=value, unit="mg/dL", raw_value=str(value), raw_unit="mg/dL",
                                 source_span=f"HDL {value} mg/dL", source_span_start=0, source_span_end=12,
                                 documented_date=date, specimen="Serum", laboratory_method="Enzymatic")
        db_session.add(row)
        db_session.flush()
        return row

    first, second = measurement(84.0, "2026-01-10"), measurement(50.0, "2026-03-10")
    db_session.commit()
    return case, finding, first, second


def _propose(client, finding, user, correction):
    response = client.post(f"/api/v1/reviews/{finding.id}", headers=get_auth_headers(user), json={
        "review_status": "MODIFIED",
        "reviewer_comments": "Value misread from the photographed table.",
        "correction_payload": {"measurement_corrections": [correction]},
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _effective(client, case, user, measurement_id):
    response = client.get(f"/api/v1/cases/{case.id}/effective-evidence", headers=get_auth_headers(user))
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["measurements"] if item["measurement_id"] == measurement_id)


def test_approved_correction_changes_only_the_effective_view(client, db_session, test_users):
    owner, member = test_users["clinician_a"], test_users["clinician_b"]
    case, finding, first, second = _case_with_measurements(db_session, owner, member)
    review_id = _propose(client, finding, owner, {"target_measurement_id": first.id, "action": "AMEND", "corrected_value": 48.0})

    pending = _effective(client, case, owner, first.id)
    assert pending["correction_state"] == "CORRECTION_PROPOSED"
    assert pending["effective"]["value"] == 84.0

    self_approval = client.post(f"/api/v1/reviews/corrections/{review_id}/decision", headers=get_auth_headers(owner),
                                json={"decision": "APPROVED", "rationale": "Checked against the source page."})
    assert self_approval.status_code == 403
    assert self_approval.json()["detail"]["code"] == "FOUR_EYES_REQUIRED"

    approval = client.post(f"/api/v1/reviews/corrections/{review_id}/decision", headers=get_auth_headers(member),
                           json={"decision": "APPROVED", "rationale": "Checked against the source page."})
    assert approval.status_code == 201, approval.text

    applied = _effective(client, case, owner, first.id)
    assert applied["correction_state"] == "CORRECTION_APPLIED_TO_EFFECTIVE_VIEW"
    assert (applied["original"]["value"], applied["effective"]["value"]) == (84.0, 48.0)
    assert applied["applied_review_id"] == review_id
    db_session.refresh(first)
    assert first.value == 84.0, "the extracted measurement row is immutable"

    repeat = client.post(f"/api/v1/reviews/corrections/{review_id}/decision", headers=get_auth_headers(member),
                         json={"decision": "REJECTED", "rationale": "Second thoughts."})
    assert repeat.status_code == 409

    series = next(item for item in build_series(db_session, case.id) if item["name"] == "hdl_cholesterol")
    point = next(point for point in series["points"] if point["measurement_id"] == first.id)
    assert (point["value"], point["correction_review_id"]) == (48.0, review_id)


def test_rejected_and_removed_corrections(client, db_session, test_users):
    owner, member = test_users["clinician_a"], test_users["clinician_b"]
    case, finding, first, second = _case_with_measurements(db_session, owner, member)

    rejected_id = _propose(client, finding, owner, {"target_measurement_id": first.id, "action": "AMEND", "corrected_unit": "mmol/L"})
    response = client.post(f"/api/v1/reviews/corrections/{rejected_id}/decision", headers=get_auth_headers(member),
                           json={"decision": "REJECTED", "rationale": "The printed unit is mg/dL."})
    assert response.status_code == 201
    rejected = _effective(client, case, owner, first.id)
    assert rejected["correction_state"] == "CORRECTION_REJECTED"
    assert rejected["effective"]["unit"] == "mg/dL"

    removed_id = _propose(client, finding, owner, {"target_measurement_id": second.id, "action": "REMOVE"})
    response = client.post(f"/api/v1/reviews/corrections/{removed_id}/decision", headers=get_auth_headers(member),
                           json={"decision": "APPROVED", "rationale": "Row belongs to a different analyte."})
    assert response.status_code == 201
    assert _effective(client, case, owner, second.id)["correction_state"] == "REMOVED_IN_EFFECTIVE_VIEW"
    series = next(item for item in build_series(db_session, case.id) if item["name"] == "hdl_cholesterol")
    assert {point["measurement_id"] for point in series["points"]} == {first.id}
    assert {item["reason"] for item in series["excluded"]} == {f"REMOVED_BY_APPROVED_CORRECTION_R{removed_id}"}


def test_decisions_require_case_access_and_a_correction(client, db_session, test_users):
    owner, member = test_users["clinician_a"], test_users["clinician_b"]
    case, finding, first, _ = _case_with_measurements(db_session, owner, member)
    plain = client.post(f"/api/v1/reviews/{finding.id}", headers=get_auth_headers(owner),
                        json={"review_status": "CONFIRMED", "reviewer_comments": "Agree."})
    assert plain.status_code == 201
    response = client.post(f"/api/v1/reviews/corrections/{plain.json()['id']}/decision", headers=get_auth_headers(member),
                           json={"decision": "APPROVED", "rationale": "n/a"})
    assert response.status_code == 422

    db_session.query(CaseMembership).filter(CaseMembership.case_id == case.id).delete()
    db_session.commit()
    review_id = _propose(client, finding, owner, {"target_measurement_id": first.id, "action": "AMEND", "corrected_value": 47.0})
    outsider = client.post(f"/api/v1/reviews/corrections/{review_id}/decision", headers=get_auth_headers(member),
                           json={"decision": "APPROVED", "rationale": "Looks right."})
    assert outsider.status_code in {403, 404}


def test_report_contract_keeps_approved_value_when_newer_proposal_is_pending(client, db_session, test_users):
    owner, member = test_users["clinician_a"], test_users["clinician_b"]
    case, finding, first, _ = _case_with_measurements(db_session, owner, member)
    approved_id = _propose(client, finding, owner, {"target_measurement_id": first.id, "action": "AMEND", "corrected_value": 48.0})
    response = client.post(f"/api/v1/reviews/corrections/{approved_id}/decision", headers=get_auth_headers(member),
                           json={"decision": "APPROVED", "rationale": "Synthetic source reviewed independently."})
    assert response.status_code == 201
    pending_id = _propose(client, finding, owner, {"target_measurement_id": first.id, "action": "AMEND", "corrected_value": 47.0})
    record = _effective(client, case, owner, first.id)
    assert record["original"]["value"] == 84.0
    assert record["effective"]["value"] == 48.0
    assert record["applied_review_id"] == approved_id
    assert record["correction_state"] == "CORRECTION_APPLIED_TO_EFFECTIVE_VIEW"
    assert {entry["review_id"]: entry["state"] for entry in record["corrections"]} == {
        approved_id: "CORRECTION_APPROVED", pending_id: "CORRECTION_PROPOSED",
    }
    series = next(item for item in build_series(db_session, case.id) if item["name"] == "hdl_cholesterol")
    point = next(item for item in series["points"] if item["measurement_id"] == first.id)
    assert point["documented_value"] == record["effective"]["value"]
    assert point["correction_review_id"] == record["applied_review_id"]


def test_report_statement_contract_preserves_source_and_exposes_approved_assertion_and_removal(client, db_session, test_users):
    owner, member = test_users["clinician_a"], test_users["clinician_b"]
    case, finding, _, _ = _case_with_measurements(db_session, owner, member)
    statement = ClinicalReportStatement(case_id=case.id, finding_id=finding.id, entity="synthetic finding",
                                        negation="AFFIRMED", certainty="CERTAIN", temporality="CURRENT",
                                        experiencer="PATIENT", source_span="Synthetic source sentence.", source_span_start=0,
                                        source_span_end=26, anatomical_site="documented source site")
    db_session.add(statement)
    db_session.commit()

    def propose_and_approve(correction):
        response = client.post(f"/api/v1/reviews/{finding.id}", headers=get_auth_headers(owner), json={
            "review_status": "MODIFIED", "reviewer_comments": "Synthetic fixture correction.",
            "correction_payload": {"entity_corrections": [{"target_statement_id": statement.id, **correction}]},
        })
        assert response.status_code == 201, response.text
        review_id = response.json()["id"]
        response = client.post(f"/api/v1/reviews/corrections/{review_id}/decision", headers=get_auth_headers(member),
                               json={"decision": "APPROVED", "rationale": "Synthetic source independently reviewed."})
        assert response.status_code == 201, response.text
        return review_id

    amended_id = propose_and_approve({"action": "AMEND", "corrected_assertion": "NEGATED", "corrected_anatomical_site": "reviewed site"})
    response = client.get(f"/api/v1/cases/{case.id}/effective-evidence", headers=get_auth_headers(owner))
    record = response.json()["statements"][0]
    assert record["original"]["negation"] == "AFFIRMED"
    assert record["effective"]["negation"] == "NEGATED"
    assert record["effective"]["anatomical_site"] == "reviewed site"
    assert record["applied_review_id"] == amended_id
    removed_id = propose_and_approve({"action": "REMOVE"})
    response = client.get(f"/api/v1/cases/{case.id}/effective-evidence", headers=get_auth_headers(owner))
    record = response.json()["statements"][0]
    assert record["correction_state"] == "REMOVED_IN_EFFECTIVE_VIEW"
    assert record["applied_review_id"] == removed_id
    assert len(record["corrections"]) == 2
    source = client.get(f"/api/v1/cases/{case.id}/statements", headers=get_auth_headers(owner)).json()[0]
    assert source["source_span"] == "Synthetic source sentence."
    assert source["negation"] == "AFFIRMED"
    assert source["anatomical_site"] == "documented source site"


def test_report_join_matches_raw_endpoint_identifiers_and_original_field_aliases(client, db_session, test_users):
    owner, member = test_users["clinician_a"], test_users["clinician_b"]
    case, finding, first, _ = _case_with_measurements(db_session, owner, member)
    # Reprints remain in both API responses; the client deduplicates only its active display.
    duplicate = MedicalMeasurement(case_id=case.id, source_file_id=first.source_file_id, finding_id=finding.id,
                                   name=first.name, display_name=first.display_name, value=first.value, unit=first.unit,
                                   raw_value=first.raw_value, raw_unit=first.raw_unit, source_span="Synthetic repeated row.",
                                   source_span_start=0, source_span_end=23, documented_date=first.documented_date)
    db_session.add(duplicate)
    db_session.commit()
    headers = get_auth_headers(owner)
    raw = client.get(f"/api/v1/cases/{case.id}/measurements", headers=headers).json()
    reviewed = client.get(f"/api/v1/cases/{case.id}/effective-evidence", headers=headers).json()
    assert {row["id"] for row in raw} == {row["measurement_id"] for row in reviewed["measurements"]}
    assert len(raw) == len(reviewed["measurements"]) == 3
    for source in raw:
        record = next(row for row in reviewed["measurements"] if row["measurement_id"] == source["id"])
        assert record["original"] == {field: source[field] for field in record["original"]}
        assert record["effective"] == record["original"]
    assert next(row for row in raw if row["id"] == duplicate.id)["duplicate_of_measurement_id"] == first.id
