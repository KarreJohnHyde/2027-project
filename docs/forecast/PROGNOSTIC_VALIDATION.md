# Prognostic model validation

| Capability | Status | Evidence |
| --- | --- | --- |
| Time-to-event (survival) models on public cohorts | **IMPLEMENTED_UNVALIDATED** (internal hold-out only) | `ml_training/survival.py`; reports `docs/validation/models/pbc_mayo_survival_cox.json`, `heart_failure_survival_cox.json`; tests `backend/tests/test_ecg_and_survival_training.py` |
| Case-level survival estimates in Prognosis Studio | **NOT_STARTED** (deliberately not wired) | see "Why no case-level estimate" |
| Longitudinal trajectory forecasting (biomarker or lesion trajectories) | **BLOCKED** | no dataset with repeated measurements per patient |
| Treatment-effect (scenario B) estimates | **BLOCKED** | no target-trial specification or causal validation (`SCENARIO_ELIGIBILITY.md`) |

## Survival models (2026-10-25)

Both cohorts are CC BY 4.0 on the UCI Machine Learning Repository (licences verified on
the official pages; `dataset_registry/tasks.json`). Model: Cox proportional hazards
(Breslow ties) on standardised covariates, fitted by Newton-Raphson; Breslow baseline
hazard. The implementation was checked on simulated data with known hazard ratios
(recovered without bias on continuous times; analytic gradient equal to the numerical
one) before any real result was produced. Each hold-out set was evaluated once.

### Primary biliary cirrhosis, Mayo covariates (`pbc_mayo_survival_cox`) — research

- Design follows the original Mayo model (Dickson et al., Hepatology 1989): development
  cohort = the 312 randomized trial patients (125 deaths); hold-out cohort = the 104
  non-randomized patients with complete covariates (35 deaths; 2 excluded for missing
  prothrombin time). Covariates fixed in advance: age, log bilirubin, log albumin, log
  prothrombin time, oedema; no penalty.
- **Hold-out: Harrell's C 0.786 (95% CI 0.709–0.854); integrated Brier score 0.105 vs
  0.146 for the Kaplan–Meier reference (skill 0.28); Brier 0.058 / 0.111 / 0.123 at
  1 / 3 / 5 years (Kaplan–Meier 0.063 / 0.166 / 0.190).**
- Hazard ratios per SD (development cohort): bilirubin 2.47, age 1.42, prothrombin 1.30,
  oedema 1.24, albumin 0.68 — the direction and ranking of the published Mayo model.
- Calibration by predicted-risk tertile at 5 years: predicted 0.08 / 0.20 / 0.64 vs
  observed 0.07 / 0.30 / 0.60 (Kaplan–Meier).
- Limitations: 1974–1984 Mayo population; liver transplantation censored (competing
  risk); proportional hazards not formally tested; research-only.

### Heart failure (`heart_failure_survival_cox`) — exploratory only

- 299 patients (Faisalabad, Pakistan, 2015; 96 deaths, follow-up 4–285 days); stratified
  70/30 split (209 / 90; 67 / 29 deaths); L2 penalty 0.1 chosen by 5-fold CV C-index in
  the development part. Follow-up time is the survival time only, never a predictor.
- **Hold-out: Harrell's C 0.671 (95% CI 0.569–0.774), but integrated Brier 0.168 vs
  0.158 for Kaplan–Meier (skill −0.065)**; at 180 days the low-risk tertile is predicted
  8.7% and observed 19.5%. The model ranks patients but its absolute risks are no better
  than the population average, so the registry marks it `EXPLORATORY_ONLY`
  (`validation_readiness.readiness = NO_HELD_OUT_BRIER_SKILL_OVER_KAPLAN_MEIER`).

## Why no case-level estimate

A survival model applies only to its population (Mayo PBC patients; Pakistani
heart-failure patients with LVEF ≤ 45%). MedTwin does not establish diagnoses, so it
cannot know that a case belongs to either population, and the registry has no
clinician-confirmed population membership or complete-input gate yet. Prognosis Studio
therefore continues to abstain (`MODEL_NOT_VALIDATED`) for every case; the models are
evaluation evidence in Validation Center → Trained models.

## Evaluation tooling

`backend/app/services/evaluation_metrics.py` (Validation Center) and
`ml_training/survival.py`: Harrell's C with patient bootstrap CIs, IPCW time-dependent
Brier scores (Graf et al. 1999; censoring distribution from the development cohort),
integrated Brier score against a Kaplan–Meier reference, grouped calibration; forecast
MAE/RMSE per target and horizon for future longitudinal data.

## What would unblock the remaining items

1. Case-level survival: a clinician-confirmed population gate (e.g. documented PBC
   diagnosis) plus a complete-input check, external validation in a contemporary cohort,
   and a decision about competing risks.
2. Trajectory forecasting: a lawful dataset with repeated measurements per patient and
   chronological splits.
3. Scenario B: a target-trial estimand with positivity, confounding and causal validation.
