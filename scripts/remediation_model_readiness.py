"""Export docs/universal/remediation/MODEL_READINESS.csv from the live registry, through the app's own services.

One row per registry model: anatomy, task, input path, supported inputs, checkpoint SHA-256, dataset licence, research
gate, applicability (OOD) reference, upload runnability, headline held-out metrics, saved external evaluation, and the
separate engineering and scientific status fields of the 2026-11-14 remediation directive. Generated, never hand-edited.

  python scripts/remediation_model_readiness.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.services.model_inference import UPLOAD_INPUTS, head_ct_series_mode  # noqa: E402
from app.services.model_registry import list_models  # noqa: E402

OUT = ROOT / "docs" / "universal" / "remediation" / "MODEL_READINESS.csv"
HEADLINE = ("auroc", "macro_f1", "mean_auroc", "accuracy", "mean_case_macro_dice", "mean_foreground_dice", "harrell_c", "mae", "map_50_95", "ap_50",
            "macro_auroc", "study_level_any_auroc", "sensitivity", "specificity", "s_sensitivity", "v_sensitivity")


def headline(evaluation: dict | None) -> str:
    if not evaluation:
        return ""
    parts = [f"test_n={evaluation.get('test_n')}"] if evaluation.get("test_n") is not None else []
    parts += [f"{key}={float(evaluation[key]):.3f}" for key in HEADLINE if isinstance(evaluation.get(key), (int, float))]
    return "; ".join(parts)


def main() -> int:
    rows = []
    for model in list_models()["models"]:
        bundle = model.get("artifact_bundle") or {}
        gate = model.get("research_gate") or {}
        # Same default as model_inference: a research model without a declared input path is a 2-D image model.
        kind = model.get("inference_input", "image_2d" if model.get("research_inference") else None)
        series = head_ct_series_mode(model)
        runnable_path = ("upload" if kind in UPLOAD_INPUTS else "dicom_series" if kind == "head_ct_series" else "evaluation_evidence_only")
        if series == "per_slice":
            runnable_path += "+dicom_series"
        if (model.get("task") == "tabular_classification" and bundle.get("input_envelope_path")
                and (model.get("validation_readiness") or {}).get("run_scope") == "RESEARCH"):
            runnable_path = "typed_values_in_envelope"
        external = model.get("external_evaluation") or []
        failed = model.get("status") == "FAILED"
        engineering = ("BLOCKED" if failed or not gate.get("allowed", model.get("activation", {}).get("eligible")) else
                       "VERIFIED" if runnable_path != "evaluation_evidence_only" else "IMPLEMENTED_EVALUATION_ONLY")
        scientific = ("VALIDATION_BLOCKED" if failed else "INDEPENDENTLY_EVALUATED_RESEARCH" if external else
                      "INTERNAL_RESEARCH_ONLY" if model.get("held_out_evaluation") else "REFERENCE_DATA_MISSING")
        rows.append({
            "model_id": model["model_id"], "display_name": model.get("display_name"), "anatomy": model.get("anatomy"), "task": model.get("task"),
            "input_path": kind, "runnable_path": runnable_path, "supported_modalities": " ".join(model.get("supported_modalities") or []),
            "registry_status": model.get("status"), "checkpoint_sha256": bundle.get("checkpoint_sha256"),
            "dataset_license": bundle.get("dataset_license"), "research_gate": "ALLOWED" if gate.get("allowed") else ("BLOCKED: " + ",".join(gate.get("blockers") or [])) if gate else "NOT_RESEARCH_MODEL",
            "applicability_reference": "YES" if bundle.get("ood_reference_path") else "NO", "held_out_headline": headline(model.get("held_out_evaluation")),
            "external_evaluation": "; ".join(f"{item['dataset'][:40]} ({item['scope']})" for item in external),
            "engineering_status": engineering, "scientific_status": scientific, "clinical_status": "CLINICALLY_UNVALIDATED",
            "input_pathways": 0 if runnable_path == "evaluation_evidence_only" else len(runnable_path.split("+")),
            "research_status": ("BLOCKED" if engineering == "BLOCKED" else
                                "EXPLORATORY" if (model.get("validation_readiness") or {}).get("run_scope") == "EXPLORATORY_ONLY" else
                                "RESEARCH_ACTIVE" if runnable_path != "evaluation_evidence_only" else "READY_FOR_INTEGRATION"),
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["anatomy"] or "", row["model_id"])))
    counts = {}
    for row in rows:
        counts[row["scientific_status"]] = counts.get(row["scientific_status"], 0) + 1
    research = {}
    for row in rows:
        research[row["research_status"]] = research.get(row["research_status"], 0) + 1
    # Unique checkpoints and input pathways are counted separately: one model can serve several pathways.
    print(json.dumps({"unique_models": len(rows), "by_research_status": research, "by_scientific_status": counts,
                      "unique_models_runnable": sum(row["input_pathways"] > 0 and row["research_status"] == "RESEARCH_ACTIVE" for row in rows),
                      "input_pathways_runnable": sum(row["input_pathways"] for row in rows if row["research_status"] == "RESEARCH_ACTIVE"),
                      "not_in_registry_still_training": ["mri_hippocampus_segresnet", "mri_prostate_zones_segresnet", "ct_spleen_segresnet",
                                                         "gastrovision class-weighting experiment (development only)"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
