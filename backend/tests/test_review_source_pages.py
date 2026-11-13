"""Source verification needs page 1 even for a one-page PDF or OCR image."""
import pytest

from app.services import derived_text, nlp_processor


@pytest.mark.parametrize("suffix,method,page", [(".pdf", "EMBEDDED_TEXT", 1), (".png", "OCR", 1), (".txt", "TEXT", None)])
def test_single_page_measurements_keep_container_page_identity(monkeypatch, tmp_path, suffix, method, page):
    text = "Hemoglobin 12.4 g/dL (12.0-16.0)."
    path = tmp_path / ("synthetic" + suffix)
    path.write_bytes(b"synthetic; decoded text supplied by controlled reader")
    metadata = [{"page": 1, "method": method, "lines": [], "coordinate_space": "RENDERED_PAGE_PIXELS_TOP_LEFT"}]
    monkeypatch.setattr(derived_text, "prepared", lambda *args: (text, [0], metadata))
    result = nlp_processor.analyze_clinical_report(path, "a" * 64)
    rows = result["measurements"]
    assert rows and rows[0]["value"] == 12.4
    assert rows[0]["source_page"] == page
    assert text[rows[0]["source_span_start"]:rows[0]["source_span_end"]] == rows[0]["source_span"]
