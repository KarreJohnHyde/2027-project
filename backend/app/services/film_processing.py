"""Conservative raster source assessment and reproducible film-panel previews.

This is a viewing heuristic, not a diagnostic model or a DICOM reconstruction.
Coordinates refer to the EXIF-upright source pixels. No intensities are converted
to HU, and visible panel order never implies patient-space slice order.
"""
from __future__ import annotations

import io
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.services.imaging_readers import open_raster

VERSION = "film-preview-v1"
LIMITATIONS = [
    "Raster provenance cannot be established from pixels alone; source classification requires review.",
    "No Hounsfield units, slice spacing, orientation or patient coordinates can be recovered from film.",
    "Coloured source marks are annotations, not AI detections or ground-truth lesion masks.",
    "Glare and perspective may obscure content; previews preserve source pixels without diagnostic enhancement.",
]


def assess_raster(path: Path | Image.Image) -> dict:
    image = (path if isinstance(path, Image.Image) else open_raster(path)[0]).convert("RGB")
    width, height = image.size
    # Bound processing cost; map every rectangle back to the original upright grid.
    ratio = min(1.0, 1600 / max(width, height))
    small = image.resize((max(1, round(width * ratio)), max(1, round(height * ratio))))
    rgb = np.asarray(small)
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    sh, sw = grey.shape
    candidates = []
    contours = []
    for threshold in (130, 175, 210):
        bright = (grey > threshold).astype(np.uint8) * 255
        bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        # RETR_LIST finds film inside a scanned PDF's white page margin too.
        found, _ = cv2.findContours(bright, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours.extend(found)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        # Film skull outlines enclose a darker interior and are roughly elliptical.
        if w < max(32, sw * .065) or h < max(40, sh * .065) or w * h > sw * sh * .9 or not .48 < w / h < 1.45:
            continue
        if not .42 < area / (w * h) < .94:
            continue
        perimeter = cv2.arcLength(contour, True)
        hull_area = cv2.contourArea(cv2.convexHull(contour))
        if hull_area <= 0 or area / hull_area < .9 or perimeter <= 0 or 4 * np.pi * area / perimeter ** 2 < .55:
            continue
        crop = grey[y:y+h, x:x+w]
        cy, cx = max(1, h // 6), max(1, w // 6)
        corners = np.concatenate([crop[:cy, :cx].ravel(), crop[:cy, -cx:].ravel(), crop[-cy:, :cx].ravel(), crop[-cy:, -cx:].ravel()])
        if float(np.median(corners)) > 100:
            continue
        inner = grey[y + h // 4:y + 3 * h // 4, x + w // 4:x + 3 * w // 4]
        if not inner.size or np.mean(inner < np.percentile(grey[y:y+h, x:x+w], 95) - 15) < .25:
            continue
        if any(max(0, min(x+w, a+c) - max(x, a)) * max(0, min(y+h, b+d) - max(y, b)) /
               min(w*h, c*d) > .65 for a, b, c, d in candidates):
            continue
        candidates.append((x, y, w, h))
    found_by = {box: "CONTOUR" for box in candidates}
    for box in grid_completion(grey, candidates):
        candidates.append(box)
        found_by[box] = "GRID_COMPLETION"
    # Order in visual rows, retaining actual positions rather than assuming a fixed grid.
    rows: list[list[tuple]] = []
    for box in sorted(candidates, key=lambda b: (b[1] + b[3] / 2, b[0])):
        row = next((r for r in rows if abs((box[1] + box[3] / 2) - np.median([b[1] + b[3] / 2 for b in r])) < box[3] * .45), None)
        if row is None:
            rows.append([box])
        else:
            row.append(box)
    panels = []
    for row_index, row in enumerate(rows):
        for col_index, (x, y, w, h) in enumerate(sorted(row)):
            margin = max(2, round(min(w, h) * .025))
            rect = [max(0, round((x - margin) / ratio)), max(0, round((y - margin) / ratio)),
                    min(width, round((x + w + margin) / ratio)), min(height, round((y + h + margin) / ratio))]
            panels.append({"panel_id": len(panels), "row": row_index, "column": col_index, "bbox_xyxy": rect,
                           "detection": found_by.get((x, y, w, h), "CONTOUR")})
    r, g, b = rgb.astype(np.int16).transpose(2, 0, 1)
    marks = (r > 95) & (r - g > 30) & (r - b > 20)
    colour_fraction = float(marks.mean())
    # A monochrome single CT slice cannot be distinguished from a digital export
    # by its skull contour. Do not label a native grayscale slice as photographed.
    colour_spread = float(np.mean(np.max(rgb, axis=2) - np.min(rgb, axis=2) > 25))
    detected = len(panels) > 1 or bool(panels and colour_spread > .03)
    if not detected:
        panels = []
    source = "FILM_MONTAGE_CANDIDATE" if len(panels) > 1 else "FILM_SLICE_CANDIDATE" if panels else "AMBIGUOUS_RASTER"
    return {
        "version": VERSION, "source_type": source, "classification_basis": "UNVALIDATED_PIXEL_HEURISTIC",
        "modality": "CT_LIKE_REQUIRES_REVIEW" if detected else "UNKNOWN",
        "dimensions": [width, height], "coordinate_space": "EXIF_UPRIGHT_SOURCE_PIXELS",
        "spatial_metadata_available": False, "patient_registration_eligible": False,
        "inference_eligibility": "ABSTAIN_FILM_INPUT" if detected else "MODEL_SPECIFIC_CHECKS_REQUIRED",
        "model_compatibility": "Native-image models blocked for suspected film" if detected else "Not established by this assessment",
        "quality": {"status": "REVIEW_REQUIRED", "grayscale_dynamic_range": int(np.ptp(grey)),
                    "laplacian_variance": round(float(cv2.Laplacian(grey, cv2.CV_64F).var()), 3),
                    "metrics_calibrated": False},
        "source_annotations": {"coloured_marks_suspected": colour_fraction > .0005,
                               "red_colour_fraction": round(colour_fraction, 6), "is_ai_mask": False},
        "panels": panels, "panel_order": "VISUAL_ROW_MAJOR_ONLY", "limitations": LIMITATIONS,
    }


def _centres(values: list[float], tolerance: float) -> list[float]:
    """Cluster 1-D centres that lie within ``tolerance`` of each other; the cluster means, sorted."""
    clusters: list[list[float]] = []
    for value in sorted(values):
        if clusters and value - clusters[-1][-1] <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [float(np.mean(cluster)) for cluster in clusters]


def _lattice(centres: list[float], pitch: float, low: float, high: float) -> list[float]:
    """The detected centres extended at ``pitch`` across [low, high], keeping the detected positions."""
    lattice = list(centres)
    while lattice[0] - pitch >= low:
        lattice.insert(0, lattice[0] - pitch)
    while lattice[-1] + pitch <= high:
        lattice.append(lattice[-1] + pitch)
    filled = [lattice[0]]
    for value in lattice[1:]:  # gaps of about n pitches between detected centres get n - 1 intermediate cells
        steps = max(1, int(round((value - filled[-1]) / pitch)))
        filled += [filled[-1] + (value - filled[-1]) * step / steps for step in range(1, steps + 1)]
    return filled


def grid_completion(grey: np.ndarray, boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Montage cells the contour pass missed (faint skull outlines, glare). With two or more panels of similar size, the
    row and column pitch of the detected panels defines a lattice across the image; an empty lattice cell becomes a panel
    only when its content resembles the detected panels (mean brightness well above the film background and a similar
    spread). Unvalidated viewing aid like the contour pass; each such panel is marked GRID_COMPLETION."""
    if len(boxes) < 2:
        return []
    sh, sw = grey.shape
    widths, heights = np.array([b[2] for b in boxes], float), np.array([b[3] for b in boxes], float)
    w, h = float(np.median(widths)), float(np.median(heights))
    if np.any(np.abs(widths - w) > .35 * w) or np.any(np.abs(heights - h) > .35 * h):
        return []  # panels of mixed size are not one regular montage
    xs = _centres([b[0] + b[2] / 2 for b in boxes], .45 * w)
    ys = _centres([b[1] + b[3] / 2 for b in boxes], .45 * h)
    pitches_x = np.diff(xs) if len(xs) > 1 else np.array([])
    pitches_y = np.diff(ys) if len(ys) > 1 else np.array([])
    # A single row or column gives no pitch for the other axis; use the panel size plus the observed gap.
    pitch_x = float(np.min(pitches_x)) if len(pitches_x) else None
    pitch_y = float(np.min(pitches_y)) if len(pitches_y) else None
    if pitch_x is None and pitch_y is None:
        return []
    pitch_x = pitch_x or (w * pitch_y / h if pitch_y else None)
    pitch_y = pitch_y or (h * pitch_x / w if pitch_x else None)
    if not (w * .9 <= pitch_x <= w * 2.2 and h * .9 <= pitch_y <= h * 2.2):
        return []
    columns = _lattice(xs, pitch_x, w / 2, sw - w / 2)
    rows = _lattice(ys, pitch_y, h / 2, sh - h / 2)
    background = float(np.median(np.concatenate([grey[:max(1, sh // 20)].ravel(), grey[-max(1, sh // 20):].ravel()])))
    inside = [grey[y:y + bh, x:x + bw] for x, y, bw, bh in boxes]
    panel_mean = float(np.median([region.mean() for region in inside]))
    panel_spread = float(np.median([region.std() for region in inside]))
    if panel_mean - background < 15:
        return []
    added = []
    for cy in rows:
        for cx in columns:
            x, y = int(round(cx - w / 2)), int(round(cy - h / 2))
            if x < 0 or y < 0 or x + w > sw or y + h > sh:
                continue
            if any(abs((bx + bw / 2) - cx) < .5 * w and abs((by + bh / 2) - cy) < .5 * h for bx, by, bw, bh in boxes + added):
                continue
            region = grey[y:y + int(h), x:x + int(w)]
            if region.size and region.mean() - background >= .35 * (panel_mean - background) and region.std() >= .4 * panel_spread:
                added.append((x, y, int(w), int(h)))
    return added


def render_panel(path: Path | Image.Image, assessment: dict, panel_id: int) -> bytes:
    panel = next((p for p in assessment["panels"] if p["panel_id"] == panel_id), None)
    if panel is None:
        raise ValueError("PANEL_NOT_FOUND")
    image = (path if isinstance(path, Image.Image) else open_raster(path)[0]).crop(tuple(panel["bbox_xyxy"]))
    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
