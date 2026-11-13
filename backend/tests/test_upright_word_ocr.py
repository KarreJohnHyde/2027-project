"""Opt-in word ROI constraints, authenticated source binding and review-only output."""
from datetime import datetime
import hashlib
import io
import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.database import get_db
from app.models.entities import Case, UploadedFile, ModalityType, AuditEvent, Finding
from app.routers import upright_word_ocr as route
from app.services import upright_word_ocr as service
from conftest import get_auth_headers


@pytest.fixture
def image():
    image = Image.new("RGB", (1200, 1600), "white")
    ImageDraw.Draw(image).text((112, 112), "Glucose", fill="black")
    return image


@pytest.fixture
def evaluated_runtime(monkeypatch):
    monkeypatch.setattr(service, "capability", lambda: {"available": True, "blockers": [], "provenance": {"engine": "fixture"}})
    monkeypatch.setattr(service, "_upright_read", lambda crop: [{"text": "Glucose", "confidence": .8, "box": [5., 10., 80., 40.]}])


def recognise(image, **kwargs):
    return service.recognise(image, [100, 100, 228, 228], source={"upload_id": 1}, upright_attested=True,
                             single_word_attested=True, latin_text_attested=True, **kwargs)


def test_source_boxes_are_translated_and_proposal_requires_review(image, evaluated_runtime):
    result = recognise(image)
    assert result["status"] == "AVAILABLE" and result["text_proposal"] == "Glucose"
    assert result["source_word_bbox_xyxy"] == [105., 110., 180., 140.]
    assert result["crop_to_preview_affine"] == [[1, 0, 100], [0, 1, 100], [0, 0, 1]]
    assert result["rotation_degrees"] == 0
    assert result["review_required"] and not result["persisted_finding_or_correction"] and not result["clinical_activation"]


@pytest.mark.parametrize("box", [[0, 0, 1200, 1600], [-1, 100, 128, 228], [100, 100, 101, 101], [100, 100, 1200, 112], [1.2, 100, 228, 228], [True, 100, 228, 228]])
def test_unsafe_or_non_word_rois_refuse_before_engine(image, evaluated_runtime, box):
    result = service.recognise(image, box, source={}, upright_attested=True, single_word_attested=True, latin_text_attested=True)
    assert result["status"] == "REFUSED" and result["text_proposal"] is None


def test_missing_attestation_and_runtime_mismatch_fail_closed(image, evaluated_runtime, monkeypatch):
    assert service.recognise(image, [100, 100, 228, 228], source={})["code"] == "EXPLICIT_UPRIGHT_SINGLE_LATIN_WORD_ATTESTATION_REQUIRED"
    monkeypatch.setattr(service, "capability", lambda: {"available": False, "blockers": ["MODEL_HASH_MISMATCH"]})
    assert recognise(image)["code"] == "EVALUATED_OCR_RUNTIME_UNAVAILABLE"


@pytest.mark.parametrize("lines,code", [([], "SINGLE_DETECTED_WORD_LINE_REQUIRED"),
    ([{"text": "one two", "confidence": .9, "box": [0, 0, 70, 10]}], "SINGLE_LATIN_WORD_OUTPUT_REQUIRED"),
    ([{"text": "test", "confidence": float("nan"), "box": [0, 0, 70, 10]}], "OCR_SCORE_INVALID"),
    ([{"text": "test", "confidence": .9, "box": [-1, 0, 70, 10]}], "OCR_BOX_OUTSIDE_SOURCE_ROI")])
def test_ambiguous_output_and_geometry_abstain(image, evaluated_runtime, monkeypatch, lines, code):
    monkeypatch.setattr(service, "_upright_read", lambda crop: lines)
    assert recognise(image)["code"] == code


def test_blank_or_privacy_masked_crop_abstains(image, evaluated_runtime):
    ImageDraw.Draw(image).rectangle((100, 100, 228, 228), fill="black")
    assert recognise(image)["code"] == "BLANK_OR_PRIVACY_MASKED_ROI"


