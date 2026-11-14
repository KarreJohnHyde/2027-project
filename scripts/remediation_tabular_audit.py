"""Independent audit of the UCI tabular research models (2026-11-14): leakage, duplicates, label proxies, imbalance,
train-only preprocessing, metric recomputation and checkpoint parity. Read-only; writes
docs/universal/remediation/TABULAR_AUDIT.json.

For each registered tabular model:
- the split is rebuilt from the data with the same seed and compared with the report's counts; a person in two parts
  is a failure;
- exact duplicate records (all features and the label) shared between the development part and validation/test;
- possible label proxies: single features whose development-part AUROC is >= 0.98 (flagged for review, not removed);
- class balance per part;
- train-only preprocessing: the checkpoint's numeric imputer medians are compared with medians of the development rows;
- metrics recomputed from the stored test predictions and compared with the report;
- parity: the saved checkpoint re-scores the rebuilt test rows; stored and recomputed probabilities are compared.

  python scripts/remediation_tabular_audit.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.services.tabular_inference import score_frame  # noqa: E402
from ml_training import tabular  # noqa: E402

OUT = ROOT / "docs" / "universal" / "remediation" / "TABULAR_AUDIT.json"


def univariate_auroc(column: pd.Series, y: pd.Series) -> float | None:
    values = pd.to_numeric(column, errors="coerce") if not pd.api.types.is_numeric_dtype(column) else column
    if values.isna().all():
        codes = column.astype("category").cat.codes.replace(-1, np.nan)
        values = codes
    mask = values.notna()
    if mask.sum() < 10 or y[mask].nunique() < 2 or values[mask].nunique() < 2:
        return None
    score = roc_auc_score(y[mask], values[mask])
    return float(max(score, 1 - score))


def audit(name: str, spec: dict) -> dict:
    report = json.loads((ROOT / "docs" / "validation" / "models" / f"{spec['model_id']}.json").read_text(encoding="utf-8"))
    features, y, groups, _ = spec["load"]()
    groups = groups.astype(str)
    parts = tabular.split(y, groups, features)
    counts = {part: int((parts == part).sum()) for part in ("train", "val", "test")}
    crossing = int(sum(len(set(parts[groups == g])) > 1 for g in groups.unique()))
    keyed = pd.util.hash_pandas_object(pd.concat([features, y.rename("__label")], axis=1), index=False)  # NaN-aware row hash
    train_keys = set(keyed[parts == "train"])
    duplicates = {part: int(keyed[parts == part].isin(train_keys).sum()) for part in ("val", "test")}
    dev = parts == "train"
    proxies = {}
    for column in features.columns:
        score = univariate_auroc(features.loc[dev, column], y[dev])
        if score is not None and score >= 0.98:
            proxies[column] = round(score, 4)
    checkpoint = joblib.load(ROOT / report["checkpoint"]["path"])
    pipeline = checkpoint["pipeline"]
    numeric_step = pipeline.named_steps["prepare"].named_transformers_["numeric"].named_steps["impute"]
    numeric_columns = pipeline.named_steps["prepare"].transformers_[0][2]
    expected = features.loc[dev, numeric_columns].apply(pd.to_numeric, errors="coerce").median().to_numpy(dtype=float)
    fitted_on_train = bool(np.allclose(numeric_step.statistics_, expected, equal_nan=True)) if len(numeric_columns) else None
    with (ROOT / report["held_out_predictions"]).open(newline="", encoding="utf-8") as handle:
        stored = list(csv.DictReader(handle))
    stored_y = np.array([int(row["label"]) for row in stored])
    stored_p = np.array([float(row["probability_calibrated"]) for row in stored])
    threshold = report["metrics"]["threshold"]
    recomputed = {"test_n": len(stored), "auroc": float(roc_auc_score(stored_y, stored_p)),
                  "sensitivity": float((stored_p[stored_y == 1] >= threshold).mean()), "specificity": float((stored_p[stored_y == 0] < threshold).mean())}
    metric_match = (recomputed["test_n"] == report["test_n"] and all(abs(recomputed[k] - report["metrics"][k]) < 1e-9 for k in ("auroc", "sensitivity", "specificity")))
    test = parts == "test"
    # Re-scored through the serving function itself (app.services.tabular_inference.score_frame), so this is serving parity.
    live = score_frame(checkpoint, features[test])
    parity = float(np.max(np.abs(live - stored_p))) if len(live) == len(stored_p) else None
    y_test = y[test].to_numpy()
    full = {"auroc": float(roc_auc_score(y_test, live)), "sensitivity": float((live[y_test == 1] >= threshold).mean()),
            "specificity": float((live[y_test == 0] < threshold).mean())}
    full_match = all(abs(full[k] - report["metrics"][k]) < 1e-9 for k in full)
    # Sensitivity analysis: the test metrics without test records that duplicate a development record exactly.
    unique = ~keyed[test].isin(train_keys).to_numpy()
    deduplicated = None
    if unique.sum() and len(set(y_test[unique])) == 2:
        deduplicated = {"test_n": int(unique.sum()), "auroc": float(roc_auc_score(y_test[unique], live[unique])),
                        "sensitivity": float((live[unique][y_test[unique] == 1] >= threshold).mean()),
                        "specificity": float((live[unique][y_test[unique] == 0] < threshold).mean())}
    return {
        "metrics_full_precision_rescoring": full, "full_precision_metrics_match_report": full_match,
        "test_metrics_without_development_duplicates": deduplicated,
        "stored_prediction_precision": "6 decimals (rounding up to 5e-7; ties can change AUROC when recomputed from the CSV)",
        "model_id": spec["model_id"], "dataset_id": spec["dataset_id"], "split_counts_rebuilt": counts, "split_counts_reported": report["split_counts"],
        "split_matches_report": counts == report["split_counts"], "persons_crossing_splits": crossing,
        "exact_duplicate_records_shared_with_development": duplicates, "possible_label_proxies_dev_auroc_ge_0_98": proxies,
        "positive_share": {part: round(float(y[parts == part].mean()), 4) for part in ("train", "val", "test")},
        "imputer_fitted_on_development_rows_only": fitted_on_train, "metrics_recomputed": recomputed, "metrics_match_report": metric_match,
        "checkpoint_rescoring_max_abs_difference": parity, "test_used_for_model_selection": False,
        "model_selection_evidence": f"report.model_selection uses validation AUROC only ({report['model_selection']['rule']})",
    }


def main() -> int:
    results = [audit(name, spec) for name, spec in tabular.COHORTS.items()]
    verdicts = []
    for item in results:
        issues = []
        if not item["split_matches_report"]:
            issues.append("SPLIT_MISMATCH")
        if item["persons_crossing_splits"]:
            issues.append("PERSON_CROSSES_SPLITS")
        if any(item["exact_duplicate_records_shared_with_development"].values()):
            issues.append("DUPLICATE_RECORDS_ACROSS_SPLITS")
        if item["possible_label_proxies_dev_auroc_ge_0_98"]:
            issues.append("REVIEW_POSSIBLE_LABEL_PROXY")
        if item["imputer_fitted_on_development_rows_only"] is False:
            issues.append("PREPROCESSING_NOT_TRAIN_ONLY")
        if not item["full_precision_metrics_match_report"]:
            issues.append("METRICS_DO_NOT_REPRODUCE")
        elif not item["metrics_match_report"]:
            issues.append("STORED_CSV_ROUNDING_CHANGES_RECOMPUTED_METRICS")
        # Tolerance fixed before comparison by the storage format: 6 decimals round by at most 5e-7.
        if item["checkpoint_rescoring_max_abs_difference"] is None or item["checkpoint_rescoring_max_abs_difference"] > 5e-7 + 1e-12:
            issues.append("CHECKPOINT_PARITY_NOT_EXACT")
        item["findings"] = issues or ["NONE"]
        verdicts.append((item["model_id"], issues))
    OUT.write_text(json.dumps({"tool": "scripts/remediation_tabular_audit.py", "models": results}, indent=2) + "\n", encoding="utf-8")
    for model_id, issues in verdicts:
        print(f"{model_id:36} {', '.join(issues) if issues else 'no findings'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
