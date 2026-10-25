# Model card: Primary biliary cirrhosis mortality Cox model, Mayo covariates (research)

- **Model id:** `pbc_mayo_survival_cox` (registry status `READY_UNVALIDATED`; research-only)
- **Data:** Cirrhosis patient survival, Mayo Clinic PBC (UCI id 878) (CC BY 4.0; https://archive.ics.uci.edu/dataset/878/cirrhosis+patient+survival+prediction+dataset-1). Dataset version `24ae2d5bedbc5989`.
- **Population:** Mayo Clinic primary biliary cirrhosis patients 1974-1984: 312 randomized trial patients (development) and 106 consenting non-randomized patients (hold-out).
- **Split:** development = randomized trial patients (Drug recorded); hold-out = non-randomized patients (as in Dickson et al. 1989): 312 development (125 deaths), 104 held out (35 deaths).
- **Model:** Cox proportional hazards (Breslow), covariates age_years, log_bilirubin, log_albumin, log_prothrombin, edema; L2 penalty 0.0.
- **Checkpoint:** `artifacts/training/pbc_mayo_survival_cox-20261025T072517Z/model.pt`, SHA-256 `3d86d29f24382b8d1cac71361eebbbf66ee90237d8b0261fc95077bfcc281af9`.

## Held-out results (evaluated once)

- Harrell's C 0.786 (95% CI 0.709-0.854).
- Integrated Brier score 0.105 vs 0.146 for the Kaplan-Meier reference (skill 0.281).
- Brier at 365 days: 0.058 (Kaplan-Meier reference 0.063).
- Brier at 1095 days: 0.111 (Kaplan-Meier reference 0.166).
- Brier at 1826 days: 0.123 (Kaplan-Meier reference 0.190).

## Limitations

- Population: Mayo Clinic primary biliary cirrhosis patients 1974-1984: 312 randomized trial patients (development) and 106 consenting non-randomized patients (hold-out). Predictions do not transfer to other populations without external validation.
- Liver transplantation is a competing risk censored at transplant; mortality risk may be underestimated.
- Cox proportional-hazards assumption not formally tested; small held-out cohort, so confidence intervals are wide.
- Research-only survival estimates; not validated for clinical decision-making.

Full report: `docs/validation/models/pbc_mayo_survival_cox.json`.
