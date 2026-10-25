"""Local OCR for scanned document pages.

Engine: RapidOCR (PP-OCR detection/recognition models in ONNX, bundled in the
rapidocr-onnxruntime wheel) on onnxruntime CPU. Pages are rendered with pypdfium2.
Nothing leaves the host. Each page reports the engine, line count and mean line
confidence so reviewers can see which text was machine-read.

OCR text quality has not been evaluated on annotated scanned clinical reports;
values read from OCR pages are labelled OCR_RULE_BASELINE and require review.
"""

from __future__ import annotations

import io
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

OCR_DPI = 300
ENGINE_NAME = "rapidocr-onnxruntime"


@dataclass
class OcrPage:
    text: str
    engine: str
    line_count: int
    mean_confidence: Optional[float]
    image_width: int
    image_height: int
    lines: list[dict] = field(default_factory=list)


@lru_cache(maxsize=1)
def engine_version() -> Optional[str]:
    try:
        from importlib.metadata import version

        return f"{ENGINE_NAME} {version('rapidocr-onnxruntime')}"
    except Exception:  # noqa: BLE001 - absence is a reported capability state
        return None


def ocr_available() -> bool:
    try:
        import pypdfium2  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


_lock = threading.Lock()


@lru_cache(maxsize=1)
def _engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _reading_order(detections: list) -> list[dict]:
    """Groups detected text boxes into lines (top to bottom, then left to right)."""
    items = []
    for box, text, score in detections:
        xs = [point[0] for point in box]
        ys = [point[1] for point in box]
        items.append({"text": text, "confidence": float(score), "box": [min(xs), min(ys), max(xs), max(ys)]})
    items.sort(key=lambda item: (item["box"][1] + item["box"][3]) / 2)
    rows: list[list[dict]] = []
    for item in items:
        center = (item["box"][1] + item["box"][3]) / 2
        height = item["box"][3] - item["box"][1]
        if rows:
            last = rows[-1]
            last_center = sum((cell["box"][1] + cell["box"][3]) / 2 for cell in last) / len(last)
            last_height = max(cell["box"][3] - cell["box"][1] for cell in last)
            if abs(center - last_center) <= 0.5 * max(height, last_height):
                last.append(item)
                continue
        rows.append([item])
    lines = []
    text_cursor = 0
    for row in rows:
        row.sort(key=lambda cell: cell["box"][0])
        line_text = " ".join(cell["text"] for cell in row)
        lines.append({
            "text": line_text,
            "text_start": text_cursor,
            "text_end": text_cursor + len(line_text),
            "confidence": min(cell["confidence"] for cell in row),
            "box": [min(c["box"][0] for c in row), min(c["box"][1] for c in row), max(c["box"][2] for c in row), max(c["box"][3] for c in row)],
        })
        text_cursor += len(line_text) + 1
    return lines


def ocr_image(image) -> OcrPage:
    """OCR one PIL image."""
    import numpy as np

    array = np.asarray(image.convert("RGB"))
    with _lock:  # the ONNX sessions are shared; serialise calls
        detections, _elapsed = _engine()(array)
    lines = _reading_order(detections or [])
    confidences = [line["confidence"] for line in lines]
    return OcrPage(
        text="\n".join(line["text"] for line in lines),
        engine=engine_version() or ENGINE_NAME,
        line_count=len(lines),
        mean_confidence=round(sum(confidences) / len(confidences), 4) if confidences else None,
        image_width=int(array.shape[1]),
        image_height=int(array.shape[0]),
        lines=[{**line, "box": [round(value, 1) for value in line["box"]]} for line in lines],
    )


def ocr_pdf_page(content_bytes: bytes, index: int, dpi: int = OCR_DPI) -> OcrPage:
    import pypdfium2

    document = pypdfium2.PdfDocument(io.BytesIO(content_bytes))
    try:
        page = document[index]
        image = page.render(scale=dpi / 72).to_pil()
        page.close()
    finally:
        document.close()
    return ocr_image(image)
