# Model card: 30-day readmission of diabetic inpatients (UCI Diabetes 130-US hospitals, research)

- **Model id:** `tabular_diabetes_readmission_uci` (registry status `READY_UNVALIDATED`; research-only)
- **Target:** readmission within 30 days of discharge (diabetic inpatient encounters, 130 US hospitals).
- **Data:** UCI dataset 296 (CC BY 4.0); Diabetic inpatient encounters in 130 US hospitals, 1999-2008.
- **Split:** StratifiedGroupKFold 70/15/15 by outcome; one person's rows and every exact duplicate record stay in one part: 70961 development, 14190 validation, 14192 test (1616 positive).
- **Selected model:** `gradient_boosting_depthNone_lr0.1` (validation AUROC 0.655).
- **Checkpoint:** `artifacts/training/tabular_diabetes_readmission_uci-20261114T090948Z/model.joblib`, SHA-256 `6f0062deef5a5c0a0a540d5c0a2cb9359775787febffbb835ec0946623ebcfe1`.

## Test results (evaluated once)

- AUROC 0.659 (95% CI 0.642-0.675); AUPRC 0.214.
- At the validation threshold 0.108: sensitivity 0.629, specificity 0.603.
- Brier 0.097 vs 0.101 for the prevalence-only baseline; ECE 0.002.

## Limitations

- Population: Diabetic inpatient encounters in 130 US hospitals, 1999-2008. Results do not transfer to other populations without external evaluation.
- Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.
- Single public cohort; no external test set.
- Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, so it is not an independent final test.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/tabular_diabetes_readmission_uci.json`.
