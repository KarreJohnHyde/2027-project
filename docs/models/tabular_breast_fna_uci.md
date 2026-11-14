# Model card: Malignant breast mass from aspirate image features (UCI Wisconsin Diagnostic, research)

- **Model id:** `tabular_breast_fna_uci` (registry status `READY_UNVALIDATED`; research-only)
- **Target:** malignant (vs benign) breast mass from fine-needle aspirate image features.
- **Data:** UCI dataset 17 (CC BY 4.0); 569 breast masses sampled by fine-needle aspiration at the University of Wisconsin (1990s).
- **Split:** StratifiedKFold-equivalent 70/15/15 by outcome (one row per person, no duplicate records): 406 development, 82 validation, 81 test (30 positive).
- **Selected model:** `logistic_C0.01` (validation AUROC 1.000).
- **Checkpoint:** `artifacts/training/tabular_breast_fna_uci-20261114T090837Z/model.joblib`, SHA-256 `db9dc215be28827e4bfc8b1711232fd6b1b34d5727d6d0b2a671e3b4b4ae3a0e`.

## Test results (evaluated once)

- AUROC 0.986 (95% CI 0.964-0.999); AUPRC 0.979.
- At the validation threshold 0.980: sensitivity 0.933, specificity 0.961.
- Brier 0.056 vs 0.233 for the prevalence-only baseline; ECE 0.059.

## Limitations

- Population: 569 breast masses sampled by fine-needle aspiration at the University of Wisconsin (1990s). Results do not transfer to other populations without external evaluation.
- Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.
- Small public cohort: confidence intervals are wide.
- Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, so it is not an independent final test.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/tabular_breast_fna_uci.json`.
