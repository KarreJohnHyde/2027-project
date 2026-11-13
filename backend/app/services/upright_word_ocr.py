"""Opt-in, source-bound OCR for a reviewer-attested upright Latin word ROI.

The existing full-page OCR path is unchanged. This helper preserves the exact
installed detector/recognizer and preprocessing, omitting only page orientation
retries for an explicitly attested upright crop. It produces a review proposal,
never an accepted measurement, drug instruction, diagnosis or source correction.
"""
from __future__ import annotations
from functools import lru_cache
import hashlib
import importlib.util
from importlib.metadata import version
import math
from pathlib import Path
import re

import numpy as np
from PIL import ImageStat
from app.services import ocr

VERSION = "medtwin.upright-word-ocr.v1"
FROZEN_OCR_CODE_SHA = "bd4e41fb67bd45ee41011e431f6208ec729b6c70b5a892a01ff7da419808f531"
EXPECTED_MODELS = {
    "ch_PP-OCRv4_det_infer.onnx": "d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9",
    "ch_PP-OCRv4_rec_infer.onnx": "48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b",
    "ch_ppocr_mobile_v2.0_cls_infer.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
}
BOUNDS = {"min_width": 12, "max_width": 1024, "min_height": 12, "max_height": 256,
          "max_pixels": 262144, "min_aspect": .5, "max_aspect": 16., "max_page_fraction": .10,
          "max_source_pixels": 20_000_000, "max_characters": 64}
FALLBACK = "Use the original source-verification/full-page OCR workflow and human correction; do not infer an unreadable word."
NOTICE = ("Research OCR proposal requiring visual human review. Raw OCR confidence is not a calibrated correctness probability. "
          "This opt-in policy has limited internal word-crop evidence only; it is not a general report, medication, laboratory or clinical validation.")
LATIN_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9.,/+%µμ°()_-]{0,63}\Z")


def _sha(path: Path) -> str:
    stat = path.stat()
    return _cached_sha(str(path), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=12)
def _cached_sha(path: str, size: int, modified: int) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def capability() -> dict:
    blockers, artifacts = [], []
    try:
        package = importlib.util.find_spec("rapidocr_onnxruntime")
        folder = Path(package.origin).parent
        code_hash = _sha(Path(ocr.__file__))
        installed = version("rapidocr-onnxruntime")
        if installed != "1.4.4": blockers.append("ENGINE_VERSION_DIFFERS_FROM_EVALUATED_CONFIGURATION")
        if code_hash != FROZEN_OCR_CODE_SHA: blockers.append("OCR_CODE_DIFFERS_FROM_EVALUATED_CONFIGURATION")
        for name, expected in EXPECTED_MODELS.items():
            digest = _sha(folder / "models" / name)
            artifacts.append({"file": name, "sha256": digest, "matches_evaluated_artifact": digest == expected})
            if digest != expected: blockers.append("OCR_MODEL_ARTIFACT_MISMATCH")
        provenance = {"engine": "rapidocr-onnxruntime", "version": installed, "onnxruntime": version("onnxruntime"),
                      "ocr_source_sha256": code_hash, "bundled_models": artifacts,
                      "code_licence": "Apache-2.0 (installed wheel metadata and upstream RapidOCR LICENSE)",
                      "model_provenance": "Existing bundled PaddleOCR PP-OCRv4 detector/recognizer and mobile classifier; classifier is not executed by this helper",
                      "model_family_licence": "Apache-2.0 upstream PaddleOCR; existing installed artifacts only, no newly downloaded weights",
                      "primary_sources": ["https://github.com/RapidAI/RapidOCR/blob/main/LICENSE", "https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE"],
                      "rights_review_semantics": "Automated source/package provenance, not independent human legal or clinical approval"}
    except (OSError, ValueError, AttributeError, TypeError, ModuleNotFoundError):
        blockers.append("EVALUATED_OCR_RUNTIME_UNAVAILABLE"); provenance = {"bundled_models": artifacts}
    return {"schema_version": VERSION, "available": not blockers, "blockers": sorted(set(blockers)), "bounds": BOUNDS,
            "provenance": provenance, "source_contract": "Privacy-masked report-page preview at110DPI; native preview pixel coordinates; upright single Latin word attested by requesting reviewer",
            "evaluation": {"kind": "PREREGISTERED_INTERNAL_PUBLISHER_TRAIN_WORD_CROP_HOLDOUT", "development_n": 128, "reserved_n": 256,
                           "baseline_cer": .5836120401337793, "upright_cer": .5652173913043478,
                           "paired_word_bootstrap_cer_delta_95": [-.031041491588061867, -.007671022936020575],
                           "patient_writer_independence_verified": False, "clinical_validation": False},
            "notice": NOTICE, "fallback": FALLBACK}


def refusal(code: str, reason: str, source: dict | None = None, *, status="REFUSED") -> dict:
    return {"schema_version": VERSION, "status": status, "code": code, "reason": reason, "text_proposal": None,
            "source": source, "review_required": True, "persisted_finding_or_correction": False,
            "clinical_activation": False, "fallback": FALLBACK, "notice": NOTICE}


