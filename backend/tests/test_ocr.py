"""OCR of scanned (image-only) PDF pages. The page is rendered from fixed,
non-clinical fixture text at test time; it is not a patient document."""

from io import BytesIO

import pytest

from app.services import ocr
from app.services.document_parser import extract_pdf_document
from tests.conftest import get_auth_headers

pytestmark = pytest.mark.skipif(not ocr.ocr_available(), reason="OCR dependencies are not installed")

FIXTURE_LINES = [
    "SOFTWARE TEST FIXTURE - NOT PATIENT DATA",
    "Hemoglobin 13.5 g/dL (13.0-17.0)",
    "Creatinine 1.2 mg/dL (0.7-1.3)",
]


def scanned_pdf(lines=FIXTURE_LINES) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (2480, 900), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=60)
    for row, line in enumerate(lines):
        draw.text((160, 140 + row * 140), line, fill="black", font=font)
    buffer = BytesIO()
    image.save(buffer, format="PDF", resolution=300)
    return buffer.getvalue()


def test_scanned_page_is_read_with_page_level_provenance():
    pages, meta = extract_pdf_document(scanned_pdf())
    assert meta[0]["method"] == "OCR" and meta[0]["engine"].startswith("rapidocr-onnxruntime")
    assert meta[0]["line_count"] == 3 and meta[0]["mean_confidence"] > 0.8
    assert meta[0]["coordinate_space"] == "RENDERED_PAGE_PIXELS_TOP_LEFT"
    assert meta[0]["image_width"] > 0 and meta[0]["image_height"] > 0
    assert len(meta[0]["lines"]) == 3
    assert all(len(line["box"]) == 4 for line in meta[0]["lines"])
    text = pages[0]
    assert "Hemoglobin" in text and "13.5" in text and "1.2" in text


def test_scanned_report_values_keep_decimals_and_ocr_provenance(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-OCR"}, headers=headers).json()["id"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("scan.pdf", scanned_pdf(), "application/pdf")},
                         data={"deidentified": "true"}, headers=headers)
    assert upload.status_code == 201, upload.text
    assert client.post(f"/api/v1/uploads/{upload.json()['id']}/analysis-jobs", headers=headers).status_code == 201
    measurements = {m["name"]: m for m in client.get(f"/api/v1/cases/{case_id}/measurements", headers=headers).json()}
    assert measurements["hemoglobin"]["value"] == 13.5 and measurements["hemoglobin"]["unit"] == "g/dL"
    assert measurements["creatinine"]["value"] == 1.2
    assert {m["extraction_method"] for m in measurements.values()} == {"OCR_RULE_BASELINE"}
    assert measurements["hemoglobin"]["reference_low"] == 13.0 and measurements["hemoglobin"]["reference_high"] == 17.0
    assert len(measurements["hemoglobin"]["source_bbox"]) == 4
    assert measurements["hemoglobin"]["source_bbox_coordinate_space"] == "RENDERED_PAGE_PIXELS_TOP_LEFT"
    assert measurements["hemoglobin"]["source_image_width"] > 0
    assert measurements["hemoglobin"]["source_image_height"] > 0
    text = client.get(f"/api/v1/uploads/{upload.json()['id']}/text", headers=headers).json()
    assert text["pages"][0]["method"] == "OCR"
    assert text["pages"][0]["lines"]
    assert all("text" not in line and len(line["bbox_xyxy"]) == 4 for line in text["pages"][0]["lines"])
