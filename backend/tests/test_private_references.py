"""Synthetic fixtures only: privacy must hold even in shared workspace mode."""
import io
import json
from pathlib import Path

import pytest
from PIL import Image
from fastapi import HTTPException

from app.services import private_references as store
from app.services.ocr import OcrPage
from app.services.storage_crypto import is_encrypted
from conftest import get_auth_headers


@pytest.fixture
def packet(tmp_path, monkeypatch, test_users):
    monkeypatch.setenv("MEDTWIN_PRIVATE_REFERENCE_DIR", str(tmp_path / "vault"))
    monkeypatch.setenv("MEDTWIN_PRIVATE_REFERENCE_KEY_FILE", str(tmp_path / "keys" / "local.json"))
    monkeypatch.setattr("app.services.ocr.ocr_image", lambda image: OcrPage("SYNTHETIC PRIVATE TEXT", "synthetic-test", 1, .5, 20, 20))
    image_path = tmp_path / "synthetic.png"
    Image.new("RGB", (20, 20), "white").save(image_path)
    definition = {"import_key": "synthetic-v1", "title": "Synthetic private reference", "summary": "Test only.",
                  "sources": [{"id": "doc1", "path": str(image_path), "label": "Synthetic source"}],
                  "facts": [{"title": "Example", "text": "SYNTHETIC FINDING", "refs": [{"source": "doc1", "page": 1}]}],
                  "model_outputs": [{"status": "ABSTAIN"}]}
    owner = test_users["clinician_a"]
    study_id = store.import_packet(owner, definition)
    return owner, study_id, definition


def test_encrypted_roundtrip_and_fixed_trust(packet):
    owner, study_id, _ = packet
    report = store.load(owner, study_id)
    assert report["trust"]["ground_truth"] is False
    assert report["trust"]["training_eligible"] is False
    assert report["trust"]["clinical_review"] == "NOT_REVIEWED"
    assert report["sources"][0]["pages"][0]["ocr"]["text"] == "SYNTHETIC PRIVATE TEXT"
    for path in store.packet_dir(owner, study_id).iterdir():
        assert is_encrypted(path)
        assert b"SYNTHETIC" not in path.read_bytes()
    image, mime = store.asset(owner, study_id, "doc1_page_1")
    assert mime == "image/png"
    assert Image.open(io.BytesIO(image)).size == (20, 20)


def test_owner_only_even_for_admin_and_shared_workspace(client, packet, test_users):
    owner, study_id, _ = packet
    base = f"/api/v1/private-references/{study_id}"
    assert client.get(base).status_code == 401
    for other in (test_users["clinician_b"], test_users["admin"]):
        headers = get_auth_headers(other)
        assert client.get("/api/v1/private-references", headers=headers).json() == []
        assert client.get(base, headers=headers).status_code == 404
        assert client.get(base + "/assets/doc1_original", headers=headers).status_code == 404
        assert client.delete(base, headers=headers).status_code == 404
    headers = get_auth_headers(owner)
    response = client.get(base, headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert "owner" not in response.json() and "assets" not in response.json()
    assert "path" not in response.json()["sources"][0]
    assert client.get(base + "/assets/doc1_original", headers=headers).status_code == 200
    assert client.get(base + "/assets/not_listed", headers=headers).status_code == 404


def test_no_overwrite_and_no_fabricated_predictions(packet):
    owner, _, definition = packet
    with pytest.raises(ValueError, match="already exists"):
        store.import_packet(owner, definition)
    definition["import_key"] = "synthetic-v2"
    definition["model_outputs"] = [{"status": "COMPLETED"}]
    with pytest.raises(ValueError, match="manufacture"):
        store.import_packet(owner, definition)
    definition["model_outputs"] = []
    definition["insights"] = [{"links": [{"url": "javascript:alert(1)"}]}]
    with pytest.raises(ValueError, match="HTTPS"):
        store.import_packet(owner, definition)


def test_tamper_and_plaintext_refused(packet):
    owner, study_id, _ = packet
    page = store.packet_dir(owner, study_id) / "doc1_page_1.enc"
    content = bytearray(page.read_bytes()); content[-1] ^= 1; page.write_bytes(content)
    with pytest.raises(HTTPException) as failure:
        store.asset(owner, study_id, "doc1_page_1")
    assert failure.value.status_code == 503
    report = store.packet_dir(owner, study_id) / "report.enc"
    report.write_text(json.dumps({"owner": store.binding(owner)}))
    with pytest.raises(HTTPException) as failure:
        store.load(owner, study_id)
    assert failure.value.status_code == 503


def test_invalid_refs_cleanup_and_owner_binding(packet):
    owner, study_id, definition = packet
    definition["import_key"] = "invalid-page"
    definition["facts"][0]["refs"][0]["page"] = 2
    with pytest.raises(ValueError, match="beyond"):
        store.import_packet(owner, definition)
    assert len(store.listing(owner)) == 1
    original_username = owner.username
    owner.username = "different-account"
    try:
        with pytest.raises(HTTPException) as failure:
            store.load(owner, study_id)
        assert failure.value.status_code == 404
    finally:
        owner.username = original_username


def test_scoped_erasure_and_invalid_id(packet, tmp_path):
    owner, study_id, _ = packet
    sentinel = tmp_path / "keep.txt"; sentinel.write_text("keep")
    with pytest.raises(HTTPException):
        store.erase(owner, "../keep.txt")
    store.erase(owner, study_id)
    assert store.listing(owner) == []
    assert sentinel.read_text() == "keep"
