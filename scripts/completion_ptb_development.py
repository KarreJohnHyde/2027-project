"""Isolated age/sex-only PTB-XL development experiment, no test evaluation.

Two prespecified logistic baselines (unweighted / balanced) fit publisher folds
1–8 and report fold-9 validation results only. Fold-10 labels are never parsed.
No original checkpoint, serving registry, threshold or clinical state is changed.
"""
from __future__ import annotations
import argparse
import ast
import csv
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import hashlib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))


def read_development(metadata_path: Path, statements_path: Path) -> dict:
    from app.services.ecg_inference import demographic_vector
    from ml_training.ptbxl import SUPERCLASSES
    with statements_path.open(newline="", encoding="utf-8-sig") as stream:
        diagnostic = {row[""]: row["diagnostic_class"] for row in csv.DictReader(stream) if row.get("diagnostic") in {"1", "1.0"}}
    result = {"train": [], "validation": []}
    skipped_test = 0
    with metadata_path.open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            fold = int(row["strat_fold"])
            if not 1 <= fold <= 10:
                raise ValueError("Unknown publisher fold; expected 1–10")
            # This branch precedes parsing any labels/features from test rows.
            if fold == 10:
                skipped_test += 1
                continue
            classes = {diagnostic[key] for key in ast.literal_eval(row["scp_codes"]) if key in diagnostic}
            classes &= set(SUPERCLASSES)
            if not classes:
                continue
            age = float(row["age"]) if row.get("age", "").strip() else None
            sex = {"0": "M", "0.0": "M", "1": "F", "1.0": "F"}.get(row.get("sex"))
            result["validation" if fold == 9 else "train"].append({"record_id": row["ecg_id"], "patient_id": row["patient_id"],
                "features": demographic_vector(age, sex), "labels": [int(label in classes) for label in SUPERCLASSES],
                "age": age, "sex": sex})
    train_patients = {r["patient_id"] for r in result["train"]}
    validation_patients = {r["patient_id"] for r in result["validation"]}
    if train_patients & validation_patients:
        raise ValueError("Development patient leakage across publisher folds")
    if not result["train"] or not result["validation"]:
        raise ValueError("Empty train or validation cohort")
    return {**result, "skipped_test_rows_without_label_parsing": skipped_test,
            "patient_disjoint": True, "features": ["age_div100_clipped0_0.9", "age_missing", "female", "sex_missing"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rights-registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/completion-2026-11-13/research")
    args = parser.parse_args()
    # Existing gate before reading patient metadata, building arrays or fitting.
    from ml_training.volumetric_manifest import enforce_training_license
    rights = enforce_training_license({"dataset_id": "ptb-xl-1.0.1"}, args.rights_registry)
    from ml_training.ptbxl import DATASET_DIR, SUPERCLASSES, publisher_checksums, verify_files
    integrity = verify_files(["ptbxl_database.csv", "scp_statements.csv"], publisher_checksums())
    parts = read_development(DATASET_DIR / "ptbxl_database.csv", DATASET_DIR / "scp_statements.csv")
    from sklearn.linear_model import LogisticRegression
    from app.services.evaluation_metrics import _auroc, _average_precision
    from app.services.universal_arena import _reliability
    x = np.asarray([r["features"] for r in parts["train"]], dtype=float)
    y = np.asarray([r["labels"] for r in parts["train"]], dtype=int)
    vx = np.asarray([r["features"] for r in parts["validation"]], dtype=float)
    vy = np.asarray([r["labels"] for r in parts["validation"]], dtype=int)
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    results = {}
    for arm, weighting in (("unweighted", None), ("balanced", "balanced")):
        scores, coefficients = [], []
        for index, label in enumerate(SUPERCLASSES):
            if len(np.unique(y[:, index])) != 2:
                raise ValueError("Both training classes required for every target")
            model = LogisticRegression(C=1., class_weight=weighting, max_iter=500, random_state=20261113)
            model.fit(x, y[:, index])
            scores.append(model.predict_proba(vx)[:, 1])
            coefficients.append({"label": label, "coef": model.coef_.tolist(), "intercept": model.intercept_.tolist()})
        probability = np.stack(scores, axis=1)
        per_class = [{"label": label, "auroc": _auroc(vy[:, i], probability[:, i]), "average_precision": _average_precision(vy[:, i], probability[:, i]),
                      "reliability": _reliability(vy[:, i], probability[:, i])} for i, label in enumerate(SUPERCLASSES)]
        prediction_path = output / f"metadata-{arm}-validation-predictions.csv"
        with prediction_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["record_id", "patient_id", *[f"label_{label}" for label in SUPERCLASSES], *[f"p_{label}" for label in SUPERCLASSES]])
            for row, labels, p in zip(parts["validation"], vy, probability):
                writer.writerow([row["record_id"], row["patient_id"], *labels.tolist(), *p.tolist()])
        coefficients_path = output / f"metadata-{arm}-coefficients.json"
        coefficients_path.write_text(json.dumps({"arm": arm, "features": parts["features"], "models": coefficients}, indent=2) + "\n")
        results[arm] = {"macro_auroc": float(np.mean([entry["auroc"] for entry in per_class])),
            "macro_average_precision": float(np.mean([entry["average_precision"] for entry in per_class])),
            "macro_brier": float(np.mean([entry["reliability"]["brier"] for entry in per_class])), "per_class": per_class,
            "validation_predictions_sha256": hashlib.sha256(prediction_path.read_bytes()).hexdigest(),
            "coefficients_sha256": hashlib.sha256(coefficients_path.read_bytes()).hexdigest()}
    # Production contract stress test: missing data must refuse before prediction.
    from app.services.model_inference import resolve_demographics, InferenceNotPermitted
    sample = next(row for row in parts["validation"] if row["age"] is not None and 0 <= row["age"] <= 120 and row["sex"] is not None)
    scenarios = {"complete": {"age_years": sample["age"], "sex": sample["sex"]}, "age_missing": {"sex": sample["sex"]},
                 "sex_missing": {"age_years": sample["age"]}, "both_missing": {}}
    missingness = []
    for name, options in scenarios.items():
        try:
            resolve_demographics(SimpleNamespace(case_id=0), options, None)
            status, reason = "INPUT_ACCEPTED_NO_PREDICTION_EXECUTED", None
        except InferenceNotPermitted as exc:
            status, reason = "REFUSED_BEFORE_MODEL_EXECUTION", str(exc)
        missingness.append({"scenario": name, "status": status, "reason": reason, "model_prediction_executed": False})
    report = {"schema_version": "medtwin.ptb-metadata-development.v1", "status": "DEVELOPMENT_COMPLETE_TEST_NOT_EVALUATED",
        "summary": "Two prespecified from-scratch age/sex-only logistic baselines fit publisher train folds and evaluated on validation fold only; missing-demographic serving paths refuse before model execution. No weak deployed model is claimed improved.",
        "rights": rights, "publisher_metadata_integrity": integrity, "dataset": "PTB-XL 1.0.1", "labels": SUPERCLASSES,
        "source_license": "CC BY 4.0; attribution in rights-evidence/ATTRIBUTION.md", "train_n": len(y), "validation_n": len(vy),
        "skipped_test_rows_without_label_parsing": parts["skipped_test_rows_without_label_parsing"], "patient_disjoint": parts["patient_disjoint"],
        "features": parts["features"], "predeclared_protocol": {"C": 1., "max_iter": 500, "seed": 20261113,
            "arms": ["unweighted", "balanced"], "feature_scaling": "Fixed published demographic encoding; no validation/test fit", "selection": "No winner promoted; validation-only descriptive comparison"},
        "arms": results, "balanced_minus_unweighted_validation_macro_auroc": results["balanced"]["macro_auroc"] - results["unweighted"]["macro_auroc"],
        "missing_demographics_contract": missingness, "clinical_activation": False, "registry_promotion": False,
        "original_checkpoint_modified": False, "test_evaluated": False,
        "limitations": ["Demographics alone do not constitute an ECG interpretation or diagnosis.", "Validation-fold descriptive results, not an independently evaluated clinical predictor.",
            "This compatible-source software experiment does not repair the six blocked data families or prove fusion superiority."]}
    path = output / "development-experiment.json"
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(path), "status": report["status"], "train_n": len(y), "validation_n": len(vy),
                      "arms": {arm: {key: value for key, value in item.items() if key.startswith("macro")} for arm, item in results.items()}}, indent=2))


if __name__ == "__main__":
    main()
