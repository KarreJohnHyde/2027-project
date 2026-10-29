"""Page-level document type from what a page prints (keyword and layout rules, not a model).

A photographed packet mixes documents: a laboratory panel, an ultrasound report, a CT report,
a bill. Each page is typed on its own from the words and value layouts printed on it, with the
matched cues returned so a reviewer can see why. The rules have not been evaluated on an
annotated corpus; a page that matches nothing clearly is UNCLASSIFIED, never guessed.
"""

from __future__ import annotations

import re
from typing import Any

CLASSIFIER_VERSION = "page-type-rules-v1"

LABORATORY_REPORT = "LABORATORY_REPORT"
IMAGING_REPORT = "IMAGING_REPORT"
PROCEDURE_REPORT = "PROCEDURE_REPORT"
PATHOLOGY_REPORT = "PATHOLOGY_REPORT"
DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
CONSULTATION_NOTE = "CONSULTATION_NOTE"
PRESCRIPTION = "PRESCRIPTION"
BILLING = "BILLING"
UNCLASSIFIED = "UNCLASSIFIED"


def _cues(*patterns: str) -> list[re.Pattern]:
    return [re.compile(rf"(?<![A-Za-z])(?:{pattern})(?![A-Za-z])", re.IGNORECASE) for pattern in patterns]


CUES: dict[str, list[re.Pattern]] = {
    LABORATORY_REPORT: _cues(
        r"bio\s*chemistry", r"ha?ematology", r"serology", r"immunology", r"clinical\s+pathology", r"lipid\s+profile",
        r"thyroid\s+profile", r"liver\s+function", r"renal\s+function|kidney\s+function", r"complete\s+blood\s+(?:count|picture)",
        r"cbc|cbp", r"urine\s+(?:routine|analysis|examination)|urinalysis", r"reference\s+(?:range|interval)|ref\.?\s*range",
        r"bio\.?\s*ref(?:erence)?", r"normal\s+(?:range|value)s?", r"test\s+name|investigation", r"specimen|sample\s+type",
        r"method\s*[:=]", r"units?",
    ),
    IMAGING_REPORT: _cues(
        r"ultrasono?graphy|sonography|usg|doppler", r"c\.?e\.?c\.?t|n\.?c\.?c\.?t|hrct|computed\s+tomography|ct\s+(?:scan|chest|abdomen|brain|head)",
        r"mri|magnetic\s+resonance", r"x-?\s*ray|radiograph|cxr|skiagram", r"echocardiograph\w*|2d\s*echo", r"mammogra\w*",
        r"findings", r"impression", r"contrast", r"visuali[sz]ed", r"echotexture|echogenicity|attenuation|enhancement",
        r"radiologist|sonologist", r"(?:right|left)\s+(?:lobe|kidney|lung)",
        # Findings wording that imaging reports print and laboratory pages do not.
        r"parenchyma\w*", r"fatty\s+liver|hepatomegaly|splenomegaly", r"hydronephrosis|calculus|calculi",
        r"effusion|consolidation|opacit\w*|nodules?", r"hemidiaphragm|diaphragm\w*",
    ),
    PROCEDURE_REPORT: _cues(
        r"colonoscop\w*|endoscop\w*|gastroscop\w*|sigmoidoscop\w*|bronchoscop\w*|ercp|egd", r"scope\s+(?:was\s+)?(?:introduced|passed|advanced|inserted)",
        r"mucosa\w*", r"ca?ecum|terminal\s+ileum|rectum|sigmoid\s+colon|duodenum|antrum|oesophag\w*|esophag\w*",
        r"procedure\s+(?:done|performed|note|report)", r"sedation", r"biops(?:y|ies)\s+(?:taken|obtained)",
    ),
    PATHOLOGY_REPORT: _cues(
        r"histopatholog\w*", r"cytolog\w*", r"biopsy", r"gross\s+(?:description|examination)", r"microscop\w*\s+(?:description|examination)",
        r"fnac", r"nature\s+of\s+specimen", r"received\s+in\s+formalin", r"sections?\s+(?:show|studied)", r"pathologist",
    ),
    DISCHARGE_SUMMARY: _cues(
        r"discharge\s+summary", r"date\s+of\s+(?:admission|discharge)", r"course\s+in\s+(?:the\s+)?hospital", r"condition\s+(?:at|on)\s+discharge",
        r"advice\s+on\s+discharge|discharge\s+advice", r"final\s+diagnosis", r"admitted\s+(?:with|for|on)",
    ),
    CONSULTATION_NOTE: _cues(
        r"chief\s+complaints?|c/o", r"history\s+of\s+present\s+illness|hopi", r"on\s+examination|o/e", r"provisional\s+diagnosis",
        r"vitals?", r"follow[\s-]*up", r"review\s+after",
    ),
    PRESCRIPTION: _cues(
        r"rx", r"tab\.?", r"cap\.?", r"syp\.?|syrup", r"inj\.?", r"(?:1|0)\s*-\s*(?:1|0)\s*-\s*(?:1|0)", r"od|bd|tds|qid|hs|sos",
        r"(?:x|for)\s*\d+\s*days", r"before\s+food|after\s+food",
    ),
    BILLING: _cues(
        r"bill(?:\s*(?:no|date|amount))?", r"invoice", r"receipt", r"amount\s+(?:paid|due)|net\s+amount|total\s+amount", r"gst",
        r"payment|paid", r"discount", r"rate|qty|quantity",
    ),
}
# A numeric result with a unit and a printed interval on one line is the clearest laboratory cue.
LAB_RESULT_ROW = re.compile(
    r"\d+(?:\.\d+)?\s*\*?\s*(?:mg/d[lL]|g/d[lL]|g/L|mmol/L|µmol/L|umol/L|IU/L|U/L|mIU/(?:m)?L|µIU/mL|uIU/mL|ng/(?:d|m)L|pg/mL|"
    r"µg/d[lL]|ug/d[lL]|%|fL|pg|cells/cumm|/cumm|/µL|10\^\d/µL|mEq/L|mm/hr|lakhs?)[^\n]{0,40}?\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?",
    re.IGNORECASE,
)
IMAGING_MODALITIES = (
    ("ULTRASOUND", re.compile(r"(?<![A-Za-z])(?:ultrasono?graphy|sonography|usg|doppler|echotexture|echogenic\w*)(?![A-Za-z])", re.IGNORECASE)),
    ("CT", re.compile(r"(?<![A-Za-z])(?:c\.?e\.?c\.?t|n\.?c\.?c\.?t|hrct|computed\s+tomography|ct)(?![A-Za-z])", re.IGNORECASE)),
    ("MRI", re.compile(r"(?<![A-Za-z])(?:mri|magnetic\s+resonance)(?![A-Za-z])", re.IGNORECASE)),
    ("RADIOGRAPH", re.compile(r"(?<![A-Za-z])(?:x-?\s*ray|radiograph\w*|cxr|skiagram)(?![A-Za-z])", re.IGNORECASE)),
    ("ECHOCARDIOGRAPHY", re.compile(r"(?<![A-Za-z])(?:echocardiograph\w*|2d\s*echo)(?![A-Za-z])", re.IGNORECASE)),
    ("MAMMOGRAPHY", re.compile(r"(?<![A-Za-z])mammogra\w*", re.IGNORECASE)),
)
# A type needs this many distinct cues, and must lead the next type by this margin.
MIN_CUES = 2
MIN_LEAD = 1
# Each laboratory result row counts as a cue, up to this many.
MAX_RESULT_ROW_CUES = 4
# A page that ends like this continues on the next ("(P.T.O)", "contd.", "Page 1 of 2").
CONTINUES_ON_NEXT_PAGE = re.compile(r"(?:\(?\s*p\.?\s*t\.?\s*o\.?\s*\)?|cont(?:d|inued)\.?|page\s*\d+\s*of\s*\d+)\s*$", re.IGNORECASE)


