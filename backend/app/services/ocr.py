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
import os
import re
import statistics
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
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
    # Counter-clockwise turn applied before reading a sideways or upside-down page (0, 90, -90 or 180).
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


# Recognition takes most of the time on a page (long table lines), and one engine does not use
# the cores well on it, so the pages of a document are read in parallel: OCR runs only on these
# worker threads, each with its own engine and about three cores. Measured on a 16-core
# machine, five photographed pages took 26 s on one engine and 17 s on five.
OCR_WORKERS = max(1, min(6, (os.cpu_count() or 1) // 3))
OCR_THREADS_PER_ENGINE = max(1, (os.cpu_count() or 1) // OCR_WORKERS)
_WORKER_PREFIX = "medtwin-ocr"
# PDFium is not thread-safe; every render in the process takes this lock.
PDFIUM_LOCK = threading.Lock()
_pool: Optional[ThreadPoolExecutor] = None
_pool_lock = threading.Lock()
_local = threading.local()


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=OCR_WORKERS, thread_name_prefix=_WORKER_PREFIX)
        return _pool


def _engine():
    """This worker thread's engine (an ONNX session serves one call at a time)."""
    engine = getattr(_local, "engine", None)
    if engine is None:
        from rapidocr_onnxruntime import RapidOCR

        engine = _local.engine = RapidOCR(intra_op_num_threads=OCR_THREADS_PER_ENGINE)
    return engine


def _on_worker() -> bool:
    return threading.current_thread().name.startswith(_WORKER_PREFIX)


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
# Upright photographed report pages read at 0.89-0.95 character-weighted confidence; a page
# below this is also read turned 180 degrees and the more confident reading is kept.
UPSIDE_DOWN_CHECK_BELOW = 0.85
# The recognition model sometimes emits fullwidth punctuation ("TSH（Thyroid…）"); map the
# fullwidth ASCII block to ASCII one-for-one so lengths and offsets are unchanged.
FULLWIDTH_TO_ASCII = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)}
# A row that opens in lower case after a vertical gap of at least this many text heights
# follows a line the recogniser did not return ("...Focally at a" / [lost line] / "evidence of
# dysplasia/ malignancy."). Joining across it would silently drop the lost words.
LOST_LINE_GAP = 2.0
# Denominators that print on their own line under a wrapped unit; "PL" is µL read as P.
UNIT_TAIL = re.compile(r"[µμuUpP][lL]|[cC]umm|mm3|[dD]?[lL]")


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
    return _join_wrapped_units(rows)


def _join_wrapped_units(rows: list[list[dict]]) -> list[list[dict]]:
    """A unit wrapped under its own column ("millioncells/" over "µL") is one token: a row
    holding only a unit tail is appended to the cell above that ends in "/" and overlaps it
    horizontally. The joined text is the two readings concatenated, nothing more."""
    joined: list[list[dict]] = []
    for row in rows:
        if joined and len(row) == 1 and UNIT_TAIL.fullmatch(row[0]["text"].strip()):
            tail = row[0]
            head = next((cell for cell in joined[-1] if cell["text"].endswith("/")
                         and cell["box"][0] <= tail["box"][2] and tail["box"][0] <= cell["box"][2]), None)
            if head is not None:
                head["text"] += tail["text"].strip()
                head["box"] = [min(head["box"][0], tail["box"][0]), min(head["box"][1], tail["box"][1]),
                               max(head["box"][2], tail["box"][2]), max(head["box"][3], tail["box"][3])]
                head["confidence"] = min(head["confidence"], tail["confidence"])
                continue
        joined.append(row)
    return joined


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
    elif turns == 2:  # rotated[r, c] = page[height - r, width - c]
        xs, ys = (width - x0, width - x1), (height - y0, height - y1)
    else:  # turns == -1: rotated[r, c] = page[height - c, r]
        xs, ys = (y0, y1), (height - x0, height - x1)
    return [min(xs), min(ys), max(xs), max(ys)]


def ocr_image(image) -> OcrPage:
    """OCR one PIL image. A sideways or upside-down page is read turned upright; reported
    boxes stay in the pixels of the image as given."""
    if _on_worker():
        return _read_page(image)
    return _executor().submit(_read_page, image).result()


def ocr_images(images: list) -> list[OcrPage]:
    """OCR several images in parallel, results in input order."""
    return list(_executor().map(_read_page, images))


def _read_page(image) -> OcrPage:
    import numpy as np

    array = np.asarray(image.convert("RGB"))
    height, width = int(array.shape[0]), int(array.shape[1])
    turns = 0
    engine = _engine()
    # Read without the per-box 180-degree classifier. On photographed reports it turned
    # upright boxes over: units read as garbage ("mg/dl" as "Ip/Bw", "g/dL" as "1p/6"), and
    # a whole negated line ("...no features suggestive of myelomalacia / cord") was read
    # upside down below the text score and dropped. A page that is upside down as a whole
    # reads with low confidence and is retried turned around.
    detections, _elapsed = engine(array, use_cls=False, box_thresh=DETECTION_BOX_THRESHOLD)
    if detections and _sideways(detections):
        # Turn both ways: the upright turn reads with clearly higher confidence than the
        # upside-down one.
        readings = []
        for candidate in (1, -1):
            found, _ = engine(np.ascontiguousarray(np.rot90(array, candidate)), use_cls=False, box_thresh=DETECTION_BOX_THRESHOLD)
            readings.append((_read_confidence(found or []), candidate, found or []))
        confidence, candidate, found = max(readings, key=lambda reading: reading[0])
        if confidence > _read_confidence(detections):
            turns, detections = candidate, found
    elif detections and _read_confidence(detections) < UPSIDE_DOWN_CHECK_BELOW:
        found, _ = engine(np.ascontiguousarray(np.rot90(array, 2)), use_cls=False, box_thresh=DETECTION_BOX_THRESHOLD)
        if _read_confidence(found or []) > _read_confidence(detections):
            turns, detections = 2, found
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


def render_pdf_page(content_bytes: bytes, index: int, dpi: int = OCR_DPI):
    """One PDF page as a PIL image. PDFium is not thread-safe, so pages are rendered on the
    calling thread and only the OCR runs on the workers."""
    import pypdfium2

    with PDFIUM_LOCK:
        document = pypdfium2.PdfDocument(io.BytesIO(content_bytes))
        try:
            page = document[index]
            image = page.render(scale=dpi / 72).to_pil()
            page.close()
        finally:
            document.close()
    return image


def ocr_pdf_page(content_bytes: bytes, index: int, dpi: int = OCR_DPI) -> OcrPage:
    return ocr_image(render_pdf_page(content_bytes, index, dpi))


def ocr_pdf_pages(content_bytes: bytes, indices: list[int], dpi: int = OCR_DPI) -> list[OcrPage]:
    """OCR several PDF pages, results in input order. The next page is rendered as soon as a
    worker is free, so at most OCR_WORKERS rendered pages are held in memory."""
    results: list[Optional[OcrPage]] = [None] * len(indices)
    in_flight: deque = deque()
    for position, index in enumerate(indices):
        if len(in_flight) >= OCR_WORKERS:
            done, future = in_flight.popleft()
            results[done] = future.result()
        in_flight.append((position, _executor().submit(_read_page, render_pdf_page(content_bytes, index, dpi))))
    for done, future in in_flight:
        results[done] = future.result()
    return results  # type: ignore[return-value]
