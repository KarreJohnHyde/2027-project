"""
Unit and integration tests for Clinical Packages, Imaging Services, and Laboratory Investigations.
"""

from tests.conftest import get_auth_headers


def test_catalog_packages_and_imaging_endpoints(client):
    """Verifies that all standard health packages and imaging services are available."""
    # Packages
    pkg_res = client.get("/api/v1/catalog/packages")
    assert pkg_res.status_code == 200
    packages = pkg_res.json()
    pkg_ids = [p["id"] for p in packages]
    expected_ids = [
        "PKG-GEN-01",
        "PKG-WOMEN-01",
        "PKG-EXEC-01",
        "PKG-CARD-01",
        "PKG-RENAL-BASIC",
        "PKG-DIGEST-01",
        "PKG-RENAL-ADV",
        "PKG-LIVER-01",
    ]
    for exp_id in expected_ids:
        assert exp_id in pkg_ids, f"Expected package {exp_id} in catalog"

    # Expanded Package detail
    detail_res = client.get("/api/v1/catalog/packages/PKG-EXEC-01")
    assert detail_res.status_code == 200
    exec_pkg = detail_res.json()
    assert "lab_test_codes" in exec_pkg
    assert len(exec_pkg["lab_test_codes"]) > 0

    # Imaging services
    img_res = client.get("/api/v1/catalog/imaging")
    assert img_res.status_code == 200
    imaging = img_res.json()
    categories = [cat["category"] for cat in imaging]
    assert "CT Imaging" in categories
    assert "Ultrasound Imaging" in categories
    assert "Angiography" in categories
    assert "Cardiac CT Services" in categories

    # Lab tests catalog
    lab_res = client.get("/api/v1/catalog/lab-tests")
    assert lab_res.status_code == 200
    lab_data = lab_res.json()
    assert "panels" in lab_data
    assert "tests" in lab_data
    assert len(lab_data["tests"]) >= 20