def validate_roi(image_size, bbox, *, upright_attested: bool, single_word_attested: bool, latin_text_attested: bool) -> str | None:
    if not all((upright_attested is True, single_word_attested is True, latin_text_attested is True)):
        return "EXPLICIT_UPRIGHT_SINGLE_LATIN_WORD_ATTESTATION_REQUIRED"
    if len(bbox) != 4 or any(type(v) is not int for v in bbox): return "INTEGER_PREVIEW_PIXEL_BOX_REQUIRED"
    page_width, page_height = image_size
    x0, y0, x1, y1 = bbox
    width, height = x1 - x0, y1 - y0
    if not (0 <= x0 < x1 <= page_width and 0 <= y0 < y1 <= page_height): return "ROI_OUTSIDE_SOURCE_PREVIEW"
    if (not BOUNDS["min_width"] <= width <= BOUNDS["max_width"] or not BOUNDS["min_height"] <= height <= BOUNDS["max_height"]
            or width * height > BOUNDS["max_pixels"] or not BOUNDS["min_aspect"] <= width / height <= BOUNDS["max_aspect"]
            or width * height > page_width * page_height * BOUNDS["max_page_fraction"]
            or page_width * page_height > BOUNDS["max_source_pixels"]):
        return "ROI_NOT_WITHIN_SINGLE_WORD_GEOMETRY_BOUNDS"
    return None


def _upright_read(crop):
    # Same detector, threshold, recognizer, normalization and reading-order code
    # as ocr._read_page. The attestation replaces page-level orientation retry.
    found, _ = ocr._engine()(np.asarray(crop.convert("RGB")), use_cls=False, box_thresh=ocr.DETECTION_BOX_THRESHOLD)
    return ocr._reading_order(found or [])


def recognise(image, bbox: list[int], *, source: dict, upright_attested=False, single_word_attested=False, latin_text_attested=False) -> dict:
    code = validate_roi(image.size, bbox, upright_attested=upright_attested, single_word_attested=single_word_attested, latin_text_attested=latin_text_attested)
    if code: return refusal(code, "The selected source does not satisfy the bounded upright single-word contract.", source)
    runtime = capability()
    if not runtime["available"]: return {**refusal("EVALUATED_OCR_RUNTIME_UNAVAILABLE", "The exact evaluated engine/code artifacts are unavailable or changed.", source), "runtime": runtime}
    x0, y0, x1, y1 = bbox
    crop = image.crop((x0, y0, x1, y1)).convert("RGB")
    if ImageStat.Stat(crop.convert("L")).stddev[0] < 2:
        return refusal("BLANK_OR_PRIVACY_MASKED_ROI", "A uniform or privacy-masked region cannot support a word proposal.", source, status="ABSTAIN")
    lines = ocr._executor().submit(_upright_read, crop).result()
    if len(lines) != 1: return refusal("SINGLE_DETECTED_WORD_LINE_REQUIRED", "No text line or multiple lines were detected; single-word context is not established.", source, status="ABSTAIN")
    line = lines[0]
    text = str(line["text"]).strip()
    if not math.isfinite(float(line["confidence"])) or not 0 <= float(line["confidence"]) <= 1:
        return refusal("OCR_SCORE_INVALID", "The engine did not provide a finite bounded raw score.", source, status="ABSTAIN")
    if not LATIN_WORD.fullmatch(text): return refusal("SINGLE_LATIN_WORD_OUTPUT_REQUIRED", "Multiple tokens, unsupported script/characters or excessive output length require the original review workflow.", source, status="ABSTAIN")
    box = line["box"]
    if len(box) != 4 or not all(math.isfinite(float(v)) for v in box) or not (0 <= box[0] < box[2] <= crop.width and 0 <= box[1] < box[3] <= crop.height):
        return refusal("OCR_BOX_OUTSIDE_SOURCE_ROI", "A source-coordinate mapping could not be established.", source, status="ABSTAIN")
    source_box = [float(box[0]) + x0, float(box[1]) + y0, float(box[2]) + x0, float(box[3]) + y0]
    return {"schema_version": VERSION, "status": "AVAILABLE", "code": "OCR_WORD_PROPOSAL_REVIEW_REQUIRED", "reason": None,
            "text_proposal": text, "raw_ocr_confidence": float(line["confidence"]), "confidence_semantics": "Uncalibrated engine line score, not probability that a clinical word/value is correct",
            "source": source, "roi_bbox_xyxy": bbox, "crop_word_bbox_xyxy": [float(v) for v in box],
            "source_word_bbox_xyxy": source_box, "coordinate_space": "REPORT_PAGE_PREVIEW_110_DPI",
            "crop_to_preview_affine": [[1, 0, x0], [0, 1, y0], [0, 0, 1]], "rotation_degrees": 0,
            "context_verification": "REVIEWER_ATTESTATION_PLUS_GEOMETRY_AND_SINGLE_DETECTED_TOKEN; not independently verified language/clinical meaning",
            "runtime": runtime, "review_required": True, "persisted_finding_or_correction": False, "clinical_activation": False, "notice": NOTICE}
