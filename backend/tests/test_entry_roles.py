"""The welcome page's self-described roles: one list in the frontend and backend, and none of them grants anything."""

import re
from pathlib import Path

from app.schemas.entry_roles import ENTRY_ROLES
from app.services import browser_sessions

FRONTEND_ROLES = Path(__file__).resolve().parents[2] / "src" / "data" / "entryRoles.ts"
WEB = {browser_sessions.CLIENT_HEADER: "web"}


def frontend_values() -> set[str]:
    source = FRONTEND_ROLES.read_text(encoding="utf-8")
    values = set(re.findall(r'value: "([a-z_]+)"', source))
    values |= {f"specialist_{key}" for key in re.findall(r'specialist\("([a-z_]+)"', source)}
    values |= {f"department_{key}" for key in re.findall(r'department\("([a-z_]+)"', source)}
    return values


def test_the_frontend_offers_exactly_the_roles_the_backend_accepts():
    assert frontend_values() == set(ENTRY_ROLES)


def test_clinical_roles_specialties_and_departments_are_accepted_and_grant_nothing(client):
    for role in ("doctor", "nurse", "clinical_staff", "surgeon", "specialist_cardiology", "specialist_neurosurgery",
                 "department_emergency", "department_icu", "radiologist"):
        response = client.post("/api/v1/auth/enter", json={"name": "Role check", "role": role}, headers=WEB)
        assert response.status_code == 201, (role, response.text)
        user = response.json()["user"]
        assert user["stated_role"] == role and user["role"] == "public" and user["verification_status"] == "UNVERIFIED"
    for role in ("admin", "administrator", "specialist_", "department_unknown", "Doctor"):
        assert client.post("/api/v1/auth/enter", json={"name": "Role check", "role": role}, headers=WEB).status_code == 422