def test_order_package_and_status_lifecycle(client, test_users):
    """Tests ordering a package or imaging service for a case, then transitioning status."""
    clinician = test_users["clinician_a"]
    headers = get_auth_headers(clinician)

    # Create a test case
    case_res = client.post(
        "/api/v1/cases",
        json={"pseudonymous_id": "CASE-PKG-TEST-01", "patient_ref": "REF-PKG-1"},
        headers=headers,
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]

    # Order General Health Check-up
    order_res = client.post(
        f"/api/v1/cases/{case_id}/orders",
        json={"item_id": "PKG-GEN-01", "clinical_notes": "Annual check-up requested."},
        headers=headers,
    )
    assert order_res.status_code == 201
    order_data = order_res.json()
    assert order_data["package_id"] == "PKG-GEN-01"
    assert order_data["status"] == "ORDERED"
    order_id = order_data["id"]

    # Order an imaging service (CT-KUB)
    kub_order_res = client.post(
        f"/api/v1/cases/{case_id}/orders",
        json={"item_id": "CT-KUB", "clinical_notes": "Evaluate flank pain."},
        headers=headers,
    )
    assert kub_order_res.status_code == 201
    assert kub_order_res.json()["package_id"] == "CT-KUB"

    # List orders for case
    list_orders_res = client.get(f"/api/v1/cases/{case_id}/orders", headers=headers)
    assert list_orders_res.status_code == 200
    orders = list_orders_res.json()
    assert len(orders) == 2

    # Transition order status: ORDERED -> IN_PROGRESS
    patch_res = client.patch(
        f"/api/v1/cases/{case_id}/orders/{order_id}",
        json={"status": "IN_PROGRESS"},
        headers=headers,
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "IN_PROGRESS"

    # Transition order status: IN_PROGRESS -> COMPLETED
    complete_res = client.patch(
        f"/api/v1/cases/{case_id}/orders/{order_id}",
        json={"status": "COMPLETED"},
        headers=headers,
    )
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == "COMPLETED"

    # Invalid transition from COMPLETED should fail
    conflict_res = client.patch(
        f"/api/v1/cases/{case_id}/orders/{order_id}",
        json={"status": "IN_PROGRESS"},
        headers=headers,
    )
    assert conflict_res.status_code == 409


def test_record_lab_investigation_report(client, test_users):
    """Tests recording structured laboratory results with automatic range evaluation."""
    clinician = test_users["clinician_a"]
    headers = get_auth_headers(clinician)

    # Create a test case
    case_res = client.post(
        "/api/v1/cases",
        json={"pseudonymous_id": "CASE-LAB-TEST-02", "patient_ref": "REF-LAB-2"},
        headers=headers,
    )
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]

    # Order Renal Basic package
    order_res = client.post(
        f"/api/v1/cases/{case_id}/orders",
        json={"item_id": "PKG-RENAL-BASIC"},
        headers=headers,
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["id"]

    # Record valid lab report linked to package (synthetic test values). Positions are
    # computed only against intervals printed by the laboratory; the rest are INDETERMINATE.
    report_payload = {
        "ordered_package_id": order_id,
        "lab_name": "Test Fixture Laboratory",
        "sample_type": "Serum",
        "patient_sex": "M",
        "results": [
            {"code": "UREA", "value": 45.0, "ref_low": 15.0, "ref_high": 40.0},  # above the printed interval
            {"code": "NA", "value": 140.0, "ref_low": 135.0, "ref_high": 145.0},
            {"code": "K", "value": 4.1, "ref_low": 3.5, "ref_high": 5.1},
            {"code": "CA", "value": 9.2},
            {"code": "PHOS", "value": 3.4},
            {"code": "HCO3", "value": 24.0},
        ],
    }
    lab_res = client.post(
        f"/api/v1/cases/{case_id}/lab-reports",
        json=report_payload,
        headers=headers,
    )
    assert lab_res.status_code == 201
    lab_data = lab_res.json()
    assert lab_data["report_title"] == "Renal Basic - Top Up Package"
    assert lab_data["flag_counts"] == {"HIGH": 1, "NORMAL": 2, "INDETERMINATE": 3}
    calcium = next(result for result in lab_data["results"] if result["code"] == "CA")
    assert calcium["ref_low"] is None and calcium["catalog_interval"] == "8.8 - 10.2"

    # Fetch lab reports for case
    list_lab_res = client.get(f"/api/v1/cases/{case_id}/lab-reports", headers=headers)
    assert list_lab_res.status_code == 200
    assert len(list_lab_res.json()) == 1

    # Attempting to record test outside the package should fail
    invalid_payload = {
        "ordered_package_id": order_id,
        "results": [
            {"code": "HBSAG", "value": "NON_REACTIVE"}  # Not in Renal Basic
        ],
    }
    fail_res = client.post(
        f"/api/v1/cases/{case_id}/lab-reports",
        json=invalid_payload,
        headers=headers,
    )
    assert fail_res.status_code == 400


def test_lab_report_never_assumes_laboratory_or_specimen(client, test_users):
    """Omitted provenance is recorded as NOT_DOCUMENTED and each interval states its source."""
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-LAB-PROVENANCE"}, headers=headers).json()["id"]
    response = client.post(
        f"/api/v1/cases/{case_id}/lab-reports",
        json={"patient_sex": "M", "results": [{"code": "HB", "value": 14.2}, {"code": "CREAT", "value": 1.1, "ref_low": 0.7, "ref_high": 1.3}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["lab_name"] == "NOT_DOCUMENTED" and report["sample_type"] == "NOT_DOCUMENTED"
    assert report["entry_method"] == "MANUAL_TRANSCRIPTION" and isinstance(report["recorded_by_id"], int)
    results = {result["code"]: result for result in report["results"]}
    assert results["CREAT"]["reference_source"] == "REPORTING_LABORATORY" and results["CREAT"]["status"] == "NORMAL"
    assert results["HB"]["reference_source"] == "NONE" and results["HB"]["status"] == "INDETERMINATE"
    assert results["HB"]["catalog_interval_source"] == "CATALOG_SEX_SPECIFIC_DEFAULT"


def test_manual_censored_result_and_method_round_trip_without_range_classification(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-LAB-CENSORED"}, headers=headers).json()["id"]
    response = client.post(
        f"/api/v1/cases/{case_id}/lab-reports",
        json={
            "lab_name": "Software Fixture Lab",
            "sample_type": "serum",
            "laboratory_method": "enzymatic assay",
            "results": [{"code": "CREAT", "result_operator": "<", "value": 0.01, "ref_low": 0.7, "ref_high": 1.3}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["laboratory_method"] == "enzymatic assay"
    result = report["results"][0]
    assert result["result_operator"] == "<" and result["result_value"] == 0.01
    assert result["status"] == "INDETERMINATE"
    assert "not treated as an exact result" in result["censoring_note"]


def test_transcribed_results_join_trends_without_double_counting(client, test_users):
    """A transcription of an already-extracted value is excluded; a new dated one joins the series."""
    headers = get_auth_headers(test_users["clinician_a"])
    case = client.post(
        "/api/v1/cases",
        json={"pseudonymous_id": "CASE-LAB-TREND", "examinations": [{"exam_date": "2025-01-01T09:00:00Z", "modality": "REPORT"}]},
        headers=headers,
    ).json()
    upload = client.post(
        f"/api/v1/cases/{case['id']}/uploads",
        files={"file": ("cr.txt", b"Specimen: serum\nMethod: enzymatic assay\nCreatinine 1.0 mg/dL.", "text/plain")},
        data={"deidentified": "true", "is_associated": "true", "examination_id": str(case["examinations"][0]["id"])},
        headers=headers,
    ).json()
    assert client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=headers).status_code == 201

    def record(case_id, collection_date, value, **extra):
        payload = {"collection_date": collection_date, "sample_type": "serum", "laboratory_method": "enzymatic assay", "results": [{"code": "CREAT", "value": value}], **extra}
        return client.post(f"/api/v1/cases/{case_id}/lab-reports", json=payload, headers=headers)

    assert record(case["id"], "2025-01-01", 1.0, source_file_id=upload["id"]).status_code == 201
    assert record(case["id"], "2025-06-01", 1.3).status_code == 201
    assert record(case["id"], "2999-01-01", 1.3).status_code == 400

    other = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-LAB-OTHER"}, headers=headers).json()
    assert record(other["id"], "2025-01-01", 1.0, source_file_id=upload["id"]).status_code == 404

    series = {item["name"]: item for item in client.get(f"/api/v1/cases/{case['id']}/biomarker-trends", headers=headers).json()["series"]}
    creatinine = series["creatinine"]
    assert [point["source_type"] for point in creatinine["points"]] == ["DOCUMENT_EXTRACTION", "MANUAL_TRANSCRIPTION"]
    assert [item["reason"] for item in creatinine["excluded"]] == [f"DUPLICATE_OF_M{creatinine['points'][0]['measurement_id']}"]
    # A catalog default is not the laboratory's documented interval, so no interval is drawn.
    assert creatinine["points"][1]["reference_low"] is None and creatinine["points"][1]["lab_report_id"] is not None
    assert creatinine["analysis"]["n"] == 2 and creatinine["analysis"]["status"] == "COMPUTED"
