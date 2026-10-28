"""Clinical terminology resources for MedTwin's transparent text extractor.

Three kinds of resource live here:

* Analyte definitions: aliases, accepted units, organ association and, where
  unambiguous, a LOINC code. LOINC mappings are curated and have not been
  checked against a licensed LOINC release; responses label them that way.
* Unit conversions: only standard SI conversion factors for specific analytes.
  A value is never converted between units without an entry here.
* Finding and anatomical-site lexicons. Anatomical sites resolve to structure
  names in the bundled Z-Anatomy atlas index (app/data/atlas_structures.json),
  so a documented site can be linked to a labelled reference structure.

Organ associations are schematic. They never place evidence at a location.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOINC = "http://loinc.org"
LOINC_MAPPING_STATUS = "CURATED_NOT_VERIFIED_AGAINST_LOINC_RELEASE"

ANATOMY_SYSTEMS = (
    "heart",
    "lungs",
    "brain",
    "liver",
    "pancreas",
    "intestines",
    "nervous",
    "skeletal",
    "hybrid",
    "kidneys",
)


@dataclass(frozen=True)
class Analyte:
    name: str
    display: str
    aliases: str
    units: Optional[str]
    system: Optional[str] = None
    association: str = "SCHEMATIC_ORGAN_ASSOCIATION"
    loinc: dict[str, str] = field(default_factory=dict)
    unitless_unit: Optional[str] = None
    note: Optional[str] = None
    # A label match is rejected when the text immediately before it ends with this
    # qualifier: "HDL Cholesterol 48" is not total cholesterol, "Indirect Bilirubin"
    # is not total bilirubin, even when OCR splits the label across lines.
    forbid_prefix: Optional[str] = None


_COUNT_UNITS = (
    r"(?:x\s*)?10\s*(?:\^|\*|e)?\s*9\s*/\s*l|(?:x\s*)?10\s*(?:\^|\*|e)?\s*3\s*/\s*(?:µl|ul|μl|mm3|mm\^3)"
    r"|k\s*/\s*(?:µl|ul|μl)|(?:cells?\s*)?/\s*(?:µl|ul|μl|mm3|cu\.?\s*mm|cumm)"
)
_PERCENT = r"%|percent"

# Order matters: more specific aliases (NT-proBNP, direct bilirubin) precede
# generic ones so that a span is claimed by the most specific analyte.
ANALYTES: tuple[Analyte, ...] = (
    Analyte("heart_rate", "Heart rate", r"heart\s*rate|pulse(?:\s*rate)?|\bhr\b", r"bpm|beats\s*(?:/|per)\s*min(?:ute)?|/\s*min", "heart", "PHYSIOLOGICAL_SIGNAL", {"*": "8867-4"}),
    Analyte("respiratory_rate", "Respiratory rate", r"respiratory\s*rate|resp(?:iration)?\s*rate|\brr\b", r"breaths\s*(?:/|per)\s*min(?:ute)?|/\s*min", "lungs", "PHYSIOLOGICAL_SIGNAL", {"*": "9279-1"}),
    Analyte("oxygen_saturation", "Oxygen saturation", r"spo2|sp02|sao2|oxygen\s*saturation|o2\s*sat(?:uration)?", r"%|percent", "lungs", "PHYSIOLOGICAL_SIGNAL"),
    Analyte("temperature", "Body temperature", r"(?:body\s*)?temperature|\btemp\b", r"°\s*[cf]|deg(?:rees?)?\s*[cf]|(?<=\d)\s*[cf]\b", None, "SYSTEMIC_MEASURE", {"*": "8310-5"}),
    Analyte("body_weight", "Body weight", r"(?:body\s*)?weight|\bwt\b", r"kg|lbs?", None, "SYSTEMIC_MEASURE", {"*": "29463-7"}),
    Analyte("body_height", "Body height", r"(?:body\s*)?height|\bht\b", r"cm|m(?![a-z])|in(?:ches)?", None, "SYSTEMIC_MEASURE", {"*": "8302-2"}),
    Analyte("bmi", "Body mass index", r"\bbmi\b|body\s*mass\s*index", r"kg\s*/\s*m(?:2|²|\^2)", None, "SYSTEMIC_MEASURE", {"*": "39156-5"}),
    Analyte("ejection_fraction", "Left ventricular ejection fraction", r"left\s*ventricular\s*ejection\s*fraction|\blvef\b|ejection\s*fraction|\bef\b", r"%|percent", "heart", "DOCUMENTED_ORGAN_MEASURE", {"*": "10230-1"}),
    Analyte("nt_probnp", "NT-proBNP", r"nt[-\s]*pro[-\s]*bnp|n[-\s]*terminal\s*pro[-\s]*b[-\s]*type\s*natriuretic\s*peptide", r"pg\s*/\s*ml|ng\s*/\s*l", "heart", loinc={"*": "33762-6"}),
    Analyte("bnp", "B-type natriuretic peptide", r"\bbnp\b|b[-\s]*type\s*natriuretic\s*peptide|brain\s*natriuretic\s*peptide", r"pg\s*/\s*ml|ng\s*/\s*l", "heart", loinc={"*": "30934-4"}),
    Analyte("troponin_i", "Troponin I", r"(?:hs[-\s]*)?troponin\s*i\b|\b(?:hs[-\s]*)?c?tni\b", r"ng\s*/\s*l|ng\s*/\s*ml|pg\s*/\s*ml|µg\s*/\s*l|ug\s*/\s*l", "heart", note="Conventional and high-sensitivity assays are not interchangeable."),
    Analyte("troponin_t", "Troponin T", r"(?:hs[-\s]*)?troponin\s*t\b|\b(?:hs[-\s]*)?c?tnt\b", r"ng\s*/\s*l|ng\s*/\s*ml|pg\s*/\s*ml", "heart", note="Conventional and high-sensitivity assays are not interchangeable."),
    Analyte("mchc", "Mean corpuscular hemoglobin concentration", r"\bmchc\b|mean\s*corpuscular\s*ha?emoglobin\s*concentration(?:\s*\(\s*mchc\s*\))?", r"g\s*/\s*dl|g\s*/\s*l|%", None, "SYSTEMIC_MEASURE", {"g/dL": "786-4"}),
    Analyte("mch", "Mean corpuscular hemoglobin", r"\bmch\b|mean\s*corpuscular\s*ha?emoglobin(?!\s*concentration)(?:\s*\(\s*mch\s*\))?", r"pg", None, "SYSTEMIC_MEASURE", {"*": "785-6"}),
    Analyte("hemoglobin", "Hemoglobin", r"ha?emoglobin(?!\s*[-\s]*(?:hb\s*)?a1c)(?:\s*\(\s*hb\s*\))?|\bhgb\b|\bhb\b(?!\s*a1c)", r"gm?\s*/\s*dl|g\s*/\s*l|mmol\s*/\s*l", None, "SYSTEMIC_MEASURE", {"*": "718-7"},
            forbid_prefix=r"(?:corpuscular|glycosylated|glycated|cell|mean)[-\s(]*$"),
    Analyte("hematocrit", "Hematocrit", r"ha?ematocrit|\bhct\b|\bpcv\b|packed\s*cell\s*volume(?:\s*\(\s*pcv\s*\))?", r"%|l\s*/\s*l", None, "SYSTEMIC_MEASURE", {"*": "4544-3"}),
    Analyte("rdw", "Red cell distribution width", r"\brdw(?:\s*[-\s]*cv)?\b|red\s*(?:blood\s*)?cell\s*distribution\s*width(?:\s*[-\s]*cv)?", _PERCENT, None, "SYSTEMIC_MEASURE", {"%": "788-0"}),
    Analyte("white_blood_cell_count", "White blood cell count", r"white\s*blood\s*cell(?:s|\s*count)?|(?:total\s*)?\bwbc\b(?:\s*count)?|total\s*leu[ck]ocyte\s*count|\btlc\b|leu[ck]ocytes", _COUNT_UNITS, None, "SYSTEMIC_MEASURE", {"*": "6690-2"}),
    Analyte("platelet_count", "Platelet count", r"platelets?(?:\s*count)?|\bplt\b", _COUNT_UNITS + r"|lakhs?\s*/\s*(?:cumm|cu\.?\s*mm|mm3|µl|ul|μl)", None, "SYSTEMIC_MEASURE", {"*": "777-3"}),
    Analyte("red_blood_cell_count", "Red blood cell count", r"red\s*blood\s*cell(?:s|\s*count)?|(?:total\s*)?\brbc\b(?:\s*count)?|erythrocytes(?!\s*sedimentation)", r"(?:x\s*)?10\s*(?:\^|\*|e)?\s*12\s*/\s*l|(?:x\s*)?10\s*(?:\^|\*|e)?\s*6\s*/\s*(?:µl|ul|μl)|m\s*/\s*(?:µl|ul)|millions?\s*(?:cells\s*)?/\s*(?:µl|ul|μl|mm3|cumm|cu\.?\s*mm)", None, "SYSTEMIC_MEASURE", {"*": "789-8"}),
    Analyte("mcv", "Mean corpuscular volume", r"\bmcv\b|mean\s*corpuscular\s*volume(?:\s*\(\s*mcv\s*\))?", r"fl", None, "SYSTEMIC_MEASURE", {"*": "787-2"}),
    Analyte("mpv", "Mean platelet volume", r"mean\s*platelet\s*volume(?:\s*\(\s*mpv\s*\))?|\bmpv\b", r"fl", None, "SYSTEMIC_MEASURE", {"*": "32623-1"}),
    Analyte("rdw_sd", "Red cell distribution width (SD)", r"\brdw\s*[-\s]*sd\b", r"fl", None, "SYSTEMIC_MEASURE", {"*": "21000-5"}),
    *(
        Analyte(f"absolute_{cell}_count", f"Absolute {cell} count", rf"absolute\s*{cell}\s*count|\ba{cell[0]}c\b", _COUNT_UNITS, None, "SYSTEMIC_MEASURE")
        for cell in ("neutrophil", "lymphocyte", "monocyte", "eosinophil", "basophil")
    ),
    Analyte("neutrophils_percent", "Neutrophils (%)", r"neutrophils?|polymorphs|\bpmn\b", _PERCENT, None, "SYSTEMIC_MEASURE", {"%": "770-8"}),
    Analyte("lymphocytes_percent", "Lymphocytes (%)", r"lymphocytes?", _PERCENT, None, "SYSTEMIC_MEASURE", {"%": "736-9"}),
    Analyte("monocytes_percent", "Monocytes (%)", r"monocytes?", _PERCENT, None, "SYSTEMIC_MEASURE", {"%": "5905-5"}),
    Analyte("eosinophils_percent", "Eosinophils (%)", r"eosinophils?", _PERCENT, None, "SYSTEMIC_MEASURE", {"%": "713-8"}),
    Analyte("basophils_percent", "Basophils (%)", r"basophils?", _PERCENT, None, "SYSTEMIC_MEASURE", {"%": "706-2"}),
    Analyte("hba1c", "Hemoglobin A1c", r"glyc(?:ated|osylated)\s*ha?emoglobin(?:\s*[-–(]?\s*hb\s*a1c\s*\)?)?|hb\s*a1c|ha?emoglobin\s*a1c|\ba1c\b", r"%|mmol\s*/\s*mol", None, "METABOLIC_MARKER", {"%": "4548-4", "mmol/mol": "59261-8"}, note="Metabolic marker; not an anatomical pancreatic finding."),
    Analyte("estimated_average_glucose", "Estimated average glucose (calculated from HbA1c)", r"estimated\s*average\s*glucose|\beag\b", r"mg\s*/\s*dl|mmol\s*/\s*l", None, "METABOLIC_MARKER", {"mg/dL": "27353-2"}, note="Calculated from HbA1c by the laboratory; not a measured glucose."),
    Analyte("glucose", "Glucose", r"(?:fasting\s*|random\s*)?(?:blood\s*|plasma\s*|serum\s*)?glucose|\bfbs\b|\bfbg\b|\brbs\b", r"mg\s*/\s*dl|mmol\s*/\s*l", None, "METABOLIC_MARKER", note="Metabolic marker; not an anatomical pancreatic finding.",
            forbid_prefix=r"(?:estimated\s*average|average|mean\s*plasma|urine)[-\s]*$"),
    Analyte("creatinine", "Creatinine", r"(?:serum\s*)?creatinine(?!\s*(?:ratio|clearance))|\bs\.?\s*cr\b|\bcreat\b", r"mg\s*/\s*dl|µmol\s*/\s*l|umol\s*/\s*l|μmol\s*/\s*l", "kidneys", loinc={"mg/dL": "2160-0"},
            forbid_prefix=r"(?:albumin|protein)[-/\s]*(?:to[-\s]*)?$"),
    Analyte("blood_urea_nitrogen", "Blood urea nitrogen", r"blood\s*urea\s*nitrogen|\bbun\b|urea\s*nitrogen", r"mg\s*/\s*dl", "kidneys", loinc={"*": "3094-0"}),
    Analyte("urea", "Urea", r"\burea\b(?!\s*nitrogen)", r"mmol\s*/\s*l|mg\s*/\s*dl", "kidneys", note="Urea and urea nitrogen differ by a factor of about 2.14 and are never compared directly."),
    Analyte("egfr_documented", "eGFR (as documented)", r"\begfr\b(?:\s*[-–]\s*creatinine\s*clearance)?(?:\s*\(\s*egfr\s*\))?|estimated\s*gfr|estimated\s*glomerular\s*filtration\s*rate(?:\s*\(\s*egfr\s*\))?", r"ml\s*/\s*min\s*/\s*1\.73\s*m(?:2|²|\^2)|ml\s*/\s*min", "kidneys", note="Documented value; the equation used by the reporting laboratory is not known."),
    Analyte("albumin_creatinine_ratio", "Urine albumin-to-creatinine ratio", r"(?:urine\s*)?albumin[-/\s]*(?:to[-\s]*)?creatinine\s*ratio|\buacr\b|\bacr\b", r"mg\s*/\s*g|mg\s*/\s*mmol", "kidneys"),
    Analyte("alt", "Alanine aminotransferase (ALT)", r"\balt\b|\bsgpt\b|alanine\s*(?:amino)?transferase|alanine\s*transaminase", r"u\s*/\s*l|iu\s*/\s*l|units\s*/\s*l", "liver", loinc={"*": "1742-6"}),
    Analyte("ast", "Aspartate aminotransferase (AST)", r"\bast\b|\bsgot\b|aspartate\s*(?:amino)?transferase|aspartate\s*transaminase", r"u\s*/\s*l|iu\s*/\s*l|units\s*/\s*l", "liver", loinc={"*": "1920-8"}),
    Analyte("alkaline_phosphatase", "Alkaline phosphatase (ALP)", r"\balp\b|alkaline\s*phosphatase", r"u\s*/\s*l|iu\s*/\s*l|units\s*/\s*l", "liver", loinc={"*": "6768-6"}),
    Analyte("ggt", "Gamma-glutamyl transferase (GGT)", r"\bggtp?\b|gamma[-\s]*glutamyl\s*transferase|gamma[-\s]*gt", r"u\s*/\s*l|iu\s*/\s*l|units\s*/\s*l", "liver", loinc={"*": "2324-2"}),
    Analyte("bilirubin_direct", "Direct bilirubin", r"(?:direct|conjugated)\s*bilirubin|bilirubin,?\s*(?:direct|conjugated)|\bdbil\b", r"mg\s*/\s*dl|µmol\s*/\s*l|umol\s*/\s*l|μmol\s*/\s*l", "liver", loinc={"mg/dL": "1968-7"}),
    Analyte("bilirubin_indirect", "Indirect bilirubin", r"(?:indirect|unconjugated)\s*bilirubin|bilirubin,?\s*(?:indirect|unconjugated)", r"mg\s*/\s*dl|µmol\s*/\s*l|umol\s*/\s*l|μmol\s*/\s*l", "liver", loinc={"mg/dL": "1971-1"}),
    Analyte("bilirubin_total", "Total bilirubin", r"total\s*bilirubin|bilirubin,?\s*total|\btbil\b|bilirubin", r"mg\s*/\s*dl|µmol\s*/\s*l|umol\s*/\s*l|μmol\s*/\s*l", "liver", loinc={"mg/dL": "1975-2"},
            forbid_prefix=r"(?:indirect|direct|conjugated|unconjugated|urine)[-\s]*$"),
    Analyte("albumin", "Albumin", r"(?:serum\s*)?albumin(?!\s*[-/]?\s*(?:to\s*)?creatinine)", r"g\s*/\s*dl|g\s*/\s*l", "liver", loinc={"g/dL": "1751-7"}),
    Analyte("total_protein", "Total protein", r"total\s*protein", r"g\s*/\s*dl|g\s*/\s*l", "liver", loinc={"g/dL": "2885-2"}),
    Analyte("inr", "International normalized ratio", r"\binr\b|international\s*normali[sz]ed\s*ratio", None, "liver", unitless_unit="{ratio}", loinc={"*": "6301-6"}),
    Analyte("lipase", "Lipase", r"(?:serum\s*)?lipase", r"u\s*/\s*l|iu\s*/\s*l|units\s*/\s*l", "pancreas", loinc={"*": "3040-3"}, note="Pancreatic enzyme; association with the pancreas is biochemical, not spatial."),
    Analyte("amylase", "Amylase", r"(?:serum\s*)?amylase", r"u\s*/\s*l|iu\s*/\s*l|units\s*/\s*l", "pancreas", loinc={"*": "1798-8"}, note="Not specific to the pancreas."),
    Analyte("cholesterol_hdl_ratio", "Total cholesterol/HDL ratio", r"(?:total\s*)?cholesterol\s*/\s*hdl(?:\s*cholesterol)?\s*ratio|\btc\s*/\s*hdl\b(?:\s*ratio)?|chol\s*/\s*hdl\s*ratio", None, None, "METABOLIC_MARKER", unitless_unit="{ratio}", loinc={"*": "9830-1"}),
    Analyte("vldl_cholesterol", "VLDL cholesterol", r"\bvldl(?:[-\s]*c(?:holesterol)?)?\b|very[-\s]*low[-\s]*density\s*lipoprotein(?:\s*cholesterol)?", r"mg\s*/\s*dl|mmol\s*/\s*l", None, "METABOLIC_MARKER", {"mg/dL": "13458-5"}),
    Analyte("hdl_cholesterol", "HDL cholesterol", r"\bhdl(?:[-\s]*c(?:holesterol)?)?\b|high[-\s]*density\s*lipoprotein(?:\s*cholesterol)?", r"mg\s*/\s*dl|mmol\s*/\s*l", None, "METABOLIC_MARKER", {"mg/dL": "2085-9"},
            forbid_prefix=r"non[-\s]*$"),
    Analyte("ldl_cholesterol", "LDL cholesterol", r"\bldl(?:[-\s]*c(?:holesterol)?)?\b|low[-\s]*density\s*lipoprotein(?:\s*cholesterol)?", r"mg\s*/\s*dl|mmol\s*/\s*l", None, "METABOLIC_MARKER",
            forbid_prefix=r"(?:very[-\s]*)$"),
    Analyte("cholesterol_total", "Total cholesterol", r"total\s*cholesterol|cholesterol,?\s*total|\bcholesterol\b(?!\s*,?\s*(?:hdl|ldl|/))", r"mg\s*/\s*dl|mmol\s*/\s*l", None, "METABOLIC_MARKER", {"mg/dL": "2093-3"},
            forbid_prefix=r"(?:hdl|ldl|vldl|non[-\s]*hdl|lipoprotein|density)[-\s]*(?:c[-\s]*)?$"),
    # "Tniglycerides", "Trigiycerides": common OCR misreads of the long name.
    Analyte("triglycerides", "Triglycerides", r"t[rn][il1]g[l1i]ycerides?|\btrigs?\b|\btg\b", r"mg\s*/\s*dl|mmol\s*/\s*l", None, "METABOLIC_MARKER", {"mg/dL": "2571-8"}),
    Analyte("tsh", "Thyroid-stimulating hormone", r"\btsh\b(?:\s*\(\s*thyroid[-\s]*stimulating\s*hormone\s*\))?|thyroid[-\s]*stimulating\s*hormone(?:\s*\(\s*tsh\s*\))?|thyrotropin", r"miu\s*/\s*l|mu\s*/\s*l|µiu\s*/\s*ml|uiu\s*/\s*ml|μiu\s*/\s*ml|mlu\s*/\s*l", None, "SYSTEMIC_MEASURE", {"*": "3016-3"}),
    Analyte("free_t3", "Free triiodothyronine (FT3)", r"\bft3\b|free\s*t3|free\s*triiodothyronine", r"pg\s*/\s*ml|pmol\s*/\s*l|ng\s*/\s*dl", None, "SYSTEMIC_MEASURE", {"*": "3051-0"}),
    Analyte("free_t4", "Free thyroxine (FT4)", r"\bft4\b|free\s*t4|free\s*thyroxine", r"ng\s*/\s*dl|pmol\s*/\s*l|pg\s*/\s*ml", None, "SYSTEMIC_MEASURE", {"*": "3024-7"}),
    Analyte("total_t3", "Total triiodothyronine (T3)", r"(?:total\s*)?\bt3\b(?!\s*uptake)|(?:total\s*)?triiodothyronine", r"ng\s*/\s*dl|nmol\s*/\s*l|ng\s*/\s*ml", None, "SYSTEMIC_MEASURE", {"ng/dL": "3053-6"},
            forbid_prefix=r"free[-\s]*$"),
    Analyte("total_t4", "Total thyroxine (T4)", r"(?:total\s*)?\bt4\b|(?:total\s*)?thyroxine", r"µg\s*/\s*dl|μg\s*/\s*dl|ug\s*/\s*dl|mcg\s*/\s*dl|nmol\s*/\s*l", None, "SYSTEMIC_MEASURE", {"µg/dL": "3026-2"},
            forbid_prefix=r"free[-\s]*$"),
    Analyte("vitamin_d_25oh", "25-hydroxyvitamin D", r"25\s*[-(]?\s*(?:oh|hydroxy)\s*\)?\s*[-\s]*vitamin\s*d\s*(?:2|3)?(?:\s*\(\s*total\s*\))?|vitamin\s*d\s*(?:2|3|total)?(?:\s*\(\s*total\s*\))?|25\s*\(\s*oh\s*\)\s*d", r"ng\s*/\s*ml|nmol\s*/\s*l", None, "SYSTEMIC_MEASURE", {"ng/mL": "1989-3"}),
    Analyte("vitamin_b12", "Vitamin B12", r"vitamin\s*b\s*[-\s]*12|cyanocobalamin|cobalamin|\bb12\b", r"pg\s*/\s*ml|pmol\s*/\s*l|ng\s*/\s*l", None, "SYSTEMIC_MEASURE", {"pg/mL": "2132-9"}),
    Analyte("cea", "Carcinoembryonic antigen", r"\bcea\b|carcinoembryonic\s*antigen", r"ng\s*/\s*ml|µg\s*/\s*l|ug\s*/\s*l|μg\s*/\s*l", None, "SYSTEMIC_MEASURE", {"*": "2039-6"},
            note="Tumour marker; a value is not evidence for or against malignancy on its own."),
    Analyte("c_reactive_protein", "C-reactive protein", r"(?:hs[-\s]*)?c[-\s]*reactive\s*protein(?:\s*\(\s*(?:hs[-\s]*)?crp\s*\))?|\b(?:hs[-\s]*)?crp\b", r"mg\s*/\s*l|mg\s*/\s*dl", None, "SYSTEMIC_MEASURE"),
    Analyte("esr", "Erythrocyte sedimentation rate", r"\besr\b|erythrocytes?\s*sedimentation\s*rate(?:\s*\(\s*esr\s*\))?|sed\s*rate", r"mm\s*/\s*h(?:r|our)?|mm\s*/\s*1st\s*h(?:ou)?r|mm\s*(?:in|at)\s*1\s*h(?:ou)?r", None, "SYSTEMIC_MEASURE"),
    Analyte("sodium", "Sodium", r"(?:serum\s*)?sodium|\bna\+?(?=\s*[:=]?\s*\d)", r"mmol\s*/\s*l|meq\s*/\s*l", None, "SYSTEMIC_MEASURE", {"*": "2951-2"}),
    Analyte("potassium", "Potassium", r"(?:serum\s*)?potassium|\bk\+?(?=\s*[:=]?\s*\d)", r"mmol\s*/\s*l|meq\s*/\s*l", None, "SYSTEMIC_MEASURE", {"*": "2823-3"}),
    Analyte("chloride", "Chloride", r"(?:serum\s*)?chloride|\bcl-?(?=\s*[:=]?\s*\d)", r"mmol\s*/\s*l|meq\s*/\s*l", None, "SYSTEMIC_MEASURE", {"*": "2075-0"}),
    Analyte("calcium", "Calcium", r"(?:serum\s*|total\s*)?calcium|\bca(?:\+\+|2\+)?(?=\s*[:=]?\s*\d)", r"mg\s*/\s*dl|mmol\s*/\s*l", None, "SYSTEMIC_MEASURE", {"mg/dL": "17861-6", "mmol/L": "2000-8"}),
    Analyte("magnesium", "Magnesium", r"(?:serum\s*)?magnesium", r"mg\s*/\s*dl|mmol\s*/\s*l|meq\s*/\s*l", None, "SYSTEMIC_MEASURE"),
    Analyte("phosphate", "Phosphate", r"(?:serum\s*)?phosph(?:ate|orus)|\bphos\b", r"mg\s*/\s*dl|mmol\s*/\s*l", None, "SYSTEMIC_MEASURE", {"mg/dL": "2777-1"}),
    Analyte("uric_acid", "Uric acid", r"uric\s*acid|\burate\b", r"mg\s*/\s*dl|µmol\s*/\s*l|umol\s*/\s*l|μmol\s*/\s*l", None, "SYSTEMIC_MEASURE", {"mg/dL": "3084-1"}),
    Analyte("ferritin", "Ferritin", r"(?:serum\s*)?ferritin", r"ng\s*/\s*ml|µg\s*/\s*l|ug\s*/\s*l|μg\s*/\s*l", None, "SYSTEMIC_MEASURE", {"*": "2276-4"}),
    Analyte("psa", "Prostate-specific antigen", r"\bpsa\b|prostate[-\s]*specific\s*antigen", r"ng\s*/\s*ml", None, "SYSTEMIC_MEASURE", {"*": "2857-1"}),
    Analyte("lactate", "Lactate", r"lactate|lactic\s*acid", r"mmol\s*/\s*l|mg\s*/\s*dl", None, "SYSTEMIC_MEASURE"),
    Analyte("creatine_kinase", "Creatine kinase", r"\bck\s*[-\s]*nac(?:\s*/\s*cpk)?|\bcpk\b|creatine\s*(?:phospho)?kinase", r"u\s*/\s*l|iu\s*/\s*l|units\s*/\s*l", None, "SYSTEMIC_MEASURE", {"*": "2157-6"}),
)

ANALYTES_BY_NAME = {analyte.name: analyte for analyte in ANALYTES}

# Standard SI conversion factors: value_in_target = value_in_source * factor.
UNIT_CONVERSIONS: dict[str, dict[tuple[str, str], float]] = {
    "glucose": {("mmol/L", "mg/dL"): 18.016, ("mg/dL", "mmol/L"): 1 / 18.016},
    "creatinine": {("µmol/L", "mg/dL"): 1 / 88.42, ("mg/dL", "µmol/L"): 88.42},
    "hemoglobin": {("g/L", "g/dL"): 0.1, ("g/dL", "g/L"): 10.0},
    "cholesterol_total": {("mmol/L", "mg/dL"): 38.67, ("mg/dL", "mmol/L"): 1 / 38.67},
    "hdl_cholesterol": {("mmol/L", "mg/dL"): 38.67, ("mg/dL", "mmol/L"): 1 / 38.67},
    "ldl_cholesterol": {("mmol/L", "mg/dL"): 38.67, ("mg/dL", "mmol/L"): 1 / 38.67},
    "triglycerides": {("mmol/L", "mg/dL"): 88.57, ("mg/dL", "mmol/L"): 1 / 88.57},
    "bilirubin_total": {("µmol/L", "mg/dL"): 1 / 17.1, ("mg/dL", "µmol/L"): 17.1},
    "bilirubin_direct": {("µmol/L", "mg/dL"): 1 / 17.1, ("mg/dL", "µmol/L"): 17.1},
    "albumin": {("g/L", "g/dL"): 0.1, ("g/dL", "g/L"): 10.0},
    "total_protein": {("g/L", "g/dL"): 0.1, ("g/dL", "g/L"): 10.0},
    "calcium": {("mmol/L", "mg/dL"): 4.008, ("mg/dL", "mmol/L"): 1 / 4.008},
    "lesion_size": {("cm", "mm"): 10.0, ("mm", "cm"): 0.1},
    "kidney_length": {("cm", "mm"): 10.0, ("mm", "cm"): 0.1},
    "liver_span": {("cm", "mm"): 10.0, ("mm", "cm"): 0.1},
}
CONVERSION_SOURCE = "Standard SI conversion factors (e.g. AMA Manual of Style SI conversion table)."

# Counts reported per µL x10^3 equal counts per L x10^9; this is an identity,
# not an approximation, so both spellings normalise to 10^9/L.
_UNIT_ALIASES = {
    "percent": "%",
    "beats/min": "bpm",
    "beatspermin": "bpm",
    "beats/minute": "bpm",
    "beatsperminute": "bpm",
    "/min": "/min",
    "breaths/min": "/min",
    "breathspermin": "/min",
    "breaths/minute": "/min",
    "g/dl": "g/dL",
    "g/l": "g/L",
    "mg/dl": "mg/dL",
    "mg/l": "mg/L",
    "mmol/l": "mmol/L",
    "mmol/mol": "mmol/mol",
    "meq/l": "mmol/L",
    "µmol/l": "µmol/L",
    "μmol/l": "µmol/L",
    "umol/l": "µmol/L",
    "u/l": "U/L",
    "iu/l": "U/L",
    "units/l": "U/L",
    "ng/l": "ng/L",
    "ng/ml": "ng/mL",
    "pg/ml": "pg/mL",
    "µg/l": "µg/L",
    "ug/l": "µg/L",
    "μg/l": "µg/L",
    "miu/l": "mIU/L",
    "mlu/l": "mIU/L",  # OCR commonly reads the capital I of mIU as a lower-case l
    "mu/l": "mIU/L",
    "ng/dl": "ng/dL",
    "nmol/l": "nmol/L",
    "pmol/l": "pmol/L",
    "pg": "pg",
    "µg/dl": "µg/dL",
    "μg/dl": "µg/dL",
    "ug/dl": "µg/dL",
    "mcg/dl": "µg/dL",
    "lakh/cumm": "10^5/µL",
    "lakhs/cumm": "10^5/µL",
    "lakh/µl": "10^5/µL",
    "lakhs/µl": "10^5/µL",
    "lakhs/mm3": "10^5/µL",
    "µiu/ml": "mIU/L",
    "uiu/ml": "mIU/L",
    "μiu/ml": "mIU/L",
    "fl": "fL",
    "l/l": "L/L",
    "mg/g": "mg/g",
    "mg/mmol": "mg/mmol",
    "mm/h": "mm/h",
    "mm/hr": "mm/h",
    "mm/hour": "mm/h",
    "ml/min/1.73m2": "mL/min/1.73m²",
    "ml/min/1.73m²": "mL/min/1.73m²",
    "ml/min/1.73m^2": "mL/min/1.73m²",
    "ml/min": "mL/min",
    "kg/m2": "kg/m²",
    "kg/m²": "kg/m²",
    "kg/m^2": "kg/m²",
    "kg": "kg",
    "lb": "lb",
    "lbs": "lb",
    "cm": "cm",
    "mm": "mm",
    "m": "m",
    "in": "in",
    "inches": "in",
    "°c": "°C",
    "c": "°C",
    "degc": "°C",
    "degreec": "°C",
    "degreesc": "°C",
    "°f": "°F",
    "f": "°F",
    "degf": "°F",
    "degreef": "°F",
    "degreesf": "°F",
}


def normalise_unit(raw_unit: str) -> str:
    compact = re.sub(r"\s+", "", raw_unit.lower())
    if compact in _UNIT_ALIASES:
        return _UNIT_ALIASES[compact]
    if re.fullmatch(r"(?:x)?10(?:\^|\*|e)?9/l|(?:x)?10(?:\^|\*|e)?3/(?:µl|ul|μl|mm3|mm\^3)|k/(?:µl|ul|μl)", compact):
        return "10^9/L"
    if re.fullmatch(r"(?:cells?)?/(?:µl|ul|μl|mm3|cumm|cu\.?mm)", compact):
        return "/µL"
    if compact in {"gm/dl"}:
        return "g/dL"
    if re.fullmatch(r"(?:x)?10(?:\^|\*|e)?12/l|(?:x)?10(?:\^|\*|e)?6/(?:µl|ul|μl)|m/(?:µl|ul)|millions?(?:cells)?/(?:µl|ul|μl|mm3|cumm|cu\.?mm)", compact):
        return "10^12/L"
    return compact


def convert(analyte_name: str, value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """Convert only through a registered factor; None means not convertible."""
    if from_unit == to_unit:
        return value
    if analyte_name == "temperature":
        if (from_unit, to_unit) == ("°F", "°C"):
            return (value - 32.0) * 5.0 / 9.0
        if (from_unit, to_unit) == ("°C", "°F"):
            return value * 9.0 / 5.0 + 32.0
        return None
    factor = UNIT_CONVERSIONS.get(analyte_name, {}).get((from_unit, to_unit))
    return None if factor is None else value * factor


def loinc_for(analyte: Analyte, unit: str) -> Optional[str]:
    return analyte.loinc.get(unit) or analyte.loinc.get("*")


@dataclass(frozen=True)
class EntityTerm:
    pattern: str
    label: str
    category: str
    system: Optional[str]


# Category values: FINDING, CONDITION, PROCEDURE, MEDICATION, NORMAL_STATEMENT,
# METABOLIC_CONDITION, SYSTEMIC_CONDITION. A None system means the organ is
# taken from an anatomical site in the same sentence, if one is documented.
ENTITY_TERMS: tuple[EntityTerm, ...] = (
    EntityTerm(r"normal\s+sinus\s+rhythm|sinus\s+rhythm", "Sinus rhythm", "NORMAL_STATEMENT", "heart"),
    EntityTerm(r"atrial\s+fibrillation|\ba-?fib\b", "Atrial fibrillation", "CONDITION", "heart"),
    EntityTerm(r"atrial\s+flutter", "Atrial flutter", "CONDITION", "heart"),
    EntityTerm(r"arrhythmias?", "Cardiac arrhythmia", "CONDITION", "heart"),
    EntityTerm(r"cardiomegaly|enlarged\s+(?:heart|cardiac\s+silhouette)", "Cardiomegaly", "FINDING", "heart"),
    EntityTerm(r"pericardial\s+effusion", "Pericardial effusion", "FINDING", "heart"),
    EntityTerm(r"(?:acute\s+)?myocardial\s+infarction|\bn?stemi\b", "Myocardial infarction", "CONDITION", "heart"),
    EntityTerm(r"myocardial\s+isch(?:a)?emia", "Myocardial ischemia", "FINDING", "heart"),
    EntityTerm(r"(?:congestive\s+)?heart\s+failure|cardiac\s+failure", "Heart failure", "CONDITION", "heart"),
    EntityTerm(r"left\s+ventricular\s+hypertrophy|\blvh\b", "Left ventricular hypertrophy", "FINDING", "heart"),
    EntityTerm(r"(?:lv\s+|left\s+ventricular\s+)?diastolic\s+dysfunction", "Diastolic dysfunction", "FINDING", "heart"),
    EntityTerm(r"regional\s+wall\s+motion\s+abnormalit(?:y|ies)|\brwma\b", "Regional wall motion abnormality", "FINDING", "heart"),
    EntityTerm(r"pulmonary\s+(?:arterial\s+)?hypertension|\bpah\b", "Pulmonary hypertension", "CONDITION", "heart"),
    EntityTerm(r"(?:intracardiac|lv|la|left\s+(?:atrial|ventricular)(?:\s+appendage)?)\s+(?:clot|thrombus)|clot\s*/\s*vegetations?|vegetations?", "Intracardiac clot or vegetation", "FINDING", "heart"),
    EntityTerm(r"(?:aortic|mitral|tricuspid|pulmonic|pulmonary)\s+(?:valve\s+)?(?:stenosis|regurgitation|insufficiency)", "Valvular heart disease", "FINDING", "heart"),
    EntityTerm(r"coronary\s+artery\s+disease|\bcad\b", "Coronary artery disease", "CONDITION", "heart"),
    EntityTerm(r"pleural\s+effusions?", "Pleural effusion", "FINDING", "lungs"),
    EntityTerm(r"pneumothorax", "Pneumothorax", "FINDING", "lungs"),
    EntityTerm(r"consolidations?", "Consolidation", "FINDING", "lungs"),
    EntityTerm(r"atelectasis", "Atelectasis", "FINDING", "lungs"),
    EntityTerm(r"pneumonia", "Pneumonia", "CONDITION", "lungs"),
    EntityTerm(r"emphysema", "Emphysema", "FINDING", "lungs"),
    EntityTerm(r"ground[-\s]glass\s+opacit(?:y|ies)", "Ground-glass opacity", "FINDING", "lungs"),
    EntityTerm(r"pulmonary\s+embol(?:ism|us|i)", "Pulmonary embolism", "CONDITION", "lungs"),
    EntityTerm(r"pulmonary\s+(?:o|e)?edema", "Pulmonary edema", "FINDING", "lungs"),
    EntityTerm(r"pulmonary\s+fibrosis|(?:fibrotic\s+)?interstitial\s+lung\s+disease|\bild\b", "Pulmonary fibrosis", "FINDING", "lungs"),
    EntityTerm(r"(?:subpleural\s+)?honeycombing", "Honeycombing", "FINDING", "lungs"),
    EntityTerm(r"(?:reticular\s+)?interstitial\s+opacit(?:y|ies)|reticular\s+opacit(?:y|ies)", "Interstitial opacity", "FINDING", "lungs"),
    EntityTerm(r"ground[-\s]glass\s+attenuation", "Ground-glass opacity", "FINDING", "lungs"),
    EntityTerm(r"(?:elevated|raised)\s+(?:(?:right|left)\s+)?hemi-?diaphragm|hemi-?diaphragm\s+(?:is\s+)?(?:elevated|raised)", "Elevated hemidiaphragm", "FINDING", "lungs"),
    EntityTerm(r"diaphragmatic\s+hernia|hiatal\s+hernia|hiatus\s+hernia", "Diaphragmatic hernia", "FINDING", None),
    EntityTerm(r"hernias?", "Hernia", "FINDING", None),
    EntityTerm(r"(?:mediastinal\s+)?lymphadenopathy|(?:enlarged\s+)?(?:mediastinal\s+|pretracheal\s+|paratracheal\s+|hilar\s+)?lymph\s*nodes?", "Lymph node finding", "FINDING", None),
    EntityTerm(r"(?:pulmonary|lung)\s+nodules?", "Pulmonary nodule", "FINDING", "lungs"),
    EntityTerm(r"bronchiectasis", "Bronchiectasis", "FINDING", "lungs"),
    EntityTerm(r"(?:acute\s+)?(?:isch(?:a)?emic\s+)?stroke|cerebrovascular\s+accident|\bcva\b", "Stroke", "CONDITION", "brain"),
    EntityTerm(r"(?:cerebral|lacunar)\s+infarcts?|(?:cerebral|lacunar)\s+infarction", "Cerebral infarct", "FINDING", "brain"),
    EntityTerm(r"(?:intracranial|intracerebral|intraparenchymal|subdural|subarachnoid|epidural|extradural)\s+h(?:a)?emorrhage|(?:subdural|epidural)\s+h(?:a)?ematoma", "Intracranial hemorrhage", "FINDING", "brain"),
    EntityTerm(r"hydrocephalus", "Hydrocephalus", "FINDING", "brain"),
    EntityTerm(r"midline\s+shift", "Midline shift", "FINDING", "brain"),
    EntityTerm(r"(?:white\s+matter|small\s+vessel)\s+(?:isch(?:a)?emic\s+)?(?:disease|changes?|hyperintensit(?:y|ies))", "White matter change", "FINDING", "brain"),
    EntityTerm(r"(?:punctate\s+)?(?:t2\s+|flair\s+)?hyperintense\s+(?:foci|focus|lesions?)", "T2 hyperintense foci", "FINDING", "brain"),
    EntityTerm(r"myelomalacia|(?:spinal\s+)?cord\s+atrophy", "Spinal cord change", "FINDING", "nervous"),
    EntityTerm(r"chiari\s+malformation|basilar\s+invagination", "Craniovertebral junction anomaly", "FINDING", "nervous"),
    EntityTerm(r"glioblastoma|glioma|meningioma|astrocytoma", "Brain tumour", "FINDING", "brain"),
    EntityTerm(r"multiple\s+sclerosis|demyelinat(?:ion|ing)", "Demyelinating disease", "CONDITION", "nervous"),
    EntityTerm(r"(?:peripheral\s+)?neuropathy", "Neuropathy", "CONDITION", "nervous"),
    EntityTerm(r"(?:phrenic|facial|cranial|recurrent\s+laryngeal)\s+nerve\s+(?:palsy|paralysis|injury)|nerve\s+palsy", "Nerve palsy", "CONDITION", "nervous"),
    EntityTerm(r"radiculopathy", "Radiculopathy", "CONDITION", "nervous"),
    EntityTerm(r"(?:hepatic\s+)?steatosis|fatty\s+(?:infiltration\s+of\s+(?:the\s+)?)?liver", "Hepatic steatosis", "FINDING", "liver"),
    EntityTerm(r"(?:increased|raised|altered)\s+(?:echo\s*texture|echogenicity)", "Altered echotexture", "FINDING", None),
    EntityTerm(r"cirrhosis", "Cirrhosis", "CONDITION", "liver"),
    EntityTerm(r"hepatomegaly", "Hepatomegaly", "FINDING", "liver"),
    EntityTerm(r"(?:biliary|bile\s+duct)\s+dilat(?:ation|ion)", "Biliary dilatation", "FINDING", "liver"),
    EntityTerm(r"cholelithiasis|gallstones?", "Cholelithiasis", "FINDING", "liver"),
    EntityTerm(r"pancreatitis", "Pancreatitis", "CONDITION", "pancreas"),
    EntityTerm(r"pancreatic\s+(?:duct\s+)?dilat(?:ation|ion)", "Pancreatic duct dilatation", "FINDING", "pancreas"),
    EntityTerm(r"polyps?", "Polyp", "FINDING", "intestines"),
    EntityTerm(r"ulcerative\s+colitis|colitis", "Colitis", "CONDITION", "intestines"),
    EntityTerm(r"diverticul(?:osis|itis)", "Diverticular disease", "CONDITION", "intestines"),
    EntityTerm(r"(?:small\s+)?bowel\s+obstruction", "Bowel obstruction", "FINDING", "intestines"),
    EntityTerm(r"o?esophagitis", "Esophagitis", "CONDITION", "intestines"),
    EntityTerm(r"(?:stricturing\s*|fistulising\s*|fistulizing\s*)?crohn'?s(?:\s*disease)?", "Crohn disease", "CONDITION", "intestines"),
    EntityTerm(r"gastro[-\s]*o?esophageal\s+reflux(?:\s+disease)?|\bgo?erd\b|\bgord\b", "Gastro-oesophageal reflux", "CONDITION", "intestines"),
    EntityTerm(r"laryngo[-\s]*pharyngeal\s+reflux|\blpr\b", "Laryngopharyngeal reflux", "CONDITION", None),
    EntityTerm(r"dysplasia", "Dysplasia", "FINDING", None),
    EntityTerm(r"granulomas?", "Granuloma", "FINDING", None),
    EntityTerm(r"crypt\s+abscess(?:es)?|cryptitis", "Cryptitis or crypt abscess", "FINDING", "intestines"),
    EntityTerm(r"congestion", "Congestion", "FINDING", None),
    EntityTerm(r"hydronephrosis", "Hydronephrosis", "FINDING", "kidneys"),
    EntityTerm(r"pyelonephritis", "Pyelonephritis", "CONDITION", "kidneys"),
    EntityTerm(r"(?:renal\s+)?parenchymal?\s+(?:renal\s+)?(?:disease|changes?)", "Renal parenchymal change", "FINDING", "kidneys"),
    EntityTerm(r"nephrolithiasis|urolithiasis|(?:renal|kidney|ureteric|ureteral)\s+(?:calculus|calculi|stones?)", "Urinary tract calculus", "FINDING", "kidneys"),
    EntityTerm(r"calculus|calculi", "Calculus", "FINDING", None),
    EntityTerm(r"chronic\s+kidney\s+disease|\bckd\b", "Chronic kidney disease", "CONDITION", "kidneys"),
    EntityTerm(r"acute\s+kidney\s+injury|\baki\b", "Acute kidney injury", "CONDITION", "kidneys"),
    EntityTerm(r"fractures?", "Fracture", "FINDING", "skeletal"),
    EntityTerm(r"dislocations?", "Dislocation", "FINDING", "skeletal"),
    EntityTerm(r"osteoarthritis|degenerative\s+(?:joint|disc)\s+(?:disease|changes?)", "Degenerative joint or disc change", "FINDING", "skeletal"),
    EntityTerm(r"osteoporosis|osteopenia", "Reduced bone density", "FINDING", "skeletal"),
    EntityTerm(r"dis[ck]\s+herniation|herniated\s+dis[ck]", "Disc herniation", "FINDING", "skeletal"),
    EntityTerm(r"(?:wedge\s+)?compression\s+(?:deformity|fracture)|vertebral\s+(?:body\s+)?(?:collapse|compression)", "Vertebral compression deformity", "FINDING", "skeletal"),
    EntityTerm(r"(?:cervical\s+|lumbar\s+|thoracic\s+)?spondylo(?:sis|tic\s+changes?)|osteophytes?", "Spondylosis or osteophytes", "FINDING", "skeletal"),
    EntityTerm(r"dis[ck]\s+(?:bulge|bulging|desiccation|protrusion)", "Disc degeneration or bulge", "FINDING", "skeletal"),
    EntityTerm(r"kyphosis|kyphotic\s+angulation|scoliosis", "Spinal curvature change", "FINDING", "skeletal"),
    EntityTerm(r"metasta(?:sis|ses|tic\s+disease)", "Metastasis", "FINDING", None),
    EntityTerm(r"carcinomas?|malignanc(?:y|ies)|malignant\s+neoplasm|cancers?", "Malignancy", "FINDING", None),
    EntityTerm(r"\bmass(?:es)?\b", "Mass", "FINDING", None),
    EntityTerm(r"tumou?rs?|neoplasms?|neoplastic(?:\s+(?:lesion|process|growth))?", "Neoplasm", "FINDING", None),
    EntityTerm(r"calcifications?", "Calcification", "FINDING", None),
    EntityTerm(r"(?:bulky|enlarged)\s+(?:(?:left|right)\s+)?thyroid(?:\s+(?:lobe|gland))?|thyromegaly|goitre|goiter", "Thyroid enlargement", "FINDING", None),
    EntityTerm(r"nodules?", "Nodule", "FINDING", None),
    EntityTerm(r"lesions?", "Lesion", "FINDING", None),
    EntityTerm(r"cysts?", "Cyst", "FINDING", None),
    EntityTerm(r"opacit(?:y|ies)", "Opacity", "FINDING", None),
    EntityTerm(r"(?:o|e)?edema", "Edema", "FINDING", None),
    EntityTerm(r"effusions?", "Effusion", "FINDING", None),
    EntityTerm(r"atrophy", "Atrophy", "FINDING", None),
    EntityTerm(r"stenosis", "Stenosis", "FINDING", None),
    EntityTerm(r"isch(?:a)?emia", "Ischemia", "FINDING", None),
    EntityTerm(r"infarcts?|infarction", "Infarct", "FINDING", None),
    EntityTerm(r"h(?:a)?emorrhage", "Hemorrhage", "FINDING", None),
    EntityTerm(r"ulcers?", "Ulcer", "FINDING", None),
    # "American Diabetes Association" names the organisation behind a printed reference band.
    EntityTerm(r"(?<!american\s)diabetes(?:\s+mellitus)?(?!\s+association)|\bt[12]dm\b|type\s+[12]\s+diabetes", "Diabetes mellitus", "METABOLIC_CONDITION", None),
    EntityTerm(r"hypertension", "Hypertension", "SYSTEMIC_CONDITION", None),
    EntityTerm(r"cholecystectomy|hepatectomy|liver\s+resection", "Hepatobiliary surgery", "PROCEDURE", "liver"),
    EntityTerm(r"appendectomy|appendicectomy|colectomy|bowel\s+resection|hemicolectomy", "Intestinal surgery", "PROCEDURE", "intestines"),
    EntityTerm(r"nephrectomy|nephrolithotomy|pyeloplasty", "Renal surgery", "PROCEDURE", "kidneys"),
    EntityTerm(r"lobectomy|pneumonectomy|segmentectomy|wedge\s+resection", "Lung resection", "PROCEDURE", "lungs"),
    EntityTerm(r"pancreatectomy|whipple(?:\s+procedure)?|pancreaticoduodenectomy", "Pancreatic surgery", "PROCEDURE", "pancreas"),
    EntityTerm(r"craniotomy|craniectomy", "Cranial surgery", "PROCEDURE", "brain"),
    EntityTerm(r"laminectomy|spinal\s+fusion|arthroplasty|joint\s+replacement|internal\s+fixation|\borif\b", "Orthopaedic surgery", "PROCEDURE", "skeletal"),
    EntityTerm(r"\bcabg\b|coronary\s+artery\s+bypass|\bpci\b|(?:coronary\s+)?stent(?:ing)?", "Coronary intervention", "PROCEDURE", "heart"),
    EntityTerm(r"(?:kidney|renal|liver|hepatic|lung|heart|pancreas)\s+transplant(?:ation)?", "Organ transplantation", "PROCEDURE", None),
    EntityTerm(r"hysterectomy", "Hysterectomy", "PROCEDURE", None),
    EntityTerm(r"ileostomy|colostomy", "Intestinal stoma procedure", "PROCEDURE", "intestines"),
    EntityTerm(r"fine[-\s]*needle\s+aspiration(?:\s+cytology)?|\bfnac\b|\bfna\b", "Fine-needle aspiration", "PROCEDURE", None),
    EntityTerm(r"biops(?:y|ies)", "Biopsy", "PROCEDURE", None),
    # Throat, larynx and nose endoscopy is an ENT examination, not a gastrointestinal one.
    EntityTerm(r"(?:video\s+)?(?:laryngo|naso(?:pharyngo)?|pharyngo)scopy|(?:video\s+)?endoscopy\s+(?:report\s+)?of\s+(?:the\s+)?(?:throat|larynx|nose|pharynx)", "ENT endoscopy", "PROCEDURE", None),
    EntityTerm(r"colonoscopy|endoscopy|gastroscopy|o?esophagogastroduodenoscopy|\begd\b", "Endoscopic procedure", "PROCEDURE", "intestines"),
    EntityTerm(r"metformin|insulin|aspirin|atorvastatin|rosuvastatin|statins?|warfarin|apixaban|rivaroxaban|heparin|clopidogrel|lisinopril|ramipril|losartan|metoprolol|bisoprolol|amlodipine|furosemide|spironolactone|prednisone|prednisolone|levothyroxine|chemotherapy", "Medication mention", "MEDICATION", None),
    EntityTerm(r"unremarkable|within\s+normal\s+limits|no\s+acute\s+(?:abnormality|findings?|process)|\bnad\b|no\s+abnormality\s+(?:detected|seen)", "Unremarkable statement", "NORMAL_STATEMENT", None),
)


@dataclass(frozen=True)
class SiteTerm:
    pattern: str
    atlas_name: Optional[str]
    system: str
    side: Optional[str] = None


# Each site resolves either to an atlas structure/group name (verified to exist
# in the bundled index) or to an organ-level system only.
SITE_TERMS: tuple[SiteTerm, ...] = (
    SiteTerm(r"right\s+upper\s+lobe|\brul\b", "Superior lobe of right lung", "lungs", "right"),
    SiteTerm(r"right\s+middle\s+lobe|\brml\b", "Middle lobe of right lung", "lungs", "right"),
    SiteTerm(r"right\s+lower\s+lobe|\brll\b", "Inferior lobe of right lung", "lungs", "right"),
    SiteTerm(r"left\s+upper\s+lobe|\blul\b", "Superior lobe of left lung", "lungs", "left"),
    SiteTerm(r"left\s+lower\s+lobe|\blll\b", "Inferior lobe of left lung", "lungs", "left"),
    SiteTerm(r"lingula", None, "lungs", "left"),
    SiteTerm(r"right\s+lung", "Right lung", "lungs", "right"),
    SiteTerm(r"left\s+lung", "Left lung", "lungs", "left"),
    SiteTerm(r"(?:both\s+|bilateral\s+)?lungs?|pulmonary|pleura(?:l)?", None, "lungs"),
    SiteTerm(r"trachea", "Trachea", "lungs"),
    SiteTerm(r"right\s+main(?:stem)?\s+bronchus", "Right main bronchus", "lungs", "right"),
    SiteTerm(r"left\s+main(?:stem)?\s+bronchus", "Left main bronchus", "lungs", "left"),
    SiteTerm(r"left\s+atri(?:um|al)", "Left atrium", "heart", "left"),
    SiteTerm(r"right\s+atri(?:um|al)", "Right atrium", "heart", "right"),
    SiteTerm(r"left\s+ventric(?:le|ular)", "Left ventricle", "heart", "left"),
    SiteTerm(r"right\s+ventric(?:le|ular)", "Right ventricle", "heart", "right"),
    SiteTerm(r"aortic\s+valve", "Aortic valve", "heart"),
    SiteTerm(r"pulmonary\s+valve|pulmonic\s+valve", "Pulmonary valve", "heart"),
    SiteTerm(r"mitral\s+valve|tricuspid\s+valve", None, "heart"),
    SiteTerm(r"ascending\s+aorta", "Ascending aorta", "heart"),
    SiteTerm(r"pulmonary\s+trunk", "Pulmonary trunk", "heart"),
    SiteTerm(r"heart|cardiac|myocardi(?:um|al)|pericardi(?:um|al)", None, "heart"),
    SiteTerm(r"(?:liver\s+)?segment\s+(?:viii|8)(?:\s+of\s+the\s+liver)?", "Posterior medial segment of liver (VIII)", "liver"),
    SiteTerm(r"(?:liver\s+)?segment\s+(?:vii|7)(?:\s+of\s+the\s+liver)?", "Posterior lateral segment of liver (VII)", "liver"),
    SiteTerm(r"(?:liver\s+)?segment\s+(?:vi|6)(?:\s+of\s+the\s+liver)?", "Anterior lateral segment of liver (VI)", "liver"),
    SiteTerm(r"(?:liver\s+)?segment\s+(?:v|5)(?:\s+of\s+the\s+liver)?", "Anterior medial segment of liver (V)", "liver"),
    SiteTerm(r"(?:liver\s+)?segment\s+(?:iva|ivb|iv|4a|4b|4)(?:\s+of\s+the\s+liver)?", "Left medial segment of liver (IV)", "liver"),
    SiteTerm(r"(?:liver\s+)?segment\s+(?:iii|3)(?:\s+of\s+the\s+liver)?", "Left anterior lateral segment of liver (III)", "liver"),
    SiteTerm(r"(?:liver\s+)?segment\s+(?:ii|2)(?:\s+of\s+the\s+liver)?", "Left posterior lateral segment of liver (II)", "liver"),
    SiteTerm(r"caudate\s+lobe|(?:liver\s+)?segment\s+(?:i|1)\b(?:\s+of\s+the\s+liver)?", "Posterior segment of liver (I)", "liver"),
    SiteTerm(r"gall\s*bladder", "Gallbladder", "liver"),
    SiteTerm(r"(?:common\s+)?bile\s+duct|\bcbd\b", "Bile duct", "liver"),
    SiteTerm(r"liver|hepatic", "Liver", "liver"),
    SiteTerm(r"pancreatic\s+duct|duct\s+of\s+wirsung", "Pancreatic duct", "pancreas"),
    SiteTerm(r"(?:head|neck|body|tail|uncinate\s+process)\s+of\s+(?:the\s+)?pancreas|pancreatic\s+(?:head|neck|body|tail)", "Pancreas", "pancreas"),
    SiteTerm(r"pancrea(?:s|tic)", "Pancreas", "pancreas"),
    SiteTerm(r"o?esophag(?:us|eal)", "Oesophagus", "intestines"),
    SiteTerm(r"stomach|gastric", "Stomach", "intestines"),
    SiteTerm(r"duoden(?:um|al)", "Duodenum", "intestines"),
    SiteTerm(r"jejun(?:um|al)", "Jejunum", "intestines"),
    SiteTerm(r"ileum|ileal|terminal\s+ileum", None, "intestines"),
    SiteTerm(r"c(?:a)?ecum|c(?:a)?ecal", None, "intestines"),
    SiteTerm(r"(?:vermiform\s+)?appendix", "Vermiform appendix", "intestines"),
    SiteTerm(r"ascending\s+colon", "Ascending colon", "intestines"),
    SiteTerm(r"transverse\s+colon", "Transverse colon", "intestines"),
    SiteTerm(r"descending\s+colon", "Descending colon", "intestines"),
    SiteTerm(r"sigmoid(?:\s+colon)?", "Sigmoid colon", "intestines"),
    SiteTerm(r"rectum|rectal", None, "intestines"),
    SiteTerm(r"colon|colonic|large\s+(?:bowel|intestine)", "Colon", "intestines"),
    SiteTerm(r"small\s+(?:bowel|intestine)", "Small intestine", "intestines"),
    SiteTerm(r"bowel|intestin(?:e|al)", None, "intestines"),
    SiteTerm(r"(?:left\s+|right\s+)?renal\s+pelvis", "Renal pelvis", "kidneys"),
    SiteTerm(r"(?:left\s+|right\s+)?renal\s+cortex", "Renal cortex", "kidneys"),
    SiteTerm(r"left\s+(?:kidney|renal)", "Kidney", "kidneys", "left"),
    SiteTerm(r"right\s+(?:kidney|renal)", "Kidney", "kidneys", "right"),
    SiteTerm(r"ureters?|ureteric|ureteral", "Ureter", "kidneys"),
    SiteTerm(r"(?:urinary\s+)?bladder", "Urinary bladder", "kidneys"),
    SiteTerm(r"kidneys?|renal", None, "kidneys"),
    SiteTerm(r"frontal\s+lobe", "Frontal lobe", "brain"),
    SiteTerm(r"parietal\s+lobe", "Parietal lobe", "brain"),
    SiteTerm(r"temporal\s+lobe", "Temporal lobe", "brain"),
    SiteTerm(r"occipital\s+lobe", "Occipital lobe", "brain"),
    SiteTerm(r"insula(?:r)?", "Insula", "brain"),
    SiteTerm(r"cerebell(?:um|ar)", "Cerebellum", "brain"),
    SiteTerm(r"brain\s*stem", "Brainstem", "brain"),
    SiteTerm(r"thalam(?:us|ic)", None, "brain"),
    SiteTerm(r"hippocamp(?:us|al)", None, "brain"),
    SiteTerm(r"corpus\s+callosum", "Corpus callosum", "brain"),
    SiteTerm(r"(?:lateral\s+)?ventricles?(?=.*(?:brain|cerebral|intracranial))", None, "brain"),
    SiteTerm(r"\bpons\b|medulla\s+oblongata|midbrain", None, "brain"),
    SiteTerm(r"brain|cerebr(?:um|al)|intracranial|supratentorial|infratentorial", None, "brain"),
    SiteTerm(r"spinal\s+cord", "Spinal cord", "nervous"),
    SiteTerm(r"sciatic\s+nerve", None, "nervous"),
    SiteTerm(r"median\s+nerve|ulnar\s+nerve|radial\s+nerve|femoral\s+nerve", None, "nervous"),
    SiteTerm(r"brachial\s+plexus", "Brachial plexus", "nervous"),
    SiteTerm(r"(?:cranial|optic|facial|vagus|trigeminal)\s+nerve|peripheral\s+nerves?|nerve\s+roots?", None, "nervous"),
    SiteTerm(r"\b[ltc]\d{1,2}\s*[-–/]\s*[lts]?\d{1,2}\b|lumbar\s+spine|thoracic\s+spine|cervical\s+spine|vertebra(?:e|l)?|spine|spinal", None, "skeletal"),
    SiteTerm(r"femo(?:r|ral)\s*(?:neck|shaft)?|femur", None, "skeletal"),
    SiteTerm(r"tibia(?:l)?|fibula(?:r)?|humer(?:us|al)|radius|ulna(?:r)?|clavicle|scapula|patella|sacrum|mandible|sternum|ribs?|pelvi(?:s|c)|hip|skull|cranium|wrist|ankle|knee|shoulder|elbow", None, "skeletal"),
)

_SITE_PATTERNS = [(re.compile(rf"\b(?:{term.pattern})\b", re.IGNORECASE), term) for term in SITE_TERMS]
ENTITY_PATTERNS = [(re.compile(rf"\b(?:{term.pattern})\b", re.IGNORECASE), term) for term in ENTITY_TERMS]


@lru_cache(maxsize=1)
def atlas_structures() -> dict[str, list[dict]]:
    """Atlas English name (lower-case) -> structure records. Empty if not built."""
    path = DATA_DIR / "atlas_structures.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    index: dict[str, list[dict]] = {}
    for structure in payload.get("structures", []):
        index.setdefault(structure["name"].lower(), []).append(structure)
    return index


def resolve_atlas_structure(name: Optional[str], side: Optional[str]) -> Optional[dict]:
    if not name:
        return None
    candidates = atlas_structures().get(name.lower(), [])
    if side:
        sided = [item for item in candidates if item.get("side") == side]
        if sided:
            return sided[0]
    unsided = [item for item in candidates if not item.get("side")]
    if unsided:
        return unsided[0]
    # Left and right structures exist but the text gives no side: ambiguous.
    return candidates[0] if len(candidates) == 1 else None


def find_sites(text: str) -> list[dict]:
    """Return documented anatomical sites with offsets, most specific first, non-overlapping."""
    hits = []
    for pattern, term in _SITE_PATTERNS:
        for match in pattern.finditer(text):
            hits.append((match.start(), match.end(), term, match.group(0)))
    hits.sort(key=lambda item: (-(item[1] - item[0]), item[0]))
    chosen: list[tuple[int, int, SiteTerm, str]] = []
    for start, end, term, surface in hits:
        if any(start < other_end and end > other_start for other_start, other_end, _, _ in chosen):
            continue
        chosen.append((start, end, term, surface))
    results = []
    for start, end, term, surface in sorted(chosen, key=lambda item: item[0]):
        side = term.side
        if side is None:
            if re.search(r"\bleft\b", surface, re.IGNORECASE):
                side = "left"
            elif re.search(r"\bright\b", surface, re.IGNORECASE):
                side = "right"
        atlas = resolve_atlas_structure(term.atlas_name, side)
        results.append({
            "text": surface,
            "start": start,
            "end": end,
            "system": term.system,
            "side": side,
            "atlas_structure_id": atlas["id"] if atlas else None,
            "atlas_structure_name": atlas["name"] if atlas else None,
        })
    return results
