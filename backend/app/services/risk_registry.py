"""Organ-specific risk-model and explainability registry.

A patient-specific risk requires a validated model applied inside its
derivation population with every input documented and reviewed. The entries
below name candidate published instruments and the precise reason each is not
computed here. No weighted score is ever assembled from abnormal values.
"""

from __future__ import annotations

from typing import Any

INPUTS_NOT_STRUCTURED = "INPUTS_NOT_AVAILABLE_AS_REVIEWED_STRUCTURED_DATA"
POPULATION_NOT_ESTABLISHED = "APPLICABLE_POPULATION_NOT_ESTABLISHED"
NOT_IMPLEMENTED = "NOT_IMPLEMENTED_PENDING_SOURCE_VERIFICATION"


def _model(organ: str, name: str, target: str, horizon: str | None, inputs: list[str], population: str, blockers: list[str]) -> dict[str, Any]:
    return {
        "organ_system": organ,
        "model_id": None,
        "instrument": name,
        "risk_target": target,
        "risk_horizon": horizon,
        "required_inputs": inputs,
        "derivation_population": population,
        "calibration_status": "NOT_ASSESSED_IN_THIS_WORKSPACE",
        "validation_status": "NOT_VALIDATED_IN_THIS_WORKSPACE",
        "status": "NOT_COMPUTED",
        "blockers": blockers,
        "output": None,
    }


RISK_MODELS: tuple[dict[str, Any], ...] = (
    _model("heart", "CHA2DS2-VASc", "Thromboembolic stroke in atrial fibrillation", "Annualised", ["Age", "Sex", "Heart failure", "Hypertension", "Stroke/TIA history", "Vascular disease", "Diabetes"], "Adults with non-valvular atrial fibrillation", [INPUTS_NOT_STRUCTURED, POPULATION_NOT_ESTABLISHED]),
    _model("heart", "Pooled Cohort Equations", "First atherosclerotic cardiovascular event", "10 years", ["Age", "Sex", "Total cholesterol", "HDL cholesterol", "Systolic BP", "BP treatment", "Diabetes", "Smoking"], "Adults 40-79 without prior ASCVD", [INPUTS_NOT_STRUCTURED]),
    _model("kidneys", "Kidney Failure Risk Equation (4-variable)", "Kidney failure requiring replacement therapy", "2 and 5 years", ["Age", "Sex", "eGFR", "Urine albumin-to-creatinine ratio"], "Adults with CKD G3a-G5", [NOT_IMPLEMENTED, POPULATION_NOT_ESTABLISHED]),
    _model("liver", "MELD / MELD-Na", "90-day mortality in end-stage liver disease", "90 days", ["Bilirubin", "INR", "Creatinine", "Sodium", "Dialysis status"], "Adults with end-stage liver disease", [INPUTS_NOT_STRUCTURED, POPULATION_NOT_ESTABLISHED]),
    _model("liver", "FIB-4 index", "Advanced fibrosis (rule-in/rule-out triage)", None, ["Age", "AST", "ALT", "Platelet count"], "Adults with chronic liver disease (e.g. NAFLD, HCV)", [POPULATION_NOT_ESTABLISHED]),
    _model("lungs", "Brock (PanCan) nodule model", "Malignancy of a CT-detected pulmonary nodule", None, ["Age", "Sex", "Family history", "Emphysema", "Nodule size", "Nodule type", "Location", "Count", "Spiculation"], "Screen-detected nodules in current/former smokers", [INPUTS_NOT_STRUCTURED, NOT_IMPLEMENTED]),
    _model("brain", "ABCD2", "Early stroke after TIA", "2 days", ["Age", "Blood pressure", "Clinical features", "Symptom duration", "Diabetes"], "Patients with transient ischaemic attack", [INPUTS_NOT_STRUCTURED, POPULATION_NOT_ESTABLISHED]),
    _model("pancreas", "Revised Atlanta severity classification", "Acute pancreatitis severity", None, ["Organ failure duration", "Local complications"], "Acute pancreatitis", [INPUTS_NOT_STRUCTURED, POPULATION_NOT_ESTABLISHED]),
    _model("skeletal", "FRAX", "Major osteoporotic and hip fracture", "10 years", ["Age", "Sex", "BMI", "Prior fracture", "Parental hip fracture", "Smoking", "Glucocorticoids", "Rheumatoid arthritis", "Secondary osteoporosis", "Alcohol", "Femoral neck BMD (optional)"], "Adults 40-90", [INPUTS_NOT_STRUCTURED, NOT_IMPLEMENTED]),
)

