"""Try the demo: a temporary guest sign-in with one synthetic case analysed by the ordinary pipeline."""

import pytest

from app.models.entities import User
from tests.conftest import get_auth_headers


@pytest.mark.private_workspace
def test_try_the_demo_creates_a_signed_in_guest_with_an_analysed_synthetic_case(client, db_session):
    started = client.post("/api/v1/auth/guest")
    assert started.status_code == 201, started.text
    session = started.json()
    assert session["username"].startswith("guest-") and session["role"] == "public"
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    case_id = session["case_id"]

    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["is_guest"] is True and me["verification_status"] == "UNVERIFIED"
    files = client.get(f"/api/v1/cases/{case_id}/uploads", headers=headers).json()
    assert sorted(item["filename"] for item in files) == ["demo_ct_abdomen_report.txt", "demo_lab_report_june.txt", "demo_lab_report_march.txt"]

    # The values come from extracting the fictional documents, compared with the intervals printed in them.
    rows = client.get(f"/api/v1/cases/{case_id}/measurements", headers=headers).json()
    found = {(row["name"], row["documented_date"]): row for row in rows}
    assert found[("hemoglobin", "2026-03-14")]["value"] == 10.8
    assert found[("hemoglobin", "2026-03-14")]["documented_range_position"] == "BELOW_DOCUMENTED_INTERVAL"
    assert found[("creatinine", "2026-06-18")]["documented_range_position"] == "ABOVE_DOCUMENTED_INTERVAL"
    assert found[("urea", "2026-06-18")]["documented_range_position"] == "WITHIN_DOCUMENTED_INTERVAL"
    assert all(row["reference_source"] in {"DOCUMENTED_IN_SOURCE", None} for row in rows)
    assert {date for _, date in found} >= {"2026-03-14", "2026-06-18"}

    statements = client.get(f"/api/v1/cases/{case_id}/statements", headers=headers).json()
    negated = {s["entity_text"].lower() for s in statements if s["is_negated"]}
    affirmed = {s["entity_text"].lower() for s in statements if not s["is_negated"]}
    assert "hydronephrosis" in negated and "lymphadenopathy" in negated
    assert any("calculus" in entity for entity in affirmed)

    # A guest has every feature, on its own cases only.
    assert client.post("/api/v1/cases", json={"pseudonymous_id": "GUEST-OWN-CASE"}, headers=headers).status_code == 201
    other = User(username="someone_else", email="someone-else@test.medtwin", hashed_password="unused", is_active=True)
    db_session.add(other)
    db_session.commit()
    assert client.get(f"/api/v1/cases/{case_id}/measurements", headers=get_auth_headers(other)).status_code == 403

    # The account is kept; nobody knows its password, so it cannot be signed into again.
    guest = db_session.query(User).filter(User.username == session["username"]).one()
    assert guest.is_guest and guest.is_active
    assert client.post("/api/v1/auth/login", json={"username": session["username"], "password": "guess"}).status_code == 401


def test_guest_usernames_are_reserved(client):
    response = client.post("/api/v1/auth/register", json={"username": "guest-mine", "email": "mine@test.medtwin", "password": "secret1"})
    assert response.status_code == 400
    assert "reserved" in response.json()["detail"]
