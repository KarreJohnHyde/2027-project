"""File replacement (versioning) and withdrawal: metadata changes only, bytes and provenance kept.

Synthetic, de-identified fixtures only.
"""

from app.models.entities import Case, CaseMembership
from tests.conftest import get_auth_headers


def _upload(client, case_id, user, text, name="report.txt"):
    response = client.post(
        f"/api/v1/cases/{case_id}/uploads",
        headers=get_auth_headers(user),
        files={"file": (name, text.encode("utf-8"), "text/plain")},
        data={"deidentified": "true"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _new_version(client, file_id, user, text, reason="Clearer rescan of the same page."):
    return client.post(
        f"/api/v1/uploads/{file_id}/versions",
        headers=get_auth_headers(user),
        files={"file": ("report-v2.txt", text.encode("utf-8"), "text/plain")},
        data={"deidentified": "true", "reason": reason},
    )


def test_replacing_a_file_keeps_the_previous_version_and_its_provenance(client, db_session, test_users):
    owner = test_users["clinician_a"]
    case = Case(pseudonymous_id="VERSION-TEST", created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()
    first = _upload(client, case.id, owner, "Haemoglobin 12.1 g/dL (13.0-17.0)\n")

    identical = _new_version(client, first["id"], owner, "Haemoglobin 12.1 g/dL (13.0-17.0)\n")
    assert identical.status_code == 409 and identical.json()["detail"]["code"] == "IDENTICAL_CONTENT"

    response = _new_version(client, first["id"], owner, "Haemoglobin 12.4 g/dL (13.0-17.0)\n")
    assert response.status_code == 201, response.text
    second = response.json()
    assert (second["version_number"], second["supersedes_file_id"]) == (2, first["id"])

    previous = client.get(f"/api/v1/uploads/{first['id']}", headers=get_auth_headers(owner)).json()
    assert previous["superseded_by_file_id"] == second["id"]
    assert previous["is_associated"] is False
    assert previous["file_hash"] == first["file_hash"], "the earlier version's bytes and hash are unchanged"
    content = client.get(f"/api/v1/uploads/{first['id']}/content", headers=get_auth_headers(owner))
    assert content.status_code == 200 and content.content == b"Haemoglobin 12.1 g/dL (13.0-17.0)\n"

    stale = _new_version(client, first["id"], owner, "Haemoglobin 12.9 g/dL\n")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "NOT_THE_LATEST_VERSION"


def test_withdrawal_is_a_reasoned_tombstone(client, db_session, test_users):
    owner, viewer = test_users["clinician_a"], test_users["clinician_b"]
    case = Case(pseudonymous_id="WITHDRAW-TEST", created_by_id=owner.id)
    db_session.add(case)
    db_session.flush()
    db_session.add(CaseMembership(case_id=case.id, user_id=viewer.id, role="VIEWER", granted_by_id=owner.id))
    db_session.commit()
    record = _upload(client, case.id, owner, "Creatinine 1.0 mg/dL\n")

    forbidden = client.request("DELETE", f"/api/v1/uploads/{record['id']}", headers=get_auth_headers(viewer), json={"reason": "Wrong patient."})
    assert forbidden.status_code == 403

    response = client.request("DELETE", f"/api/v1/uploads/{record['id']}", headers=get_auth_headers(owner), json={"reason": "Uploaded to the wrong case."})
    assert response.status_code == 200, response.text
    withdrawn = response.json()
    assert withdrawn["withdrawn_at"] and withdrawn["withdrawal_reason"] == "Uploaded to the wrong case."
    assert withdrawn["is_associated"] is False

    assert client.get(f"/api/v1/uploads/{record['id']}/content", headers=get_auth_headers(owner)).status_code == 410
    assert client.get(f"/api/v1/uploads/{record['id']}", headers=get_auth_headers(owner)).status_code == 200, "metadata stays for provenance"
    again = client.request("DELETE", f"/api/v1/uploads/{record['id']}", headers=get_auth_headers(owner), json={"reason": "Twice."})
    assert again.status_code == 409
    assert _new_version(client, record["id"], owner, "Creatinine 1.1 mg/dL\n").status_code == 409
