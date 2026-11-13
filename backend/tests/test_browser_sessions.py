"""Persistent, passwordless browser sessions for the entry page (HttpOnly cookie), the demo, and their limits.

All accounts and cases here are created in the test; none is patient evidence."""

import secrets
from datetime import datetime, timedelta

import pytest

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.models.entities import BrowserSession, Case, User
from app.services import browser_sessions
from app.services.auth import get_password_hash
from tests.conftest import get_auth_headers

WEB = {browser_sessions.CLIENT_HEADER: "web"}
COOKIE = browser_sessions.COOKIE_NAME


def _enter(client, key=None, **overrides):
    body = {"name": "Asha", "role": "researcher", **overrides}
    headers = {**WEB, **({"Idempotency-Key": key} if key else {})}
    return client.post("/api/v1/auth/enter", json=body, headers=headers)


def _cookie(response):
    value = response.cookies.get(COOKIE)
    assert value, "the session cookie was not set"
    return value


def _as(client, raw, method="GET", path="/api/v1/auth/session", web=True, **kwargs):
    client.cookies.clear()
    headers = {**(WEB if web else {}), "Cookie": f"{COOKIE}={raw}", **kwargs.pop("headers", {})}
    return client.request(method, path, headers=headers, **kwargs)


@pytest.mark.private_workspace
def test_entering_sets_an_httponly_cookie_and_returns_no_token(client, db_session):
    response = _enter(client, age=None, gender=None)
    assert response.status_code == 201, response.text
    body = response.json()
    assert "access_token" not in body and body["user"]["full_name"] == "Asha" and body["user"]["stated_role"] == "researcher"
    assert body["user"]["age"] is None and body["user"]["gender"] is None and body["session"]["kind"] == "VISITOR"
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=lax" in header and "path=/api" in header
    raw = _cookie(response)
    # The database keeps only a hash of the cookie value.
    stored = db_session.query(BrowserSession).one()
    assert stored.token_hash == browser_sessions.digest(raw) and stored.token_hash != raw
    # A later visit from the same browser restores the profile without the form.
    restored = _as(client, raw)
    assert restored.status_code == 200 and restored.json()["user"]["id"] == body["user"]["id"]
    assert _as(client, raw, path="/api/v1/auth/me").json()["username"].startswith("visitor-")


def test_the_same_name_makes_two_separate_visitors(client):
    first, second = _enter(client), _enter(client)
    assert first.json()["user"]["id"] != second.json()["user"]["id"]
    assert _cookie(first) != _cookie(second)


def test_a_retried_entry_with_the_same_key_reuses_the_visitor(client, db_session):
    key = "entry-attempt-0001"
    first, retried = _enter(client, key=key), _enter(client, key=key)
    assert first.status_code == retried.status_code == 201
    assert first.json()["user"]["id"] == retried.json()["user"]["id"]
    assert db_session.query(User).filter(User.is_visitor.is_(True)).count() == 1
    # A different attempt is a different visitor, even with the same details.
    assert _enter(client, key="entry-attempt-0002").json()["user"]["id"] != first.json()["user"]["id"]


def test_entry_validation(client):
    assert _enter(client, name="   ").status_code == 422
    assert _enter(client, role="administrator").status_code == 422
    assert _enter(client, age=121).status_code == 422
    assert _enter(client, role="clinician", age=40, gender="female").status_code == 201
    assert client.post("/api/v1/auth/enter", json={"name": "No role"}, headers=WEB).status_code == 422
    assert _enter(client, key="short").status_code == 400


@pytest.mark.private_workspace
def test_cookie_writes_need_the_client_header_and_visitors_are_isolated(client):
    first, second = _cookie(_enter(client)), _cookie(_enter(client, name="Ravi"))
    blocked = _as(client, first, "POST", "/api/v1/cases", web=False, json={"pseudonymous_id": "VISITOR-A-CASE"})
    assert blocked.status_code == 403 and "CLIENT_HEADER_REQUIRED" in blocked.json()["detail"]
    created = _as(client, first, "POST", "/api/v1/cases", json={"pseudonymous_id": "VISITOR-A-CASE"})
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    assert _as(client, second, path=f"/api/v1/cases/{case_id}/measurements").status_code == 403
    assert _as(client, first, path=f"/api/v1/cases/{case_id}/measurements").status_code == 200


