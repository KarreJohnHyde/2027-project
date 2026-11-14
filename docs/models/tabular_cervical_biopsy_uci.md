# Model card: Positive cervical biopsy from risk factors (UCI Cervical Cancer, research)

- **Model id:** `tabular_cervical_biopsy_uci` (registry status `READY_UNVALIDATED`; research-only)
- **Target:** positive cervical biopsy from questionnaire risk factors.
- **Data:** UCI dataset 383 (CC BY 4.0); 858 patients at Hospital Universitario de Caracas, Venezuela; few positive biopsies.
- **Split:** StratifiedGroupKFold 70/15/15 by outcome; one person's rows and every exact duplicate record stay in one part: 612 development, 123 validation, 123 test (8 positive).
- **Selected model:** `logistic_C0.01` (validation AUROC 0.761).
- **Checkpoint:** `artifacts/training/tabular_cervical_biopsy_uci-20261114T091254Z/model.joblib`, SHA-256 `6f0cb2f124c97bbe2571540282ebf49b187342d88c39b8100661f7fb079e1b7a`.

## Test results (evaluated once)

- AUROC 0.687 (95% CI 0.476-0.891); AUPRC 0.169.
- At the validation threshold 0.067: sensitivity 0.500, specificity 0.748.
- Brier 0.061 vs 0.061 for the prevalence-only baseline; ECE 0.040.

## Limitations

- Population: 858 patients at Hospital Universitario de Caracas, Venezuela; few positive biopsies. Results do not transfer to other populations without external evaluation.
- Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.
- Small public cohort: confidence intervals are wide.
- Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, so it is not an independent final test.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/tabular_cervical_biopsy_uci.json`.
