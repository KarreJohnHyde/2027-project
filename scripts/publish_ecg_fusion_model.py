"""Publish the ECG + age/sex fusion run (ml_training.ecg_fusion): model card and registry entry from its report.

Every number in the card is read from docs/validation/models/ptbxl_ecg_demographic_fusion.json.

    python scripts/publish_ecg_fusion_model.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_training.common import MODEL_CARDS, REPORTS, register_model  # noqa: E402

MODEL_ID = "ptbxl_ecg_demographic_fusion"
DISPLAY = "12-lead ECG + age and sex fusion classifier (research)"
LIMITATIONS = [
    "Single-source internal evaluation (PTB-XL, recordings 1989-1996); no external or clinical validation.",
    "On the same held-out records, adding age and sex did not measurably change macro AUROC over the ECG-only network (paired difference in the report).",
    "Age and sex come from the request or the case's reviewed demographics, never from extracted text; without both the run is refused.",
    "Superclass labels aggregate cardiologist SCP statements; they are not adjudicated clinical diagnoses.",
    "Only 100 Hz, 10-second, 12-lead resting ECGs in the PTB-XL lead order are in scope.",
    "Platt calibration was fitted on the validation fold of the same source; probabilities are not calibrated for any clinical population.",
    "Research-only output; not validated for clinical use.",
]


def _ci(block: dict) -> str:
    return f"{block['low']:.4f} to {block['high']:.4f}" if block.get("status") == "COMPUTED" else "not computed"


def main() -> int:
    report_path = REPORTS / f"{MODEL_ID}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    licence = report["dataset_license"]
    licence_name = licence["name"] if isinstance(licence, dict) else str(licence)
    fusion, alone, difference = report["arms"]["fusion"], report["arms"]["ecg_only"], report["paired_difference"]
    lines = [
        f"# Model card: {DISPLAY}", "",
        f"- **Model id:** `{MODEL_ID}` (registry status `READY_UNVALIDATED`; research-only).",
        "- **Fusion:** intermediate fusion; the ECG network's pooled features (512) are joined with a 16-unit embedding of age and sex "
        "(age/100 clipped to 0.9, age-missing flag, female/male, sex-missing flag) before the classifier.",
        f"- **Data:** PTB-XL 1.0.1 ({licence_name}); publisher folds 1-8 / 9 / 10, patient-disjoint; {report['split_counts']}. "
        f"Age missing for {report['demographic_coverage']['age_missing']} records, sex for {report['demographic_coverage']['sex_missing']}.",
        "- **Comparison arm:** the same ECG network without age and sex, trained with identical data order, augmentation, epochs and seed.",
        f"- **Checkpoint:** `{report['checkpoint']['path']}`, SHA-256 `{report['checkpoint']['sha256']}`.", "",
        f"## Held-out test (fold 10, {report['test_n']} records, evaluated once)", "",
        f"- Fusion macro AUROC {fusion['macro_auroc']:.4f} (95% CI {_ci(fusion['macro_auroc_95ci'])}); macro F1 at validation thresholds {fusion['macro_f1_at_validation_thresholds']:.3f}.",
        f"- ECG only macro AUROC {alone['macro_auroc']:.4f} (95% CI {_ci(alone['macro_auroc_95ci'])}); macro F1 {alone['macro_f1_at_validation_thresholds']:.3f}.",
        f"- Paired difference (fusion minus ECG only) {difference['macro_auroc']:+.4f} (95% CI {_ci(difference['macro_auroc_95ci'])}): **{difference['conclusion'].replace('_', ' ').lower()}**.",
        "- Per class: " + "; ".join(f"{name} {values['auroc']:+.4f} ({_ci(values['auroc_95ci'])})" for name, values in difference["per_class"].items()) + ".",
        "", "## Limitations", "", *[f"- {item}" for item in LIMITATIONS], "",
        f"Full report: `docs/validation/models/{MODEL_ID}.json`.", "",
    ]
    card_path = MODEL_CARDS / f"{MODEL_ID}.md"
    card_path.write_text("\n".join(lines), encoding="utf-8")
    register_model({
        "model_id": MODEL_ID, "display_name": DISPLAY, "domain": "cardiology", "task": "multilabel_ecg_classification", "anatomy": "heart",
        "framework": "pytorch", "adapter": "ml_training.ecg_fusion", "source_repository": "medtwin (ml_training/ecg_fusion.py)",
        "dependency_environment": ".venv", "weights_path": report["checkpoint"]["path"], "device": "cuda_or_cpu",
        "supported_inputs": ["application/wfdb (format 16 header + signal file; 100 Hz, 12-lead, 10 s)",
                             "text/csv (time column in seconds, 12 lead columns, amplitude unit declared by the user; 100 Hz, 10 s)"],
        "supported_modalities": ["ECG"], "inference_input": "ecg_12lead", "demographic_inputs": ["age_years", "sex"],
        "supported_classes": ["NORM", "MI", "STTC", "CD", "HYP"], "status": "READY_UNVALIDATED", "validated": False, "processor_only": False,
        "research_inference": True, "limitations": LIMITATIONS,
        "artifact_bundle": {
            "dataset_version": report["dataset_version"], "dataset_license": licence_name, "split_manifest_path": f"docs/validation/models/{MODEL_ID}.json",
            "task_definition": "Multi-label PTB-XL diagnostic superclasses from SCP statements with diagnostic == 1, from the ECG plus age and sex",
            "label_definition": {"source": "scp_statements.csv diagnostic_class", "classes": ["NORM", "MI", "STTC", "CD", "HYP"]},
            "preprocessing_version": "wfdb16-100hz-10s-leadstd-v1", "checkpoint_path": report["checkpoint"]["path"],
            "checkpoint_sha256": report["checkpoint"]["sha256"], "calibration": report["calibration"],
            "decision_thresholds": report["decision_thresholds"], "abstention_thresholds": None,
            "held_out_predictions_path": report["held_out_predictions"], "evaluation_report_path": f"docs/validation/models/{MODEL_ID}.json",
            "model_card_path": f"docs/models/{MODEL_ID}.md",
        },
        "source_display_name": "PTB-XL 12-lead ECG + age/sex fusion classifier (research)",
    })
    print(json.dumps({"model_id": MODEL_ID, "conclusion": difference["conclusion"], "difference": difference["macro_auroc"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