def test_sign_out_revokes_the_session(client):
    raw = _cookie(_enter(client))
    out = _as(client, raw, "POST", "/api/v1/auth/logout")
    assert out.status_code == 204 and COOKIE in out.headers.get("set-cookie", "")
    assert _as(client, raw).status_code == 401
    assert _as(client, raw, path="/api/v1/auth/me").status_code == 401


def test_expired_and_unknown_sessions_fail_safely(client, db_session):
    raw = _cookie(_enter(client))
    session = db_session.query(BrowserSession).one()
    session.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    expired = _as(client, raw)
    assert expired.status_code == 401 and "NO_SESSION" in expired.json()["detail"]
    assert _as(client, "not-a-real-session-token").status_code == 401
    assert _as(client, raw, path="/api/v1/cases").status_code == 401


def test_old_sessions_are_rotated_with_a_short_grace(client, db_session):
    raw = _cookie(_enter(client))
    session = db_session.query(BrowserSession).one()
    session.created_at = datetime.utcnow() - browser_sessions.ROTATE_AFTER - timedelta(minutes=1)
    db_session.commit()
    rotated = _as(client, raw)
    assert rotated.status_code == 200 and rotated.json()["session"]["rotated"] is True
    fresh = _cookie(rotated)
    assert fresh != raw and _as(client, fresh).status_code == 200
    # The old token still serves requests in flight, then stops.
    assert _as(client, raw, path="/api/v1/auth/me").status_code == 200
    db_session.refresh(session)
    session.revoked_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert _as(client, raw, path="/api/v1/auth/me").status_code == 401


def test_an_earlier_browser_token_moves_to_a_cookie(client):
    legacy = client.post("/api/v1/auth/enter", json={"name": "Before", "role": "student"}).json()
    assert "access_token" in legacy, "API clients without the web header still receive a bearer token"
    client.cookies.clear()
    claimed = client.post("/api/v1/auth/session/claim", headers={**WEB, "Authorization": f"Bearer {legacy['access_token']}"})
    assert claimed.status_code == 200 and claimed.json()["user"]["id"] == legacy["user_id"]
    assert _as(client, _cookie(claimed)).json()["user"]["id"] == legacy["user_id"]
    client.cookies.clear()
    assert client.post("/api/v1/auth/session/claim", headers={**WEB, "Authorization": "Bearer forged"}).status_code == 401


@pytest.mark.private_workspace
def test_a_stated_role_grants_nothing_and_a_name_reaches_no_existing_account(client, db_session, test_users):
    owner = test_users["clinician_a"]
    case = Case(pseudonymous_id="REGISTERED-OWNER-CASE", created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()
    raw = _cookie(_enter(client, name=owner.full_name, role="clinician"))
    assert _as(client, raw).json()["user"]["role"] == "public"
    assert _as(client, raw, path=f"/api/v1/cases/{case.id}/measurements").status_code == 403
    assert _as(client, raw, path="/api/v1/system/audit").status_code == 403
    listed = _as(client, raw, path="/api/v1/cases").json()
    assert all(item["id"] != case.id for item in (listed if isinstance(listed, list) else listed.get("items", [])))
    # The registered account and its case are untouched and still reachable by their owner.
    assert client.get(f"/api/v1/cases/{case.id}/measurements", headers=get_auth_headers(owner)).status_code == 200


@pytest.mark.private_workspace
def test_password_accounts_sign_in_to_a_cookie_session_from_the_web(client, db_session, test_users):
    # A password made for this test only, so no credential-like literal is kept in the repository.
    secret = secrets.token_urlsafe(18)
    test_users["clinician_a"].hashed_password = get_password_hash(secret)
    db_session.commit()
    credentials = {"username": "clinician_a", "password": secret}
    response = client.post("/api/v1/auth/login", json=credentials, headers=WEB)
    assert response.status_code == 200 and "access_token" not in response.json()
    assert response.json()["session"]["kind"] == "ACCOUNT"
    assert _as(client, _cookie(response)).json()["user"]["username"] == "clinician_a"
    api = client.post("/api/v1/auth/login", json=credentials)
    assert "access_token" in api.json(), "API clients keep the bearer token response"
    # Moving an account's earlier browser token to a cookie keeps the password sign-in lifetime, not the visitor one.
    client.cookies.clear()
    claimed = client.post("/api/v1/auth/session/claim", headers={**WEB, "Authorization": f"Bearer {api.json()['access_token']}"})
    assert claimed.json()["session"]["kind"] == "ACCOUNT"
    expires = datetime.fromisoformat(claimed.json()["session"]["expires_at"]).replace(tzinfo=None)
    assert expires <= datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES, seconds=60)


