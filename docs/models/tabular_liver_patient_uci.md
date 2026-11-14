# Model card: Liver patient from liver function tests (UCI ILPD, research)

- **Model id:** `tabular_liver_patient_uci` (registry status `READY_UNVALIDATED`; research-only)
- **Target:** liver patient (the source's selector = 1) from liver function tests.
- **Data:** UCI dataset 225 (CC BY 4.0); 583 patients from north-east Andhra Pradesh, India.
- **Split:** StratifiedGroupKFold 70/15/15 by outcome; one person's rows and every exact duplicate record stay in one part: 416 development, 84 validation, 83 test (59 positive).
- **Selected model:** `logistic_C10.0` (validation AUROC 0.698).
- **Checkpoint:** `artifacts/training/tabular_liver_patient_uci-20261114T091238Z/model.joblib`, SHA-256 `a00edd71be141945dcf07d6232155952b98f6bd9e89bf43db040d99b4f49b7b6`.

## Test results (evaluated once)

- AUROC 0.748 (95% CI 0.628-0.858); AUPRC 0.879.
- At the validation threshold 0.781: sensitivity 0.441, specificity 0.958.
- Brier 0.173 vs 0.206 for the prevalence-only baseline; ECE 0.048.

## Limitations

- Population: 583 patients from north-east Andhra Pradesh, India. Results do not transfer to other populations without external evaluation.
- Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.
- Small public cohort: confidence intervals are wide.
- Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, so it is not an independent final test.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/tabular_liver_patient_uci.json`.
