"""
Laboratory test reference catalog for MedTwin.

Defines the structured tests behind the health-package catalog and validates
clinician-entered results against it. Reference intervals are typical adult
defaults; results should carry the performing laboratory's own interval.
"""

from typing import List, Dict, Any, Optional, Tuple

# ---------------------------------------------------------------------------
# Laboratory test reference catalog
#
# Every laboratory component of a health package (see clinical_catalog.py)
# references test codes defined here. Reference intervals are typical adult
# defaults only; each performing laboratory publishes its own intervals, so the
# API accepts per-result overrides (ref_low / ref_high) taken from the lab report.
#
# kind:
#   QUANTITATIVE  -> numeric value, flagged LOW / NORMAL / HIGH
#   QUALITATIVE   -> one of `options`, flagged NORMAL when equal to `expected`
#                    and ABNORMAL otherwise
#   INFORMATIONAL -> recorded only (e.g. blood group), never flagged
# Sex-specific intervals are given as ref_male / ref_female (low, high).
# A bound of None means "no limit on that side".
# ---------------------------------------------------------------------------

LAB_PANELS: Dict[str, str] = {
    "haemogram": "Complete Haemogram",
    "diabetic": "Diabetic Profile",
    "lipid": "Lipid Profile Panel",
    "liver": "Liver Function Panel",
    "kidney": "Kidney Function",
    "electrolytes": "Electrolytes & Minerals",
    "urine": "Urine Complete Analysis / Routine",
    "blood_bank": "Blood Grouping",
    "thyroid": "Thyroid",
    "micronutrients": "Vitamins & Iron Studies",
    "endocrine": "Endocrine",
    "serology": "Infectious Serology",
    "tumour_markers": "Tumour Markers",
    "stool_parasitology": "Stool & Parasitology",
}

_SEROLOGY_OPTIONS = ["NON_REACTIVE", "REACTIVE"]
_DETECTION_OPTIONS = ["NEGATIVE", "POSITIVE"]
_URINE_DIPSTICK_OPTIONS = ["NIL", "TRACE", "1+", "2+", "3+", "4+"]


def _q(code, name, unit, panel, low=None, high=None, organ="", male=None, female=None):
    return {
        "code": code, "name": name, "unit": unit, "panel": panel, "kind": "QUANTITATIVE",
        "ref_low": low, "ref_high": high, "ref_male": male, "ref_female": female,
        "organ_system": organ,
    }


def _ql(code, name, panel, options, expected, organ=""):
    return {
        "code": code, "name": name, "unit": "", "panel": panel, "kind": "QUALITATIVE",
        "options": options, "expected": expected, "organ_system": organ,
    }


