"""Open-workspace mode: a workstation the owner controls, with no sign-in at all. Every account and case here is made in
the test; none is patient evidence."""

import pytest

from app import config
from app.models.entities import Case, User, UserRole, VerificationStatus
from app.services import browser_sessions
from app.services.auth import get_password_hash

WEB = {browser_sessions.CLIENT_HEADER: "web"}


def test_open_mode_is_refused_on_public_and_production_deployments():
    assert config.open_workspace_refusal("10", "development", vercel=False) is None
    assert config.open_workspace_refusal("", "production", vercel=True) is None
    assert "refused" in config.open_workspace_refusal("10", "production", vercel=False)
    assert "refused" in config.open_workspace_refusal("owner", "development", vercel=True)


@pytest.fixture
def owner(db_session):
    user = User(username="workspace_owner", email="workspace-owner@test.medtwin", hashed_password=get_password_hash("unused-in-test"),
                full_name="Workspace owner (synthetic)", role=UserRole.PUBLIC, verification_status=VerificationStatus.UNVERIFIED, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def open_mode(monkeypatch, owner):
    monkeypatch.setattr(config, "OPEN_WORKSPACE_ACCOUNT", str(owner.id))
    monkeypatch.setattr(config, "OPEN_WORKSPACE", True)
    monkeypatch.setattr(config, "SHARED_WORKSPACE", True)
    return owner


def test_every_browser_opens_the_workspace_without_signing_in(client, db_session, test_users, open_mode):
    other = Case(pseudonymous_id="SYNTHETIC-OTHER-ACCOUNT-CASE", created_by_id=test_users["clinician_a"].id)
    db_session.add(other)
    db_session.commit()
    client.cookies.clear()
    opened = client.get("/api/v1/auth/session")
    assert opened.status_code == 200, opened.text
    assert opened.json()["user"]["id"] == open_mode.id and opened.json()["open_workspace"] is True
    assert opened.json()["session"]["kind"] == "ACCOUNT"
    cookie = opened.cookies.get(browser_sessions.COOKIE_NAME)
    assert cookie
    # The same browser keeps its session; every case is open to it, and it can work on them.
    client.cookies.clear()
    headers = {"Cookie": f"{browser_sessions.COOKIE_NAME}={cookie}", **WEB}
    assert client.get("/api/v1/auth/session", headers=headers).json()["user"]["id"] == open_mode.id
    listed = client.get("/api/v1/cases", headers=headers).json()
    assert other.id in {item["id"] for item in listed}
    assert client.get(f"/api/v1/cases/{other.id}/measurements", headers=headers).status_code == 200
    created = client.post("/api/v1/cases", json={"pseudonymous_id": "SYNTHETIC-OPEN-CASE"}, headers=headers)
    assert created.status_code == 201
    # "My record" lists the workspace's cases, with reviewed results only.
    portal = client.get("/api/v1/portal/cases", headers=headers).json()
    assert {other.id, created.json()["id"]} <= {item["case_id"] for item in portal if item["relationship"] == "WORKSPACE"}
    record = client.get(f"/api/v1/portal/cases/{other.id}", headers=headers)
    assert record.status_code == 200 and record.json()["relationship"] == "WORKSPACE"


def test_an_earlier_visitor_or_demo_session_gives_way_to_the_workspace(client, open_mode):
    visitor = client.post("/api/v1/auth/enter", json={"name": "Earlier visitor", "role": "student"}, headers=WEB)
    raw = visitor.cookies.get(browser_sessions.COOKIE_NAME)
    client.cookies.clear()
    restored = client.get("/api/v1/auth/session", headers={"Cookie": f"{browser_sessions.COOKIE_NAME}={raw}"})
    assert restored.json()["user"]["id"] == open_mode.id
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers={"Cookie": f"{browser_sessions.COOKIE_NAME}={raw}"}).status_code == 401


def test_demo_cases_stay_out_of_the_open_record(client, db_session, open_mode):
    demo = client.post("/api/v1/auth/guest", headers=WEB).json()
    client.cookies.clear()
    opened = client.get("/api/v1/auth/session")
    headers = {"Cookie": f"{browser_sessions.COOKIE_NAME}={opened.cookies.get(browser_sessions.COOKIE_NAME)}", **WEB}
    assert demo["case_id"] not in {item["case_id"] for item in client.get("/api/v1/portal/cases", headers=headers).json()}


def test_an_administrator_cannot_be_the_open_account(client, monkeypatch, test_users):
    monkeypatch.setattr(config, "OPEN_WORKSPACE_ACCOUNT", str(test_users["admin"].id))
    monkeypatch.setattr(config, "OPEN_WORKSPACE", True)
    client.cookies.clear()
    refused = client.get("/api/v1/auth/session")
    assert refused.status_code == 503 and "administrator" in refused.json()["detail"]


def test_without_open_mode_nothing_changes(client):
    client.cookies.clear()
    assert client.get("/api/v1/auth/session").status_code == 401
    entered = client.post("/api/v1/auth/enter", json={"name": "Closed mode", "role": "doctor"}, headers=WEB)
    raw = entered.cookies.get(browser_sessions.COOKIE_NAME)
    client.cookies.clear()
    assert client.get("/api/v1/auth/session", headers={"Cookie": f"{browser_sessions.COOKIE_NAME}={raw}"}).json()["open_workspace"] is False
