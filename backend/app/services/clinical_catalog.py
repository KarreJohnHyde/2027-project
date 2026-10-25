"""
Clinical Diagnostic & Health Check-up Packages Catalog for MedTwin.

Implements the health check-up packages, top-up packages, and imaging services
(CT, Ultrasound, Angiography, Cardiac CT) exactly as specified by the clinical
service list. Nothing here is a diagnosis; it is an orderable service catalog.

Package components are typed so the API and UI can tell which items produce
laboratory results (LAB, linked to lab_service test codes) and which are
imaging, cardiac, procedural, or consultation services.
"""

from copy import deepcopy
from typing import List, Dict, Any, Optional

from app.services.lab_service import CBC_CODES, URINE_CODES, LAB_TESTS

# Component types
LAB = "LAB"
IMAGING = "IMAGING"
CARDIAC = "CARDIAC"
PROCEDURE = "PROCEDURE"
CONSULTATION = "CONSULTATION"
PACKAGE = "PACKAGE"  # Includes every component of another package

# Package kinds
COMPREHENSIVE = "COMPREHENSIVE"
TOP_UP = "TOP_UP"


def _c(name: str, ctype: str, lab_codes: Optional[List[str]] = None, note: Optional[str] = None,
       includes_package: Optional[str] = None) -> Dict[str, Any]:
    comp: Dict[str, Any] = {"name": name, "type": ctype, "lab_codes": lab_codes or []}
    if note:
        comp["note"] = note
    if includes_package:
        comp["includes_package"] = includes_package
    return comp


PAP_PSA_NOTE = "Cervical (Pap) smear for women; PSA for men."