_LAB_TEST_LIST: List[Dict[str, Any]] = [
    # Complete Haemogram (CBC)
    _q("HB", "Haemoglobin", "g/dL", "haemogram", organ="Hematopoietic", male=(13.0, 17.0), female=(12.0, 15.0)),
    _q("PCV", "Packed Cell Volume (PCV)", "%", "haemogram", organ="Hematopoietic", male=(40.0, 50.0), female=(36.0, 46.0)),
    _q("RBC", "RBC Count", "10^12/L", "haemogram", organ="Hematopoietic", male=(4.5, 5.5), female=(3.8, 4.8)),
    _q("MCV", "Mean Corpuscular Volume (MCV)", "fL", "haemogram", 83.0, 101.0, "Hematopoietic"),
    _q("MCH", "Mean Corpuscular Haemoglobin (MCH)", "pg", "haemogram", 27.0, 32.0, "Hematopoietic"),
    _q("MCHC", "MCHC", "g/dL", "haemogram", 31.5, 34.5, "Hematopoietic"),
    _q("RDW_CV", "Red Cell Distribution Width (RDW-CV)", "%", "haemogram", 11.6, 14.0, "Hematopoietic"),
    _q("TLC", "Total Leucocyte Count (TLC)", "10^9/L", "haemogram", 4.0, 10.0, "Immune System"),
    _q("NEUT", "Neutrophils", "%", "haemogram", 40.0, 80.0, "Immune System"),
    _q("LYMPH", "Lymphocytes", "%", "haemogram", 20.0, 40.0, "Immune System"),
    _q("MONO", "Monocytes", "%", "haemogram", 2.0, 10.0, "Immune System"),
    _q("EOS", "Eosinophils", "%", "haemogram", 1.0, 6.0, "Immune System"),
    _q("BASO", "Basophils", "%", "haemogram", 0.0, 2.0, "Immune System"),
    _q("PLT", "Platelet Count", "10^9/L", "haemogram", 150.0, 410.0, "Hematopoietic / Coagulation"),
    _q("MPV", "Mean Platelet Volume (MPV)", "fL", "haemogram", 7.8, 11.2, "Hematopoietic"),
    # Diabetic profile
    _q("FBS", "Glucose (Fasting)", "mg/dL", "diabetic", 70.0, 99.0, "Pancreas / Metabolic"),
    _q("PPBS", "Glucose (PP)", "mg/dL", "diabetic", 70.0, 140.0, "Pancreas / Metabolic"),
    _q("HBA1C", "HbA1c (Glycated Haemoglobin)", "%", "diabetic", 4.0, 5.6, "Pancreas / Metabolic"),
    # Lipid profile
    _q("TC", "Total Cholesterol", "mg/dL", "lipid", None, 200.0, "Cardiovascular"),
    _q("TG", "Triglycerides", "mg/dL", "lipid", None, 150.0, "Cardiovascular"),
    _q("HDL", "HDL Cholesterol", "mg/dL", "lipid", 40.0, None, "Cardiovascular"),
    _q("LDL", "LDL Cholesterol", "mg/dL", "lipid", None, 100.0, "Cardiovascular"),
    _q("VLDL", "VLDL Cholesterol", "mg/dL", "lipid", 5.0, 40.0, "Cardiovascular"),
    # Liver function
    _q("TBIL", "Bilirubin (Total)", "mg/dL", "liver", 0.2, 1.2, "Liver / Biliary"),
    _q("DBIL", "Bilirubin (Direct)", "mg/dL", "liver", 0.0, 0.3, "Liver / Biliary"),
    _q("AST", "SGOT / AST", "U/L", "liver", 10.0, 40.0, "Liver"),
    _q("ALT", "SGPT / ALT", "U/L", "liver", 10.0, 45.0, "Liver"),
    _q("ALP", "Alkaline Phosphatase (ALP)", "U/L", "liver", 30.0, 120.0, "Liver / Biliary / Bone"),
    _q("TP", "Total Protein", "g/dL", "liver", 6.4, 8.3, "Liver"),
    _q("ALB", "Albumin", "g/dL", "liver", 3.5, 5.0, "Liver"),
    # Kidney function
    _q("UREA", "Urea", "mg/dL", "kidney", 15.0, 40.0, "Kidneys"),
    _q("CREAT", "Creatinine", "mg/dL", "kidney", 0.6, 1.2, "Kidneys"),
    _q("URIC", "Uric Acid", "mg/dL", "kidney", 3.5, 7.2, "Kidneys / Joints"),
    # Electrolytes & minerals
    _q("NA", "Sodium", "mEq/L", "electrolytes", 135.0, 145.0, "Kidneys / Electrolytes"),
    _q("K", "Potassium", "mEq/L", "electrolytes", 3.5, 5.1, "Kidneys / Electrolytes"),
    _q("HCO3", "Bicarbonate", "mEq/L", "electrolytes", 22.0, 29.0, "Kidneys / Acid-Base"),
    _q("CA", "Calcium", "mg/dL", "electrolytes", 8.8, 10.2, "Kidneys / Bone"),
    _q("PHOS", "Phosphorous", "mg/dL", "electrolytes", 2.5, 4.5, "Kidneys / Bone"),
    # Urine routine
    _q("URINE_PH", "Urine pH", "", "urine", 4.6, 8.0, "Urinary Tract"),
    _q("URINE_SG", "Urine Specific Gravity", "", "urine", 1.005, 1.030, "Urinary Tract"),
    _ql("URINE_PROTEIN", "Urine Protein", "urine", _URINE_DIPSTICK_OPTIONS, "NIL", "Kidneys"),
    _ql("URINE_GLUCOSE", "Urine Glucose", "urine", _URINE_DIPSTICK_OPTIONS, "NIL", "Kidneys / Metabolic"),
    _q("URINE_PUS", "Urine Pus Cells", "/hpf", "urine", 0.0, 5.0, "Urinary Tract"),
    _q("URINE_RBC", "Urine RBCs", "/hpf", "urine", 0.0, 2.0, "Urinary Tract"),
    # Blood bank
    {
        "code": "BLOOD_GROUP", "name": "Blood Group & Rh Type", "unit": "", "panel": "blood_bank",
        "kind": "INFORMATIONAL", "options": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
        "organ_system": "Hematology",
    },
    # Thyroid
    _q("TSH", "Thyroid Stimulating Hormone (TSH)", "uIU/mL", "thyroid", 0.35, 4.94, "Thyroid"),
    # Vitamins & iron studies
    _q("VITD", "25 OH Vitamin D (Total)", "ng/mL", "micronutrients", 30.0, 100.0, "Bone Metabolism"),
    _q("B12", "Vitamin B12", "pg/mL", "micronutrients", 211.0, 911.0, "Hematopoietic / Neurology"),
    _q("IRON", "Iron", "ug/dL", "micronutrients", 60.0, 170.0, "Hematopoietic"),
    _q("TIBC", "TIBC", "ug/dL", "micronutrients", 250.0, 450.0, "Hematopoietic"),
    # Endocrine
    _q("PTH", "PTH-Intact", "pg/mL", "endocrine", 15.0, 65.0, "Parathyroid / Kidneys"),
    # Serology
    _ql("HBSAG", "HBsAg", "serology", _SEROLOGY_OPTIONS, "NON_REACTIVE", "Liver / Immune"),
    _ql("HCV_AB", "HCV Ab", "serology", _SEROLOGY_OPTIONS, "NON_REACTIVE", "Liver / Immune"),
    _ql("HIV_AB_AG", "HIV 1 & 2 Ab & Ag", "serology", _SEROLOGY_OPTIONS, "NON_REACTIVE", "Immune System"),
    # Tumour markers
    _q("AFP", "Alpha Feto Protein (AFP)", "ng/mL", "tumour_markers", None, 7.0, "Liver"),
    _q("PSA", "PSA (Prostate Specific Antigen)", "ng/mL", "tumour_markers", None, 4.0, "Prostate"),
    # Stool & parasitology
    _ql("MP", "Malarial Parasite (MP)", "stool_parasitology", _DETECTION_OPTIONS, "NEGATIVE", "Hematology"),
    _ql("OCCULT_BLOOD", "Occult Blood", "stool_parasitology", _DETECTION_OPTIONS, "NEGATIVE", "Gastrointestinal Tract"),
]

