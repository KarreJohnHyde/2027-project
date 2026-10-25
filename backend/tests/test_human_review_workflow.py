"""Clinician review appends a decision without overwriting extracted evidence."""

from tests.conftest import get_auth_headers


def _create_report_evidence(client, headers, suffix: str):
    case_response = client.post(
        "/api/v1/cases",
        json={"pseudonymous_id": f"CASE-HUMAN-REVIEW-{suffix}"},
        headers=headers,
    )
    assert case_response.status_code == 201, case_response.text
    case_id = case_response.json()["id"]
    upload_response = client.post(
        f"/api/v1/cases/{case_id}/uploads",
        files={
            "file": (
                f"review-{suffix}.txt",
                b"No pleural effusion. Hemoglobin 13.2 g/dL (13.0-17.0).",
                "text/plain",
            )
        },
        data={"deidentified": "true", "is_associated": "true"},
        headers=headers,
    )
    assert upload_response.status_code == 201, upload_response.text
    analysis_response = client.post(
        f"/api/v1/uploads/{upload_response.json()['id']}/analysis-jobs",
        headers=headers,
    )
    assert analysis_response.status_code == 201, analysis_response.text
    finding = analysis_response.json()["findings"][0]
    finding_detail = client.get(f"/api/v1/findings/{finding['id']}", headers=headers).json()
    measurements = client.get(f"/api/v1/cases/{case_id}/measurements", headers=headers).json()
    return case_id, finding_detail, measurements


def test_clinician_can_reject_finding_while_original_output_is_preserved(client, test_users):
    owner_headers = get_auth_headers(test_users["clinician_a"])
    other_headers = get_auth_headers(test_users["clinician_b"])

    case_response = client.post(
        "/api/v1/cases",
        json={"pseudonymous_id": "CASE-HUMAN-REVIEW"},
        headers=owner_headers,
    )
    case_id = case_response.json()["id"]
    upload_response = client.post(
        f"/api/v1/cases/{case_id}/uploads",
        files={"file": ("review.txt", b"No pleural effusion.", "text/plain")},
        data={"deidentified": "true", "is_associated": "true"},
        headers=owner_headers,
    )
    analysis_response = client.post(
        f"/api/v1/uploads/{upload_response.json()['id']}/analysis-jobs",
        headers=owner_headers,
    )
    finding = analysis_response.json()["findings"][0]
    original_label = finding["label"]

    forbidden = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={"review_status": "REJECTED", "reviewer_comments": "Not my case."},
        headers=other_headers,
    )
    assert forbidden.status_code == 403

    review_response = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={
            "review_status": "REJECTED",
            "reviewer_comments": "Synthetic acceptance fixture: reject extracted interpretation.",
        },
        headers=owner_headers,
    )
    assert review_response.status_code == 201
    review = review_response.json()
    assert review["review_status"] == "REJECTED"
    assert review["correction_payload"] is None
    assert review["original_output_preserved"] is True

    persisted_finding = client.get(
        f"/api/v1/findings/{finding['id']}",
        headers=owner_headers,
    ).json()
    assert persisted_finding["label"] == original_label
    assert persisted_finding["review_status"] == "COMPLETED"

    reviews = client.get(
        f"/api/v1/reviews/{finding['id']}",
        headers=owner_headers,
    ).json()
    assert reviews == [review]

    provenance = client.get(
        f"/api/v1/cases/{case_id}/provenance",
        headers=owner_headers,
    ).json()
    event = next(item for item in provenance if item["action"] == "HUMAN_REVIEW_SUBMITTED")
    assert event["details"]["decision"] == "REJECTED"
    assert "original_label" not in event["details"]
    assert event["details"]["entity_correction_count"] == 0
    assert event["details"]["measurement_correction_count"] == 0


def test_modified_review_stores_typed_proposal_without_changing_source_evidence(client, test_users):
    owner_headers = get_auth_headers(test_users["clinician_a"])
    other_headers = get_auth_headers(test_users["clinician_b"])
    case_id, finding, measurements = _create_report_evidence(client, owner_headers, "TYPED")
    assert finding["report_statements"]
    assert measurements
    statement = finding["report_statements"][0]
    measurement = next(item for item in measurements if item["finding_id"] == finding["id"])

    original_statement = dict(statement)
    original_measurement = dict(measurement)
    payload = {
        "schema_version": "1.0",
        "status": "PROPOSED_NOT_APPLIED",
        "entity_corrections": [
            {
                "target_statement_id": statement["id"],
                "action": "AMEND",
                "corrected_entity": "No pleural fluid",
                "corrected_assertion": "NEGATED",
            }
        ],
        "measurement_corrections": [
            {
                "target_measurement_id": measurement["id"],
                "action": "AMEND",
                "corrected_value": 13.4,
                "corrected_result_operator": "=",
                "corrected_unit": "g/dL",
            }
        ],
    }
    response = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={
            "review_status": "MODIFIED",
            "reviewer_comments": "Synthetic fixture: transcription correction proposed.",
            "correction_payload": payload,
        },
        headers=owner_headers,
    )
    assert response.status_code == 201, response.text
    review = response.json()
    assert review["correction_payload"]["schema_version"] == "1.0"
    assert review["correction_payload"]["status"] == "PROPOSED_NOT_APPLIED"
    assert review["correction_payload"]["entity_corrections"][0]["corrected_entity"] == "No pleural fluid"
    assert review["correction_payload"]["measurement_corrections"][0]["corrected_value"] == 13.4
    assert review["original_output_preserved"] is True

    persisted_finding = client.get(f"/api/v1/findings/{finding['id']}", headers=owner_headers).json()
    persisted_measurements = client.get(f"/api/v1/cases/{case_id}/measurements", headers=owner_headers).json()
    persisted_measurement = next(item for item in persisted_measurements if item["id"] == measurement["id"])
    assert persisted_finding["report_statements"][0] == original_statement
    for key in ("value", "result_operator", "unit", "source_span", "source_span_start", "source_span_end"):
        assert persisted_measurement[key] == original_measurement[key]

    assert client.get(f"/api/v1/reviews/{finding['id']}", headers=other_headers).status_code == 403
    provenance = client.get(f"/api/v1/cases/{case_id}/provenance", headers=owner_headers).json()
    event = next(item for item in provenance if item["action"] == "HUMAN_REVIEW_SUBMITTED")
    expected_audit_metadata = {
        "finding_id": finding["id"],
        "decision": "MODIFIED",
        "original_output_preserved": True,
        "correction_schema_version": "1.0",
        "entity_correction_count": 1,
        "measurement_correction_count": 1,
    }
    assert all(event["details"].get(key) == value for key, value in expected_audit_metadata.items())
    assert "No pleural fluid" not in str(event["details"])
    assert "13.4" not in str(event["details"])