def classify_page(text: str) -> dict[str, Any]:
    """The document type a page prints, with the cues that decided it."""
    scores: dict[str, list[str]] = {}
    for kind, patterns in CUES.items():
        found = []
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                found.append(match.group(0).strip())
        scores[kind] = found
    rows = LAB_RESULT_ROW.findall(text)
    scores[LABORATORY_REPORT] += [f"result row {number + 1}" for number in range(min(len(rows), MAX_RESULT_ROW_CUES))]
    ranked = sorted(scores.items(), key=lambda item: len(item[1]), reverse=True)
    (best, best_cues), (_second, second_cues) = ranked[0], ranked[1]
    if len(best_cues) < MIN_CUES or len(best_cues) - len(second_cues) < MIN_LEAD:
        best, best_cues = UNCLASSIFIED, []
    modality = None
    if best == IMAGING_REPORT:
        counts = [(len(pattern.findall(text)), name) for name, pattern in IMAGING_MODALITIES]
        top = max(counts)
        modality = top[1] if top[0] else None
    return {
        "document_type": best,
        "imaging_modality": modality,
        "cues": best_cues[:8],
        "scores": {kind: len(found) for kind, found in scores.items() if found},
        "method": CLASSIFIER_VERSION,
        "validation_status": "RULES_NOT_EVALUATED_ON_ANNOTATED_CORPUS",
    }


def classify_pages(texts: list[str]) -> list[dict[str, Any]]:
    """Each page's type. A page continuing the previous one (which ended "P.T.O" or "contd.")
    and printing no type of its own takes that page's type and modality, marked as continued."""
    results = [classify_page(text) for text in texts]
    for number in range(1, len(results)):
        previous, current = results[number - 1], results[number]
        if not CONTINUES_ON_NEXT_PAGE.search(texts[number - 1].strip()):
            continue
        if current["document_type"] in (UNCLASSIFIED, previous["document_type"]) and previous["document_type"] != UNCLASSIFIED:
            if current["document_type"] == UNCLASSIFIED or (current["imaging_modality"] is None and previous["imaging_modality"]):
                current.update(document_type=previous["document_type"], imaging_modality=previous["imaging_modality"],
                               continued_from_page=number)
    return results
