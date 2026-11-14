# Model card: Chronic kidney disease from routine tests (UCI CKD, research)

- **Model id:** `tabular_ckd_uci` (registry status `READY_UNVALIDATED`; research-only)
- **Target:** chronic kidney disease (the source's 'ckd' class).
- **Data:** UCI dataset 336 (CC BY 4.0); 400 hospital patients in India (2015), small and with a high disease share.
- **Split:** StratifiedKFold-equivalent 70/15/15 by outcome (one row per person, no duplicate records): 285 development, 58 validation, 57 test (36 positive).
- **Selected model:** `logistic_C0.01` (validation AUROC 1.000).
- **Checkpoint:** `artifacts/training/tabular_ckd_uci-20261114T090920Z/model.joblib`, SHA-256 `2056bce7bf650dcda4785a7a1a8ba3ca28e89dc2fe69a17d4ff93742a5d344cf`.

## Test results (evaluated once)

- AUROC 0.997 (95% CI 0.987-1.000); AUPRC 0.998.
- At the validation threshold 0.992: sensitivity 1.000, specificity 0.952.
- Brier 0.033 vs 0.233 for the prevalence-only baseline; ECE 0.034.

## Limitations

- Population: 400 hospital patients in India (2015), small and with a high disease share. Results do not transfer to other populations without external evaluation.
- Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.
- Small public cohort: confidence intervals are wide.
- Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, so it is not an independent final test.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/tabular_ckd_uci.json`.
