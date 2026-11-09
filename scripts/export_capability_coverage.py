"""Export declared organ/test/target/checkpoint coverage with current artifact gates.

No model is activated and class names are never promoted to clinical diagnoses.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def build_rows(models):
    rows = []
    for model in models:
        bundle = model["artifact_bundle"]
        if model.get("processor_only") or not bundle.get("checkpoint_path"):
            continue
        segmentation = "segmentation" in model["task"]
        for label in model.get("supported_classes", []):
            if label == "background":
                continue
            rows.append({"organ_or_system": label if segmentation and model["anatomy"] == "multi_system" else model["anatomy"],
                         "test_type": ";".join(model.get("supported_modalities", [])),
                         "target": label, "target_kind": "ANATOMICAL_OR_LESION_MASK" if segmentation else "DECLARED_LABEL",
                         "task": model["task"], "model_id": model["model_id"],
                         "checkpoint_sha256": bundle.get("checkpoint_sha256"),
                         "preprocessing_version": bundle.get("preprocessing_version"),
                         "dataset_version": bundle.get("dataset_version"),
                         "dataset_licence": bundle.get("dataset_license"),
                         "research_artifact_gate_passed": bool(model.get("research_gate", {}).get("allowed")),
                         "research_input": model.get("inference_input") or "dedicated_adapter_or_not_registered",
                         "dedicated_endpoint": model.get("inference_route"),
                         "registry_activation_gate_passed": model["activation"]["eligible"],
                         "registry_validated_flag": model.get("validated", False),
                         "evaluation_report": bundle.get("evaluation_report_path"),
                         "limitations": " ".join(model.get("limitations", []))})
    return rows


def main():
    from app.services.model_registry import list_models
    from datetime import datetime, timezone

    models = list_models()["models"]
    rows = build_rows(models)
    source = ROOT / "model_registry/models.json"
    summary = {"registry_entries": len(models), "checkpoint_backed_entries": len({row["model_id"] for row in rows}),
               "declared_target_rows": len(rows),
               "generic_research_artifact_gates_passed": sum(bool(m.get("research_gate", {}).get("allowed")) for m in models),
               "registry_activation_gates_passed": sum(m["activation"]["eligible"] for m in models)}
    result = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "generator": "scripts/export_capability_coverage.py", "registry_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "summary": summary,
              "scope": "Declared targets with checkpoints and recomputed registry gates; not verified clinical capabilities.",
              "limitations": ["A segmentation label establishes anatomy/lesion scope, not all-organ disease detection.",
                              "Registry activation eligibility is not regulatory approval or independent clinical validation.",
                              "Research artifact gates include evaluation-only survival baselines without upload serving.",
                              "Dedicated third-party adapters have additional source and input requirements.",
                              "A local evaluation can cover fewer structures than a model's declared label list."],
              "capabilities": rows}
    output = ROOT / "dataset_registry/capability_coverage.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    target = ROOT / "docs/data/CAPABILITY_COVERAGE.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
