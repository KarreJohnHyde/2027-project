# Prognosis scenario eligibility

Status: **IMPLEMENTED_TESTED as abstention**. `/prognosis-studio` is a separate route
from `/anatomy-studio` with two scenario panels (A: without the specified treatment,
B: with it). Both panels work as UI and, because no forecasting or causal model is
validated, both return observed evidence plus machine-readable reasons, never a
forecast, risk, treatment effect, future image or future geometry.

Code: `backend/app/services/prognosis_registry.py` (`evaluate_scenarios`,
`capability_registry`), `backend/app/services/forecasting_service.py`,
`backend/app/routers/prognosis.py`, `backend/app/routers/forecast.py`,
`src/pages/PrognosisStudioPage.tsx`.

## Eligibility chain

A forecast for a scenario would require **all** of the following; the first missing
item becomes a reason code.

| Requirement | Reason code when missing | Current state |
| --- | --- | --- |
| Source-linked numeric observations for the target with valid collection dates and matching units | `NOT_ELIGIBLE` / `INSUFFICIENT_EVIDENCE` | depends on the case |
| At least `L_MIN_OBSERVATIONS` (default 3) observations on ≥ 3 distinct dates | `NOT_ELIGIBLE: Insufficient comparable observations` | depends on the case |
| A trained model registered for the organ, endpoint, population and horizon, evaluated on a chronological held-out split | `MODEL_NOT_VALIDATED` | **none registered for any of the ten systems** (`trained_model_status = NOT_TRAINED`) |
| Spatial / image evolution model (2D) | `NO_VALIDATED_IMAGE_EVOLUTION_MODEL` | none |
| Spatial progression model (3D geometry) | `NO_VALIDATED_SPATIAL_PROGRESSION_MODEL` | none |
| Scenario B only: an intervention defined in the capability registry | `INTERVENTION_NOT_SPECIFIED` / `ESTIMAND_UNDEFINED` | no interventions registered |
| Treatment effect: full target-trial specification (population, intervention, comparator, time zero, outcome, follow-up, covariates, eligibility, data source, missing-data strategy, confounding assumptions, causal estimand, validation methodology) and a validated causal model | `NOT_IDENTIFIABLE` (`ESTIMAND_UNDEFINED`, `NO_VALIDATED_CAUSAL_MODEL`) | all thirteen fields `null` |
| Guideline information | `NOT_PROVIDED` | no verified guideline source; MedTwin gives no treatment recommendations |

Even when observations are sufficient, the forecasting service returns `NOT_ELIGIBLE`
with `MODEL_NOT_VALIDATED` and the observed series only: persistence and linear
extrapolations are deliberately not emitted ("an untested extrapolation is still a
prediction").

## Per-system capability registry

Ten systems (heart, lungs, brain, liver, pancreas, intestines, nervous, skeletal, hybrid,
kidneys) each list candidate outcomes, the data that would be suitable, candidate model
families and required inputs, all with `trained_model_status = NOT_TRAINED`,
`model_validation_status = NOT_VALIDATED` and
`workspace_data_status = NO_LONGITUDINAL_OUTCOME_DATASET_REGISTERED`. None of the 24
named archives contains longitudinal outcome data. The 2026-10-25 supplementary batch
added two public time-to-event cohorts (Mayo PBC, heart-failure clinical records); the
resulting research survival models are population-specific and are not applied to
cases, so the scenario panels still abstain (`PROGNOSTIC_VALIDATION.md`). No archive
contains repeated per-patient measurements for trajectory forecasting.

## Tests and browser evidence

- `test_evidence_and_fusion.py::test_forecasting_eligibility_enforcement` — insufficient
  and sufficient series both produce no forecast without a validated model.
- `test_medtwin2_capabilities.py::test_prognosis_registry_covers_ten_organs_without_forecasts`.
- `test_medtwin2_capabilities.py::test_forecast_errors_are_reported_per_target_and_horizon`
  (evaluation tooling, below).
- Browser walkthrough: `/prognosis-studio` renders separately from `/anatomy-studio`,
  shows `INSUFFICIENT_EVIDENCE` markers and no numeric risk statement
  (`docs/anatomy/BROWSER_WALKTHROUGH.md`).