def test_review_correction_schema_rejects_unscoped_arbitrary_and_oversized_payloads(client, test_users):
    owner_headers = get_auth_headers(test_users["clinician_a"])
    _, finding, _ = _create_report_evidence(client, owner_headers, "VALIDATION")
    statement_id = finding["report_statements"][0]["id"]
    base_payload = {
        "schema_version": "1.0",
        "status": "PROPOSED_NOT_APPLIED",
        "entity_corrections": [
            {"target_statement_id": statement_id, "action": "AMEND", "corrected_entity": "Pleural effusion"}
        ],
        "measurement_corrections": [],
    }

    missing_payload = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={"review_status": "MODIFIED", "reviewer_comments": "Synthetic fixture rationale."},
        headers=owner_headers,
    )
    assert missing_payload.status_code == 422

    wrong_decision = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={"review_status": "CONFIRMED", "correction_payload": base_payload},
        headers=owner_headers,
    )
    assert wrong_decision.status_code == 422

    arbitrary = {**base_payload, "script": "not allowed"}
    arbitrary_response = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={"review_status": "MODIFIED", "reviewer_comments": "Synthetic fixture rationale.", "correction_payload": arbitrary},
        headers=owner_headers,
    )
    assert arbitrary_response.status_code == 422

    oversized_string = {
        **base_payload,
        "entity_corrections": [
            {"target_statement_id": statement_id, "action": "AMEND", "corrected_entity": "x" * 129}
        ],
    }
    oversized_response = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={"review_status": "MODIFIED", "reviewer_comments": "Synthetic fixture rationale.", "correction_payload": oversized_string},
        headers=owner_headers,
    )
    assert oversized_response.status_code == 422

    coerced_numeric = {
        **base_payload,
        "entity_corrections": [],
        "measurement_corrections": [
            {"target_measurement_id": 1, "action": "AMEND", "corrected_value": "13.4"}
        ],
    }
    coerced_numeric_response = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={"review_status": "MODIFIED", "reviewer_comments": "Synthetic fixture rationale.", "correction_payload": coerced_numeric},
        headers=owner_headers,
    )
    assert coerced_numeric_response.status_code == 422

    too_many = {
        **base_payload,
        "entity_corrections": [
            {"target_statement_id": index + 1, "action": "REMOVE"} for index in range(21)
        ],
    }
    too_many_response = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={"review_status": "MODIFIED", "reviewer_comments": "Synthetic fixture rationale.", "correction_payload": too_many},
        headers=owner_headers,
    )
    assert too_many_response.status_code == 422

    byte_oversized = {
        **base_payload,
        "entity_corrections": [],
        "measurement_corrections": [
            {
                "target_measurement_id": index + 1,
                "action": "AMEND",
                "corrected_display_name": "n" * 128,
                "corrected_value": float(index),
                "corrected_result_operator": "=",
                "corrected_unit": "u" * 32,
                "corrected_specimen": "s" * 64,
                "corrected_laboratory_method": "m" * 128,
            }
            for index in range(20)
        ],
    }
    byte_oversized_response = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={"review_status": "MODIFIED", "reviewer_comments": "Synthetic fixture rationale.", "correction_payload": byte_oversized},
        headers=owner_headers,
    )
    assert byte_oversized_response.status_code == 422
    assert "8192-byte" in byte_oversized_response.text

    foreign_target = {
        **base_payload,
        "entity_corrections": [
            {"target_statement_id": statement_id + 100000, "action": "REMOVE"}
        ],
    }
    foreign_response = client.post(
        f"/api/v1/reviews/{finding['id']}",
        json={"review_status": "MODIFIED", "reviewer_comments": "Synthetic fixture rationale.", "correction_payload": foreign_target},
        headers=owner_headers,
    )
    assert foreign_response.status_code == 422
    assert foreign_response.json()["detail"]["code"] == "CORRECTION_TARGET_NOT_IN_FINDING"
