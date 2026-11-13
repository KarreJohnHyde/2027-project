"""Read-only reproducible catalogue/schema/registered-target and live-file gate audit.

This verifies catalogue integrity and current research preflight only. It does not
execute inference, estimate accuracy, open a case, train a model or activate one.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from app.services import universal_catalogue as catalogue

REQUIRED_SYSTEMS = {
    "neurological", "cardiovascular", "respiratory", "hepatobiliary", "urinary", "pancreatic", "gastrointestinal",
    "skeletal", "musculoskeletal", "endocrine", "haematological", "immune-lymphatic", "dermatological", "ophthalmic",
    "ent", "oral-dental", "breast", "female-reproductive", "male-reproductive", "maternal-fetal", "vascular",
    "infectious", "genetic-metabolic", "mental-behavioural", "systemic",
}


def audit() -> dict:
    base, entries, revision = catalogue.catalogue_data()
    models = {m["model_id"]: m for m in catalogue._registry_models()}
    invalid = [{"concept_id": row["id"], **link} for row in entries for link in row["model_targets"]
               if link["model_id"] not in models or not catalogue._target_matches(models[link["model_id"]], link["target"])]
    condition_counts = {s["id"]: sum(row["kind"] == "condition" and s["id"] in row["system_ids"] for row in entries)
                        for s in base["systems"]}
    missing = sorted(REQUIRED_SYSTEMS - condition_counts.keys())
    empty = sorted(s for s in REQUIRED_SYSTEMS if condition_counts.get(s, 0) == 0)
    return {
        "schema_version": "medtwin.universal-catalogue-verification.v1",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "verification_scope": "CATALOGUE_SCHEMA_REFERENCE_TARGETS_AND_LIVE_FILE_PREFLIGHT_ONLY",
        "command": "python scripts/audit_universal_catalogue.py --output <explicit-report.json>",
        "source_specification_sha256": base["source_sha256"],
        "catalogue_file_sha256": hashlib.sha256(catalogue.CATALOGUE_PATH.read_bytes()).hexdigest(),
        "data_version": revision,
        "system_count": len(base["systems"]), "curated_entries": len(base["entries"]), "total_entries": len(entries),
        "entry_kinds": dict(Counter(row["kind"] for row in entries)),
        "condition_count_by_system": condition_counts,
        "missing_required_systems": missing, "required_systems_without_conditions": empty,
        "invalid_target_links": invalid, "catalogue_checks_passed": not (invalid or missing or empty),
        "actual_registry_capabilities": catalogue.capabilities(),
        "separate_test_command": "python -m pytest backend/tests/test_universal_catalogue.py -q",
        "limitations": [
            "No official licensed ICD-11 or other disease terminology release was supplied; curated condition code mappings remain empty.",
            "Existing LOINC mappings remain RELATED/CURATED_UNVERIFIED; no verified official-release mapping is claimed.",
            "This command does not execute pytest, inference, training, accuracy evaluation or clinical release.",
            "Actual input permissions, modality, quality, OOD, channel order and geometry remain checked at execution.",
            "Existing atlas terms retain their source licence; coarse system and schematic organ links are not patient registration.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit()
    # Only the explicitly selected report is written; all source registries and
    # checkpoints remain read-only. The containing directory must exist.
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "catalogue_checks_passed": report["catalogue_checks_passed"],
                      "systems": report["system_count"], "entries": report["total_entries"],
                      "models": report["actual_registry_capabilities"]["model_count"],
                      "capability_states": dict(Counter(m["capability_state"] for m in report["actual_registry_capabilities"]["items"]))}, indent=2))
    return 0 if report["catalogue_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