EXPLAINABILITY_METHODS: tuple[dict[str, Any], ...] = (
    {"method": "Grad-CAM", "applies_to": "Convolutional image classifiers", "status": "REQUIRES_VALIDATED_MODEL", "limits": "Coarse class-discriminative heatmap; not lesion localisation or causal attribution."},
    {"method": "Integrated Gradients", "applies_to": "Differentiable models", "status": "REQUIRES_VALIDATED_MODEL", "limits": "Depends on the chosen baseline; attributions are model-relative."},
    {"method": "SHAP", "applies_to": "Tabular and tree models", "status": "REQUIRES_VALIDATED_MODEL", "limits": "Explains the model's output, not the patient's biology; correlated features share credit unpredictably."},
    {"method": "Permutation feature importance", "applies_to": "Any model with held-out data", "status": "REQUIRES_VALIDATED_MODEL", "limits": "Population-level; unstable with correlated features."},
    {"method": "Attention inspection", "applies_to": "Transformer models", "status": "REQUIRES_VALIDATED_MODEL", "limits": "Attention weights are not faithful explanations by themselves."},
    {"method": "Segmentation mask overlay", "applies_to": "Validated segmentation models", "status": "REQUIRES_VALIDATED_MODEL", "limits": "Shows model output geometry, which must be reviewed against the source image."},
    {"method": "Biomarker contribution analysis", "applies_to": "Validated risk models", "status": "REQUIRES_VALIDATED_MODEL", "limits": "Contributions are defined by the model's functional form only."},
)

EXPLANATION_PROVENANCE_FIELDS = ("model_id", "model_version", "input_sha256", "preprocessing_version", "method", "method_parameters", "baseline_definition", "generated_at", "reviewer_status")


def _explainability_methods() -> list[dict[str, Any]]:
    """The static method list, with the two methods MedTwin now applies to research models marked as such
    (and the measured localisation of the Grad-CAM marks, when that evaluation has been run)."""
    from app.services import cxr_research

    summary = cxr_research.localisation_summary()
    methods = []
    for method in EXPLAINABILITY_METHODS:
        method = dict(method)
        if method["method"] == "Grad-CAM":
            method.update({"applies_to": "Convolutional image classifiers (used on the research chest-radiograph model)", "status": "USED_ON_RESEARCH_MODELS"})
            if summary:
                overall = summary["overall"]
                method["limits"] += (f" On {overall['boxes']} NIH radiologist boxes its peak fell inside the box {overall['pointing_hit_rate']:.0%} of the "
                                     f"time (a random point {overall['chance_hit_rate']:.0%}); the rate is shown per finding beside each mark.")
        elif method["method"] == "Segmentation mask overlay":
            method.update({"applies_to": "Segmentation models (research models, with their held-out evaluation)", "status": "USED_ON_RESEARCH_MODELS",
                           "limits": method["limits"] + " Reviewers can save a correction beside the run; the model output is never changed."})
        methods.append(method)
    return methods


def risk_registry() -> dict[str, Any]:
    return {
        "schema_version": "medtwin-risk-registry-1.0.0",
        "models": list(RISK_MODELS),
        "explainability_methods": _explainability_methods(),
        "explanation_provenance_fields": list(EXPLANATION_PROVENANCE_FIELDS),
        "distinctions": [
            {"term": "Classifier confidence", "meaning": "A model's score for a label on one input. Not a probability of a future event, and not calibrated unless calibration is shown."},
            {"term": "Calibrated probability", "meaning": "A score whose stated probabilities match observed frequencies in a held-out population."},
            {"term": "Clinical risk", "meaning": "The probability of a defined event over a defined horizon in a defined population, from a validated model."},
        ],
        "notice": "No risk score is computed: each candidate needs reviewed structured inputs and an established applicable population.",
    }