HEALTH_PACKAGES: List[Dict[str, Any]] = [
    {
        "id": "PKG-GEN-01",
        "name": "General Health Check-up",
        "kind": COMPREHENSIVE,
        "category": "Comprehensive Health",
        "description": "Baseline blood, urine, imaging and ECG screening with a general consultation.",
        "components": [
            _c("Complete Haemogram", LAB, CBC_CODES),
            _c("Diabetic Profile (Fasting, PP & HbA1c)", LAB, ["FBS", "PPBS", "HBA1C"]),
            _c("Lipid Profile Panel", LAB, ["TC", "TG", "HDL", "LDL", "VLDL"]),
            _c("Liver Function Panel", LAB, ["TBIL", "DBIL", "AST", "ALT", "ALP", "TP", "ALB"]),
            _c("Urea, Creatinine, Uric Acid", LAB, ["UREA", "CREAT", "URIC"]),
            _c("Urine Complete Analysis / Routine", LAB, URINE_CODES),
            _c("Blood Grouping and Rh Type", LAB, ["BLOOD_GROUP"]),
            _c("Chest X-Ray", IMAGING),
            _c("E.C.G. Computerised", CARDIAC),
            _c("Ultrasound Abdomen Scan", IMAGING),
            _c("General Consultation", CONSULTATION),
        ],
    },
    {
        "id": "PKG-WOMEN-01",
        "name": "Well Women Master Health Check-up",
        "kind": COMPREHENSIVE,
        "category": "Women's Health",
        "description": "Women's health screening with Pap smear, pelvic and abdominal ultrasound, thyroid and metabolic tests.",
        "components": [
            _c("Creatinine", LAB, ["CREAT"]),
            _c("Glucose (Fasting)", LAB, ["FBS"]),
            _c("Urea", LAB, ["UREA"]),
            _c("Cervical (Pap) Smear", PROCEDURE),
            _c("Chest X-Ray", IMAGING),
            _c("Gynaecology Consultation with Examination", CONSULTATION),
            _c("Ultrasound Scan – Pelvic and Abdomen", IMAGING),
            _c("Glucose (PP)", LAB, ["PPBS"]),
            _c("Lipid Profile Panel", LAB, ["TC", "TG", "HDL", "LDL", "VLDL"]),
            _c("Haemogram", LAB, CBC_CODES),
            _c("Thyroid Stimulating Hormone (TSH)", LAB, ["TSH"]),
            _c("E.C.G. Computerised", CARDIAC),
        ],
    },
    {
        "id": "PKG-EXEC-01",
        "name": "Executive Health Check-up",
        "kind": COMPREHENSIVE,
        "category": "Executive Wellness",
        "description": "The General Health Package plus echocardiography and Pap smear / PSA screening.",
        "components": [
            _c("General Health Package", PACKAGE, includes_package="PKG-GEN-01"),
            _c("ECHO Cardiography", CARDIAC),
            _c("Pap Smear / PSA", LAB, ["PSA"], note=PAP_PSA_NOTE),
        ],
    },
    {
        "id": "PKG-CARD-01",
        "name": "Cardiac Health Check-up",
        "kind": COMPREHENSIVE,
        "category": "Cardiovascular",
        "description": "The General Health Package plus ECHO, treadmill test (TMT) and a cardiologist consultation.",
        "components": [
            _c("General Health Package", PACKAGE, includes_package="PKG-GEN-01"),
            _c("ECHO Cardiography", CARDIAC),
            _c("Pap Smear / PSA", LAB, ["PSA"], note=PAP_PSA_NOTE),
            _c("TMT (Treadmill Test)", CARDIAC),
            _c("Cardiologist Consultation", CONSULTATION),
        ],
    },
    {
        "id": "PKG-RENAL-BASIC",
        "name": "Renal Basic - Top Up Package",
        "kind": TOP_UP,
        "category": "Nephrology",
        "description": "Electrolytes, minerals and urea with a nephrology consultation.",
        "components": [
            _c("Bicarbonate", LAB, ["HCO3"]),
            _c("Calcium", LAB, ["CA"]),
            _c("Phosphorous", LAB, ["PHOS"]),
            _c("Potassium", LAB, ["K"]),
            _c("Urea", LAB, ["UREA"]),
            _c("Sodium", LAB, ["NA"]),
            _c("Nephrology Consultation", CONSULTATION),
        ],
    },
    {
        "id": "PKG-DIGEST-01",
        "name": "Digestive Health - Top Up",
        "kind": TOP_UP,
        "category": "Gastroenterology",
        "description": "Vitamin and iron studies, malarial parasite and occult blood with a gastroenterology consultation.",
        "components": [
            _c("25 OH Vitamin D (Total)", LAB, ["VITD"]),
            _c("Iron", LAB, ["IRON"]),
            _c("TIBC", LAB, ["TIBC"]),
            _c("Vitamin B12", LAB, ["B12"]),
            _c("Malarial Parasite (MP)", LAB, ["MP"]),
            _c("Occult Blood", LAB, ["OCCULT_BLOOD"]),
            _c("Gastroenterology Consultation", CONSULTATION),
        ],
    },
    {
        "id": "PKG-RENAL-ADV",
        "name": "Renal Advance - Top Up Package",
        "kind": TOP_UP,
        "category": "Nephrology",
        "description": "Vitamin D, PTH, iron studies, B12 and viral serology (HBsAg, HCV, HIV).",
        "components": [
            _c("25 OH Vitamin D (Total)", LAB, ["VITD"]),
            _c("PTH-Intact", LAB, ["PTH"]),
            _c("Iron", LAB, ["IRON"]),
            _c("TIBC", LAB, ["TIBC"]),
            _c("Vitamin B12", LAB, ["B12"]),
            _c("HBsAg", LAB, ["HBSAG"]),
            _c("HCV Ab", LAB, ["HCV_AB"]),
            _c("HIV 1 & 2 Ab & Ag", LAB, ["HIV_AB_AG"]),
        ],
    },
    {
        "id": "PKG-LIVER-01",
        "name": "Liver Health - Top Up Package",
        "kind": TOP_UP,
        "category": "Hepatology",
        "description": "AFP, hepatitis B/C serology and FibroScan with a gastroenterology consultation.",
        "components": [
            _c("Alpha Feto Protein (AFP)", LAB, ["AFP"]),
            _c("HBsAg", LAB, ["HBSAG"]),
            _c("HCV Ab", LAB, ["HCV_AB"]),
            _c("FIBRO SCAN TEST", IMAGING),
            _c("Gastroenterology Consultation", CONSULTATION),
        ],
    },
]

