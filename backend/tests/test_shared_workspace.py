"""Explicit shared-workspace opt-in: every account lists, opens and works on every case.

Per-account privacy remains available with MEDTWIN_SHARED_WORKSPACE=false; tests marked private_workspace cover it."""


def _enter(client, name):
    session = client.post("/api/v1/auth/enter", json={"name": name, "age": 40, "gender": "other", "role": "researcher"}).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_every_account_works_on_every_case(client, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "SHARED_WORKSPACE", True)
    first, second = _enter(client, "First"), _enter(client, "Second")
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "SHARED-SPACE-CASE"}, headers=first).json()["id"]

    assert case_id in {item["id"] for item in client.get("/api/v1/cases", headers=second).json()}
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("note.txt", b"SYNTHETIC NOTE\nNo pleural effusion.\n", "text/plain")},
                         data={"deidentified": "true"}, headers=second)
    assert upload.status_code == 201, upload.text
    analysis = client.post(f"/api/v1/uploads/{upload.json()['id']}/analysis-jobs", headers=first)
    assert analysis.status_code == 201, analysis.text
    statements = client.get(f"/api/v1/cases/{case_id}/statements", headers=second).json()
    assert any(item["entity_text"].lower() == "pleural effusion" for item in statements)


def test_evaluation_runs_are_shared(client):
    first, second = _enter(client, "Evaluator"), _enter(client, "Reader")
    assert client.get("/api/v1/evaluation/runs", headers=second).status_code == 200
    assert client.get("/api/v1/evaluation/runs/999999", headers=first).status_code == 404


def test_deleting_a_whole_case_stays_with_its_creator(client):
    first, second = _enter(client, "Creator"), _enter(client, "Other")
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "SHARED-SPACE-DELETE"}, headers=first).json()["id"]
    assert client.delete(f"/api/v1/cases/{case_id}", headers=second).status_code == 403
    assert client.delete(f"/api/v1/cases/{case_id}", headers=first).status_code == 204
