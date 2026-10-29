"""The third-party chest-radiograph research model: report comparison, summaries, the anatomy
input check and the endpoint's refusals. Images are synthetic; no radiograph is stored here."""

from io import BytesIO
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.services import cxr_research
from tests.conftest import get_auth_headers


def _finding(name, score):
    return {"finding": name, "score": score, "above_operating_point": score > 0.5, "weak": abs(score - 0.5) < 0.1}


def _statement(statement_id, entity, negation="AFFIRMED", experiencer="PATIENT", system="lungs", certainty="CERTAIN"):
    return SimpleNamespace(id=statement_id, entity=entity, negation=negation, experiencer=experiencer, anatomy_system=system,
                           certainty=certainty, source_span=f"Fixture {entity}.")


def test_scores_are_compared_with_what_the_reports_state():
    findings = [_finding("Fibrosis", 0.82), _finding("Effusion", 0.71), _finding("Cardiomegaly", 0.52), _finding("Pneumothorax", 0.2),
                _finding("Lung Lesion", 0.2), _finding("Hernia", 0.8)]
    statements = [_statement(1, "Honeycombing"), _statement(2, "Pleural effusion", "NEGATED"), _statement(3, "Cardiomegaly", system="heart"),
                  _statement(4, "Pneumothorax", "NEGATED"), _statement(5, "Pleural effusion", experiencer="FAMILY"),
                  _statement(6, "Lesion", system=None),  # a thyroid lesion is not a lung lesion
                  _statement(7, "Hiatal hernia", system="intestines", certainty="HYPOTHETICAL")]  # "to rule out" states nothing
    rows = {row["finding"]: row for row in cxr_research.report_comparison(findings, statements)}
    assert "Lung Lesion" not in rows and "Hernia" not in rows
    assert rows["Fibrosis"]["status"] == "AGREES" and rows["Fibrosis"]["report_entities"] == ["Honeycombing"]
    assert rows["Effusion"]["status"] == "DIFFERS" and rows["Effusion"]["report_statement_ids"] == [2]  # family history ignored
    assert rows["Cardiomegaly"]["status"] == "MODEL_INDETERMINATE"  # within the weak band
    assert rows["Pneumothorax"]["status"] == "AGREES"  # both say absent


def test_the_summary_never_calls_a_weak_score_a_finding():
    weak = [_finding("Mass", 0.55), _finding("Fibrosis", 0.51), _finding("Edema", 0.1)]
    assert cxr_research.summarise(weak).startswith("No finding clearly above its operating point; highest Mass 0.55")
    assert cxr_research.summarise([_finding("Effusion", 0.74), *weak]) == "Above the operating point: Effusion 0.74"


def test_zones_split_each_lung_into_thirds_of_its_height():
    lung = np.zeros((12, 6), dtype=bool)
    lung[3:9, 1:4] = True
    zones = cxr_research._zone_masks(lung)
    assert [int(zones[zone].sum()) for zone in cxr_research.ZONES] == [6, 6, 6]
    assert not zones["upper"][5:].any() and not zones["lower"][:7].any()


def _upload(client, headers, case_id, name, image):
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (name, buffer.getvalue(), "image/png")},
                       data={"deidentified": "true"}, headers=headers).json()


def test_the_endpoint_needs_an_attested_image_upload(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-CXR-INPUT"}, headers=headers).json()["id"]
    report = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("note.txt", b"SOFTWARE TEST FIXTURE", "text/plain")},
                         data={"deidentified": "true"}, headers=headers).json()
    assert client.post(f"/api/v1/uploads/{report['id']}/chest-radiograph-analysis", json={"attest_frontal_chest_radiograph": True},
                       headers=headers).status_code == 400
    image = _upload(client, headers, case_id, "frame.png", Image.new("L", (64, 64), 128))
    assert client.post(f"/api/v1/uploads/{image['id']}/chest-radiograph-analysis", json={}, headers=headers).status_code == 422
    card = client.get("/api/v1/chest-radiograph-model", headers=headers).json()
    assert card["model_id"] == cxr_research.MODEL_ID and card["output_status"] == cxr_research.OUTPUT_STATUS


@pytest.mark.skipif(not cxr_research.availability()["available"], reason="TorchXRayVision weights are not fetched here")
def test_an_image_without_chest_anatomy_is_refused_before_any_score(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-CXR-REFUSED"}, headers=headers).json()["id"]
    gradient = Image.fromarray(np.tile(np.linspace(0, 255, 512, dtype=np.uint8), (512, 1)))
    image = _upload(client, headers, case_id, "gradient.png", gradient)
    response = client.post(f"/api/v1/uploads/{image['id']}/chest-radiograph-analysis", json={"attest_frontal_chest_radiograph": True}, headers=headers)
    assert response.status_code == 400 and "No frontal chest anatomy was recognised" in response.json()["detail"]
    findings = client.get(f"/api/v1/cases/{case_id}/findings", headers=headers).json()
    assert not any((item.get("evidence_provenance") or {}).get("model_id") == cxr_research.MODEL_ID for item in findings)
