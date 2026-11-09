"""Entry page: name, age, gender and role open a private workspace without a password."""

import pytest

from app.models.entities import User


def _enter(client, **overrides):
    body = {"name": "Asha", "age": 34, "gender": "female", "role": "doctor", **overrides}
    return client.post("/api/v1/auth/enter", json=body)


@pytest.mark.private_workspace
def test_entering_opens_a_workspace_with_every_feature(client, db_session):
    response = _enter(client)
    assert response.status_code == 201, response.text
    session = response.json()
    headers = {"Authorization": f"Bearer {session['access_token']}"}
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert (me["full_name"], me["age"], me["gender"], me["stated_role"]) == ("Asha", 34, "female", "doctor")
    assert me["is_visitor"] is True and me["role"] == "public" and me["verification_status"] == "UNVERIFIED"
    assert session["username"].startswith("visitor-")

    case = client.post("/api/v1/cases", json={"pseudonymous_id": "VISITOR-OWN-CASE"}, headers=headers)
    assert case.status_code == 201, case.text
    # Another visitor has the same features on their own workspace, and cannot open this one.
    other = {"Authorization": f"Bearer {_enter(client, name='Ravi', gender='male', role='patient').json()['access_token']}"}
    assert client.get(f"/api/v1/cases/{case.json()['id']}/measurements", headers=other).status_code == 403
    # No password exists to sign in with; the account is kept.
    assert client.post("/api/v1/auth/login", json={"username": session["username"], "password": "x"}).status_code == 401
    assert db_session.query(User).filter(User.username == session["username"]).one().is_active


def test_entry_values_are_checked(client):
    assert _enter(client, name="").status_code == 422
    assert _enter(client, age=150).status_code == 422
    assert _enter(client, gender="unknown").status_code == 422
    assert _enter(client, role="administrator").status_code == 422
    assert _enter(client, password="x").status_code == 422, "the entry page takes no password"


def test_visitor_usernames_are_reserved(client):
    response = client.post("/api/v1/auth/register", json={"username": "visitor-mine", "email": "mine@test.medtwin", "password": "secret1"})
    assert response.status_code == 400 and "reserved" in response.json()["detail"]
