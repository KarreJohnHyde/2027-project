"""Offline full-report evaluation against supplied independent checked references.

Never creates/finalizes gold, infers permissions, writes patient text or contacts
an external service. Source/reference gates run before OCR. Aggregates remain
outside the repository or in Git-ignored local cache/artifacts. Synthetic
controls never count as real.
"""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import re
import sys
import subprocess
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
from scripts.review_document_annotations import validate, export_ocr

SCHEMA = "medtwin.independent-report-evaluation.v1"
SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_DOCUMENTS, MAX_PAGES, MAX_BYTES = 50, 250, 128 * 1024 * 1024


class Refused(ValueError):
    """Fixed non-sensitive refusal code, never a report/path/text excerpt."""


def require(condition, code):
    if not condition:
        raise Refused(code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def file_bytes(path: Path, maximum=MAX_BYTES) -> bytes:
    require(path.is_file() and path.stat().st_size <= maximum, "SOURCE_OR_EVIDENCE_FILE_UNAVAILABLE_OR_TOO_LARGE")
    return path.read_bytes()


def read_json(path: Path) -> dict:
    value = json.loads(file_bytes(path, 16 * 1024 * 1024).decode("utf-8-sig"))
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


def _path(base: Path, value) -> Path:
    require(isinstance(value, str) and bool(value.strip()) and not re.match(r"^[a-z]+://", value, re.I), "LOCAL_SOURCE_PATH_REQUIRED")
    return (base / value).resolve()


def _hash_match(path: Path, expected) -> bytes:
    require(isinstance(expected, str) and bool(SHA.fullmatch(expected)), "EXPLICIT_SOURCE_HASH_REQUIRED")
    data = file_bytes(path)
    require(digest(data) == expected, "SOURCE_OR_PERMISSION_EVIDENCE_HASH_MISMATCH")
    return data


def _permission_gate(permissions: dict, base: Path, document: dict, annotation_sha: str, synthetic: bool) -> str:
    require(permissions.get("schema_version") == "medtwin.independent-report-permissions.v1", "PERMISSION_SCHEMA_UNSUPPORTED")
    matches = [row for row in permissions.get("records", []) if row.get("source_pdf_sha256") == document["source_pdf_sha256"]]
    require(len(matches) == 1, "EXACT_SOURCE_PERMISSION_RECORD_REQUIRED")
    record = matches[0]
    require(record.get("annotations_sha256") == annotation_sha, "PERMISSION_REFERENCE_HASH_BINDING_REQUIRED")
    require(record.get("commercial_evaluation_allowed") is True and record.get("scope") == "LOCAL_COMMERCIAL_DEVELOPMENT_EVALUATION", "COMMERCIAL_EVALUATION_SCOPE_NOT_GRANTED")
    require(record.get("evidence_type") == ("SYNTHETIC" if synthetic else "REAL_PERMITTED"), "PERMISSION_EVIDENCE_TYPE_MISMATCH")
    publication_scope = record.get("publication_scope") or "PRIVATE_OPERATOR_EVALUATION"
    require(publication_scope in {"PRIVATE_OPERATOR_EVALUATION", "PUBLIC_AGGREGATE_ALLOWED"}, "PUBLICATION_SCOPE_UNSUPPORTED")
    require(isinstance(record.get("authority_id"), str) and bool(record["authority_id"].strip()), "PERMISSION_AUTHORITY_ATTESTATION_REQUIRED")
    review = record.get("review") or {}
    require(isinstance(review.get("reviewer_id"), str) and bool(review["reviewer_id"].strip()) and bool(review.get("reviewed_at")), "PERMISSION_REVIEW_ATTESTATION_REQUIRED")
    try:
        require(datetime.fromisoformat(review["reviewed_at"]).tzinfo is not None, "PERMISSION_REVIEW_TIMEZONE_REQUIRED")
    except (ValueError, TypeError):
        raise Refused("PERMISSION_REVIEW_TIMESTAMP_INVALID")
    content = {key: value for key, value in record.items() if key != "review"}
    require(review.get("reviewed_content_sha256") == digest(canonical(content)), "PERMISSION_REVIEW_CONTENT_HASH_MISMATCH")
    evidence = record.get("evidence_files")
    require(isinstance(evidence, list) and bool(evidence), "HASH_BOUND_PERMISSION_EVIDENCE_REQUIRED")
    for item in evidence:
        _hash_match(_path(base, item.get("path")), item.get("sha256"))
    return publication_scope


def _box_for_span(lines: list[dict], start, end):
    selected = [line.get("box") for line in lines if isinstance(start, int) and isinstance(end, int)
                and line.get("text_start", 0) < end and line.get("text_end", 0) > start and line.get("box")]
    return [min(box[0] for box in selected), min(box[1] for box in selected), max(box[2] for box in selected), max(box[3] for box in selected)] if selected else None


def predict_page(image) -> dict:
    """Canonical local OCR plus transparent rules; no optional hosted/NC NLP."""
    from app.services import ocr, nlp_processor as rules
    result = ocr.ocr_image(image)
    text, lines = result.text, result.lines
    fields = rules.extract_numeric_measurements(text, [0])
    attributes = rules.extract_documented_attributes(text)
    rules.assign_measurement_context(text, [0], fields)
    rules.assign_documented_dates(attributes, [0], len(text), fields)
    dates = {name: [a.get("value_text") for a in attributes if a["name"] == name and a.get("value_text")] for name in ("sampling_date", "report_date")}
    for item in fields:
        item["source_bbox"] = _box_for_span(lines, item["source_span_start"], item["source_span_end"])
        item["collection_date"] = dates["sampling_date"][0] if len(set(dates["sampling_date"])) == 1 else None
        item["report_date"] = dates["report_date"][0] if len(set(dates["report_date"])) == 1 else None
    entities = rules.extract_clinical_statements(text, [0])
    for item in entities:
        item["source_bbox"] = _box_for_span(lines, item["entity_start"], item["entity_end"])
    return {"text": text, "fields": fields, "entities": entities, "engine": result.engine, "rotation_degrees": result.rotation_degrees}


def _local_ocr_models() -> list[str]:
    """Require the existing wheel's bundled weights; never download a model."""
    try:
        distribution = importlib.metadata.distribution("rapidocr-onnxruntime")
        paths = [Path(distribution.locate_file(item)) for item in distribution.files or [] if str(item).endswith(".onnx")]
        require(len(paths) >= 3 and all(path.is_file() for path in paths), "BUNDLED_LOCAL_OCR_WEIGHTS_REQUIRED_NO_DOWNLOAD")
        return sorted(digest(file_bytes(path)) for path in paths)
    except importlib.metadata.PackageNotFoundError:
        raise Refused("BUNDLED_LOCAL_OCR_WEIGHTS_REQUIRED_NO_DOWNLOAD")


def _norm(value):
    if value is None or str(value).strip().upper() in {"", "NOT_DOCUMENTED", "NOT DOCUMENTED", "UNKNOWN"}:
        return None
    return " ".join(str(value).casefold().split())


def _analyte(value):
    return re.sub(r"[\s_]", "", _norm(value) or "")


def _overlap(a, b) -> float:
    if not a or not b:
        return 0.
    intersection = max(0., min(a[2], b[2]) - max(a[0], b[0])) * max(0., min(a[3], b[3]) - max(a[1], b[1]))
    return intersection / max((a[2] - a[0]) * (a[3] - a[1]), 1.)


def _pairs(gold, predicted, compatible):
    # Fixed descending source-overlap greedy one-to-one assignment. No value,
    # unit, date or context agreement is used to cherry-pick matching results.
    candidates = sorted([(-_overlap(g["source_bbox"], p.get("source_bbox")), gi, pi)
        for gi, g in enumerate(gold) for pi, p in enumerate(predicted)
        if compatible(g, p) and _overlap(g["source_bbox"], p.get("source_bbox")) >= .5])
    used_g, used_p, pairs = set(), set(), []
    for _, gi, pi in candidates:
        if gi not in used_g and pi not in used_p:
            used_g.add(gi); used_p.add(pi); pairs.append((gi, pi))
    return pairs


def _scores(tp, gold, predicted):
    precision = tp / predicted if predicted else None
    recall = tp / gold if gold else None
    return {"precision": precision, "recall": recall, "f1": 2 * precision * recall / (precision + recall) if precision is not None and recall is not None and precision + recall else 0. if gold or predicted else None,
            "tp": tp, "fn": gold - tp, "fp": predicted - tp, "gold": gold, "predicted": predicted}


def _number_equal(a, b):
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except (InvalidOperation, ValueError):
        return False


def _nlp_artifacts(page, doc_id):
    from app.services.nlp_processor import extract_clinical_statements
    text = page["gold_text"]
    documents = [{"document_id": doc_id, "character_count": len(text), "document_sha256": digest(text.encode("utf-8"))}]
    gold = [{"document_id": doc_id, **{key: entity[key] for key in ("start", "end", "label", "assertion", "negation", "temporality")}} for entity in page["entities"]]
    prediction = [{"document_id": doc_id, "start": item["entity_start"], "end": item["entity_end"], "label": item["category"], "assertion": item["certainty"], "negation": item["negation"], "temporality": item["temporality"]} for item in extract_clinical_statements(text, [0])]
    return documents, gold, prediction


def evaluate(inventory_path: Path, annotations_path: Path, permissions_path: Path, *, synthetic_software_control=False, predictor=None) -> dict:
    inventory, annotations, permissions = (read_json(path) for path in (inventory_path, annotations_path, permissions_path))
    require(inventory.get("schema_version") == "medtwin.independent-full-report-inventory.v1", "FULL_REPORT_INVENTORY_SCHEMA_UNSUPPORTED")
    require(annotations.get("schema_version") == "medtwin.review-document-annotation.v1", "ANNOTATION_ADAPTER_REQUIRED_UNSUPPORTED_SCHEMA")
    require(all(page.get("readability") != "READABLE" or isinstance(page.get("gold_text"), str) and bool(page["gold_text"].strip())
                for page in annotations.get("pages", [])), "FULL_TRANSCRIPTION_REQUIRED_BY_THIS_ANNOTATION_ADAPTER")
    try:
        counts = validate(annotations, require_finalized=True)
    except ValueError as error:
        raise Refused("ANNOTATIONS_NOT_FINALIZED_INDEPENDENT_AND_CONTENT_BOUND") from error
    require(bool(annotations["pages"]), "EMPTY_REFERENCE_REFUSED")
    types = {page["evidence_type"] for page in annotations["pages"]}
    synthetic = types == {"SYNTHETIC"}
    require(types in ({"SYNTHETIC"}, {"REAL_PERMITTED"}), "MIXED_OR_UNDECLARED_REFERENCE_EVIDENCE_TYPE")
    require(synthetic == synthetic_software_control, "SYNTHETIC_CONTROL_REQUIRES_EXPLICIT_SEPARATE_FLAG")
    require(predictor is None or synthetic, "CUSTOM_PREDICTOR_FOR_REAL_REPORTS_FORBIDDEN")
    independence = inventory.get("reference_provenance") or {}
    require(independence.get("independently_checked_full_reports") is True and independence.get("created_without_system_predictions") is True,
            "INDEPENDENT_FULL_REPORT_REFERENCE_ATTESTATION_REQUIRED")
    require(independence.get("target_annotations_complete") is True, "EXHAUSTIVE_TARGET_ANNOTATION_ATTESTATION_REQUIRED")
    require(independence.get("used_for_training_or_tuning") is False and independence.get("predictions_visible_to_annotators") is False
            and independence.get("evaluation_split") == "HELD_OUT_UNEXPOSED", "EXPOSED_OR_UNDECLARED_REFERENCE_REFUSED")
    documents = inventory.get("documents")
    require(isinstance(documents, list) and 1 <= len(documents) <= MAX_DOCUMENTS, "DOCUMENT_COUNT_OUT_OF_BOUNDS")
    annotations_sha = digest(file_bytes(annotations_path))
    gold = {(p["document_id"], p["page"]): p for p in annotations["pages"]}
    require(len(gold) <= MAX_PAGES, "PAGE_COUNT_OUT_OF_BOUNDS")
    validated_pages, pdf_hashes, scopes, source_manifest, document_ids = [], [], [], [], set()
    from app.services.ocr import render_pdf_page
    from PIL import Image
    import pypdfium2
    # Entire source/reference/permission validation completes before first OCR.
    for document in documents:
        document_id = document.get("document_id")
        require(isinstance(document_id, str) and document_id, "DOCUMENT_PSEUDONYM_REQUIRED")
        require(document_id not in document_ids and document.get("source_pdf_sha256") not in pdf_hashes, "DUPLICATE_FULL_REPORT_INPUT_REFUSED")
        document_ids.add(document_id)
        scopes.append(_permission_gate(permissions, permissions_path.parent, document, annotations_sha, synthetic))
        raw = _hash_match(_path(inventory_path.parent, document.get("source_pdf_path")), document.get("source_pdf_sha256"))
        pdf = pypdfium2.PdfDocument(io.BytesIO(raw))
        try: actual_pages = len(pdf)
        finally: pdf.close()
        require(type(document.get("page_count")) is int and document["page_count"] == actual_pages, "ACTUAL_PDF_PAGE_COUNT_MISMATCH")
        page_inventory = document.get("pages")
        require(isinstance(page_inventory, list) and sorted(item.get("page", -1) for item in page_inventory) == list(range(1, actual_pages + 1)), "FULL_REPORT_PAGE_COVERAGE_REQUIRED")
        rendering = document.get("rendering") or {}
        require(rendering.get("engine") == "pypdfium2" and rendering.get("dpi") in {150, 200, 300} and rendering.get("crop") == "FULL_PAGE" and rendering.get("rotation_degrees") == 0, "EXPLICIT_SUPPORTED_FULL_PAGE_RENDERING_REQUIRED")
        for item in page_inventory:
            key = document_id, item["page"]
            require(key in gold, "EVERY_SOURCE_PAGE_REQUIRES_CHECKED_ANNOTATION")
            page = gold[key]
            image_path = _path(inventory_path.parent, item.get("source_image_path"))
            source = _hash_match(image_path, item.get("source_image_sha256"))
            require(item["source_image_sha256"] == page["source_image_sha256"], "GOLD_RASTER_HASH_BINDING_MISMATCH")
            image = Image.open(io.BytesIO(source)).convert("RGB")
            require(image.width * image.height <= 40_000_000, "SOURCE_RASTER_PIXEL_LIMIT_EXCEEDED")
            require(image.size == (page["width"], page["height"]) == (item.get("width"), item.get("height")), "SOURCE_RASTER_DIMENSIONS_MISMATCH")
            rendered = render_pdf_page(raw, item["page"] - 1, rendering["dpi"]).convert("RGB")
            require(rendered.size == image.size and rendered.tobytes() == image.tobytes(), "RASTER_DOES_NOT_MATCH_ACTUAL_FULL_PDF_PAGE")
            image.close(); rendered.close()
            validated_pages.append((page, image_path))
            source_manifest.append((digest(document_id.encode()), item["page"], document["source_pdf_sha256"], page["source_image_sha256"]))
        pdf_hashes.append(document["source_pdf_sha256"])
    require(len(validated_pages) == len(gold) and len({(p["document_id"], p["page"]) for p, _ in validated_pages}) == len(gold), "SOURCE_AND_REFERENCE_PAGE_SETS_DIFFER")
    require(any(page["readability"] == "READABLE" for page, _ in validated_pages), "NO_READABLE_REFERENCE_FOR_THIS_ADAPTER")
    custom_predictor = predictor is not None
    model_hashes = [] if custom_predictor else _local_ocr_models()
    predictor = predictor or predict_page
    predictions, numeric_rows, errors = [], [], Counter()
    nlp_docs, nlp_gold, nlp_prediction = [], [], []
    lab_gold_count = lab_prediction_count = lab_tp = region_gold = region_prediction = region_tp = 0
    from app.services.ocr_evaluation import evaluate_ocr
    from app.services.evaluation_metrics import evaluate_lab_extraction
    from app.services.clinical_nlp_evaluation import evaluate_clinical_nlp
    for page, image_path in validated_pages:
        image = Image.open(io.BytesIO(_hash_match(image_path, page["source_image_sha256"]))).convert("RGB")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            prediction = predictor(image)
        image.close()
        predictions.append({"document_id": page["document_id"], "page": page["page"], "source_image_sha256": page["source_image_sha256"], **prediction})
        if page["readability"] != "READABLE":
            errors["unreadable_pages_with_unverified_machine_text"] += bool(prediction["text"].strip())
            errors["unreadable_page_fields_unscored"] += len(prediction["fields"])
            continue
        doc_id = digest(f"{page['document_id']}:{page['page']}".encode())
        positive = [f for f in page["fields"] if f["value_state"] == "READABLE"]
        unreadable = [f for f in page["fields"] if f["value_state"] == "UNREADABLE"]
        fields = prediction["fields"]
        excluded = {pi for _, pi in _pairs(unreadable, fields, lambda g, p: _analyte(g["analyte"]) == _analyte(p["name"]))}
        errors["unreadable_field_predictions_unscored"] += len(excluded)
        fields = [p for i, p in enumerate(fields) if i not in excluded]
        pairs = _pairs(positive, fields, lambda g, p: _analyte(g["analyte"]) == _analyte(p["name"]))
        matched = dict(pairs)
        lab_gold_count += len(positive); lab_prediction_count += len(fields); lab_tp += len(pairs)
        errors["lab_missing"] += len(positive) - len(pairs); errors["lab_spurious"] += len(fields) - len(pairs)
        for gi, reference in enumerate(positive):
            candidate = fields[matched[gi]] if gi in matched else {}
            numeric_rows.append([doc_id, f"p{page['page']}-f{gi}", digest(reference["analyte"].encode())[:16], reference["value"], candidate.get("value", ""), reference["unit"] or "", candidate.get("unit") or ""])
            if not candidate:
                continue
            errors["lab_value_mismatch"] += not _number_equal(reference["value"], candidate.get("value"))
            for name, expected, actual in (("unit", reference["unit"], candidate.get("unit")), ("comparator", reference.get("comparator") or "=", candidate.get("result_operator") or "="),
                    ("specimen", reference["specimen"], candidate.get("specimen")), ("collection_date", reference["collection_date"], candidate.get("collection_date")),
                    ("report_date", reference["report_date"], candidate.get("report_date"))):
                errors[f"lab_{name}_mismatch"] += _norm(expected) != _norm(actual)
            interval = reference.get("reference_interval")
            errors["lab_reference_interval_mismatch"] += (interval is None and (candidate.get("reference_low") is not None or candidate.get("reference_high") is not None)) or (interval is not None and any(not _number_equal(interval[bound], candidate.get(f"reference_{bound}")) if interval[bound] is not None else candidate.get(f"reference_{bound}") is not None for bound in ("low", "high")))
        docs, gs, ps = _nlp_artifacts(page, doc_id); nlp_docs.extend(docs); nlp_gold.extend(gs); nlp_prediction.extend(ps)
        gold_regions = [{**item, "surface": page["gold_text"][item["start"]:item["end"]]} for item in page["entities"]]
        entity_pairs = _pairs(gold_regions, prediction["entities"], lambda g, p: g["label"] == p["category"] and _norm(g["surface"]) == _norm(p["entity_text"]))
        region_gold += len(gold_regions); region_prediction += len(prediction["entities"]); region_tp += len(entity_pairs)
        for gi, pi in entity_pairs:
            for gold_key, pred_key in (("assertion", "certainty"), ("negation", "negation"), ("temporality", "temporality")):
                errors[f"nlp_source_region_{gold_key}_mismatch"] += gold_regions[gi][gold_key] != prediction["entities"][pi][pred_key]
    gold_ocr = export_ocr(annotations)
    ocr_predictions = {"schema_version": "medtwin.ocr-pages.v1", "artifact_role": "prediction", "pages": [{key: p[key] for key in ("document_id", "page", "source_image_sha256", "text")} for p in predictions if gold[(p["document_id"], p["page"])]["readability"] == "READABLE"]}
    ocr_result = evaluate_ocr(canonical(gold_ocr), canonical(ocr_predictions))
    lab = _scores(lab_tp, lab_gold_count, lab_prediction_count)
    if numeric_rows:
        stream = io.StringIO(); writer = csv.writer(stream); writer.writerow(["patient_id", "source_id", "analyte_code", "reference_value", "predicted_value", "reference_unit", "predicted_unit"]); writer.writerows(numeric_rows)
        lab.update(evaluate_lab_extraction(stream.getvalue().encode(), abs_tolerance=0.)["metrics"])
    nlp_base = {"schema_version": "medtwin.clinical-nlp-spans.v1", "documents": nlp_docs}
    nlp_result = evaluate_clinical_nlp(canonical({**nlp_base, "artifact_role": "gold", "spans": nlp_gold}), canonical({**nlp_base, "artifact_role": "prediction", "spans": nlp_prediction}))
    modules = [ROOT / "backend/app/services" / f"{name}.py" for name in ("ocr", "nlp_processor", "ocr_text", "ocr_evaluation", "clinical_nlp_evaluation", "evaluation_metrics")]
    versions = {}
    for package in ("rapidocr-onnxruntime", "onnxruntime", "pypdfium2", "Pillow"):
        try: versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: versions[package] = "UNAVAILABLE"
    readable = counts["ocr_exportable_pages"]
    return {"schema_version": SCHEMA, "status": "SYNTHETIC_SOFTWARE_CONTROL" if synthetic else "EVALUATED_INDEPENDENT_REPORTS", "evidence_type": "SYNTHETIC" if synthetic else "REAL_PERMITTED",
        "publication_scope": "PUBLIC_AGGREGATE_ALLOWED" if all(scope == "PUBLIC_AGGREGATE_ALLOWED" for scope in scopes) else "PRIVATE_OPERATOR_EVALUATION",
        "clinical_activation": False, "counts": {"documents": len(documents), "pages": len(validated_pages), "readable_pages": readable,
            "unreadable_pages": counts["unreadable_finalized_pages"], "independent_real_documents": 0 if synthetic else len(documents),
            "independent_real_pages": 0 if synthetic else len(validated_pages), "independent_real_readable_pages": 0 if synthetic else readable,
            "annotated_fields": counts["annotated_fields"], "annotated_entities": counts["annotated_entities"]},
        "metrics": {"ocr": ocr_result["metrics"], "lab": lab, "nlp_given_human_text": nlp_result["metrics"],
            "nlp_end_to_end_source_regions": {**_scores(region_tp, region_gold, region_prediction), "matching": "Exact normalized entity surface + category + >=0.5 gold-region coverage; OCR-line-associated boxes, not exact token-box accuracy."}},
        "error_breakdown": dict(errors), "nlp_given_human_text_errors": nlp_result["error_counts"],
        "references": {"all_readable_pages_independently_checked": True, "full_page_text_available": True, "permissions_verified": True,
            "full_report_page_coverage_verified": True, "unexposed_reference_attested": True, "verification_scope": "Source bytes and metadata attestations checked; reviewer identities/legal authority not independently authenticated."},
        "provenance": {"inventory_sha256": digest(file_bytes(inventory_path)), "annotations_sha256": annotations_sha,
            "permissions_sha256": digest(file_bytes(permissions_path)), "source_manifest_sha256": digest(canonical(sorted(source_manifest))),
            "source_pdf_sha256s": sorted(pdf_hashes), "source_page_sha256s": sorted(p["source_image_sha256"] for p, _ in validated_pages),
            "predictions_sha256": digest(canonical(predictions)), "pipeline_sha256": digest(canonical({"code": [digest(file_bytes(p)) for p in [Path(__file__), *modules]], "versions": versions, "ocr_model_sha256s": model_hashes})),
            "versions": versions, "ocr_model_sha256s": model_hashes, "processor_execution": "SYNTHETIC_TEST_DOUBLE" if custom_predictor else "LOCAL_CANONICAL_OCR_AND_RULES",
            "verified_source_bindings": True, "raw_text_persisted": False, "raw_identifiers_persisted": False,
            "optional_external_or_noncommercial_nlp_used": False},
        "limitations": ["Metrics apply only to the supplied held-out independently checked documents, not clinical validation or a tuned improvement.",
            "NLP given human text isolates rule extraction and must not be presented as end-to-end OCR/NLP span accuracy.",
            "Unverified machine output on human-unreadable pages/fields remains explicitly unscored; denominators are reported.",
            "Lab pairing uses analyte and source region, not value agreement; missing and spurious outputs remain in denominators.",
            "Commercial evaluation permission and public aggregate publication consent are separate declarations; absent public consent remains private."]}


def validate_result(payload: dict) -> bool:
    """Minimal read-only envelope check; UI must independently allowlist aggregates."""
    require(payload.get("schema_version") == SCHEMA and payload.get("clinical_activation") is False, "RESULT_SCHEMA_OR_CLINICAL_STATE_INVALID")
    require(payload.get("status") in {"EVALUATED_INDEPENDENT_REPORTS", "SYNTHETIC_SOFTWARE_CONTROL"}, "RESULT_NOT_EVALUATED")
    require(payload.get("provenance", {}).get("verified_source_bindings") is True, "RESULT_SOURCE_BINDINGS_UNVERIFIED")
    return True


def _output_allowed(path: Path) -> bool:
    target = path.resolve()
    if not target.is_relative_to(ROOT):
        return True
    relative = target.relative_to(ROOT)
    if not relative.parts or relative.parts[0] not in {".cache", "artifacts"}:
        return False
    try:
        return subprocess.run(["git", "check-ignore", "--quiet", "--", relative.as_posix()], cwd=ROOT,
                              capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True); parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--permissions", type=Path, required=True); parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--synthetic-software-control", action="store_true")
    args = parser.parse_args(argv)
    try:
        require(_output_allowed(args.out), "PRIVATE_OUTPUT_MUST_BE_OUTSIDE_REPOSITORY_OR_GIT_IGNORED_CACHE_ARTIFACTS")
        require(not args.out.exists(), "OUTPUT_ALREADY_EXISTS_NO_OVERWRITE")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = evaluate(args.inventory.resolve(), args.annotations.resolve(), args.permissions.resolve(), synthetic_software_control=args.synthetic_software_control)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as stream: json.dump(result, stream, indent=2, allow_nan=False); stream.write("\n")
        print(json.dumps({"schema_version": SCHEMA, "status": result["status"], "raw_text_persisted": False})); return 0
    except Refused as error:
        print(json.dumps({"schema_version": SCHEMA, "status": "REFUSED", "refusal_code": str(error), "metrics": None, "clinical_activation": False})); return 2
    except Exception:
        # Never echo parser/OCR exceptions: they can contain patient strings/paths.
        print(json.dumps({"schema_version": SCHEMA, "status": "REFUSED", "refusal_code": "LOCAL_SOURCE_OR_PROCESSING_FAILED_NO_OUTPUT_OVERWRITTEN", "metrics": None, "clinical_activation": False})); return 2


if __name__ == "__main__":
    raise SystemExit(main())
