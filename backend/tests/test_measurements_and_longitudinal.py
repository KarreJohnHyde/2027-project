"""Source-linked numeric extraction and longitudinal comparison acceptance tests."""

from tests.conftest import get_auth_headers

from app.services.nlp_processor import extract_numeric_measurements


def test_numeric_measurements_preserve_values_units_and_exact_spans():
    report = (
        "Heart rate: 82 bpm. SpO2: 94%. BP 120/80 mmHg. "
        "Glucose 101 mg/dL. The lesion measures 1.2 cm."
    )

    measurements = extract_numeric_measurements(report)
    by_name = {item["name"]: item for item in measurements}

    assert by_name["heart_rate"]["value"] == 82.0
    assert by_name["heart_rate"]["unit"] == "bpm"
    assert by_name["oxygen_saturation"]["value"] == 94.0
    assert by_name["oxygen_saturation"]["unit"] == "%"
    assert by_name["systolic_blood_pressure"]["value"] == 120.0
    assert by_name["diastolic_blood_pressure"]["value"] == 80.0
    assert by_name["glucose"]["value"] == 101.0
    assert by_name["glucose"]["unit"] == "mg/dL"
    assert by_name["lesion_size"]["value"] == 12.0
    assert by_name["lesion_size"]["unit"] == "mm"

    for item in measurements:
        assert report[item["source_span_start"]:item["source_span_end"]] == item["source_span"]


def test_censored_lab_result_preserves_operator_and_never_becomes_exact(client, test_users):
    report = (
        "Specimen: serum\nMethod: enzymatic assay\nLaboratory: Software Fixture Lab\n"
        "Creatinine <0.01 mg/dL (0.7-1.3). Age: 50. Sex: M."
    )
    extracted = {item["name"]: item for item in extract_numeric_measurements(report)}["creatinine"]
    assert extracted["result_operator"] == "<"
    assert extracted["value"] == 0.01
    assert extracted["source_span"] == "Creatinine <0.01 mg/dL"

    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-CENSORED-LAB"}, headers=headers).json()["id"]
    upload = client.post(
        f"/api/v1/cases/{case_id}/uploads",
        files={"file": ("censored.txt", report.encode(), "text/plain")},
        data={"deidentified": "true"},
        headers=headers,
    ).json()
    assert client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=headers).status_code == 201
    measurement = client.get(f"/api/v1/cases/{case_id}/measurements", headers=headers).json()[0]
    assert measurement["result_operator"] == "<"
    assert measurement["documented_range_position"] == "INDETERMINATE_CENSORED_RESULT"
    assert measurement["specimen"].lower() == "serum"
    assert measurement["laboratory_method"] == "enzymatic assay"
    assert measurement["laboratory_name"] == "Software Fixture Lab"
    assert measurement["source_hash"] == upload["file_hash"]
    egfr = client.get(f"/api/v1/cases/{case_id}/calculations/egfr", headers=headers).json()
    assert egfr["results"][0]["value"] is None
    assert "CREATININE_IS_CENSORED_NOT_AN_EXACT_VALUE" in egfr["results"][0]["missing_or_invalid_inputs"]


def test_report_measurements_persist_and_compare_across_examinations(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_response = client.post(
        "/api/v1/cases",
        json={"pseudonymous_id": "CASE-LONGITUDINAL-MEASUREMENTS"},
        headers=headers,
    )
    assert case_response.status_code == 201
    case_id = case_response.json()["id"]

    examinations = []
    for date, indication in (
        ("2025-01-01T09:00:00Z", "De-identified baseline report"),
        ("2025-02-01T09:00:00Z", "De-identified follow-up report"),
    ):
        response = client.post(
            f"/api/v1/cases/{case_id}/examinations",
            json={
                "exam_date": date,
                "modality": "REPORT",
                "clinical_indication": indication,
            },
            headers=headers,
        )
        assert response.status_code == 201
        examinations.append(response.json())

    reports = (
        (examinations[0]["id"], b"Heart rate: 72 bpm. SpO2: 96%. No pleural effusion."),
        (examinations[1]["id"], b"Heart rate: 80 bpm. SpO2: 94%. Pleural effusion."),
    )
    upload_ids = []
    for index, (examination_id, report_bytes) in enumerate(reports):
        upload_response = client.post(
            f"/api/v1/cases/{case_id}/uploads",
            files={"file": (f"report-{index}.txt", report_bytes, "text/plain")},
            data={
                "examination_id": str(examination_id),
                "is_associated": "true",
                "deidentified": "true",
            },
            headers=headers,
        )
        assert upload_response.status_code == 201
        upload = upload_response.json()
        assert upload["examination_id"] == examination_id
        upload_ids.append(upload["id"])

        analysis_response = client.post(
            f"/api/v1/uploads/{upload['id']}/analysis-jobs",
            headers=headers,
        )
        assert analysis_response.status_code == 201
        assert analysis_response.json()["status"] == "COMPLETED"

    measurement_response = client.get(
        f"/api/v1/cases/{case_id}/measurements",
        headers=headers,
    )
    assert measurement_response.status_code == 200
    measurements = measurement_response.json()
    assert len(measurements) == 4
    assert {item["source_file_id"] for item in measurements} == set(upload_ids)
    assert {item["examination_id"] for item in measurements} == {
        examinations[0]["id"],
        examinations[1]["id"],
    }
    assert all(item["review_status"] == "PENDING_HUMAN_REVIEW" for item in measurements)

    comparison_response = client.post(
        f"/api/v1/cases/{case_id}/compare",
        json={
            "prior_exam_id": examinations[0]["id"],
            "current_exam_id": examinations[1]["id"],
        },
        headers=headers,
    )
    assert comparison_response.status_code == 200
    comparison = comparison_response.json()
    assert comparison["status"] == "COMPARABLE"
    assert comparison["interval_days"] == 31
    deltas = {item["name"]: item for item in comparison["numeric_deltas"]}
    assert deltas["heart_rate"]["absolute_delta"] == 8.0
    assert deltas["oxygen_saturation"]["absolute_delta"] == -2.0
    assert deltas["heart_rate"]["interpretation"] is None
    assert deltas["heart_rate"]["prior"]["source_file_id"] == upload_ids[0]
    assert deltas["heart_rate"]["current"]["source_file_id"] == upload_ids[1]
    assert comparison["image_comparison"]["status"] == "NOT_RUN"
    assert comparison["twin_state_delta"]["status"] == "MAPPING_UNSUPPORTED"

    provenance = client.get(
        f"/api/v1/cases/{case_id}/provenance",
        headers=headers,
    ).json()
    assert "LONGITUDINAL_COMPARISON_RUN" in {event["action"] for event in provenance}
