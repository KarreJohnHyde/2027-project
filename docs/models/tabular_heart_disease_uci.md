# Model card: Coronary disease from clinical tests (UCI Heart Disease, 4 sites, research)

- **Model id:** `tabular_heart_disease_uci` (registry status `READY_UNVALIDATED`; research-only)
- **Target:** angiographic coronary disease (>50% narrowing; 'num' > 0).
- **Data:** UCI dataset 45 (CC BY 4.0); Patients referred for coronary angiography at Cleveland, Budapest, Zurich/Basel and Long Beach VA (1980s).
- **Split:** StratifiedGroupKFold 70/15/15 by outcome; one person's rows and every exact duplicate record stay in one part: 656 development, 132 validation, 132 test (73 positive).
- **Selected model:** `logistic_C10.0` (validation AUROC 0.926).
- **Checkpoint:** `artifacts/training/tabular_heart_disease_uci-20261114T091040Z/model.joblib`, SHA-256 `b459b2ecdcc10979ae27d62fcc841420af1c0fa092d924acc8991b965cff6e17`.

## Test results (evaluated once)

- AUROC 0.827 (95% CI 0.748-0.891); AUPRC 0.846.
- At the validation threshold 0.475: sensitivity 0.781, specificity 0.746.
- Brier 0.174 vs 0.247 for the prevalence-only baseline; ECE 0.106.

## Limitations

- Population: Patients referred for coronary angiography at Cleveland, Budapest, Zurich/Basel and Long Beach VA (1980s). Results do not transfer to other populations without external evaluation.
- Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.
- Small public cohort: confidence intervals are wide.
- Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, so it is not an independent final test.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/tabular_heart_disease_uci.json`.
