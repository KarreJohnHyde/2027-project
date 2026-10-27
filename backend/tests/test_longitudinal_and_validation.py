"""
Tests for Longitudinal Comparison (Old vs New) and IEEE Validation Metrics Endpoints.
Verifies Section IX and Section XIII of the IEEE 2026 manuscript.
"""

from datetime import datetime, timezone, timedelta

import pytest
from app.models.entities import Case, Examination, ModalityType
from app.services.auth import create_access_token


@pytest.fixture
def longitudinal_context(db_session, test_users):
    """Create deterministic evidence inside the per-test transaction only."""
    clinician = test_users["clinician_a"]
    case = Case(
        pseudonymous_id="LONGITUDINAL-TEST-CASE",
        description="Synthetic longitudinal comparison fixture.",
        created_by_id=clinician.id,
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)
    token = create_access_token(
        {"sub": clinician.username, "role": clinician.role.value, "user_id": clinician.id}
    )
    return {"headers": {"Authorization": f"Bearer {token}"}, "case": case}


def test_direct_health_endpoints(client):
    """Verifies infrastructure and versioned system health endpoints."""
    res1 = client.get("/health")
    assert res1.status_code == 200
    assert res1.json()["status"] == "HEALTHY"

    res2 = client.get("/api/v1/system/health")
    assert res2.status_code == 200
    assert res2.json()["status"] == "HEALTHY"


def test_ieee_validation_metrics_endpoint(client, longitudinal_context):
    """Verifies that GET /api/v1/metrics/ieee-validation returns all 16 IEEE equations and benchmarks."""
    auth_headers = longitudinal_context["headers"]
    res = client.get("/api/v1/metrics/ieee-validation", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "PENDING_VALIDATION"
    assert "equations" in data
    assert len(data["equations"]) >= 9

    eq_ids = [eq["equation_id"] for eq in data["equations"]]
    assert "Eq. 1-2" in eq_ids
    assert "Eq. 8-10" in eq_ids
    assert "Eq. 11-12" in eq_ids
    assert "Eq. 13-14" in eq_ids
    assert "Eq. 15" in eq_ids
    assert "Eq. 16" in eq_ids

    # Verify research notice is present
    assert "research_notice" in data
    assert "NOTICE" in data["research_notice"]
    # Registered public-dataset experiments are visible as internal held-out
    # research evidence, but the endpoint must never promote them to clinical
    # or external validation.
    for equation_id in ("Eq. 1-2", "Eq. 3-4", "Eq. 5"):
        experiment = next(eq for eq in data["equations"] if eq["equation_id"] == equation_id)["measured_metric"]
        assert experiment["status"] == "COMPLETED"
        assert experiment["value"]["clinical_validation"] is False
        assert experiment["value"]["external_validation"] is False
        assert experiment["value"]["experiments"]
    unevaluated = [eq for eq in data["equations"] if eq["equation_id"] not in {"Eq. 1-2", "Eq. 3-4", "Eq. 5", "Eq. 16"}]
    assert all(eq["measured_metric"]["value"] is None for eq in unevaluated)
    service_eq = next(eq for eq in data["equations"] if eq["equation_id"] == "Eq. 16")
    assert service_eq["measured_metric"]["status"] in {"COMPLETED", "NOT_RUN"}


def test_longitudinal_comparison_endpoint(client, longitudinal_context):
    """Comparison abstains when examination-level evidence links are absent."""
    auth_headers = longitudinal_context["headers"]
    expected_case_id = longitudinal_context["case"].id

    cases_res = client.get("/api/v1/cases", headers=auth_headers)
    assert cases_res.status_code == 200
    cases = cases_res.json()
    assert expected_case_id in {case["id"] for case in cases}

    res = client.post(f"/api/v1/cases/{expected_case_id}/compare", json={}, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "NOT_COMPARABLE"
    assert data["case_id"] == expected_case_id
    assert "interval_days" in data
    assert "semantic_report_diff" in data
    assert "numeric_deltas" in data
    assert "image_comparison" in data
    assert "twin_state_delta" in data

    assert data["semantic_report_diff"] == []
    assert data["numeric_deltas"] == []

    # Verify image comparison
    img_comp = data["image_comparison"]
    assert "status" in img_comp
    assert img_comp["is_comparable"] is False
    assert img_comp["status"] == "NOT_RUN"

    # Verify twin state delta
    twin_delta = data["twin_state_delta"]
    assert twin_delta["status"] == "MAPPING_UNSUPPORTED"
    assert twin_delta["representation_level"] == "L1"


def test_comparison_does_not_invent_numeric_deltas(db_session, longitudinal_context):
    """Two examination dates cannot create measurements by themselves."""
    from app.services.comparison_service import ComparisonService

    case = longitudinal_context["case"]
    now = datetime.now(timezone.utc)
    exam1 = Examination(case_id=case.id, exam_date=now - timedelta(days=60), modality=ModalityType.IMAGE)
    exam2 = Examination(case_id=case.id, exam_date=now, modality=ModalityType.IMAGE)

    db_session.add_all([exam1, exam2])
    db_session.commit()
    result = ComparisonService.compare_examinations(db_session, case, exam1.id, exam2.id)
    assert result["status"] == "NOT_COMPARABLE"
    assert result["numeric_deltas"] == []