@pytest.fixture
def api(db_session):
    app = FastAPI(); app.include_router(route.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as client: yield client


@pytest.fixture
def source(db_session, test_users, tmp_path, image, monkeypatch, evaluated_runtime):
    path = tmp_path / "source.pdf"; image.save(path, format="PDF", resolution=110)
    case = Case(pseudonymous_id="word-" + uuid4().hex, created_by_id=test_users["clinician_a"].id)
    db_session.add(case); db_session.flush()
    record = UploadedFile(case_id=case.id, filename="source.pdf", stored_filename="source.pdf", file_path=str(path),
                          file_hash=hashlib.sha256(path.read_bytes()).hexdigest(), file_size_bytes=path.stat().st_size,
                          mime_type="application/pdf", modality=ModalityType.REPORT)
    db_session.add(record); db_session.commit()
    monkeypatch.setattr(route.derived_text, "load", lambda digest: ("masked source", [0], [{"method": "OCR", "image_width": 3273, "image_height": 4364}]))
    def preview(*args):
        content = io.BytesIO(); image.save(content, format="PNG")
        return Response(content.getvalue(), headers={"X-MedTwin-Page": json.dumps({"width":1200,"height":1600,"masking":"NO_IDENTIFIER_LINES"})})
    monkeypatch.setattr(route, "get_report_page_image", preview)
    body = {"page": 1, "bbox_xyxy": [100, 100, 228, 228], "expected_image_size": [1200, 1600],
            "source_file_sha256": record.file_hash, "coordinate_space": "REPORT_PAGE_PREVIEW_110_DPI",
            "upright_attested": True, "single_word_attested": True, "latin_text_attested": True}
    return record, body


def test_authenticated_proposal_has_no_finding_write_or_raw_text_in_audit(api, db_session, test_users, source):
    record, body = source
    before = db_session.query(Finding).count()
    response = api.post(f"/api/v1/uploads/{record.id}/ocr/upright-word", json=body, headers=get_auth_headers(test_users["clinician_a"]))
    assert response.status_code == 200 and response.json()["status"] == "AVAILABLE"
    assert db_session.query(Finding).count() == before
    audit = db_session.query(AuditEvent).filter(AuditEvent.action == "UPRIGHT_WORD_OCR_PROPOSAL").one()
    assert "Glucose" not in json.dumps(audit.details)
    assert audit.details["source_sha256"] == record.file_hash


@pytest.mark.private_workspace
def test_route_requires_auth_and_authorized_active_source(api, db_session, test_users, source):
    record, body = source; path = f"/api/v1/uploads/{record.id}/ocr/upright-word"
    assert api.post(path, json=body).status_code == 401
    assert api.post(path, json=body, headers=get_auth_headers(test_users["clinician_b"])).status_code == 403
    record.withdrawn_at = datetime(2026, 11, 13); db_session.commit()
    assert api.post(path, json=body, headers=get_auth_headers(test_users["clinician_a"])).status_code == 409


def test_source_identity_dimensions_and_page_are_bound(api, test_users, source):
    record, body = source; path = f"/api/v1/uploads/{record.id}/ocr/upright-word"; headers=get_auth_headers(test_users["clinician_a"])
    assert api.post(path, json={**body, "source_file_sha256": "0" * 64}, headers=headers).status_code == 409
    assert api.post(path, json={**body, "expected_image_size": [1100, 1600]}, headers=headers).status_code == 409
    assert api.post(path, json={**body, "page": 2}, headers=headers).status_code == 404


def test_missing_source_context_does_not_start_whole_page_ocr(api, test_users, source, monkeypatch):
    record, body = source
    monkeypatch.setattr(route.derived_text, "load", lambda digest: None)
    response = api.post(f"/api/v1/uploads/{record.id}/ocr/upright-word", json=body, headers=get_auth_headers(test_users["clinician_a"]))
    assert response.json()["code"] == "OCR_SOURCE_CONTEXT_NOT_READY"


def test_unmasked_embedded_source_context_refuses(api, test_users, source, monkeypatch):
    record, body = source
    monkeypatch.setattr(route.derived_text, "load", lambda digest: ("text", [0], [{"method":"PDF_TEXT", "image_width":1,"image_height":1}]))
    response = api.post(f"/api/v1/uploads/{record.id}/ocr/upright-word", json=body, headers=get_auth_headers(test_users["clinician_a"]))
    assert response.json()["code"] == "SOURCE_PAGE_PRIVACY_MASKING_UNAVAILABLE"
