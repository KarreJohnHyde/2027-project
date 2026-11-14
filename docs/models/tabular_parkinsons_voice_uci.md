# Model card: Parkinson's disease from voice measurements (UCI Parkinsons, research)

- **Model id:** `tabular_parkinsons_voice_uci` (registry status `READY_UNVALIDATED`; research-only)
- **Target:** Parkinson's disease (vs healthy) from sustained-vowel voice measurements.
- **Data:** UCI dataset 174 (CC BY 4.0); 31 people (23 with Parkinson's disease), several recordings each; very few people in the test part.
- **Split:** StratifiedGroupKFold 70/15/15 by outcome; one person's rows and every exact duplicate record stay in one part: 145 development, 25 validation, 25 test (19 positive).
- **Selected model:** `logistic_C1.0` (validation AUROC 0.675).
- **Checkpoint:** `artifacts/training/tabular_parkinsons_voice_uci-20261114T091312Z/model.joblib`, SHA-256 `35b30eae472ff5cf38d71c62098537881cf1f55fa5770d1aa69bf98ae450667e`.

## Test results (evaluated once)

- AUROC 0.877; AUPRC 0.969.
- At the validation threshold 0.635: sensitivity 0.895, specificity 0.000.
- Brier 0.189 vs 0.182 for the prevalence-only baseline; ECE 0.252.

## Limitations

- Population: 31 people (23 with Parkinson's disease), several recordings each; very few people in the test part. Results do not transfer to other populations without external evaluation.
- Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.
- Small public cohort: confidence intervals are wide.
- Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, so it is not an independent final test.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/tabular_parkinsons_voice_uci.json`.
