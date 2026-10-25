"""Regression contracts from the MedTwin 2.0 directive that no other test pins down:
the IEEE equation map is authenticated and consistently numbered (#5), and the hybrid
atlas never claims patient registration (#17)."""

import json
import re

import pytest

from app.config import ANATOMY_MANIFEST_PATH
from tests.conftest import get_auth_headers


def _equation_numbers(equation_id: str) -> list[int]:
    match = re.fullmatch(r"Eq\. (\d+)(?:-(\d+))?", equation_id)
    assert match, f"unexpected equation id {equation_id!r}"
    first, last = int(match.group(1)), int(match.group(2) or match.group(1))
    assert first <= last
    return list(range(first, last + 1))


def test_earlier_and_revised_equation_numbering_stay_distinct_and_authenticated(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    for endpoint in ("/api/v1/metrics/ieee-validation", "/api/v1/research/traceability"):
        assert client.get(endpoint).status_code == 401, endpoint

    # Earlier manuscript: Eq. 1-16, each number claimed once, in manuscript order.
    earlier = client.get("/api/v1/metrics/ieee-validation", headers=headers).json()
    assert "earlier version" in earlier["manuscript"]
    numbers = [number for equation in earlier["equations"] for number in _equation_numbers(equation["equation_id"])]
    assert len(numbers) == len(set(numbers)), "an equation number is claimed by two entries"
    assert numbers == sorted(numbers) and max(numbers) == 16

    # Revised draft: claims cite Eq. (1)-(12) only and point back to the earlier mapping.
    revised = client.get("/api/v1/research/traceability", headers=headers).json()
    assert "Revised" in revised["manuscript"] and "Eq. 1-16" in revised["earlier_manuscript_traceability"]
    cited = {int(value) for claim in revised["claims"] for value in re.findall(r"\((\d+)\)", claim.get("equation") or "")}
    assert cited and max(cited) <= 12


@pytest.mark.skipif(not ANATOMY_MANIFEST_PATH.exists(), reason="anatomy manifest not generated in this checkout")
def test_hybrid_atlas_layers_never_claim_patient_registration(client, test_users):
    manifest = json.loads(ANATOMY_MANIFEST_PATH.read_text(encoding="utf-8"))
    hybrid = next(system for system in manifest["systems"] if system["id"] == "hybrid")
    allowed = {"ATLAS_LAYER": {"SOURCE_FRAME_SHARED"}, "ASSET_LAYER": {"BBOX_TRANSLATION_ALIGNED"}, "UNREGISTERED_COMPARISON": {"UNREGISTERED_BBOX_SCALED"}}
    for layer in hybrid["hybrid"]["layers"]:
        assert layer["registration"] in allowed[layer["kind"]], layer["id"]
        if layer["kind"] != "ATLAS_LAYER":
            caveat = (layer.get("alignment") or layer.get("transform"))["caveat"]
            assert "not" in caveat.lower(), "bounding-box alignment must state that it is not registration"
    assert any("not the patient" in limitation for limitation in hybrid["limitations"])
    systems = client.get("/api/v1/anatomy/systems", headers=get_auth_headers(test_users["clinician_a"])).json()
    assert systems["representation_level"] == "L1_GENERIC_REFERENCE"