LAB_TESTS: Dict[str, Dict[str, Any]] = {t["code"]: t for t in _LAB_TEST_LIST}

# Catalog codes whose meaning matches a registered analyte (app.services.terminology)
# exactly, so a transcribed result can join that analyte's longitudinal series.
# Fasting and post-prandial glucose are deliberately unmapped: the single
# "glucose" series would mix sampling contexts.
LAB_CODE_ANALYTES: Dict[str, str] = {
    "HB": "hemoglobin", "PCV": "hematocrit", "RBC": "red_blood_cell_count", "MCV": "mcv",
    "TLC": "white_blood_cell_count", "PLT": "platelet_count", "HBA1C": "hba1c",
    "TC": "cholesterol_total", "TG": "triglycerides", "HDL": "hdl_cholesterol", "LDL": "ldl_cholesterol",
    "TBIL": "bilirubin_total", "DBIL": "bilirubin_direct", "AST": "ast", "ALT": "alt",
    "ALP": "alkaline_phosphatase", "TP": "total_protein", "ALB": "albumin",
    "UREA": "urea", "CREAT": "creatinine", "URIC": "uric_acid",
    "NA": "sodium", "K": "potassium", "CA": "calcium", "PHOS": "phosphate",
    "TSH": "tsh", "PSA": "psa",
}

# Convenience groupings reused by the package catalog
CBC_CODES = [t["code"] for t in _LAB_TEST_LIST if t["panel"] == "haemogram"]
URINE_CODES = [t["code"] for t in _LAB_TEST_LIST if t["panel"] == "urine"]


