"""Page document types, the cached reading of a report, masked page images and parallel OCR.
Every page is rendered here from invented, non-clinical fixture text."""

from io import BytesIO

import pytest

from app.services import derived_text, ocr, upload_store
from app.services.page_classifier import (
    BILLING,
    DISCHARGE_SUMMARY,
    IMAGING_REPORT,
    LABORATORY_REPORT,
    PATHOLOGY_REPORT,
    PRESCRIPTION,
    PROCEDURE_REPORT,
    UNCLASSIFIED,
    classify_page,
    classify_pages,
)
from app.services.storage_crypto import generate_key, is_encrypted
from tests.conftest import get_auth_headers

LAB_PAGE = "BIOCHEMISTRY\nTest Name Result Units Bio. Ref. Range\nSerum Creatinine 1.29 mg/dL 0.55-1.02\nHaemoglobin 12.1 g/dL 12.0-15.0"
ULTRASOUND_PAGE = "ULTRASONOGRAPHY OF ABDOMEN\nLIVER: Normal in size and shows increased echotexture.\nNo calculus is seen.\nIMPRESSION: Grade I fatty liver."
CT_PAGE = "CECT - CHEST\nFINDINGS:\nFew reticular opacities in both lower lobes. No pleural effusion.\n(P.T.O)"
CT_IMPRESSION_PAGE = "IMPRESSION:\nBILATERAL LOWER LOBE RETICULAR OPACITIES.\nFEW SUBCENTIMETRIC MEDIASTINAL LYMPH NODES."


@pytest.mark.parametrize(
    "text, kind",
    [
        (LAB_PAGE, LABORATORY_REPORT),
        (ULTRASOUND_PAGE, IMAGING_REPORT),
        ("HISTOPATHOLOGY REPORT\nNature of specimen: colonic biopsy\nGross description: received in formalin\nMicroscopic description: sections show", PATHOLOGY_REPORT),
        ("COLONOSCOPY REPORT\nScope was introduced up to the caecum. Mucosa of the rectum is normal.\nBiopsies taken.", PROCEDURE_REPORT),
        ("DISCHARGE SUMMARY\nDate of admission: 01-02-2026 Date of discharge: 05-02-2026\nCourse in hospital: uneventful", DISCHARGE_SUMMARY),
        ("Rx\nTab. Paracetamol 500 mg 1-0-1 x 5 days after food\nCap. Omeprazole 20 mg OD before food", PRESCRIPTION),
        ("BILL\nBill No: 123 Invoice\nNet amount 1,200.00 GST 18%\nAmount paid", BILLING),
        ("Thank you", UNCLASSIFIED),
    ],
)
def test_each_page_is_typed_from_what_it_prints(text, kind):
    result = classify_page(text)
    assert result["document_type"] == kind
    assert (result["cues"] != []) == (kind != UNCLASSIFIED)


def test_imaging_modality_and_a_continued_page():
    pages = classify_pages([LAB_PAGE, ULTRASOUND_PAGE, CT_PAGE, CT_IMPRESSION_PAGE])
    assert [page["document_type"] for page in pages] == [LABORATORY_REPORT, IMAGING_REPORT, IMAGING_REPORT, IMAGING_REPORT]
    assert [page["imaging_modality"] for page in pages] == [None, "ULTRASOUND", "CT", "CT"]
    # The impression page names no modality; it continues the CT page that ended "(P.T.O)".
    assert pages[3]["continued_from_page"] == 3 and "continued_from_page" not in pages[2]


def _report_case(client, headers, pseudonym, filename, content, mime):
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": pseudonym}, headers=headers).json()["id"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (filename, content, mime)},
                         data={"deidentified": "true"}, headers=headers).json()
    assert client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=headers).status_code == 201
    return case_id, upload


def test_the_analysis_reading_is_cached_typed_and_erased_with_the_upload(client, test_users, monkeypatch):
    headers = get_auth_headers(test_users["clinician_a"])
    report = ("SOFTWARE TEST FIXTURE\n" + LAB_PAGE).encode("utf-8")
    case_id, upload = _report_case(client, headers, "CASE-DERIVED-CACHE", "panel.txt", report, "text/plain")
    cached = list(derived_text.cache_dir().glob(f"{upload['file_hash']}-*.json"))
    assert len(cached) == 1

    def reread(_path):
        raise AssertionError("the document was read again instead of from the cache")

    monkeypatch.setattr("app.services.nlp_processor.prepare_report_document", reread)
    text = client.get(f"/api/v1/uploads/{upload['id']}/text", headers=headers).json()
    assert "Serum Creatinine 1.29" in text["text"]
    assert text["pages"][0]["document_type"]["document_type"] == LABORATORY_REPORT

    assert client.delete(f"/api/v1/cases/{case_id}", headers=headers).status_code == 204
    assert not cached[0].exists()