IMAGING_SERVICES: List[Dict[str, Any]] = [
    {
        "id": "CT",
        "category": "CT Imaging",
        "description": (
            "CT imaging provides detailed cross-sectional images of internal organs, bones, and blood "
            "vessels, supporting diagnosis, image-guided procedures, treatment monitoring, and follow-up care."
        ),
        "modalities": [
            {"code": "CT-BRAIN", "name": "CT Brain"},
            {"code": "CT-NECK", "name": "CT Neck"},
            {"code": "CT-THORAX", "name": "CT Thorax"},
            {"code": "HRCT-CHEST", "name": "High-Resolution CT (HRCT) Chest"},
            {"code": "CT-ABDOMEN-PELVIS", "name": "CT Abdomen & Pelvis"},
            {"code": "CT-KUB", "name": "CT KUB (Kidneys, Ureters and Bladder)"},
            {"code": "CT-SPINE-JOINTS-EXTREMITIES", "name": "CT Spine, Joints, and Extremities"},
        ],
    },
    {
        "id": "US",
        "category": "Ultrasound Imaging",
        "description": (
            "Ultrasound imaging uses high-frequency sound waves to generate real-time images without "
            "radiation exposure. It is a safe and non-invasive diagnostic tool used across multiple "
            "clinical indications."
        ),
        "modalities": [
            {"code": "US-ABDOMEN", "name": "Abdominal Ultrasound",
             "details": "Liver, spleen, pancreas, kidneys, biliary system"},
            {"code": "US-PELVIS", "name": "Pelvic Ultrasound",
             "details": "Uterus, ovaries, urinary bladder"},
            {"code": "US-TVS-TRUS", "name": "Transvaginal / Transrectal Ultrasound"},
            {"code": "US-DOPPLER", "name": "Vascular and Colour Doppler Studies"},
        ],
    },
    {
        "id": "ANGIO",
        "category": "Angiography",
        "description": "Angiographic studies of the cerebral, carotid, pulmonary, aortic, renal and peripheral vessels.",
        "modalities": [
            {"code": "ANGIO-CEREBRAL-CAROTID", "name": "Cerebral and Carotid Angiography"},
            {"code": "ANGIO-PULMONARY", "name": "Pulmonary Angiography"},
            {"code": "ANGIO-AORTOGRAM", "name": "Thoracic, Abdominal, and Whole Aortogram"},
            {"code": "ANGIO-RENAL-PERIPHERAL", "name": "Renal and Peripheral Angiography"},
        ],
    },
    {
        "id": "CARDIAC-CT",
        "category": "Cardiac CT Services",
        "description": "ECG-gated cardiac CT for coronary assessment and structural heart procedure planning.",
        "modalities": [
            {"code": "CARDIAC-CT-CORONARY", "name": "Coronary CT Angiography"},
            {"code": "CARDIAC-CT-ANATOMY", "name": "Cardiac Anatomy Assessment"},
            {"code": "CARDIAC-CT-CALCIUM", "name": "Calcium Scoring"},
            {"code": "CARDIAC-CT-STRUCTURAL", "name": "Structural Heart Procedure Planning (TAVR / MAVR / TTVR)"},
        ],
    },
]

_PACKAGES_BY_ID = {p["id"]: p for p in HEALTH_PACKAGES}


def _validate_catalog() -> None:
    """Fail fast at import time if a component references an unknown test or package."""
    for pkg in HEALTH_PACKAGES:
        for comp in pkg["components"]:
            for code in comp["lab_codes"]:
                if code not in LAB_TESTS:
                    raise RuntimeError(f"{pkg['id']}: unknown lab code '{code}'")
            inc = comp.get("includes_package")
            if inc and inc not in _PACKAGES_BY_ID:
                raise RuntimeError(f"{pkg['id']}: unknown included package '{inc}'")


_validate_catalog()


def get_all_packages() -> List[Dict[str, Any]]:
    return HEALTH_PACKAGES


def get_all_imaging_services() -> List[Dict[str, Any]]:
    return IMAGING_SERVICES


def get_package_by_id(pkg_id: str) -> Dict[str, Any]:
    for p in HEALTH_PACKAGES:
        if p["id"].lower() == pkg_id.lower():
            return p
    return {}


def get_expanded_package(pkg_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns the package with included packages expanded inline and the
    de-duplicated list of lab test codes the package produces results for.
    """
    pkg = get_package_by_id(pkg_id)
    if not pkg:
        return None
    expanded = deepcopy(pkg)
    lab_codes: List[str] = []

    def collect(components: List[Dict[str, Any]]) -> None:
        for comp in components:
            if comp["type"] == PACKAGE:
                inc = deepcopy(_PACKAGES_BY_ID[comp["includes_package"]])
                comp["included_components"] = inc["components"]
                collect(inc["components"])
            for code in comp["lab_codes"]:
                if code not in lab_codes:
                    lab_codes.append(code)

    collect(expanded["components"])
    expanded["lab_test_codes"] = lab_codes
    return expanded


def get_orderable_item(item_id: str) -> Optional[Dict[str, str]]:
    """Resolves a package ID or imaging code to its canonical name and category."""
    pkg = get_package_by_id(item_id)
    if pkg:
        return {"id": pkg["id"], "name": pkg["name"], "category": pkg["category"], "item_type": "PACKAGE"}
    for group in IMAGING_SERVICES:
        for m in group["modalities"]:
            if m["code"].lower() == item_id.lower():
                return {"id": m["code"], "name": m["name"], "category": group["category"], "item_type": "IMAGING"}
    return None
