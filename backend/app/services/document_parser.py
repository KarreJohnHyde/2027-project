"""
Document Parser Service for MedTwin.
Extracts text from multi-format clinical reports:
- Plain Text (.txt, .md)
- JSON (.json)
- Tabular CSV (.csv)
- Microsoft Word (.docx) via native zip/xml extraction
- Adobe PDF (.pdf) via native object stream extraction
"""

import csv
import io
import json
from pathlib import Path
from typing import Optional


def extract_text_from_txt(content_bytes: bytes) -> str:
    """Decodes plain text with UTF-8 and Latin-1 fallback."""
    try:
        return content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return content_bytes.decode("latin-1", errors="replace")


def extract_text_from_json(content_bytes: bytes) -> str:
    """Parses JSON report format and structures into text."""
    try:
        text = content_bytes.decode("utf-8", errors="replace")
        data = json.loads(text)
        
        if isinstance(data, str):
            return data
            
        lines = []
        if isinstance(data, dict):
            # Prioritize standard clinical report fields
            if "title" in data:
                lines.append(f"REPORT TITLE: {data['title']}")
            if "patient_id" in data or "patient_ref" in data:
                lines.append(f"PATIENT: {data.get('patient_id') or data.get('patient_ref')}")
            if "indication" in data or "clinical_indication" in data:
                lines.append(f"CLINICAL INDICATION: {data.get('indication') or data.get('clinical_indication')}")
            if "technique" in data:
                lines.append(f"TECHNIQUE: {data['technique']}")
            if "findings" in data:
                lines.append(f"FINDINGS: {data['findings']}")
            if "impression" in data or "impressions" in data:
                lines.append(f"IMPRESSION: {data.get('impression') or data.get('impressions')}")
            if "vitals" in data and isinstance(data["vitals"], dict):
                vitals_str = ", ".join(f"{k}: {v}" for k, v in data["vitals"].items())
                lines.append(f"VITAL SIGNS: {vitals_str}")
            if "labs" in data and isinstance(data["labs"], dict):
                labs_str = ", ".join(f"{k}: {v}" for k, v in data["labs"].items())
                lines.append(f"LABORATORY METRICS: {labs_str}")
            if "notes" in data:
                lines.append(f"NOTES: {data['notes']}")
                
            # If standard keys not found, serialize key-values cleanly
            if not lines:
                for k, v in data.items():
                    lines.append(f"{k.upper()}: {v}")
        elif isinstance(data, list):
            for item in data:
                lines.append(str(item))
                
        return "\n".join(lines)
    except Exception as e:
        return extract_text_from_txt(content_bytes)


MAX_CSV_ROWS = 5000


def _single_line_csv_cell(value: str) -> str:
    """Keep one rendered line per logical CSV row.

    RFC CSV permits CR/LF inside quoted fields. The parser must preserve that
    field as one value instead of treating it as another record, while the
    existing text contract renders each record on one line.
    """

    return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ").strip()


def extract_text_from_csv(content_bytes: bytes) -> str:
    """Formats RFC-style CSV data into bounded, structured clinical text.

    Quoted delimiters, escaped quotes and quoted newlines are delegated to the
    standard-library CSV parser. Uneven records retain every supplied value;
    extra values use the historical ``ColN`` label rather than being dropped.
    """

    raw = extract_text_from_txt(content_bytes).strip()
    if not raw:
        return ""
    if "\x00" in raw:
        raise ValueError("Invalid CSV document: NUL bytes are not supported.")

    try:
        reader = csv.reader(io.StringIO(raw, newline=""), dialect="excel", strict=True)
        header_row = next(reader, None)
        if header_row is None:
            return ""
        # UTF-8 CSV exports commonly prefix the first cell with a BOM.
        if header_row:
            header_row[0] = header_row[0].lstrip("\ufeff")
        header = [_single_line_csv_cell(value) for value in header_row]

        rendered_rows: list[str] = []
        row_count = 0
        for row in reader:
            row_count += 1
            if row_count > MAX_CSV_ROWS:
                continue
            # csv.reader represents a blank record as []; split(",") previously
            # represented it as one empty value, so retain that output contract.
            cells = row or [""]
            item_parts = [
                f"{header[index] if index < len(header) else f'Col{index}'}: {_single_line_csv_cell(value)}"
                for index, value in enumerate(cells)
            ]
            rendered_rows.append(" | ".join(item_parts))
    except csv.Error as exc:
        raise ValueError(f"Invalid or unsupported CSV document: {exc}") from exc

    formatted = [f"CLINICAL TABULAR REPORT ({row_count} rows):", *rendered_rows]
    if row_count > MAX_CSV_ROWS:
        formatted.append(f"[Truncated after {MAX_CSV_ROWS} rows]")
    return "\n".join(formatted)


def extract_text_from_docx(content_bytes: bytes) -> str:
    """Extract paragraphs and table cells with python-docx."""
    try:
        from docx import Document

        document = Document(io.BytesIO(content_bytes))
        lines = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))
        return "\n".join(lines)
    except Exception as exc:
        raise ValueError(f"Invalid or unsupported DOCX document: {exc}") from exc


