# Model card: Heart-failure mortality Cox model (research; UCI heart failure clinical records)

- **Model id:** `heart_failure_survival_cox` (registry status `READY_UNVALIDATED`; research-only)
- **Data:** Heart failure clinical records (UCI id 519) (CC BY 4.0; https://archive.ics.uci.edu/dataset/519/heart+failure+clinical+records). Dataset version `9c73cea7468ff5d5`.
- **Population:** 299 heart-failure patients with LVEF <= 45% (NYHA III-IV), Faisalabad Institute of Cardiology and Allied Hospital, Pakistan, April-December 2015 (Ahmad et al., PLoS ONE 2017).
- **Split:** stratified by death event, 70/30, seed 20261024: 209 development (67 deaths), 90 held out (29 deaths).
- **Model:** Cox proportional hazards (Breslow), covariates age, anaemia, log_creatinine_phosphokinase, diabetes, ejection_fraction, high_blood_pressure, log_platelets, log_serum_creatinine, serum_sodium, sex, smoking; L2 penalty 0.1.
- **Checkpoint:** `artifacts/training/heart_failure_survival_cox-20261025T072515Z/model.pt`, SHA-256 `0073a7eba793269e70640a4b52f469ad3e61235b21b1c2a895a81b5b26b162ed`.

## Held-out results (evaluated once)

- Harrell's C 0.671 (95% CI 0.569-0.774).
- Integrated Brier score 0.168 vs 0.158 for the Kaplan-Meier reference (skill -0.065).
- Brier at 90 days: 0.174 (Kaplan-Meier reference 0.181).
- Brier at 180 days: 0.265 (Kaplan-Meier reference 0.241).

## Limitations

- Population: 299 heart-failure patients with LVEF <= 45% (NYHA III-IV), Faisalabad Institute of Cardiology and Allied Hospital, Pakistan, April-December 2015 (Ahmad et al., PLoS ONE 2017). Predictions do not transfer to other populations without external validation.
- Cox proportional-hazards assumption not formally tested; small held-out cohort, so confidence intervals are wide.
- Research-only survival estimates; not validated for clinical decision-making.

Full report: `docs/validation/models/heart_failure_survival_cox.json`.
