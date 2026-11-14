# Model card: Death among hepatitis patients (UCI Hepatitis, research)

- **Model id:** `tabular_hepatitis_mortality_uci` (registry status `READY_UNVALIDATED`; research-only)
- **Target:** death (vs survival) of patients with hepatitis.
- **Data:** UCI dataset 46 (CC BY 4.0); 155 hepatitis patients (1980s); very small, so estimates are uncertain.
- **Split:** StratifiedKFold-equivalent 70/15/15 by outcome (one row per person, no duplicate records): 111 development, 22 validation, 22 test (5 positive).
- **Selected model:** `logistic_C0.01` (validation AUROC 0.917).
- **Checkpoint:** `artifacts/training/tabular_hepatitis_mortality_uci-20261114T091103Z/model.joblib`, SHA-256 `f1afcc4368592a005b6ca45d37838d9c77639ae9c66ad3318f53a1d7a7c8317e`.

## Test results (evaluated once)

- AUROC 0.941 (95% CI 0.789-1.000); AUPRC 0.871.
- At the validation threshold 0.191: sensitivity 0.800, specificity 0.824.
- Brier 0.090 vs 0.176 for the prevalence-only baseline; ECE 0.095.

## Limitations

- Population: 155 hepatitis patients (1980s); very small, so estimates are uncertain. Results do not transfer to other populations without external evaluation.
- Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.
- Small public cohort: confidence intervals are wide.
- Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, so it is not an independent final test.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/tabular_hepatitis_mortality_uci.json`.
