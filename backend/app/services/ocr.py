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
import math
import statistics
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
    # Counter-clockwise turn applied before reading a sideways page (0, 90 or -90).
    rotation_degrees: int = 0


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


# Text-detection box score threshold (the engine default is 0.5). Lines on curved or
# low-contrast photographed pages score 0.3-0.5 and were dropped whole, which joined the
# sentences around them ("...Focally at a" + "evidence of dysplasia/ malignancy." lost the
# "No" between them). Recognition still drops text read below the engine's text score.
DETECTION_BOX_THRESHOLD = 0.3
MAX_SKEW_RADIANS = math.radians(15)
# Sideways page: at least this many multi-character boxes, and this share of them, are
# SIDEWAYS_ASPECT times taller than wide.
SIDEWAYS_ASPECT = 2.0
SIDEWAYS_MIN_BOXES = 5
SIDEWAYS_FRACTION = 0.6
# The recognition model sometimes emits fullwidth punctuation ("TSH（Thyroid…）"); map the
# fullwidth ASCII block to ASCII one-for-one so lengths and offsets are unchanged.
FULLWIDTH_TO_ASCII = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}
# A row that opens in lower case after a vertical gap of at least this many text heights
# follows a line the recogniser did not return ("...Focally at a" / [lost line] / "evidence of
# dysplasia/ malignancy."). Joining across it would silently drop the lost words.
LOST_LINE_GAP = 2.0


def _page_skew(items: list[dict]) -> float:
    """Median baseline angle of the wide text boxes (radians, image y pointing down).

    A photographed page is rarely level; without this, a result printed at the right of a
    tilted page drifts into the line above or below its test name."""
    angles = []
    for item in items:
        (x0, y0), (x1, y1) = item["points"][0], item["points"][1]
        width = math.hypot(x1 - x0, y1 - y0)
        if width >= 3 * max(item["height"], 1.0):
            angles.append(math.atan2(y1 - y0, x1 - x0))
    if len(angles) < 3:
        return 0.0
    angle = statistics.median(angles)
    return angle if abs(angle) <= MAX_SKEW_RADIANS else 0.0


def _rows(detections: list) -> list[list[dict]]:
    """Groups detected text boxes into rows (top to bottom, then left to right) in
    de-skewed page coordinates."""
    items = []
    for box, text, score in detections:
        points = [(float(point[0]), float(point[1])) for point in box]
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        height = math.hypot(points[3][0] - points[0][0], points[3][1] - points[0][1]) if len(points) == 4 else max(ys) - min(ys)
        items.append({"text": text, "confidence": float(score), "box": [min(xs), min(ys), max(xs), max(ys)],
                      "points": points if len(points) == 4 else [(min(xs), min(ys)), (max(xs), min(ys))], "height": height,
                      "cx": sum(xs) / len(xs), "cy": sum(ys) / len(ys)})
    angle = _page_skew(items)
    cos, sin = math.cos(angle), math.sin(angle)
    for item in items:
        # Rotate by -angle: points on one tilted baseline share the same level coordinate.
        item["level"] = -sin * item["cx"] + cos * item["cy"]
        item["along"] = cos * item["cx"] + sin * item["cy"]
    items.sort(key=lambda item: item["level"])
    rows: list[list[dict]] = []
    for item in items:
        if rows:
            last = rows[-1]
            last_level = sum(cell["level"] for cell in last) / len(last)
            last_height = max(cell["height"] for cell in last)
            if abs(item["level"] - last_level) <= 0.5 * max(item["height"], last_height):
                last.append(item)
                continue
        rows.append([item])
    for row in rows:
        row.sort(key=lambda cell: cell["along"])
    return rows