@pytest.mark.private_workspace
def test_a_one_time_sign_in_link_opens_a_registered_account_once(client, db_session, test_users):
    owner = test_users["clinician_a"]
    code = browser_sessions.issue_sign_in_link(db_session, owner)
    # The code is never a session by itself.
    assert _as(client, code).status_code == 401
    client.cookies.clear()
    assert client.post("/api/v1/auth/link", json={"code": code}).status_code == 400, "only the web app redeems links"
    opened = client.post("/api/v1/auth/link", json={"code": code}, headers=WEB)
    assert opened.status_code == 200, opened.text
    assert opened.json()["user"]["id"] == owner.id and opened.json()["session"]["kind"] == "ACCOUNT"
    assert _as(client, _cookie(opened)).json()["user"]["id"] == owner.id
    client.cookies.clear()
    assert client.post("/api/v1/auth/link", json={"code": code}, headers=WEB).status_code == 401, "a link works once"
    # An expired link is refused too.
    stale = browser_sessions.issue_sign_in_link(db_session, owner)
    row = db_session.query(BrowserSession).filter(BrowserSession.token_hash == browser_sessions.digest(stale)).one()
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert client.post("/api/v1/auth/link", json={"code": stale}, headers=WEB).status_code == 401
    assert client.post("/api/v1/auth/link", json={"code": "x" * 40}, headers=WEB).status_code == 401


def test_sign_in_links_are_for_registered_accounts_only(client, db_session):
    visitor = db_session.get(User, _enter(client).json()["user"]["id"])
    with pytest.raises(ValueError):
        browser_sessions.issue_sign_in_link(db_session, visitor)


@pytest.mark.private_workspace
def test_demo_sessions_are_isolated_and_retries_reopen_the_same_demo(client, db_session):
    first = client.post("/api/v1/auth/guest", headers={**WEB, "Idempotency-Key": "demo-attempt-0001"})
    assert first.status_code == 201, first.text
    retried = client.post("/api/v1/auth/guest", headers={**WEB, "Idempotency-Key": "demo-attempt-0001"})
    assert retried.json()["user"]["id"] == first.json()["user"]["id"] and retried.json()["case_id"] == first.json()["case_id"]
    other = client.post("/api/v1/auth/guest", headers=WEB)
    guest_a, guest_b = _cookie(first), _cookie(other)
    assert first.json()["session"]["kind"] == "GUEST"
    case_a, case_b = first.json()["case_id"], other.json()["case_id"]
    assert _as(client, guest_a, path=f"/api/v1/cases/{case_a}/uploads").status_code == 200
    assert _as(client, guest_b, path=f"/api/v1/cases/{case_a}/uploads").status_code == 403
    visitor = _cookie(_enter(client))
    assert _as(client, visitor, path=f"/api/v1/cases/{case_b}/uploads").status_code == 403
    assert _as(client, guest_a, path=f"/api/v1/cases/{case_b}/uploads").status_code == 403
