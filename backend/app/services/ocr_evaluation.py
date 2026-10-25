"""Strict, privacy-minimising OCR CER/WER evaluation over de-identified pages."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from typing import Any

from app.services.evaluation_metrics import EvaluationInputError


SCHEMA_VERSION = "medtwin.ocr-pages.v1"
MAX_PAGES = 10_000
MAX_PAGE_CHARACTERS = 100_000
MAX_TOTAL_CHARACTERS = 5_000_000
MAX_EDIT_MATRIX_CELLS = 25_000_000
MAX_PER_PAGE_ROWS = 1_000
_DOCUMENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class OcrPage:
    document_id: str
    page: int
    source_image_sha256: str
    text: str

    @property
    def key(self) -> tuple[str, int]:
        return self.document_id, self.page


def _normalise_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")


def _parse(content: bytes, role: str) -> dict[tuple[str, int], OcrPage]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except UnicodeDecodeError as exc:
        raise EvaluationInputError(f"The {role} OCR artifact must be UTF-8 JSON.") from exc
    except json.JSONDecodeError as exc:
        raise EvaluationInputError(f"The {role} OCR artifact is not valid JSON: {exc.msg}.") from exc
    if not isinstance(payload, dict):
        raise EvaluationInputError(f"The {role} OCR artifact root must be an object.")
    expected = {"schema_version", "artifact_role", "pages"}
    if set(payload) != expected:
        raise EvaluationInputError(
            f"The {role} OCR artifact must contain exactly: artifact_role, pages, schema_version."
        )
    if payload["schema_version"] != SCHEMA_VERSION:
        raise EvaluationInputError(
            f"The {role} OCR artifact schema_version must be '{SCHEMA_VERSION}'."
        )
    if payload["artifact_role"] != role:
        raise EvaluationInputError(f"The {role} upload must declare artifact_role '{role}'.")
    raw_pages = payload["pages"]
    if not isinstance(raw_pages, list):
        raise EvaluationInputError(f"The {role} OCR artifact.pages value must be an array.")
    if not raw_pages:
        raise EvaluationInputError(f"The {role} OCR artifact must contain at least one page.")
    if len(raw_pages) > MAX_PAGES:
        raise EvaluationInputError(f"At most {MAX_PAGES} pages are accepted per OCR artifact.")

    pages: dict[tuple[str, int], OcrPage] = {}
    total_characters = 0
    for index, raw in enumerate(raw_pages):
        location = f"{role} OCR artifact.pages[{index}]"
        if not isinstance(raw, dict) or set(raw) != {
            "document_id",
            "page",
            "source_image_sha256",
            "text",
        }:
            raise EvaluationInputError(
                f"{location} must contain exactly document_id, page, source_image_sha256 and text."
            )
        document_id = raw["document_id"]
        if not isinstance(document_id, str) or not _DOCUMENT_ID.fullmatch(document_id):
            raise EvaluationInputError(f"{location}.document_id is not a valid pseudonymous ID.")
        page_number = raw["page"]
        if type(page_number) is not int or page_number < 1:
            raise EvaluationInputError(f"{location}.page must be a positive integer.")
        image_hash = raw["source_image_sha256"]
        if not isinstance(image_hash, str) or not _SHA256.fullmatch(image_hash):
            raise EvaluationInputError(
                f"{location}.source_image_sha256 must be a lowercase SHA-256 digest."
            )
        text = raw["text"]
        if not isinstance(text, str):
            raise EvaluationInputError(f"{location}.text must be a string.")
        text = _normalise_text(text)
        if len(text) > MAX_PAGE_CHARACTERS:
            raise EvaluationInputError(
                f"{location}.text exceeds {MAX_PAGE_CHARACTERS} Unicode characters."
            )
        total_characters += len(text)
        if total_characters > MAX_TOTAL_CHARACTERS:
            raise EvaluationInputError(
                f"The {role} OCR artifact exceeds {MAX_TOTAL_CHARACTERS} Unicode characters."
            )
        page = OcrPage(document_id, page_number, image_hash, text)
        if page.key in pages:
            raise EvaluationInputError(
                f"Duplicate document/page key in the {role} OCR artifact: {document_id} page {page_number}."
            )
        pages[page.key] = page
    return pages


def _edit_distance(left: list[str] | str, right: list[str] | str) -> int:
    if left == right:
        return 0
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for row_index, right_item in enumerate(right, start=1):
        current = [row_index]
        for column_index, left_item in enumerate(left, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column_index] + 1,
                    previous[column_index - 1] + (left_item != right_item),
                )
            )
        previous = current
    return previous[-1]


def _rate(distance: int, reference_count: int) -> float | None:
    return None if reference_count == 0 else distance / reference_count


def evaluate_ocr(gold_content: bytes, prediction_content: bytes) -> dict[str, Any]:
    gold = _parse(gold_content, "gold")
    predictions = _parse(prediction_content, "prediction")
    if set(gold) != set(predictions):
        raise EvaluationInputError(
            "Gold and prediction OCR artifacts must contain the same document/page keys."
        )
    mismatched_images = [
        key
        for key in gold
        if gold[key].source_image_sha256 != predictions[key].source_image_sha256
    ]
    if mismatched_images:
        raise EvaluationInputError(
            "Gold and prediction OCR artifacts must reference the same source-image hash for every page."
        )

    character_edits = 0
    gold_characters = 0
    predicted_characters = 0
    word_edits = 0
    gold_words = 0
    predicted_words = 0
    exact_pages = 0
    total_cells = 0
    per_page: list[dict[str, Any]] = []
    manifest_rows: list[tuple[str, int, str]] = []
    for key in sorted(gold):
        reference = gold[key]
        predicted = predictions[key]
        reference_words = reference.text.split()
        predicted_page_words = predicted.text.split()
        if reference.text != predicted.text:
            total_cells += len(reference.text) * len(predicted.text)
            total_cells += len(reference_words) * len(predicted_page_words)
            if total_cells > MAX_EDIT_MATRIX_CELLS:
                raise EvaluationInputError(
                    "OCR edit-distance work exceeds the 25,000,000-cell safety bound; evaluate a fixed smaller partition."
                )
        page_character_edits = _edit_distance(reference.text, predicted.text)
        page_word_edits = _edit_distance(reference_words, predicted_page_words)
        character_edits += page_character_edits
        gold_characters += len(reference.text)
        predicted_characters += len(predicted.text)
        word_edits += page_word_edits
        gold_words += len(reference_words)
        predicted_words += len(predicted_page_words)
        exact_pages += int(reference.text == predicted.text)
        document_digest = hashlib.sha256(reference.document_id.encode("utf-8")).hexdigest()
        manifest_rows.append((document_digest, reference.page, reference.source_image_sha256))
        if len(per_page) < MAX_PER_PAGE_ROWS:
            per_page.append(
                {
                    "document_id_sha256": document_digest,
                    "page": reference.page,
                    "gold_characters": len(reference.text),
                    "predicted_characters": len(predicted.text),
                    "character_edits": page_character_edits,
                    "character_error_rate": _rate(page_character_edits, len(reference.text)),
                    "gold_words": len(reference_words),
                    "predicted_words": len(predicted_page_words),
                    "word_edits": page_word_edits,
                    "word_error_rate": _rate(page_word_edits, len(reference_words)),
                    "exact": reference.text == predicted.text,
                }
            )
    page_count = len(gold)
    manifest_digest = hashlib.sha256(
        json.dumps(manifest_rows, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "task_type": "ocr",
        "n": page_count,
        "n_groups": len({page.document_id for page in gold.values()}),
        "metrics": {
            "character_error_rate": _rate(character_edits, gold_characters),
            "word_error_rate": _rate(word_edits, gold_words),
            "exact_page_rate": _rate(exact_pages, page_count),
            "character_edits": character_edits,
            "word_edits": word_edits,
            "gold_characters": gold_characters,
            "predicted_characters": predicted_characters,
            "gold_words": gold_words,
            "predicted_words": predicted_words,
            "exact_pages": exact_pages,
        },
        "normalization": {
            "unicode": "NFC",
            "line_endings": "LF",
            "case_sensitive": True,
            "punctuation_sensitive": True,
            "word_tokenization": "Unicode whitespace split",
        },
        "provenance": {
            "page_manifest_sha256": manifest_digest,
            "raw_text_persisted": False,
            "raw_document_ids_persisted": False,
        },
        "per_page": per_page,
        "per_page_truncated": page_count > MAX_PER_PAGE_ROWS,
        "assumptions": [
            "Gold text is an independent human transcription of the same rendered source page.",
            "CER and WER measure transcription agreement, not downstream clinical correctness.",
            "Empty-reference pages have undefined per-page error rates.",
        ],
    }