# A page with fewer embedded characters than this is treated as scanned.
MIN_EMBEDDED_CHARACTERS = 20


def extract_pdf_document(content_bytes: bytes) -> tuple[list[str], list[dict]]:
    """Per-page text and provenance. Embedded text is used when present; a page
    without it is rendered and read by local OCR (app.services.ocr)."""
    from app.services import ocr

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content_bytes))
        embedded = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise ValueError(f"Invalid or unsupported PDF document: {exc}") from exc
    pages: list[str] = []
    meta: list[dict] = []
    available = ocr.ocr_available()
    for index, text in enumerate(embedded):
        if len(text.strip()) >= MIN_EMBEDDED_CHARACTERS:
            pages.append(text)
            meta.append({"page": index + 1, "method": "EMBEDDED_TEXT"})
        elif available:
            result = ocr.ocr_pdf_page(content_bytes, index)
            pages.append(result.text)
            meta.append({"page": index + 1, "method": "OCR" if result.text.strip() else "OCR_NO_TEXT", "engine": result.engine,
                         "line_count": result.line_count, "mean_confidence": result.mean_confidence, "dpi": ocr.OCR_DPI,
                         "coordinate_space": "RENDERED_PAGE_PIXELS_TOP_LEFT",
                         "image_width": result.image_width, "image_height": result.image_height,
                         "rotation_degrees": result.rotation_degrees,
                         # Text is retained only until de-identification maps each line
                         # to the sanitized page. It is removed before API/database output.
                         "lines": result.lines})
        else:
            pages.append(text)
            meta.append({"page": index + 1, "method": "NO_EMBEDDED_TEXT_OCR_UNAVAILABLE"})
    if not "".join(pages).strip():
        if not available:
            raise ValueError("PDF contains no embedded text; OCR is not configured.")
        raise ValueError("PDF contains no readable text: no embedded text, and OCR found none.")
    return pages, meta


def extract_pages_from_pdf(content_bytes: bytes) -> list[str]:
    return extract_pdf_document(content_bytes)[0]


def extract_text_from_pdf(content_bytes: bytes) -> str:
    return "\n".join(extract_pages_from_pdf(content_bytes)).strip()


MAX_XLSX_ROWS = 5000


def extract_text_from_xlsx(content_bytes: bytes) -> str:
    """Render worksheet rows as 'Header: value' lines. Formulas are not evaluated;
    only values cached by the authoring application are read."""
    try:
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(content_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"Invalid or unsupported XLSX workbook: {exc}") from exc
    lines: list[str] = []
    try:
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            header = next(rows, None)
            if header is None:
                continue
            names = [str(cell).strip() if cell is not None else f"Column {index + 1}" for index, cell in enumerate(header)]
            lines.append(f"WORKSHEET {sheet.title}:")
            for count, row in enumerate(rows):
                if count >= MAX_XLSX_ROWS:
                    lines.append(f"[Truncated after {MAX_XLSX_ROWS} rows]")
                    break
                cells = [f"{names[index] if index < len(names) else f'Column {index + 1}'}: {value}" for index, value in enumerate(row) if value is not None]
                if cells:
                    lines.append(" | ".join(cells))
    finally:
        workbook.close()
    return "\n".join(lines)


def parse_clinical_document_pages(file_path: Path, content_bytes: Optional[bytes] = None) -> tuple[list[str], list[dict]]:
    """Page texts plus per-page provenance (method, and OCR engine/confidence where used)."""
    if content_bytes is None:
        with open(file_path, "rb") as f:
            content_bytes = f.read()
    if file_path.suffix.lower() == ".pdf":
        return extract_pdf_document(content_bytes)
    pages = parse_clinical_document_with_pages(file_path, content_bytes)
    return pages, [{"page": 1, "method": "EMBEDDED_TEXT"}]


def parse_clinical_document_with_pages(file_path: Path, content_bytes: Optional[bytes] = None) -> list[str]:
    """Parse a clinical document into page texts (a single page for non-PDF formats)."""
    if content_bytes is None:
        with open(file_path, "rb") as f:
            content_bytes = f.read()

    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return extract_pages_from_pdf(content_bytes)
    if ext in (".txt", ".md"):
        return [extract_text_from_txt(content_bytes)]
    if ext == ".json":
        from app.services.fhir_import import render_fhir_text

        rendered = render_fhir_text(content_bytes)
        return [rendered if rendered is not None else extract_text_from_json(content_bytes)]
    if ext == ".csv":
        return [extract_text_from_csv(content_bytes)]
    if ext == ".docx":
        return [extract_text_from_docx(content_bytes)]
    if ext == ".xlsx":
        return [extract_text_from_xlsx(content_bytes)]
    return [extract_text_from_txt(content_bytes)]


def parse_clinical_document(file_path: Path, content_bytes: Optional[bytes] = None) -> str:
    """
    Universal dispatcher that parses any clinical report into clean text.
    Supports .pdf, .docx, .xlsx, .json (including FHIR), .csv, .txt, .md.
    """
    return "\n".join(parse_clinical_document_with_pages(file_path, content_bytes))
