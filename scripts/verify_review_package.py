"""Verify current review evidence consistency, never grant clinical clearance."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts/review-2026-11-13"
DOC = ROOT / "docs/review-2026-11-13"


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    checks = []

    def check(name, value, detail=None):
        checks.append({"name": name, "passed": bool(value), "detail": detail})

    required = ["IMPLEMENTATION_STATUS", "RUNTIME_VERIFICATION", "DATASET_LEAKAGE_AUDIT", "DOCUMENT_EVALUATION",
                "INPUT_ROUTING_EVALUATION", "INFERENCE_PARITY", "FUSION_FORECASTING", "ARCHITECTURE", "DEMO_GUIDE", "REMAINING_BLOCKERS"]
    for name in required:
        check(f"Required {name} report", (DOC / f"MEDTWIN_{name}_2026-11-13.md").is_file())
    workflows = load(ART / "workflows/workflow-results.json")["workflows"]
    document, image = workflows["document"], workflows["imaging"]
    check("Document and image workflows verified", document["status"] == image["status"] == "VERIFIED")
    check("All synthetic numeric, specimen and method controls checked", all(document.get(name) == 18 for name in (
        "synthetic_values_checked", "synthetic_value_matches", "synthetic_specimens_checked", "synthetic_specimen_matches",
        "synthetic_methods_checked", "synthetic_method_matches")))
    evidence = load(ART / "workflows/document-evidence.json")
    expected = {
        "hemoglobin": ("g/dL", 12.0, 15.5), "white_blood_cell_count": ("10^9/L", 4.0, 11.0),
        "platelet_count": ("10^9/L", 150.0, 410.0), "glucose": ("mg/dL", 70.0, 100.0),
        "creatinine": ("mg/dL", 0.6, 1.1), "urea": ("mg/dL", 15.0, 40.0),
        "sodium": ("mmol/L", 135.0, 145.0), "potassium": ("mmol/L", 3.5, 5.1), "hba1c": ("%", 4.0, 5.6),
    }
    field_rows = evidence["measurements"]
    check("All 18 synthetic canonical units and printed intervals match", len(field_rows) == 18 and all(
        (row["unit"], row["reference_low"], row["reference_high"]) == expected.get(row["name"]) for row in field_rows))
    dates = {upload["id"]: date for upload, date in zip(evidence["uploads"], ("2026-03-14", "2026-06-18"))}
    check("All 18 synthetic collection dates match their source", all(row["documented_date"] == dates[row["source_file_id"]] for row in field_rows))
    check("Nine descriptive comparisons; insufficient forecast remains unavailable", document["numeric_delta_count"] == 9
          and document["forecast_status"] == "NOT_ELIGIBLE")
    persistence = load(ART / "workflows/persistence.json")
    check("Restart persistence refers to current demonstrated document case", persistence.get("status") == "VERIFIED"
          and persistence.get("document_case_id") == document["case_id"] and persistence.get("image_run_id") == image["run_id"])
    check("Unsupported inputs refused without predictions", len(image["refusals"]) == 2
          and all(row["status"] == "REFUSED" and not row["prediction_produced"] for row in image["refusals"]))
    ui = load(ART / "selected-browser/selected-workflows.json")
    check("Actual image/document UI exports and context assertions passed", ui["status"] == "VERIFIED"
          and all(row["passed"] for row in ui["checks"])
          and any("specimen" in row["name"].lower() for row in ui["checks"]), len(ui["checks"]))
    check("UI document case is current", ui.get("document_selected", {}).get("case_id") == document["case_id"])
    trained = load(ART / "trained-browser-rebuilt/walkthrough.json")
    trained_section = trained.get("sections", {}).get("trained", {})
    check("Final rebuilt saved-report viewer passes every report", trained.get("assertions", {}).get("all_passed")
          and trained_section.get("passed") == trained_section.get("total") == 20)
    routes = load(ART / "trained-browser-final/walkthrough.json")
    check("Rechecked routes and prognosis pass", routes.get("assertions", {}).get("sections", {}).get("routes")
          and routes.get("assertions", {}).get("sections", {}).get("prognosis"))
    parity = load(ART / "parity-controls-final.json")
    ecg = next(row for row in parity["results"] if row["model_id"] == "ptbxl_ecg_baseline")
    historical_image = next(row for row in parity["results"] if row["model_id"] == image["model_id"])
    check("ECG actual checkpoint parity meets predefined tolerance", ecg["status"] == "VERIFIED_BOUNDED_PARITY")
    check("Historical image mismatch remains disclosed", historical_image["status"] == "DIFFERENCES_RECORDED")
    recovery = load(ART / "worker-recovery.json")
    check("Actual crash child and recovery processes recorded", [row["exit_code"] for row in recovery["steps"]] == [0, 73, 0, 0])
    audit = load(ART / "data-audit.json")
    check("Bounded dataset audit retains known overlap findings", audit["summary"]["errors"] == 0
          and audit["summary"]["manifests_with_crossing_groups"] >= 2, audit["summary"])
    experiments = load(ART / "data-experiments.json")
    check("Denied real training remains denied", len(experiments["experiments"]) == 6
          and all(row["live_training_gate"]["status"] == "BLOCKED" for row in experiments["experiments"]))
    normalization = load(ART / "document-normalization-comparison.json")
    check("No independent real annotation fabricated", normalization["independently_annotated_real_pages"] == 0)
    contracts = load(DOC / "MEDTWIN_WORKFLOW_CONTRACTS_2026-11-13.json")
    registry = load(ROOT / "model_registry/models.json")["models"]
    check("Pre-existing model-registry working changes preserved", hashlib.sha256((ROOT / "model_registry/models.json").read_bytes()).hexdigest()
          == "b56979e0591788b1d588fa11c590e0378a1f98db1114612df702f816aa5b65b7")
    model = next(row for row in registry if row["model_id"] == image["model_id"])
    check("Frozen image checkpoint matches current registry", contracts["B"]["checkpoint_sha256"] == model["artifact_bundle"]["checkpoint_sha256"])
    check("Failed kidney target not activated", next(row for row in registry if row["model_id"] == "ct_kidney_tumour_segresnet")["status"] == "FAILED")
    raw = (ART / "backend-final.log").read_bytes()
    log = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig", errors="replace")
    summaries = [line for line in log.splitlines() if re.search(r"\d+ passed", line)]
    check("Final complete backend run finished without failures", bool(summaries) and "failed" not in summaries[-1], summaries[-1] if summaries else "NO_FINAL_SUMMARY")
    with (DOC / "MEDTWIN_MODEL_RESULTS_2026-11-13.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    new = [row for row in rows if row["measurement_origin"].startswith("NEW_")]
    check("New controls remain separate from recorded cohort evaluations", len(new) == 3
          and all("NOT_" in row["measurement_origin"] for row in new))
    for row in new:
        path = ROOT / row["report_path"]
        check(f"CSV source hash {row['model_id']}", path.is_file()
              and hashlib.sha256(path.read_bytes()).hexdigest() == row["report_sha256"])
    result = {"recorded_at": datetime.now(timezone.utc).isoformat(),
              "scope": "EVIDENCE_PACKAGE_CONSISTENCY_NOT_CLINICAL_CLEARANCE",
              "blocked_requirements": ["independent real-report gold evaluation", "new real model training rights", "strict historical image-mask equality", "clinical/commercial deployment clearance"],
              "checks": checks, "passed": sum(row["passed"] for row in checks), "total": len(checks),
              "all_passed": all(row["passed"] for row in checks)}
    (ART / "package-verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "total": result["total"], "all_passed": result["all_passed"],
                      "failed": [row for row in checks if not row["passed"]]}, indent=2))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