def _reading_order(detections: list) -> list[dict]:
    """Text lines in reading order; reported boxes stay in source pixels. A line that opens in
    lower case after a gap of LOST_LINE_GAP text heights is marked ``gap_before`` and the page
    text keeps a blank line before it."""
    lines = []
    text_cursor = 0
    previous: Optional[tuple[float, float]] = None
    for row in _rows(detections):
        line_text = " ".join(cell["text"] for cell in row).translate(FULLWIDTH_TO_ASCII)
        level = sum(cell["level"] for cell in row) / len(row)
        height = max(cell["height"] for cell in row)
        gap_before = (previous is not None and line_text[:1].islower()
                      and level - previous[0] >= LOST_LINE_GAP * max(height, previous[1]))
        if gap_before:
            text_cursor += 1
        lines.append({
            "text": line_text,
            "text_start": text_cursor,
            "text_end": text_cursor + len(line_text),
            "confidence": min(cell["confidence"] for cell in row),
            "box": [min(c["box"][0] for c in row), min(c["box"][1] for c in row), max(c["box"][2] for c in row), max(c["box"][3] for c in row)],
            **({"gap_before": True} if gap_before else {}),
        })
        text_cursor += len(line_text) + 1
        previous = (level, height)
    return lines


def page_text(lines: list[dict]) -> str:
    return "\n".join(("\n" if line.get("gap_before") else "") + line["text"] for line in lines)


def _sideways(detections: list) -> bool:
    """A page photographed lying on its side: most boxes holding a few characters or more are
    at least twice as tall as they are wide."""
    tall = total = 0
    for box, text, _score in detections:
        if len(box) != 4 or len(str(text).strip()) < 4:
            continue
        (x0, y0), (x1, y1), _, (x3, y3) = box
        total += 1
        tall += math.hypot(x3 - x0, y3 - y0) >= SIDEWAYS_ASPECT * math.hypot(x1 - x0, y1 - y0)
    return tall >= SIDEWAYS_MIN_BOXES and tall >= SIDEWAYS_FRACTION * total


def _read_confidence(detections: list) -> float:
    """Character-weighted recognition score."""
    characters = sum(len(str(text)) for _box, text, _score in detections)
    return sum(len(str(text)) * float(score) for _box, text, score in detections) / characters if characters else 0.0


def _unrotate_box(box: list[float], turns: int, width: int, height: int) -> list[float]:
    """Map an axis-aligned box from the image turned by ``numpy.rot90(image, turns)`` back to
    the page as rendered."""
    x0, y0, x1, y1 = box
    if turns == 1:  # rotated[r, c] = page[c, width - r]
        xs, ys = (width - y0, width - y1), (x0, x1)
    else:  # turns == -1: rotated[r, c] = page[height - c, r]
        xs, ys = (y0, y1), (height - x0, height - x1)
    return [min(xs), min(ys), max(xs), max(ys)]


def ocr_image(image) -> OcrPage:
    """OCR one PIL image. A sideways page is read turned upright; reported boxes stay in the
    pixels of the image as given."""
    import numpy as np

    array = np.asarray(image.convert("RGB"))
    height, width = int(array.shape[0]), int(array.shape[1])
    turns = 0
    with _lock:  # the ONNX sessions are shared; serialise calls
        detections, _elapsed = _engine()(array, box_thresh=DETECTION_BOX_THRESHOLD)
        if detections and _sideways(detections):
            # Turn both ways and read without the 180-degree classifier: the upright turn reads
            # with clearly higher confidence than the upside-down one.
            readings = []
            for candidate in (1, -1):
                found, _ = _engine()(np.ascontiguousarray(np.rot90(array, candidate)), use_cls=False, box_thresh=DETECTION_BOX_THRESHOLD)
                readings.append((_read_confidence(found or []), candidate, found or []))
            confidence, candidate, found = max(readings, key=lambda reading: reading[0])
            if confidence > _read_confidence(detections):
                turns, detections = candidate, found
    lines = _reading_order(detections or [])
    if turns:
        for line in lines:
            line["box"] = _unrotate_box(line["box"], turns, width, height)
    confidences = [line["confidence"] for line in lines]
    return OcrPage(
        text=page_text(lines),
        engine=engine_version() or ENGINE_NAME,
        line_count=len(lines),
        mean_confidence=round(sum(confidences) / len(confidences), 4) if confidences else None,
        image_width=width,
        image_height=height,
        lines=[{**line, "box": [round(value, 1) for value in line["box"]]} for line in lines],
        rotation_degrees=90 * turns,
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