def get_lab_test(code: str) -> Optional[Dict[str, Any]]:
    return LAB_TESTS.get(code)


def get_all_lab_tests() -> List[Dict[str, Any]]:
    return _LAB_TEST_LIST


def resolve_reference_interval(
    test: Dict[str, Any],
    patient_sex: Optional[str] = None,
    ref_low: Optional[float] = None,
    ref_high: Optional[float] = None,
) -> Tuple[Optional[float], Optional[float], bool]:
    """
    Returns (low, high, has_reference). Lab-supplied overrides win; otherwise
    sex-specific intervals are used when available. A sex-specific test without
    a known sex and without overrides has no usable reference interval.
    """
    if ref_low is not None or ref_high is not None:
        return ref_low, ref_high, True
    if test.get("ref_male") or test.get("ref_female"):
        if patient_sex == "M" and test.get("ref_male"):
            return test["ref_male"][0], test["ref_male"][1], True
        if patient_sex == "F" and test.get("ref_female"):
            return test["ref_female"][0], test["ref_female"][1], True
        return None, None, False
    low, high = test.get("ref_low"), test.get("ref_high")
    return low, high, (low is not None or high is not None)


def format_interval(low: Optional[float], high: Optional[float]) -> str:
    if low is None and high is None:
        return ""
    if low is None:
        return f"< {high:g}"
    if high is None:
        return f"> {low:g}"
    return f"{low:g} - {high:g}"


def determine_status(value: float, ref_low: Optional[float], ref_high: Optional[float]) -> str:
    """Classifies a quantitative test value relative to biological reference interval."""
    if ref_low is not None and value < ref_low:
        return "LOW"
    elif ref_high is not None and value > ref_high:
        return "HIGH"
    return "NORMAL"


def evaluate_result(
    code: str,
    value: Any,
    patient_sex: Optional[str] = None,
    ref_low: Optional[float] = None,
    ref_high: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Validates one entered result against the test catalog and flags it.
    Raises ValueError on unknown codes or values of the wrong type.
    Flags are reference-interval comparisons only, never a diagnosis.
    """
    test = LAB_TESTS.get(code)
    if test is None:
        raise ValueError(f"Unknown lab test code '{code}'.")

    base = {
        "code": code,
        "test_name": test["name"],
        "unit": test["unit"],
        "panel": test["panel"],
        "organ_system": test.get("organ_system", ""),
    }

    if test["kind"] == "QUANTITATIVE":
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"'{test['name']}' requires a numeric value; got {value!r}.")
        if ref_low is not None or ref_high is not None:
            return {
                **base,
                "result_value": num,
                "ref_low": ref_low,
                "ref_high": ref_high,
                "reference_source": "REPORTING_LABORATORY",
                "bio_ref_interval": format_interval(ref_low, ref_high),
                "status": determine_status(num, ref_low, ref_high),
            }
        # Without the laboratory's own interval the position is INDETERMINATE: a catalog
        # default is never substituted for it (manuscript Sec. V-A). The default is
        # returned separately, labelled, for orientation only.
        low, high, has_ref = resolve_reference_interval(test, patient_sex)
        sex_specific = bool(test.get("ref_male") or test.get("ref_female"))
        return {
            **base,
            "result_value": num,
            "ref_low": None,
            "ref_high": None,
            "reference_source": "NONE",
            "bio_ref_interval": "",
            "catalog_interval": format_interval(low, high) if has_ref else None,
            "catalog_interval_source": ("CATALOG_SEX_SPECIFIC_DEFAULT" if sex_specific else "CATALOG_TYPICAL_ADULT_DEFAULT") if has_ref else None,
            "status": "INDETERMINATE",
        }

    text = str(value).strip().upper()
    if text not in test["options"]:
        raise ValueError(f"'{test['name']}' must be one of {test['options']}; got {value!r}.")
    if test["kind"] == "QUALITATIVE":
        return {
            **base,
            "result_value": text,
            "reference_source": "CATALOG_EXPECTED_RESULT",
            "bio_ref_interval": test["expected"],
            "status": "NORMAL" if text == test["expected"] else "ABNORMAL",
        }
    return {**base, "result_value": text, "reference_source": "NONE", "bio_ref_interval": "", "status": "INFO"}
