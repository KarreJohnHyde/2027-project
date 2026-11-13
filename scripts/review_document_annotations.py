"""Initialize and validate independently human-checked, de-identified page labels.

No OCR/extractor is invoked and no label is generated from model output. Real-page
annotations belong outside the repository. Identity and permission declarations
are attestations, not independently verified identities or licence approvals.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import unicodedata

SCHEMA = "medtwin.review-document-annotation.v1"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
ASSERTION = {"CERTAIN", "UNCERTAIN", "HYPOTHETICAL"}
NEGATION = {"AFFIRMED", "NEGATED"}
TEMPORALITY = {"CURRENT", "HISTORICAL"}
LABEL = re.compile(r"[A-Z][A-Z0-9_:-]{0,63}\Z")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Artifact must be a JSON object.")
    return value


def _text(value, name, *, nonempty=True):
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ValueError(f"{name} must be {'nonempty ' if nonempty else ''}text.")


def _id(value, name):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError(f"{name} must be a pseudonymous identifier of 1–100 safe characters.")


def _page_identity(page):
    _id(page.get("document_id"), "document_id")
    if type(page.get("page")) is not int or page["page"] < 1:
        raise ValueError("page must be a positive integer.")
    if not isinstance(page.get("source_image_sha256"), str) or not SHA.fullmatch(page["source_image_sha256"]):
        raise ValueError("source_image_sha256 must be a lowercase SHA-256 digest.")
    for dimension in ("width", "height"):
        if type(page.get(dimension)) is not int or page[dimension] < 1:
            raise ValueError(f"{dimension} must be a positive pixel count.")
    if page.get("deidentified") is not True:
        raise ValueError("Every page requires a de-identification attestation.")
    _text(page.get("permission_scope"), "permission_scope")
    if page.get("evidence_type") not in {"REAL_PERMITTED", "SYNTHETIC"}:
        raise ValueError("evidence_type must explicitly distinguish real permitted from synthetic pages.")


def _bbox(box, page):
    if not isinstance(box, list) or len(box) != 4:
        raise ValueError("source_bbox must contain [left, top, right, bottom] source pixels.")
    if any(type(value) not in (int, float) or not Decimal(str(value)).is_finite() for value in box):
        raise ValueError("source_bbox coordinates must be finite numbers.")
    left, top, right, bottom = box
    if not (0 <= left < right <= page["width"] and 0 <= top < bottom <= page["height"]):
        raise ValueError("source_bbox must have positive area and remain on the source page.")


def _context(item):
    for name, accepted in (("assertion", ASSERTION), ("negation", NEGATION), ("temporality", TEMPORALITY)):
        if item.get(name) not in accepted:
            raise ValueError(f"{name} must use the strict evaluator vocabulary: {sorted(accepted)}.")


def _numeric(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a decimal string preserving source precision.")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{name} must be a valid decimal string.") from exc
    if not number.is_finite():
        raise ValueError(f"{name} must be finite.")


def _date(value, name):
    if value is not None:
        try:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError()
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO date or null when unavailable.") from exc


def annotation_digest(page: dict) -> str:
    """Bind review to all source/context/text/field values, excluding review metadata."""
    content = {key: value for key, value in page.items() if key != "review"}
    return digest_bytes(json.dumps(content, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def initialize(inventory: dict, base: Path) -> dict:
    if inventory.get("schema_version") != "medtwin.review-page-inventory.v1" or not isinstance(inventory.get("pages"), list):
        raise ValueError("Inventory requires medtwin.review-page-inventory.v1 and a pages list.")
    pages, seen = [], set()
    for item in inventory["pages"]:
        if not isinstance(item, dict):
            raise ValueError("Inventory pages must be objects.")
        source = item.get("source_image_path")
        _text(source, "source_image_path")
        source_path = (base / source).resolve()
        if source_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}:
            raise ValueError("Inventory must name individual rendered raster pages, not a PDF/document hash.")
        raw = source_path.read_bytes()
        source_hash = digest_bytes(raw)
        if item.get("source_image_sha256") and item["source_image_sha256"] != source_hash:
            raise ValueError("Inventory source-image checksum mismatch.")
        page = {key: item.get(key) for key in ("document_id", "page", "width", "height", "deidentified", "permission_scope", "evidence_type")}
        page.update(source_image_sha256=source_hash, gold_text=None, readability="UNANNOTATED", unreadable_reason=None,
                    fields=[], entities=[], review={"status": "DRAFT", "annotator_id": None, "reviewer_id": None,
                    "independently_transcribed": False, "critical_fields_checked": False, "reviewed_at": None,
                    "reviewed_content_sha256": None})
        _page_identity(page)
        key = page["document_id"], page["page"]
        if key in seen:
            raise ValueError("Duplicate document/page key in inventory.")
        seen.add(key)
        pages.append(page)
    return {"schema_version": SCHEMA, "pages": pages}


def validate(bundle: dict, *, require_finalized=False) -> dict:
    if bundle.get("schema_version") != SCHEMA or not isinstance(bundle.get("pages"), list):
        raise ValueError("Unsupported annotation schema or missing pages list.")
    counts = {"total_pages": len(bundle["pages"]), "finalized_real_pages": 0, "finalized_synthetic_pages": 0,
              "unreadable_finalized_pages": 0, "ocr_exportable_pages": 0, "annotated_fields": 0, "annotated_entities": 0}
    seen = set()
    for page in bundle["pages"]:
        if not isinstance(page, dict):
            raise ValueError("Every annotation page must be an object.")
        _page_identity(page)
        key = page["document_id"], page["page"]
        if key in seen:
            raise ValueError("Duplicate document/page key in annotations.")
        seen.add(key)
        if page.get("readability") not in {"UNANNOTATED", "READABLE", "UNREADABLE"}:
            raise ValueError("Invalid page readability.")
        if page["readability"] == "READABLE":
            _text(page.get("gold_text"), "gold_text")
        elif page["readability"] == "UNREADABLE":
            _text(page.get("unreadable_reason"), "unreadable_reason")
            if page.get("gold_text") is not None:
                raise ValueError("Unreadable pages must not contain guessed gold text.")
        elif page.get("gold_text") is not None:
            raise ValueError("Unannotated pages must not contain gold text.")
        if not isinstance(page.get("fields"), list) or not isinstance(page.get("entities"), list):
            raise ValueError("fields and entities must be arrays.")
        if page["readability"] != "READABLE" and (page["fields"] or page["entities"]):
            raise ValueError("Fields/entities require a readable human transcription.")
        for field in page["fields"]:
            _text(field.get("analyte"), "analyte")
            _bbox(field.get("source_bbox"), page)
            _context(field)
            state = field.get("value_state")
            if state not in {"READABLE", "UNREADABLE", "NOT_REPORTED"}:
                raise ValueError("value_state must distinguish readable, unreadable and not-reported values.")
            if state == "READABLE":
                _numeric(field.get("value"), "value")
            elif field.get("value") is not None:
                raise ValueError("An unreadable/missing value must remain null.")
            if state == "UNREADABLE":
                _text(field.get("unreadable_reason"), "field unreadable_reason")
            for optional in ("unit", "specimen"):
                if optional not in field:
                    raise ValueError(f"{optional} must be explicit text or null.")
                if field[optional] is not None:
                    _text(field[optional], optional)
            if field.get("comparator") not in {None, "<", "<=", ">", ">="}:
                raise ValueError("Numeric comparator must be explicit, not embedded in a decimal value.")
            for name in ("collection_date", "report_date"):
                if name not in field:
                    raise ValueError(f"{name} must be explicit, using null when unavailable.")
                _date(field[name], name)
            interval = field.get("reference_interval")
            if interval is not None:
                if not isinstance(interval, dict) or set(interval) != {"low", "high", "text"}:
                    raise ValueError("reference_interval requires low, high and original text or must be null.")
                for name in ("low", "high"):
                    if interval[name] is not None:
                        _numeric(interval[name], f"interval {name}")
                _text(interval["text"], "original reference interval")
                if interval["low"] is not None and interval["high"] is not None and Decimal(interval["low"]) > Decimal(interval["high"]):
                    raise ValueError("Reference interval low exceeds high.")
            counts["annotated_fields"] += 1
        for entity in page["entities"]:
            start, end = entity.get("start"), entity.get("end")
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(page["gold_text"]):
                raise ValueError("Entity offsets must select a nonempty span in the human transcription.")
            if not isinstance(entity.get("label"), str) or not LABEL.fullmatch(entity["label"]):
                raise ValueError("Entity label must use the strict evaluator uppercase vocabulary.")
            _context(entity)
            _bbox(entity.get("source_bbox"), page)
            counts["annotated_entities"] += 1
        review = page.get("review") or {}
        if review.get("status") not in {"DRAFT", "FINALIZED"}:
            raise ValueError("Review status must be DRAFT or FINALIZED.")
        if review["status"] != "FINALIZED":
            if require_finalized:
                raise ValueError("Every exported page must be finalized by distinct human annotator/reviewer attestations.")
            continue
        if page["readability"] == "UNANNOTATED":
            raise ValueError("An unannotated page cannot be finalized.")
        for name in ("annotator_id", "reviewer_id"):
            _id(review.get(name), name)
        if review["annotator_id"].casefold() == review["reviewer_id"].casefold():
            raise ValueError("Annotator and independent reviewer identities must be distinct.")
        if review.get("independently_transcribed") is not True or review.get("critical_fields_checked") is not True:
            raise ValueError("Finalization requires independent manual transcription and checked-critical-field attestations.")
        try:
            stamp = datetime.fromisoformat(review.get("reviewed_at", ""))
            if stamp.tzinfo is None:
                raise ValueError()
        except (ValueError, TypeError) as exc:
            raise ValueError("reviewed_at must be a timezone-aware ISO timestamp.") from exc
        if review.get("reviewed_content_sha256") != annotation_digest(page):
            raise ValueError("Reviewed content changed or lacks a matching review digest; re-review is required.")
        counts["finalized_real_pages" if page["evidence_type"] == "REAL_PERMITTED" else "finalized_synthetic_pages"] += 1
        counts["unreadable_finalized_pages" if page["readability"] == "UNREADABLE" else "ocr_exportable_pages"] += 1
    return counts


def finalize(bundle: dict, annotator: str, reviewer: str, *, manual: bool, checked: bool) -> dict:
    validate(bundle)
    if not manual or not checked:
        raise ValueError("Human transcription and independent critical-field review must be explicitly attested.")
    _id(annotator, "annotator_id")
    _id(reviewer, "reviewer_id")
    if annotator.casefold() == reviewer.casefold():
        raise ValueError("Annotator and reviewer must be distinct.")
    for page in bundle["pages"]:
        if page["readability"] == "UNANNOTATED":
            raise ValueError("Complete annotation or explicitly mark unreadable before finalizing.")
    for page in bundle["pages"]:
        page["review"] = {"status": "FINALIZED", "annotator_id": annotator, "reviewer_id": reviewer,
                          "independently_transcribed": True, "critical_fields_checked": True,
                          "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                          "reviewed_content_sha256": annotation_digest(page)}
    validate(bundle, require_finalized=True)
    return bundle


def export_ocr(bundle: dict) -> dict:
    validate(bundle, require_finalized=True)
    pages = [{key: page[key] for key in ("document_id", "page", "source_image_sha256")} |
             {"text": unicodedata.normalize("NFC", page["gold_text"]).replace("\r\n", "\n").replace("\r", "\n")}
             for page in bundle["pages"] if page["readability"] == "READABLE"]
    if not pages:
        raise ValueError("No reviewed readable pages are available; an empty gold evaluation is refused.")
    return {"schema_version": "medtwin.ocr-pages.v1", "artifact_role": "gold", "pages": pages}


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Do not silently overwrite a source inventory, annotations or previous reviewed gold.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--init", type=Path, metavar="INVENTORY")
    operation.add_argument("--validate", type=Path, metavar="ANNOTATIONS")
    operation.add_argument("--finalize", type=Path, metavar="ANNOTATIONS")
    operation.add_argument("--export-ocr", type=Path, metavar="ANNOTATIONS")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--annotator")
    parser.add_argument("--reviewer")
    parser.add_argument("--attest-manual-transcription", action="store_true")
    parser.add_argument("--attest-independent-critical-review", action="store_true")
    args = parser.parse_args(argv)
    if args.validate:
        print(json.dumps(validate(load(args.validate))))
        return 0
    if not args.out:
        parser.error("--out is required for a new artifact")
    if args.init:
        result = initialize(load(args.init), args.init.parent)
    elif args.finalize:
        result = finalize(load(args.finalize), args.annotator, args.reviewer,
                          manual=args.attest_manual_transcription, checked=args.attest_independent_critical_review)
    else:
        result = export_ocr(load(args.export_ocr))
    write_new(args.out, result)
    print(json.dumps(validate(result) if result.get("schema_version") == SCHEMA else {"exported_gold_pages": len(result["pages"])}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        # No source text or private filesystem contents are printed on failures.
        raise SystemExit(f"Annotation artifact refused: {type(exc).__name__}: {exc}")
    except OSError:
        raise SystemExit("Annotation artifact refused: source/output access failed or the destination already exists. No existing file was overwritten.")