def test_the_cache_is_encrypted_when_a_storage_key_is_configured(client, test_users, monkeypatch):
    monkeypatch.setenv("MEDTWIN_STORAGE_KEYS", generate_key())
    monkeypatch.setenv("MEDTWIN_STORAGE_ENCRYPTION", "required")
    upload_store.reset()
    try:
        headers = get_auth_headers(test_users["clinician_a"])
        report = ("SOFTWARE TEST FIXTURE ENCRYPTED\n" + LAB_PAGE).encode("utf-8")
        _case_id, upload = _report_case(client, headers, "CASE-DERIVED-ENCRYPTED", "panel-enc.txt", report, "text/plain")
        [cached] = derived_text.cache_dir().glob(f"{upload['file_hash']}-*.json")
        assert is_encrypted(cached)
        assert derived_text.load(upload["file_hash"])[0].startswith("SOFTWARE TEST FIXTURE ENCRYPTED")
    finally:
        upload_store.reset()


def _scanned_pdf(pages: list[list[str]]) -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default(size=60)
    images = []
    for lines in pages:
        image = Image.new("RGB", (2480, 1100), "white")
        draw = ImageDraw.Draw(image)
        for row, line in enumerate(lines):
            draw.text((160, 140 + row * 140), line, fill="black", font=font)
        images.append(image)
    buffer = BytesIO()
    images[0].save(buffer, format="PDF", resolution=300, save_all=True, append_images=images[1:])
    return buffer.getvalue()


@pytest.mark.skipif(not ocr.ocr_available(), reason="OCR dependencies are not installed")
def test_page_images_paint_out_the_lines_that_held_identifiers(client, test_users):
    from PIL import Image

    headers = get_auth_headers(test_users["clinician_a"])
    pdf = _scanned_pdf([["SOFTWARE TEST FIXTURE - NOT PATIENT DATA", "Patient Name : JOHN EXAMPLE", "Hemoglobin 13.5 g/dL (13.0-17.0)"]])
    _case_id, upload = _report_case(client, headers, "CASE-PAGE-IMAGE", "scan.pdf", pdf, "application/pdf")
    text = client.get(f"/api/v1/uploads/{upload['id']}/text", headers=headers).json()
    page = text["pages"][0]
    [masked_line] = [line for line in page["lines"] if line["identifiers_masked"]]
    assert "JOHN" not in text["text"] and "[REDACTED_NAME]" in text["text"]

    response = client.get(f"/api/v1/uploads/{upload['id']}/pages/1/image", headers=headers)
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert '"masking":"APPLIED"' in response.headers["x-medtwin-page"]
    image = Image.open(BytesIO(response.content)).convert("L")
    scale = image.width / page["image_width"]
    x0, y0, x1, y1 = (value * scale for value in masked_line["bbox_xyxy"])
    assert image.getpixel((int((x0 + x1) / 2), int((y0 + y1) / 2))) < 16  # painted black
    assert client.get(f"/api/v1/uploads/{upload['id']}/pages/2/image", headers=headers).status_code == 404


def test_reports_without_pages_have_no_page_image(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    _case_id, upload = _report_case(client, headers, "CASE-NO-PAGE-IMAGE", "note.txt", b"SOFTWARE TEST FIXTURE\nNo pleural effusion.", "text/plain")
    assert client.get(f"/api/v1/uploads/{upload['id']}/pages/1/image", headers=headers).status_code == 422


@pytest.mark.skipif(not ocr.ocr_available(), reason="OCR dependencies are not installed")
def test_pages_read_in_parallel_come_back_in_page_order():
    pdf = _scanned_pdf([[f"SOFTWARE TEST FIXTURE PAGE {number}", f"Creatinine {number}.1 mg/dL (0.7-1.3)"] for number in range(1, 5)])
    parallel = ocr.ocr_pdf_pages(pdf, [3, 0, 2, 1])
    assert [f"Creatinine {number}.1" in page.text for number, page in zip((4, 1, 3, 2), parallel)] == [True] * 4
    assert [page.text for page in parallel] == [ocr.ocr_pdf_page(pdf, index).text for index in (3, 0, 2, 1)]
