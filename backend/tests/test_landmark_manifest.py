"""Reviewed landmark manifests for registration: four-eyes approval, declared held-out landmarks,
and L2 only from an approved manifest. Landmarks are synthetic (a known rigid transform)."""

import numpy as np

from app.models.entities import Finding
from tests.conftest import get_auth_headers


def _finding(client, clinician):
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "LANDMARK-CASE"}, headers=clinician).json()["id"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("note.txt", b"SYNTHETIC NOTE\nLiver lesion noted.\n", "text/plain")},
                         data={"deidentified": "true"}, headers=clinician).json()
    assert client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=clinician).status_code == 201
    return case_id


def _pairs(points, offset=0.0, seed=0):
    rng = np.random.default_rng(seed)
    angle = np.radians(30)
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    targets = points @ rotation.T + np.array([12.0, -4.0, 30.0]) + rng.normal(scale=0.2, size=points.shape)
    targets[:, 0] += offset
    return [{"source": [float(v) for v in s], "target": [float(v) for v in t]} for s, t in zip(points, targets)]


FIT = np.array([[0, 0, 0], [40, 0, 0], [0, 35, 0], [0, 0, 30], [25, 20, 10], [-15, 10, 20]], dtype=float)
HELD_OUT = np.array([[10, 10, 5], [-20, 5, 15], [30, -10, 8]], dtype=float)


def test_only_an_independently_approved_manifest_promotes_a_finding(client, db_session, test_users):
    owner, second = get_auth_headers(test_users["clinician_a"]), get_auth_headers(test_users["clinician_b"])
    case_id = _finding(client, owner)
    client.post(f"/api/v1/cases/{case_id}/members", json={"username": "clinician_b", "role": "EDITOR"}, headers=owner)
    finding = db_session.query(Finding).filter(Finding.case_id == case_id).first()
    body = {"coordinate_frame": "CT_LPS_mm_to_Atlas_mm", "requested_region": "liver", "fit_pairs": _pairs(FIT), "held_out_pairs": _pairs(HELD_OUT, seed=1),
            "threshold_mm": 3.0}
    proposed = client.post(f"/api/v1/findings/{finding.id}/landmark-manifests", json=body, headers=owner)
    assert proposed.status_code == 201, proposed.text
    manifest = proposed.json()
    assert (manifest["status"], manifest["fit_pairs"], manifest["held_out_pairs"]) == ("PROPOSED", 6, 3)

    gate = f"/api/v1/findings/{finding.id}/registration-gate"
    assert client.post(gate, json={"finding_id": finding.id, "manifest_id": manifest["id"]}, headers=owner).status_code == 409
    assert client.post(f"/api/v1/landmark-manifests/{manifest['id']}/decision", json={"decision": "APPROVED"}, headers=owner).status_code == 403
    approved = client.post(f"/api/v1/landmark-manifests/{manifest['id']}/decision", json={"decision": "APPROVED"}, headers=second)
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    result = client.post(gate, json={"finding_id": finding.id, "manifest_id": manifest["id"]}, headers=owner).json()
    assert result["passed_gate"] is True and result["representation_level"] == "L2" and result["assigned_region"] == "liver"
    assert result["held_out_landmarks_count"] == 3 and result["tre_error"] < 1.0

    # Held-out landmarks that disagree with the fit (20 mm off) keep the finding at L1.
    body["held_out_pairs"] = _pairs(HELD_OUT, offset=20.0, seed=1)
    bad = client.post(f"/api/v1/findings/{finding.id}/landmark-manifests", json=body, headers=owner).json()
    client.post(f"/api/v1/landmark-manifests/{bad['id']}/decision", json={"decision": "APPROVED"}, headers=second)
    failed = client.post(gate, json={"finding_id": finding.id, "manifest_id": bad["id"]}, headers=owner).json()
    assert failed["passed_gate"] is False and failed["representation_level"] == "L1" and failed["assigned_region"] is None

    # Raw coordinates, however accurate, never promote.
    raw = _pairs(np.vstack([FIT, HELD_OUT]))
    unreviewed = client.post(gate, json={"finding_id": finding.id, "landmarks_source": [p["source"] for p in raw],
                                         "landmarks_target": [p["target"] for p in raw], "threshold_mm": 3.0}, headers=owner).json()
    assert unreviewed["passed_gate"] is False and unreviewed["representation_level"] == "L1"


def test_manifests_are_validated_before_review(client, db_session, test_users):
    owner = get_auth_headers(test_users["clinician_a"])
    case_id = _finding(client, owner)
    finding = db_session.query(Finding).filter(Finding.case_id == case_id).first()
    url = f"/api/v1/findings/{finding.id}/landmark-manifests"
    collinear = np.array([[0, 0, 0], [10, 0, 0], [20, 0, 0], [30, 0, 0]], dtype=float)
    base = {"coordinate_frame": "CT_LPS_mm_to_Atlas_mm", "requested_region": "liver", "threshold_mm": 3.0}
    assert client.post(url, json={**base, "fit_pairs": _pairs(collinear), "held_out_pairs": _pairs(HELD_OUT)}, headers=owner).status_code == 422
    repeated = _pairs(FIT)
    assert client.post(url, json={**base, "fit_pairs": repeated, "held_out_pairs": repeated[:1]}, headers=owner).status_code == 422
