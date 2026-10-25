"""Organ-specific prognosis capability registry and scenario evaluation.

A forecast is returned only by a trained, validated model registered for the
organ, endpoint, population and horizon. A treatment comparison additionally
requires a fully specified target-trial estimand. Neither exists in this
workspace, so evaluation returns the observed evidence plus machine-readable
reasons for every unavailable component. Observed values are never extended
into the future, and no future image or geometry is synthesised.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entities import Examination, ModalityType, UploadedFile
from app.services.biomarker_trends import build_series

TARGET_TRIAL_FIELDS = (
    ("target_population", "Clinical target population"),
    ("intervention", "Intervention definition"),
    ("comparator", "Comparator definition"),
    ("time_zero", "Time zero"),
    ("outcome", "Outcome"),
    ("follow_up", "Follow-up period"),
    ("baseline_covariates", "Relevant baseline covariates"),
    ("eligibility", "Eligibility criteria"),
    ("data_source", "Data source"),
    ("missing_data_strategy", "Missing-data strategy"),
    ("confounding_assumptions", "Confounding assumptions"),
    ("causal_estimand", "Causal estimand"),
    ("validation_methodology", "Validation methodology"),
)

UNAVAILABLE_MODEL = {"status": "NOT_TRAINED", "reason": "MODEL_NOT_VALIDATED"}


def _capability(system: str, label: str, outcomes: list[dict[str, str]], analytes: list[str], data: str, models: list[str], inputs: list[str]) -> dict[str, Any]:
    return {
        "organ_system": system,
        "label": label,
        "outcome_variables": outcomes,
        "suitable_data": data,
        "candidate_models": models,
        "trained_model_status": "NOT_TRAINED",
        "model_validation_status": "NOT_VALIDATED",
        "applicable_population": None,
        "required_inputs": inputs,
        "forecast_horizon": None,
        "uncertainty_method": None,
        "treatment_comparison": {"status": "UNAVAILABLE", "reason": "ESTIMAND_UNDEFINED"},
        "forecast_2d": {"status": "UNAVAILABLE", "reason": "NO_VALIDATED_IMAGE_EVOLUTION_MODEL"},
        "forecast_3d": {"status": "UNAVAILABLE", "reason": "NO_VALIDATED_SPATIAL_PROGRESSION_MODEL"},
        "observed_analytes": analytes,
        "workspace_data_status": "NO_LONGITUDINAL_OUTCOME_DATASET_REGISTERED",
        "interventions": [],
    }


CAPABILITIES: tuple[dict[str, Any], ...] = (
    _capability(
        "heart", "Cardiac conditions",
        [{"name": "LVEF trajectory", "type": "BIOMARKER_TRAJECTORY"}, {"name": "Heart-failure hospitalisation", "type": "TIME_TO_EVENT"}],
        ["ejection_fraction", "nt_probnp", "bnp", "troponin_i", "troponin_t", "heart_rate", "systolic_blood_pressure", "diastolic_blood_pressure"],
        "Serial echocardiography or cardiac MRI with dated LVEF, natriuretic peptides and adjudicated events, with censoring.",
        ["Linear mixed-effects model", "Cox proportional hazards", "Competing-risk (Fine-Gray) model"],
        ["Serial LVEF with modality", "NT-proBNP series", "Event dates and censoring"],
    ),
    _capability(
        "lungs", "Pulmonary conditions",
        [{"name": "Nodule diameter/volume trajectory", "type": "LESION_SIZE"}, {"name": "Respiratory event", "type": "TIME_TO_EVENT"}],
        ["nodule_size", "lesion_size", "oxygen_saturation", "respiratory_rate"],
        "Serial CT with lesion identity tracking and segmentation volumes, plus outcomes.",
        ["Volume-doubling-time model", "Mixed-effects growth model", "Survival model"],
        ["Registered serial CT", "Lesion identity across studies", "Segmentation volumes"],
    ),
    _capability(
        "brain", "Neurological conditions",
        [{"name": "Lesion volume trajectory", "type": "LESION_SIZE"}, {"name": "Functional outcome (e.g. mRS)", "type": "ORDINAL_OUTCOME"}],
        ["lesion_size", "mass_size"],
        "Serial CT/MRI with segmented lesion volumes and standardised outcome scales.",
        ["Ordinal regression", "Mixed-effects volume model"],
        ["Serial segmentations", "Standardised outcome scale", "Treatment timing"],
    ),
    _capability(
        "liver", "Hepatic conditions",
        [{"name": "Liver biochemistry trajectory", "type": "BIOMARKER_TRAJECTORY"}, {"name": "Decompensation", "type": "TIME_TO_EVENT"}],
        ["alt", "ast", "alkaline_phosphatase", "ggt", "bilirubin_total", "albumin", "inr", "liver_span"],
        "Longitudinal liver panels with a reviewed indication, elastography or biopsy staging, and outcomes.",
        ["Mixed-effects model", "Cox model", "Validated scores applied within their population"],
        ["Reviewed indication", "Serial liver panel", "Staging reference standard"],
    ),
    _capability(
        "pancreas", "Pancreatic conditions",
        [{"name": "Pancreatic lesion size trajectory", "type": "LESION_SIZE"}, {"name": "Pancreatitis recurrence", "type": "TIME_TO_EVENT"}],
        ["lipase", "amylase", "cyst_size", "mass_size"],
        "Serial cross-sectional imaging of pancreatic lesions with identity tracking; enzyme series with episode adjudication.",
        ["Mixed-effects growth model", "Recurrent-event model"],
        ["Lesion identity", "Serial imaging", "Episode adjudication"],
    ),
    _capability(
        "intestines", "Gastrointestinal conditions",
        [{"name": "Polyp recurrence", "type": "TIME_TO_EVENT"}, {"name": "Disease activity index", "type": "ORDINAL_OUTCOME"}],
        ["polyp_size"],
        "Surveillance endoscopy series with pathology and standardised activity scores.",
        ["Recurrent-event model", "Ordinal mixed model"],
        ["Pathology-linked endoscopy", "Standardised activity score", "Surveillance intervals"],
    ),
    _capability(
        "nervous", "Nervous-system conditions",
        [{"name": "Disability progression", "type": "TIME_TO_EVENT"}],
        [],
        "Standardised neurological examinations and imaging over time.",
        ["Survival model", "Mixed-effects model"],
        ["Standardised disability scale", "Serial imaging"],
    ),
    _capability(
        "skeletal", "Musculoskeletal conditions",
        [{"name": "Fracture healing / union", "type": "TIME_TO_EVENT"}, {"name": "Bone density trajectory", "type": "BIOMARKER_TRAJECTORY"}],
        [],
        "Serial radiographs with adjudicated healing status, or serial DXA.",
        ["Survival model", "Mixed-effects model"],
        ["Serial radiographs", "Adjudicated outcome"],
    ),
    _capability(
        "hybrid", "Multi-organ conditions",
        [{"name": "Composite clinical event", "type": "TIME_TO_EVENT"}],
        [],
        "Linked multimodal records with a defined composite endpoint and competing risks.",
        ["Competing-risk model", "Joint longitudinal-survival model"],
        ["Paired multimodal evidence", "Composite endpoint definition"],
    ),
    _capability(
        "kidneys", "Renal conditions",
        [{"name": "eGFR trajectory", "type": "BIOMARKER_TRAJECTORY"}, {"name": "Kidney failure", "type": "TIME_TO_EVENT"}],
        ["creatinine", "egfr_documented", "albumin_creatinine_ratio", "blood_urea_nitrogen", "urea", "kidney_length_left", "kidney_length_right"],
        "Serial creatinine/eGFR and albuminuria in a defined CKD population, with kidney-failure events and censoring.",
        ["Linear mixed-effects eGFR slope", "Validated kidney-failure risk equation within its population", "Cox model"],
        ["Serial creatinine", "Albuminuria", "Age and sex", "Event and censoring dates"],
    ),
)
CAPABILITIES_BY_ID = {item["organ_system"]: item for item in CAPABILITIES}


def capability_registry() -> dict[str, Any]:
    return {
        "schema_version": "medtwin-prognosis-capabilities-1.0.0",
        "target_trial_fields": [{"id": key, "label": label} for key, label in TARGET_TRIAL_FIELDS],
        "status_vocabulary": ["OBSERVED", "ESTIMATED", "FORECAST", "UNAVAILABLE"],
        "capabilities": list(CAPABILITIES),
        "notice": "A forecast requires a trained model validated for the organ, endpoint, population and horizon. None is registered.",
    }


def _imaging(db: Session, case_id: int) -> list[dict[str, Any]]:
    exams = {exam.id: exam for exam in db.query(Examination).filter(Examination.case_id == case_id).all()}
    uploads = (
        db.query(UploadedFile)
        .filter(UploadedFile.case_id == case_id, UploadedFile.modality == ModalityType.IMAGE, UploadedFile.is_associated.is_(True))
        .order_by(UploadedFile.id.asc())
        .all()
    )
    rows = []
    for upload in uploads:
        exam = exams.get(upload.examination_id) if upload.examination_id else None
        rows.append({
            "upload_id": upload.id,
            "filename": upload.filename,
            "examination_id": upload.examination_id,
            "date": exam.exam_date.date().isoformat() if exam else None,
            "status": "OBSERVED",
        })
    return sorted(rows, key=lambda row: (row["date"] or "9999", row["upload_id"]))


def evaluate_scenarios(db: Session, case_id: int, organ_system: str, intervention_id: Optional[str], horizon_days: int) -> dict[str, Any]:
    capability = CAPABILITIES_BY_ID.get(organ_system)
    if capability is None:
        raise KeyError(organ_system)
    all_series = build_series(db, case_id)
    if organ_system == "hybrid":
        series = all_series
    else:
        series = [item for item in all_series if item["name"] in capability["observed_analytes"] or item["anatomy_system"] == organ_system]
    observed = {
        "status": "OBSERVED" if series else "NOT_AVAILABLE",
        "biomarker_series": series,
        "imaging_studies": _imaging(db, case_id),
    }
    if intervention_id is None:
        intervention_reasons = ["INTERVENTION_NOT_SPECIFIED"]
    elif any(item["id"] == intervention_id for item in capability["interventions"]):
        intervention_reasons = []
    else:
        intervention_reasons = ["ESTIMAND_UNDEFINED"]
    forecast_block = {
        "status": "UNAVAILABLE",
        "reason_codes": ["MODEL_NOT_VALIDATED"] + (["INSUFFICIENT_EVIDENCE"] if not series else []),
        "forecast": None,
        "uncertainty": None,
        "forecast_2d": capability["forecast_2d"],
        "forecast_3d": capability["forecast_3d"],
    }
    scenario_a = {"label": "Scenario A — Without the specified treatment", **forecast_block}
    scenario_b = {
        "label": "Scenario B — With the specified treatment",
        **forecast_block,
        "reason_codes": forecast_block["reason_codes"] + intervention_reasons,
    }
    return {
        "status": "OBSERVED_EVIDENCE_ONLY" if series or observed["imaging_studies"] else "INSUFFICIENT_EVIDENCE",
        "case_id": case_id,
        "organ_system": organ_system,
        "horizon_days": horizon_days,
        "intervention_id": intervention_id,
        "capability": capability,
        "observed": observed,
        "scenarios": {"A": scenario_a, "B": scenario_b},
        "treatment_effect": {
            "status": "NOT_IDENTIFIABLE",
            "reason_codes": ["ESTIMAND_UNDEFINED", "NO_VALIDATED_CAUSAL_MODEL"],
            "target_trial_specification": {key: None for key, _ in TARGET_TRIAL_FIELDS},
            "estimate": None,
        },
        "guideline_information": {"status": "NOT_PROVIDED", "reason": "No verified guideline source is configured; MedTwin does not generate treatment recommendations."},
        "notice": "Observed values only. No forecast, treatment effect, future image, or future geometry has been produced.",
    }
