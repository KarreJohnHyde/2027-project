"""Actual local OCR/evaluator smoke on an original synthetic printed report.

Generated reference/permission metadata is explicitly a software control, never
a real human approval or independent clinical evidence. Fixtures stay ignored.
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
from scripts import evaluate_independent_reports as evaluator
from scripts.review_document_annotations import annotation_digest


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    from PIL import Image, ImageDraw, ImageFont
    from app.services.ocr import render_pdf_page
    directory = ROOT / ".cache" / "independent-report-actual-ocr" / uuid.uuid4().hex
    proof_path = ROOT / "artifacts/finalization-2026-11-13/independent-report-tools/proof.json"
    for target in (directory / "aggregate.json", proof_path):
        assert subprocess.run(["git", "check-ignore", "--quiet", "--", target.relative_to(ROOT).as_posix()], cwd=ROOT).returncode == 0, "Control outputs must remain ignored"
    directory.mkdir(parents=True)
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof = {"schema_version": "medtwin.independent-report-actual-ocr-smoke.v1", "started_at": datetime.now(timezone.utc).isoformat(),
        "evidence_type": "SYNTHETIC_SOFTWARE_CONTROL", "real_patient_data_used": False, "independent_real_documents": 0,
        "independent_real_pages": 0, "human_legal_or_clinical_approval": False, "checks": [], "clinical_accuracy_claim": False}
    try:
        printed = "Glucose 5.2 mmol/L"
        image = Image.new("RGB", (800, 500), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default(size=38)
        position = (60, 90)
        box = list(draw.textbbox(position, printed, font=font))
        draw.text(position, printed, fill="black", font=font)
        pdf_path = directory / "synthetic-original.pdf"
        image.save(pdf_path, "PDF", resolution=150, quality=98)
        raw = pdf_path.read_bytes()
        raster = render_pdf_page(raw, 0, 150).convert("RGB")
        raster_path = directory / "synthetic-full-page.png"; raster.save(raster_path)
        now = datetime.now(timezone.utc).isoformat()
        page = {"document_id": "synthetic-programmatic-report-control", "page": 1,
            "source_image_sha256": evaluator.digest(raster_path.read_bytes()), "width": raster.width, "height": raster.height,
            "deidentified": True, "permission_scope": "Original generated synthetic software control only; no real report or human permission asserted.",
            "evidence_type": "SYNTHETIC", "readability": "READABLE", "gold_text": printed, "unreadable_reason": None,
            "fields": [{"analyte": "glucose", "value": "5.2", "value_state": "READABLE", "unit": "mmol/L", "specimen": None,
                "collection_date": None, "report_date": None, "reference_interval": None, "comparator": None,
                "assertion": "CERTAIN", "negation": "AFFIRMED", "temporality": "CURRENT", "source_bbox": box}], "entities": [],
            "review": {"status": "FINALIZED", "annotator_id": "SYNTHETIC-PROGRAMMATIC-GENERATOR", "reviewer_id": "SYNTHETIC-PROGRAMMATIC-CONTROL",
                "independently_transcribed": True, "critical_fields_checked": True, "reviewed_at": now,
                "attestation_scope": "SYNTHETIC_TEST_PROTOCOL_ONLY_NOT_A_HUMAN_APPROVAL"}}
        page["review"]["reviewed_content_sha256"] = annotation_digest(page)
        annotations_path = directory / "synthetic-reference.json"
        write(annotations_path, {"schema_version": "medtwin.review-document-annotation.v1", "pages": [page]})
        inventory_path = directory / "inventory.json"
        write(inventory_path, {"schema_version": "medtwin.independent-full-report-inventory.v1", "reference_provenance": {
            "independently_checked_full_reports": True, "target_annotations_complete": True, "created_without_system_predictions": True,
            "used_for_training_or_tuning": False, "predictions_visible_to_annotators": False, "evaluation_split": "HELD_OUT_UNEXPOSED",
            "attestation_scope": "PROGRAMMATIC_SYNTHETIC_CONTROL_ONLY"}, "documents": [{"document_id": page["document_id"],
            "source_pdf_path": pdf_path.name, "source_pdf_sha256": evaluator.digest(raw), "page_count": 1,
            "rendering": {"engine": "pypdfium2", "dpi": 150, "crop": "FULL_PAGE", "rotation_degrees": 0},
            "pages": [{"page": 1, "source_image_path": raster_path.name, "source_image_sha256": page["source_image_sha256"],
                "width": raster.width, "height": raster.height}]}]})
        evidence = directory / "synthetic-control-scope.txt"
        evidence.write_text("Original generated software-control image and fixed literal reference; no patient source, legal grant or real human approval. Local test only.\n", encoding="utf-8")
        permission = {"source_pdf_sha256": evaluator.digest(raw), "annotations_sha256": evaluator.digest(annotations_path.read_bytes()),
            "commercial_evaluation_allowed": True, "scope": "LOCAL_COMMERCIAL_DEVELOPMENT_EVALUATION", "evidence_type": "SYNTHETIC",
            "publication_scope": "PRIVATE_OPERATOR_EVALUATION", "authority_id": "SYNTHETIC-CONTROL-GENERATOR",
            "attestation_scope": "GENERATED_SYNTHETIC_CONTROL_NOT_REAL_PERMISSION", "evidence_files": [{"path": evidence.name, "sha256": evaluator.digest(evidence.read_bytes())}]}
        permission["review"] = {"reviewer_id": "SYNTHETIC-CONTROL-SCOPE-CHECK", "reviewed_at": now,
            "reviewed_content_sha256": evaluator.digest(evaluator.canonical(permission)), "human_approval": False}
        permissions_path = directory / "permissions.json"; write(permissions_path, {"schema_version": "medtwin.independent-report-permissions.v1", "records": [permission]})
        source_paths = [pdf_path, raster_path, annotations_path, inventory_path, permissions_path, evidence]
        before = [evaluator.digest(path.read_bytes()) for path in source_paths]
        aggregate_path = directory / "aggregate.json"
        completed = subprocess.run([sys.executable, str(ROOT / "scripts/evaluate_independent_reports.py"), "--inventory", str(inventory_path),
            "--annotations", str(annotations_path), "--permissions", str(permissions_path), "--out", str(aggregate_path), "--synthetic-software-control"],
            cwd=ROOT, capture_output=True, text=True, timeout=150)
        proof["command_exit_code"] = completed.returncode
        # Child output is a sanitized envelope only; never propagate stderr/paths.
        assert completed.returncode == 0, "Canonical evaluator child refused the synthetic smoke"
        result = json.loads(aggregate_path.read_text(encoding="utf-8"))
        checks = {
            "canonical_local_processor_used": result["provenance"]["processor_execution"] == "LOCAL_CANONICAL_OCR_AND_RULES",
            "synthetic_status_preserved": result["status"] == "SYNTHETIC_SOFTWARE_CONTROL",
            "independent_real_counts_remain_zero": result["counts"]["independent_real_documents"] == result["counts"]["independent_real_pages"] == 0,
            "full_page_bindings_verified": result["provenance"]["verified_source_bindings"] and result["references"]["full_report_page_coverage_verified"],
            "actual_ocr_read_characters": result["metrics"]["ocr"]["predicted_characters"] > 0,
            "actual_rule_lab_extracted_numeric_field": result["metrics"]["lab"]["predicted"] > 0,
            "original_sources_unchanged": before == [evaluator.digest(path.read_bytes()) for path in source_paths],
            "no_raw_text_or_paths_in_aggregate": printed not in aggregate_path.read_text(encoding="utf-8") and str(directory) not in aggregate_path.read_text(encoding="utf-8"),
            "raw_text_and_identifiers_not_persisted": result["provenance"]["raw_text_persisted"] is False and result["provenance"]["raw_identifiers_persisted"] is False,
            "existing_local_ocr_weights_fingerprinted": len(result["provenance"]["ocr_model_sha256s"]) >= 3,
        }
        proof["checks"] = [{"name": name, "passed": bool(passed)} for name, passed in checks.items()]
        proof["technical_counts"] = {"documents": result["counts"]["documents"], "pages": result["counts"]["pages"],
            "ocr_predicted_characters": result["metrics"]["ocr"]["predicted_characters"], "rule_lab_predicted_fields": result["metrics"]["lab"]["predicted"]}
        proof["aggregate_sha256"] = evaluator.digest(aggregate_path.read_bytes())
        proof["pipeline_sha256"] = result["provenance"]["pipeline_sha256"]
        proof["status"] = "VERIFIED_ACTUAL_SYNTHETIC_OCR_EVALUATOR_SMOKE" if all(checks.values()) else "FAILED_TECHNICAL_CONTROL"
    except Exception as error:
        proof["status"] = "FAILED_TECHNICAL_CONTROL"; proof["error_type"] = type(error).__name__
    proof["finished_at"] = datetime.now(timezone.utc).isoformat(); write(proof_path, proof)
    print(json.dumps({"status": proof["status"], "passed": sum(check["passed"] for check in proof["checks"]), "checks": len(proof["checks"]), "command_exit_code": proof.get("command_exit_code")}))
    return 0 if proof["status"] == "VERIFIED_ACTUAL_SYNTHETIC_OCR_EVALUATOR_SMOKE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
