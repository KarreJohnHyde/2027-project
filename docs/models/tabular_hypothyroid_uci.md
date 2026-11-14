# Model card: Hypothyroidism from thyroid tests (UCI Thyroid, research)

- **Model id:** `tabular_hypothyroid_uci` (registry status `READY_UNVALIDATED`; research-only)
- **Target:** hypothyroidism (Garvan Institute referrals; the source's 'hypothyroid' class).
- **Data:** UCI dataset 102 (CC BY 4.0); Thyroid referrals to the Garvan Institute, Sydney (1980s).
- **Split:** StratifiedGroupKFold 70/15/15 by outcome; one person's rows and every exact duplicate record stay in one part: 2259 development, 452 validation, 452 test (22 positive).
- **Selected model:** `gradient_boosting_depthNone_lr0.05` (validation AUROC 0.999).
- **Checkpoint:** `artifacts/training/tabular_hypothyroid_uci-20261114T091112Z/model.joblib`, SHA-256 `5a602f19366b5ebf08217ed35c3b4af43394cde5a5d35be1cbc74db4dcd215df`.

## Test results (evaluated once)

- AUROC 0.969 (95% CI 0.913-0.999); AUPRC 0.858.
- At the validation threshold 0.738: sensitivity 0.818, specificity 0.991.
- Brier 0.016 vs 0.046 for the prevalence-only baseline; ECE 0.017.

## Limitations

- Population: Thyroid referrals to the Garvan Institute, Sydney (1980s). Results do not transfer to other populations without external evaluation.
- Probabilities are Platt-calibrated on the validation part of this cohort only; they are not calibrated for any clinical population.
- Single public cohort; no external test set.
- Re-evaluated after test exposure (2026-11-14 duplicate audit): this split's test part overlaps the first run's inspected test part, so it is not an independent final test.
- Near-definitional task: the source label was assigned from these thyroid tests (FTI alone reaches development AUROC 0.984), so the high score reflects re-learning that rule, not independent diagnostic discovery.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/tabular_hypothyroid_uci.json`.
