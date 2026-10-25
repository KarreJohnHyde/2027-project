"""
Transparent clinical-text extraction for MedTwin (rules v2).

The extractor identifies what a report states; it never formulates a
diagnosis. For every recognised entity it records:

- assertion: AFFIRMED or NEGATED
- certainty: CERTAIN, UNCERTAIN or HYPOTHETICAL ("rule out", "evaluate for")
- temporality: CURRENT or HISTORICAL
- experiencer: PATIENT or FAMILY
- comparison: documented change language (STABLE, INCREASED, NEW, ...)
- the documented anatomical site, if any, and its atlas structure
- the cues that produced each attribute, with offsets

Scoping follows the NegEx/ConText approach: cues act within a clause and a
bounded word window. The rules have not been evaluated on an annotated
corpus; every output remains PENDING_HUMAN_REVIEW.
"""

from __future__ import annotations

from datetime import date
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.document_parser import parse_clinical_document_pages, parse_clinical_document_with_pages  # noqa: F401
from app.services.terminology import (
    ANALYTES,
    ENTITY_PATTERNS,
    LOINC,
    LOINC_MAPPING_STATUS,
    find_sites,
    loinc_for,
    normalise_unit,
)

EXTRACTOR_VERSION = "rules-v2.0.0"

# De-identification patterns (PHI sanitisation applied before extraction).
# Identifier patterns require a digit in the identifier so ordinary prose
# ("record of", "patient identified") is not masked.
PHI_PATTERNS = [
    (re.compile(r'\b(?:MRN|Patient\s+ID|Medical\s+record\s+(?:number|no\.?)|Record\s+(?:number|no\.?)|Accession(?:\s+(?:number|no\.?))?)\s*[:#]?\s*[A-Za-z0-9-]*\d[A-Za-z0-9-]*', re.IGNORECASE), "[REDACTED_ID]"),
    (re.compile(r'\b(DOB|Date of Birth|Birth date)[:\s]+(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2})\b', re.IGNORECASE), "[REDACTED_DOB]"),
    (re.compile(r'\bDr\.\s+[A-Z][a-z]+(\s+[A-Z][a-z]+)?\b'), "[REDACTED_PROVIDER]"),
    (re.compile(r'\b(Mr\.|Mrs\.|Ms\.|Miss)\s+[A-Z][a-z]+\b'), "[REDACTED_NAME]"),
    (re.compile(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b'), "[REDACTED_EMAIL]"),
]
PHONE_CANDIDATE = re.compile(r"(?<![\w.])\+?\(?\d[\d ().-]{6,}\d(?![\w.])")
NUMERIC_RANGE = re.compile(r"\d+(?:\.\d+)?\s*[-–]\s*\d+(?:\.\d+)?")


def _redact_phone(match: re.Match) -> str:
    """Phone numbers carry 10-15 digits; dates (8 digits) and numeric ranges are kept."""
    candidate = match.group(0)
    digits = re.sub(r"\D", "", candidate)
    if not 10 <= len(digits) <= 15 or NUMERIC_RANGE.fullmatch(candidate.strip()) or re.search(r"\d\.\d", candidate):
        return candidate
    return "[REDACTED_PHONE]"

SECTION_NAMES = (
    "findings", "impression", "conclusion", "conclusions", "history", "clinical history", "indication", "indications",
    "reason for exam", "reason for examination", "clinical question", "comparison", "technique", "procedure",
    "assessment", "plan", "diagnosis", "diagnoses", "medications", "allergies", "family history",
    "past medical history", "social history", "laboratory", "labs", "results", "recommendation",
    "recommendations", "summary", "opinion", "interpretation",
)
SECTION_RE = re.compile(
    r"^[ \t]*(?P<header>" + "|".join(re.escape(name) for name in sorted(SECTION_NAMES, key=len, reverse=True)) + r")[ \t]*:",
    re.IGNORECASE | re.MULTILINE,
)

# Sentence boundaries: newlines, semicolons, and full stops that are not part
# of a decimal number. Abbreviation full stops are masked first (same length,
# so offsets are unchanged).
BOUNDARY_RE = re.compile(r"\n+|;|(?<!\d)\.(?!\d)(?=\s|$)")
ABBREVIATION_RE = re.compile(r"\b(?:e\.g|i\.e|vs|dr|mrs|mr|ms|approx|cf|fig|resp|incl)\.", re.IGNORECASE)
TERMINATOR_RE = re.compile(r"\b(?:but|however|although|though|except|apart\s+from|aside\s+from|otherwise|whereas|yet|nevertheless)\b|[,:](?=\s+(?:but|however|although)\b)", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _cue(pattern: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z])(?:{pattern})(?![A-Za-z])", re.IGNORECASE)


# Phrases that contain a negation word but express uncertainty are matched first.
PRE_UNCERTAIN = _cue(
    r"can\s*not\s+(?:be\s+)?(?:excluded|exclude|ruled\s+out|rule\s+out)|could\s+not\s+be\s+excluded|not\s+(?:be\s+)?excluded|"
    r"possible|possibly|probable|probably|likely|suspected|suspect|suspicious\s+(?:for|of)|suspicion\s+(?:for|of)|"
    r"concerning\s+for|questionable|may\s+(?:represent|be|reflect)|might\s+(?:represent|be)|could\s+(?:represent|be)|"
    r"differential\s+(?:diagnosis\s+)?(?:includes?|considerations?)|suggestive\s+of|suggests?|compatible\s+with|"
    r"consistent\s+with|in\s+keeping\s+with|indeterminate|equivocal|presumed|presumably|apparent"
)
POST_UNCERTAIN = _cue(r"(?:can\s*not|could\s+not)\s+be\s+(?:excluded|ruled\s+out)|(?:is|are)\s+not\s+excluded|is\s+(?:suspected|possible|likely|probable)|\?")
PRE_NEGATED_UNCERTAIN = _cue(r"no\s+(?:definite|convincing|clear|obvious)\s+(?:evidence\s+(?:of|for)|signs?\s+of)?|unlikely|doubtful|not\s+(?:definitely|clearly)\s+(?:seen|identified)")
PRE_NEGATION = _cue(
    r"no\s+(?:evidence|signs?|findings?)\s+(?:of|for|to\s+suggest)|no\s+(?:new|acute|significant|focal|residual)|"
    r"negative\s+for|free\s+of|absence\s+of|absent|without|denies|denied|ruled\s+out|rules\s+out|"
    r"never\s+had|not|no|nor"
)
POST_NEGATION = _cue(
    r"(?:is|are|was|were|has\s+been|have\s+been)\s+(?:ruled\s+out|excluded|absent)|not\s+(?:seen|identified|present|visuali[sz]ed|demonstrated|detected|appreciated)|"
    r"(?:is|are)\s+absent|unlikely"
)
PRE_HYPOTHETICAL = _cue(
    r"rule\s+out|r/o|to\s+(?:rule\s+out|exclude)|evaluat(?:e|ion)\s+for|assess(?:ment)?\s+for|screen(?:ing)?\s+for|"
    r"query|in\s+case\s+of|if\s+(?:there\s+is|any)|should\s+(?:there|it)|monitor\s+for|risk\s+of|at\s+risk\s+for|return\s+if"
)
PRE_HISTORICAL = _cue(
    r"history\s+of|h/o|hx\s+of|past\s+medical\s+history\s+of|previous(?:ly)?|prior(?!\s+(?:study|studies|exam|examination|imaging|ct|mri|radiograph|x-?ray|film|report|scan))|"
    r"status\s+post|s/p|known|remote|old|healed"
)
POST_HISTORICAL = _cue(r"previously|in\s+the\s+past|years?\s+ago|was\s+treated")
PRE_FAMILY = _cue(r"family\s+history\s+of|fhx?\s+of|(?:his|her|the\s+patient'?s)?\s*(?:mother|father|brother|sister|sibling|grand(?:mother|father)|aunt|uncle|parents?)\b(?:\s+(?:has|had|with))?")
POSTOPERATIVE = _cue(r"post-?operative|post-?surgical|surgical\s+(?:changes?|clips?|bed)|status\s+post|s/p")
COMPARISON_CUES = (
    ("RESOLVED", _cue(r"resolved|resolution\s+of|no\s+longer\s+(?:seen|present|visible|identified|evident)")),
    ("NEW", _cue(r"new(?:ly)?|interval\s+development\s+of|not\s+(?:seen|present)\s+(?:on|in)\s+(?:the\s+)?(?:prior|previous)")),
    ("STABLE", _cue(r"stable|unchanged|no\s+(?:significant\s+|interval\s+)?change|similar\s+(?:to|compared\s+(?:with|to))|grossly\s+stable")),
    ("INCREASED", _cue(r"increas(?:ed|ing|e)\s*(?:in\s+size)?|enlarg(?:ed|ing)|larger|progress(?:ed|ion|ing|ive)|worsen(?:ed|ing)|grow(?:n|ing|th)|interval\s+increase")),
    ("DECREASED", _cue(r"decreas(?:ed|ing|e)\s*(?:in\s+size)?|smaller|reduc(?:ed|tion)|regress(?:ed|ion|ing)|improv(?:ed|ing|ement)|resolving|shrink(?:ing|age)?|interval\s+decrease")),
    ("PERSISTENT", _cue(r"persist(?:ent|s|ing)|again\s+(?:seen|noted|demonstrated)|redemonstrat(?:ed|es|ion)|remains?")),
)
COMPARISON_REFERENCE = _cue(r"compared\s+(?:with|to)|since\s+(?:the\s+)?(?:prior|previous|last)|from\s+(?:the\s+)?(?:prior|previous)|relative\s+to")
PRIOR_REFERENCE = re.compile(r"previous(?:ly)?|prior|known", re.IGNORECASE)
AFTER_PROCEDURE = _cue(r"(?:after|following)\s+(?:the\s+)?(?:recent\s+)?\w*ectomy|(?:after|following)\s+(?:surgery|resection|transplant(?:ation)?)")

PRE_WINDOW_WORDS = 8
POST_WINDOW_WORDS = 5


def deidentify_text(raw_text: str) -> str:
    """Apply de-identification masks before any extraction."""
    sanitized = raw_text
    for pattern, replacement in PHI_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return PHONE_CANDIDATE.sub(_redact_phone, sanitized)


def _sections(text: str) -> list[tuple[int, str]]:
    return [(match.start(), match.group("header").strip().upper()) for match in SECTION_RE.finditer(text)]


def _section_at(sections: list[tuple[int, str]], offset: int) -> Optional[str]:
    current = None
    for start, name in sections:
        if start <= offset:
            current = name
        else:
            break
    return current


def split_sentences(text: str) -> list[tuple[int, int]]:
    masked = ABBREVIATION_RE.sub(lambda match: match.group(0).replace(".", "\x00"), text)
    spans = []
    cursor = 0
    for match in BOUNDARY_RE.finditer(masked):
        if match.start() > cursor:
            spans.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(text):
        spans.append((cursor, len(text)))
    result = []
    for start, end in spans:
        segment = text[start:end]
        stripped = segment.strip()
        if not stripped:
            continue
        offset = start + segment.index(stripped)
        result.append((offset, offset + len(stripped)))
    return result


def _clause_bounds(sentence: str, entity_start: int, entity_end: int) -> tuple[int, int]:
    clause_start, clause_end = 0, len(sentence)
    for match in TERMINATOR_RE.finditer(sentence):
        if match.end() <= entity_start:
            clause_start = max(clause_start, match.end())
        elif match.start() >= entity_end:
            clause_end = min(clause_end, match.start())
            break
    return clause_start, clause_end


def _words_between(text: str) -> int:
    return len(WORD_RE.findall(text))


def _last_pre_cue(pattern: re.Pattern, sentence: str, clause_start: int, entity_start: int, consumed: list[tuple[int, int]]):
    window = sentence[clause_start:entity_start]
    best = None
    for match in pattern.finditer(window):
        start, end = clause_start + match.start(), clause_start + match.end()
        if any(start < c_end and end > c_start for c_start, c_end in consumed):
            continue
        if _words_between(sentence[end:entity_start]) <= PRE_WINDOW_WORDS:
            best = (start, end, match.group(0))
    return best


def _first_post_cue(pattern: re.Pattern, sentence: str, entity_end: int, clause_end: int):
    window = sentence[entity_end:clause_end]
    for match in pattern.finditer(window):
        start, end = entity_end + match.start(), entity_end + match.end()
        if _words_between(sentence[entity_end:start]) <= POST_WINDOW_WORDS:
            return (start, end, match.group(0))
    return None


def _entity_matches(sentence: str) -> list[tuple[int, int, Any, str]]:
    hits = []
    for pattern, term in ENTITY_PATTERNS:
        for match in pattern.finditer(sentence):
            hits.append((match.start(), match.end(), term, match.group(0)))
    hits.sort(key=lambda item: (-(item[1] - item[0]), item[0]))
    chosen: list[tuple[int, int, Any, str]] = []
    for start, end, term, surface in hits:
        if any(start < other_end and end > other_start for other_start, other_end, _, _ in chosen):
            continue
        chosen.append((start, end, term, surface))
    return sorted(chosen, key=lambda item: item[0])


def _assess(sentence: str, entity_start: int, entity_end: int, section: Optional[str]) -> dict[str, Any]:
    clause_start, clause_end = _clause_bounds(sentence, entity_start, entity_end)
    cues: list[dict[str, Any]] = []
    consumed: list[tuple[int, int]] = []

    def record(kind: str, hit) -> None:
        cues.append({"type": kind, "text": hit[2], "start": hit[0], "end": hit[1]})
        consumed.append((hit[0], hit[1]))

    negation = "AFFIRMED"
    certainty = "CERTAIN"
    temporality = "CURRENT"
    experiencer = "PATIENT"

    uncertain = _last_pre_cue(PRE_UNCERTAIN, sentence, clause_start, entity_start, consumed) or _first_post_cue(POST_UNCERTAIN, sentence, entity_end, clause_end)
    if uncertain:
        record("UNCERTAINTY", uncertain)
        certainty = "UNCERTAIN"
    negated_uncertain = _last_pre_cue(PRE_NEGATED_UNCERTAIN, sentence, clause_start, entity_start, consumed)
    if negated_uncertain:
        record("NEGATION_UNCERTAIN", negated_uncertain)
        negation, certainty = "NEGATED", "UNCERTAIN"
    hypothetical = _last_pre_cue(PRE_HYPOTHETICAL, sentence, clause_start, entity_start, consumed)
    if hypothetical:
        record("HYPOTHETICAL", hypothetical)
        certainty = "HYPOTHETICAL"
    if negation == "AFFIRMED":
        negated = _last_pre_cue(PRE_NEGATION, sentence, clause_start, entity_start, consumed) or _first_post_cue(POST_NEGATION, sentence, entity_end, clause_end)
        if negated:
            record("NEGATION", negated)
            negation = "NEGATED"
    # The experiencer cue is checked before the historical one because
    # "family history of" contains "history of".
    family = _last_pre_cue(PRE_FAMILY, sentence, clause_start, entity_start, consumed)
    if family:
        record("EXPERIENCER", family)
        experiencer = "FAMILY"
    historical = _last_pre_cue(PRE_HISTORICAL, sentence, clause_start, entity_start, consumed) or _first_post_cue(POST_HISTORICAL, sentence, entity_end, clause_end)
    if historical:
        record("HISTORICAL", historical)
        temporality = "HISTORICAL"

    clause = sentence[clause_start:clause_end]
    comparison = None
    for label, pattern in COMPARISON_CUES:
        match = pattern.search(clause)
        if match:
            comparison = label
            cues.append({"type": "COMPARISON", "text": match.group(0), "start": clause_start + match.start(), "end": clause_start + match.end()})
            break
    reference = COMPARISON_REFERENCE.search(clause)
    if reference:
        cues.append({"type": "COMPARISON_REFERENCE", "text": reference.group(0), "start": clause_start + reference.start(), "end": clause_start + reference.end()})
    if comparison == "RESOLVED":
        temporality = "HISTORICAL"
    elif comparison is not None and historical and PRIOR_REFERENCE.fullmatch(historical[2].strip()):
        # "Previously observed nodule has increased": the comparison documents
        # current presence; the prior mention is a reference, not history.
        temporality = "CURRENT"
        next(cue for cue in cues if cue["type"] == "HISTORICAL" and cue["start"] == historical[0])["type"] = "PRIOR_REFERENCE"
    postoperative = POSTOPERATIVE.search(clause) or AFTER_PROCEDURE.search(clause)
    if postoperative:
        cues.append({"type": "POSTOPERATIVE_CONTEXT", "text": postoperative.group(0), "start": clause_start + postoperative.start(), "end": clause_start + postoperative.end()})

    if section in {"INDICATION", "INDICATIONS", "REASON FOR EXAM", "REASON FOR EXAMINATION", "CLINICAL QUESTION"} and certainty == "CERTAIN" and negation == "AFFIRMED":
        certainty = "HYPOTHETICAL"
        cues.append({"type": "SECTION_CONTEXT", "text": section, "start": None, "end": None})
    if section in {"HISTORY", "PAST MEDICAL HISTORY"} and temporality == "CURRENT":
        temporality = "HISTORICAL"
        cues.append({"type": "SECTION_CONTEXT", "text": section, "start": None, "end": None})
    if section == "FAMILY HISTORY":
        experiencer = "FAMILY"
        cues.append({"type": "SECTION_CONTEXT", "text": section, "start": None, "end": None})

    return {
        "negation": negation,
        "certainty": certainty,
        "temporality": temporality,
        "experiencer": experiencer,
        "comparison": comparison,
        "cues": cues,
        "clause": (clause_start, clause_end),
    }


def extract_clinical_statements(report_text: str) -> List[Dict[str, Any]]:
    """Extract source-linked statements with assertion, certainty and context."""
    sections = _sections(report_text)
    statements: List[Dict[str, Any]] = []
    for sentence_start, sentence_end in split_sentences(report_text):
        sentence = report_text[sentence_start:sentence_end]
        section = _section_at(sections, sentence_start)
        sites = find_sites(sentence)
        for entity_start, entity_end, term, surface in _entity_matches(sentence):
            context = _assess(sentence, entity_start, entity_end, section)
            clause_start, clause_end = context.pop("clause")
            in_clause = [site for site in sites if site["start"] >= clause_start and site["end"] <= clause_end]
            site = min(
                in_clause or sites,
                key=lambda item: min(abs(item["start"] - entity_end), abs(entity_start - item["end"])),
                default=None,
            )
            system = term.system or (site["system"] if site else None)
            if site and term.system and site["system"] != term.system:
                site = None if term.system != "brain" or site["system"] != "nervous" else site
            if term.category == "PROCEDURE" and context["temporality"] == "CURRENT" and any(cue["type"] == "POSTOPERATIVE_CONTEXT" for cue in context["cues"]):
                context["temporality"] = "HISTORICAL"
            for cue in context["cues"]:
                if cue["start"] is not None:
                    cue["start"] += sentence_start
                    cue["end"] += sentence_start
            statements.append({
                "entity": term.label,
                "entity_text": surface,
                "category": term.category,
                "negation": context["negation"],
                "certainty": context["certainty"],
                "temporality": context["temporality"],
                "experiencer": context["experiencer"],
                "comparison": context["comparison"],
                "cues": context["cues"],
                "section": section,
                "anatomical_site": site["text"] if site else None,
                "laterality": site["side"] if site else None,
                "anatomy_system": system,
                "atlas_structure_id": site["atlas_structure_id"] if site else None,
                "atlas_structure_name": site["atlas_structure_name"] if site else None,
                "source_span": sentence[:256],
                "source_span_start": sentence_start,
                "source_span_end": sentence_end,
                "entity_start": sentence_start + entity_start,
                "entity_end": sentence_start + entity_end,
            })
    return statements


# ---------------------------------------------------------------------------
# Numeric measurements
# ---------------------------------------------------------------------------

VALUE = r"(?P<operator><=|>=|<|>|≤|≥)?\s*(?P<value>(?<![\d.\-–/])-?\d+(?:\.\d+)?(?!\d|\.\d|\s*[-–]\s*\d))"
SEPARATOR = r"\s*(?:\([^)\n]{1,24}\)\s*)?(?:[:=|]|\bis\b|\bof\b|\bwas\b|\bmeasures?\b|\bmeasuring\b|\bat\b)?\s*"
REFERENCE_PATTERNS = (
    re.compile(r"\s*[\(\[]\s*(?:(?:ref(?:erence)?(?:\s*(?:range|interval))?|normal(?:\s*range)?|nr|range)\s*[:=]?\s*)?(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(?P<high>\d+(?:\.\d+)?)\s*[A-Za-zµμ/%^0-9.\s]{0,15}?\s*[\)\]]", re.IGNORECASE),
    re.compile(r"\s*[,;]?\s*(?:ref(?:erence)?(?:\s*(?:range|interval))?|normal(?:\s*range)?|nr)\s*[:=]?\s*(?P<low>\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(?P<high>\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\s*[\(\[]\s*(?P<op><=|>=|<|>|≤|≥)\s*(?P<bound>\d+(?:\.\d+)?)\s*[^)\]\n]{0,12}[\)\]]", re.IGNORECASE),
    re.compile(r"(?:[ \t]{2,}|\t|[ \t]*\|[ \t]*)(?P<low>\d+(?:\.\d+)?)[ \t]*(?:-|–|—)[ \t]*(?P<high>\d+(?:\.\d+)?)"),
)
FLAG_RE = re.compile(r"[ \t]*(?:\(|\[)?[ \t]*(?P<flag>HH|LL|H|L|High|Low|Abnormal|Critical|\*{1,2}|↑|↓)[ \t]*(?:\)|\])?(?![A-Za-z0-9])")
FLAG_NAMES = {"H": "HIGH", "HIGH": "HIGH", "HH": "CRITICAL_HIGH", "L": "LOW", "LOW": "LOW", "LL": "CRITICAL_LOW", "ABNORMAL": "ABNORMAL", "CRITICAL": "CRITICAL", "*": "ABNORMAL", "**": "CRITICAL", "↑": "HIGH", "↓": "LOW"}

SPECIMEN_RE = re.compile(
    r"^[ \t]*(?:specimen|sample(?:\s+type)?)\s*[:=]\s*"
    r"(?P<value>serum|plasma|whole\s+blood|blood|urine|stool|faeces|feces|csf|cerebrospinal\s+fluid|saliva|sputum|tissue)\b",
    re.IGNORECASE | re.MULTILINE,
)
LAB_METHOD_RE = re.compile(r"^[ \t]*(?:assay|test\s+method|laboratory\s+method|method)\s*[:=]\s*(?P<value>[^\n|]{1,128})", re.IGNORECASE | re.MULTILINE)
LAB_NAME_RE = re.compile(r"^[ \t]*(?:laboratory|lab(?:oratory)?\s+name|facility)\s*[:=]\s*(?P<value>[^\n|]{1,128})", re.IGNORECASE | re.MULTILINE)


def _result_operator(raw: Optional[str]) -> str:
    return {"≤": "<=", "≥": ">="}.get(raw or "=", raw or "=")


def extract_measurement_context(report_text: str) -> dict[str, str]:
    """Return only context explicitly printed in the source report."""
    specimen = SPECIMEN_RE.search(report_text)
    method = LAB_METHOD_RE.search(report_text)
    laboratory = LAB_NAME_RE.search(report_text)
    return {
        "specimen": specimen.group("value").strip()[:64] if specimen else "NOT_DOCUMENTED",
        "laboratory_method": method.group("value").strip()[:128] if method else "NOT_DOCUMENTED",
        "laboratory_name": laboratory.group("value").strip()[:128] if laboratory else "NOT_DOCUMENTED",
    }

BLOOD_PRESSURE = re.compile(
    r"\b(?:blood\s*pressure|\bbp\b)\s*(?:[:=|]|is|of|was)?\s*"
    r"(?P<systolic>\d{2,3}(?:\.\d+)?)\s*/\s*(?P<diastolic>\d{2,3}(?:\.\d+)?)\s*(?P<unit>mm\s*hg)\b",
    re.IGNORECASE,
)
LESION_LABELS = r"lesion|nodule|mass|opacity|cyst|tumou?r|polyp|collection|calculus|stone"
DIMS = r"(?P<dims>(?<![\d.])\d+(?:\.\d+)?(?:\s*[x×]\s*\d+(?:\.\d+)?){0,2})\s*(?P<unit>mm|cm)\b"
# Label first ("the nodule measures 1.2 cm"). The gap may not contain change or
# prior-value language: "increased from 8 mm" documents an earlier size.
LESION_SIZE = re.compile(
    rf"\b(?P<label>{LESION_LABELS})\b(?P<gap>[^.;\n]{{0,40}}?)(?:\b(?:measur(?:es|ing)|of|size|diameter|sized?)\b)?\s*{DIMS}",
    re.IGNORECASE,
)
# Size first ("a 1.4 x 0.9 cm nodule").
LESION_SIZE_PREFIX = re.compile(rf"{DIMS}\s+(?:[a-z-]+\s+){{0,3}}?(?P<label>{LESION_LABELS})\b", re.IGNORECASE)
PRIOR_VALUE_GAP = re.compile(r"\b(?:from|previously|prior|was|were|increas\w*|decreas\w*|grown|shrunk|compared|then)\b", re.IGNORECASE)
LESION_NAMES = {"lesion": "lesion_size", "nodule": "nodule_size", "mass": "mass_size", "opacity": "opacity_size", "cyst": "cyst_size",
                "tumor": "mass_size", "tumour": "mass_size", "polyp": "polyp_size", "collection": "collection_size", "calculus": "calculus_size", "stone": "calculus_size"}
KIDNEY_LENGTH = re.compile(
    r"\b(?P<side>right|left)\s+kidney\b[^.;\n]{0,30}?\b(?:measures?|measuring|length(?:\s+of)?|is)\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>cm|mm)\b",
    re.IGNORECASE,
)
LIVER_SPAN = re.compile(r"\bliver\b[^.;\n]{0,20}?\b(?:span|measures?|measuring|length)\b\s*(?:of\s*)?(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>cm|mm)\b", re.IGNORECASE)


def _analyte_pattern(analyte) -> re.Pattern:
    if analyte.units is None:
        return re.compile(rf"(?P<label>\b(?:{analyte.aliases})){SEPARATOR}{VALUE}(?!\s*[A-Za-z%])", re.IGNORECASE)
    return re.compile(rf"(?P<label>\b(?:{analyte.aliases})){SEPARATOR}{VALUE}\s*(?P<unit>{analyte.units})(?![A-Za-z0-9_])", re.IGNORECASE)


ANALYTE_PATTERNS = [(analyte, _analyte_pattern(analyte)) for analyte in ANALYTES]


def _reference_and_flag(text: str, position: int) -> dict[str, Any]:
    """Read a documented reference interval and/or flag immediately after a value."""
    result: dict[str, Any] = {
        "reference_low": None, "reference_high": None,
        "reference_low_inclusive": None, "reference_high_inclusive": None,
        "reference_text": None, "reference_source": None, "documented_flag": None,
    }
    cursor = position
    line_end = text.find("\n", position)
    limit = len(text) if line_end == -1 else line_end
    for _ in range(2):
        flag = FLAG_RE.match(text, cursor, limit)
        if flag and result["documented_flag"] is None:
            result["documented_flag"] = FLAG_NAMES.get(flag.group("flag").upper(), FLAG_NAMES.get(flag.group("flag")))
            cursor = flag.end()
            continue
        if result["reference_text"] is None:
            for pattern in REFERENCE_PATTERNS:
                reference = pattern.match(text, cursor, limit)
                if not reference:
                    continue
                groups = reference.groupdict()
                if groups.get("low") is not None:
                    low, high = float(groups["low"]), float(groups["high"])
                    if low <= high:
                        result.update(reference_low=low, reference_high=high)
                elif groups.get("bound") is not None:
                    bound = float(groups["bound"])
                    if groups["op"] in {"<", "<=", "≤"}:
                        result["reference_high"] = bound
                        result["reference_high_inclusive"] = groups["op"] in {"<=", "≤"}
                    else:
                        result["reference_low"] = bound
                        result["reference_low_inclusive"] = groups["op"] in {">=", "≥"}
                if result["reference_low"] is not None or result["reference_high"] is not None:
                    result["reference_text"] = reference.group(0).strip()[:64]
                    result["reference_source"] = "DOCUMENTED_IN_SOURCE"
                    cursor = reference.end()
                break
            else:
                break
        else:
            break
    return result


def _measurement(name: str, label: str, value: float, unit: str, raw_value: str, raw_unit: str, match_start: int, match_end: int, text: str, **extra) -> Dict[str, Any]:
    record = {
        "name": name,
        "display_name": label,
        "value": value,
        "result_operator": "=",
        "unit": unit,
        "raw_value": raw_value,
        "raw_unit": raw_unit,
        "source_span": text[match_start:match_end],
        "source_span_start": match_start,
        "source_span_end": match_end,
        "canonical_code": None,
        "code_system": None,
        "code_mapping_status": None,
        "anatomy_system": None,
        "association": None,
        "conversion_status": "AS_DOCUMENTED",
        "reference_low": None,
        "reference_high": None,
        "reference_low_inclusive": None,
        "reference_high_inclusive": None,
        "reference_text": None,
        "reference_source": None,
        "documented_flag": None,
    }
    record.update(extra)
    return record


def extract_numeric_measurements(report_text: str) -> List[Dict[str, Any]]:
    """Extract explicit name/value/unit triples with exact offsets and no inference."""
    measurements: List[Dict[str, Any]] = []
    claimed: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return not any(start < other_end and end > other_start for other_start, other_end in claimed)

    for match in BLOOD_PRESSURE.finditer(report_text):
        for name, label, group, code in (
            ("systolic_blood_pressure", "Systolic blood pressure", "systolic", "8480-6"),
            ("diastolic_blood_pressure", "Diastolic blood pressure", "diastolic", "8462-4"),
        ):
            measurements.append(_measurement(
                name, label, float(match.group(group)), "mmHg", match.group(group), match.group("unit"),
                match.start(), match.end(), report_text,
                canonical_code=code, code_system=LOINC, code_mapping_status=LOINC_MAPPING_STATUS,
                anatomy_system="heart", association="PHYSIOLOGICAL_SIGNAL",
            ))
        claimed.append((match.start(), match.end()))

    lesion_matches = [(match, True) for match in LESION_SIZE_PREFIX.finditer(report_text)]
    lesion_matches += [(match, False) for match in LESION_SIZE.finditer(report_text) if not PRIOR_VALUE_GAP.search(match.group("gap"))]
    for match, _prefix in sorted(lesion_matches, key=lambda item: item[0].start()):
        if not free(match.start(), match.end()):
            continue
        dims = [float(part) for part in re.split(r"\s*[x×]\s*", match.group("dims"))]
        unit = match.group("unit").lower()
        largest = max(dims) * (10.0 if unit == "cm" else 1.0)
        label = match.group("label").lower()
        name = LESION_NAMES.get(label, "lesion_size")
        noun = "calculus" if name == "calculus_size" else label
        measurements.append(_measurement(
            name, f"Documented {noun} size (largest dimension)", round(largest, 6), "mm",
            match.group("dims"), match.group("unit"), match.start(), match.end(), report_text,
            conversion_status="CONVERTED_CM_TO_MM" if unit == "cm" else "AS_DOCUMENTED",
            association="REQUIRES_LESION_IDENTITY_REVIEW",
        ))
        claimed.append((match.start(), match.end()))

    for match in KIDNEY_LENGTH.finditer(report_text):
        if not free(match.start(), match.end()):
            continue
        side = match.group("side").lower()
        unit = match.group("unit").lower()
        value = float(match.group("value")) * (10.0 if unit == "cm" else 1.0)
        measurements.append(_measurement(
            f"kidney_length_{side}", f"{side.capitalize()} kidney length", value, "mm", match.group("value"), match.group("unit"),
            match.start(), match.end(), report_text, anatomy_system="kidneys", association="DOCUMENTED_ORGAN_MEASURE",
            conversion_status="CONVERTED_CM_TO_MM" if unit == "cm" else "AS_DOCUMENTED",
        ))
        claimed.append((match.start(), match.end()))

    for match in LIVER_SPAN.finditer(report_text):
        if not free(match.start(), match.end()):
            continue
        unit = match.group("unit").lower()
        value = float(match.group("value")) * (10.0 if unit == "cm" else 1.0)
        measurements.append(_measurement(
            "liver_span", "Liver span", value, "mm", match.group("value"), match.group("unit"),
            match.start(), match.end(), report_text, anatomy_system="liver", association="DOCUMENTED_ORGAN_MEASURE",
            conversion_status="CONVERTED_CM_TO_MM" if unit == "cm" else "AS_DOCUMENTED",
        ))
        claimed.append((match.start(), match.end()))

    for analyte, pattern in ANALYTE_PATTERNS:
        for match in pattern.finditer(report_text):
            if not free(match.start(), match.end()):
                continue
            raw_value = match.group("value")
            raw_unit = match.group("unit") if analyte.units is not None else ""
            unit = normalise_unit(raw_unit) if analyte.units is not None else analyte.unitless_unit
            code = loinc_for(analyte, unit)
            measurements.append(_measurement(
                analyte.name, analyte.display, float(raw_value), unit, raw_value, raw_unit,
                match.start(), match.end(), report_text,
                result_operator=_result_operator(match.group("operator")),
                canonical_code=code, code_system=LOINC if code else None, code_mapping_status=LOINC_MAPPING_STATUS if code else None,
                anatomy_system=analyte.system, association=analyte.association,
                **_reference_and_flag(report_text, match.end()),
            ))
            claimed.append((match.start(), match.end()))

    return sorted(measurements, key=lambda item: (item["source_span_start"], item["name"]))


# ---------------------------------------------------------------------------
# Documented attributes (dates, age, sex)
# ---------------------------------------------------------------------------

MONTHS = {name: index for index, names in enumerate(
    (("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
     ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"), ("dec", "december")),
    start=1) for name in names}
DATE_RE = re.compile(
    r"(?P<label>collection\s*date|date\s*(?:of\s*)?collection|collected(?:\s*on)?|sample\s*(?:collection\s*)?date|specimen\s*(?:collection\s*)?date|"
    r"sampling\s*date|report(?:ed)?\s*date|date\s*(?:of\s*)?report|date\s*reported|reported(?:\s*on)?|study\s*date|exam(?:ination)?\s*date|"
    r"date\s*of\s*(?:exam(?:ination)?|study|service|procedure)|\bdate\b)\s*[:\-]?\s*"
    r"(?P<date>\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4})",
    re.IGNORECASE,
)
AGE_RE = re.compile(
    r"\b(?P<age>\d{1,3})\s*[-\s]?(?:years?|yrs?|y/o|yo)[-\s]*(?:old)?\b(?=[^.\n]{0,20}(?:male|female|man|woman|patient|boy|girl|\bm\b|\bf\b))"
    r"|\bage(?:\s*/\s*sex)?\s*[:=]?\s*(?P<age2>\d{1,3})\b",
    re.IGNORECASE,
)
SEX_RE = re.compile(
    r"\b(?:sex|gender)\s*[:=]?\s*(?P<sex>male|female|m|f)\b"
    r"|\bage\s*/\s*sex\s*[:=]?\s*\d{1,3}\s*(?:y(?:ears?|rs?)?)?\s*/\s*(?P<sex2>m|f|male|female)\b"
    r"|\b\d{1,3}\s*[-\s]?(?:years?|yrs?|y/o|yo)[-\s]*(?:old)?\s+(?P<sex3>male|female|man|woman|boy|girl)\b",
    re.IGNORECASE,
)


def _parse_date(raw: str) -> tuple[Optional[str], str]:
    text = raw.strip().lower().replace(",", "")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text).isoformat(), "PARSED_ISO_8601"
        match = re.fullmatch(r"(\d{1,2})\s+([a-z]{3,9})\.?\s+(\d{4})", text)
        if match and match.group(2) in MONTHS:
            return date(int(match.group(3)), MONTHS[match.group(2)], int(match.group(1))).isoformat(), "PARSED_DAY_MONTH_NAME"
        match = re.fullmatch(r"([a-z]{3,9})\.?\s+(\d{1,2})\s+(\d{4})", text)
        if match and match.group(1) in MONTHS:
            return date(int(match.group(3)), MONTHS[match.group(1)], int(match.group(2))).isoformat(), "PARSED_MONTH_NAME_DAY"
        match = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", text)
        if match:
            first, second, year = int(match.group(1)), int(match.group(2)), match.group(3)
            if len(year) != 4:
                return None, "AMBIGUOUS_TWO_DIGIT_YEAR"
            if first > 12 and second <= 12:
                return date(int(year), second, first).isoformat(), "PARSED_DAY_FIRST_UNAMBIGUOUS"
            if second > 12 and first <= 12:
                return date(int(year), first, second).isoformat(), "PARSED_MONTH_FIRST_UNAMBIGUOUS"
            return None, "AMBIGUOUS_DAY_MONTH_ORDER"
    except ValueError:
        return None, "INVALID_CALENDAR_DATE"
    return None, "UNRECOGNISED_FORMAT"


def extract_documented_attributes(report_text: str) -> List[Dict[str, Any]]:
    attributes: List[Dict[str, Any]] = []
    for match in DATE_RE.finditer(report_text):
        label = match.group("label").lower()
        if re.search(r"collect|sampl|specimen", label):
            kind = "sampling_date"
        elif "report" in label:
            kind = "report_date"
        elif re.search(r"study|exam|service|procedure", label):
            kind = "study_date"
        else:
            kind = "document_date"
        parsed, status = _parse_date(match.group("date"))
        attributes.append({
            "name": kind, "value_text": parsed, "value_number": None, "unit": None, "parse_status": status,
            "raw_text": match.group("date"), "source_span": match.group(0), "source_span_start": match.start(), "source_span_end": match.end(),
        })
    for match in AGE_RE.finditer(report_text):
        raw = match.group("age") or match.group("age2")
        age = int(raw)
        if age > 120:
            continue
        aggregated = age > 89
        attributes.append({
            "name": "age_years", "value_text": "90+" if aggregated else str(age), "value_number": None if aggregated else float(age), "unit": "a",
            "parse_status": "AGGREGATED_SAFE_HARBOR" if aggregated else "PARSED", "raw_text": raw,
            "source_span": match.group(0), "source_span_start": match.start(), "source_span_end": match.end(),
        })
    for match in SEX_RE.finditer(report_text):
        raw = (match.group("sex") or match.group("sex2") or match.group("sex3")).lower()
        value = "male" if raw in {"m", "male", "man", "boy"} else "female"
        attributes.append({
            "name": "sex", "value_text": value, "value_number": None, "unit": None, "parse_status": "PARSED", "raw_text": raw,
            "source_span": match.group(0), "source_span_start": match.start(), "source_span_end": match.end(),
        })
    return attributes


def page_for_offset(page_starts: list[int], offset: int) -> int:
    page = 1
    for index, start in enumerate(page_starts):
        if offset >= start:
            page = index + 1
    return page


def prepare_report_document(report_path: Path) -> tuple[str, list[int], list[dict]]:
    """Parse and de-identify page by page so offsets and page numbers agree.
    Returns the text, page start offsets and per-page provenance (embedded text or OCR)."""
    pages, page_meta = parse_clinical_document_pages(report_path)
    sanitized_pages: list[str] = []
    for page, meta in zip(pages, page_meta):
        raw_lines = meta.get("lines") if meta.get("method") == "OCR" else None
        if not raw_lines:
            sanitized_pages.append(deidentify_text(page))
            continue
        safe_lines: list[dict[str, Any]] = []
        safe_text_lines: list[str] = []
        line_cursor = 0
        for line in raw_lines:
            sanitized_line = deidentify_text(str(line.get("text", "")))
            safe_text_lines.append(sanitized_line)
            safe_lines.append({
                "text_start": line_cursor,
                "text_end": line_cursor + len(sanitized_line),
                "confidence": line.get("confidence"),
                "bbox_xyxy": line.get("box"),
            })
            line_cursor += len(sanitized_line) + 1
        sanitized_pages.append("\n".join(safe_text_lines))
        meta["lines"] = safe_lines
    starts = []
    cursor = 0
    for page in sanitized_pages:
        starts.append(cursor)
        cursor += len(page) + 1
    return "\n".join(sanitized_pages), starts, page_meta


def prepare_report_text(report_path: Path) -> tuple[str, list[int]]:
    text, starts, _meta = prepare_report_document(report_path)
    return text, starts


def summarise_statements(statements: List[Dict[str, Any]]) -> str:
    """A non-diagnostic label for the processing finding."""
    if not statements:
        return "No recognised clinical entity"
    affirmed = sum(1 for item in statements if item["negation"] == "AFFIRMED" and item["certainty"] == "CERTAIN" and item["experiencer"] == "PATIENT")
    negated = sum(1 for item in statements if item["negation"] == "NEGATED")
    qualified = len(statements) - affirmed - negated
    return f"{len(statements)} source-linked statements ({affirmed} affirmed, {negated} negated, {qualified} qualified)"


def analyze_clinical_report(report_path: Path, file_hash: str) -> Dict[str, Any]:
    """Read, de-identify, and extract structured evidence from a clinical report."""
    try:
        sanitized_text, page_starts, page_meta = prepare_report_document(report_path)
    except Exception as e:
        raise ValueError(f"Unable to parse clinical report: {str(e)}") from e

    if not sanitized_text.strip():
        raise ValueError("Clinical report text file is empty.")

    from app.services.fhir_import import fhir_measurements

    statements = extract_clinical_statements(sanitized_text)
    structured = fhir_measurements(report_path, sanitized_text)
    measurements = structured if structured is not None else extract_numeric_measurements(sanitized_text)
    measurement_context = extract_measurement_context(sanitized_text)
    for measurement in measurements:
        measurement.update(measurement_context)
        measurement.setdefault("extractor_version", EXTRACTOR_VERSION)
    attributes = extract_documented_attributes(sanitized_text)
    multi_page = len(page_starts) > 1
    ocr_pages = {meta["page"] for meta in page_meta if meta.get("method") == "OCR"}
    for item in measurements:
        page = page_for_offset(page_starts, item["source_span_start"])
        item["source_page"] = page if multi_page else None
        if page in ocr_pages and item.get("extraction_method", "TRANSPARENT_RULE_BASELINE") == "TRANSPARENT_RULE_BASELINE":
            item["extraction_method"] = "OCR_RULE_BASELINE"
            meta = page_meta[page - 1]
            relative_start = item["source_span_start"] - page_starts[page - 1]
            relative_end = item["source_span_end"] - page_starts[page - 1]
            matched_lines = [
                line for line in meta.get("lines", [])
                if relative_start < line["text_end"] and relative_end > line["text_start"]
            ]
            if matched_lines:
                boxes = [line["bbox_xyxy"] for line in matched_lines]
                item["source_bbox"] = [
                    min(box[0] for box in boxes), min(box[1] for box in boxes),
                    max(box[2] for box in boxes), max(box[3] for box in boxes),
                ]
                item["source_bbox_coordinate_space"] = meta.get("coordinate_space")
                item["source_image_width"] = meta.get("image_width")
                item["source_image_height"] = meta.get("image_height")
    sampling = next((item for item in attributes if item["name"] == "sampling_date" and item["value_text"]), None)
    reported = next((item for item in attributes if item["name"] in {"report_date", "study_date", "document_date"} and item["value_text"]), None)
    documented_date = (sampling or reported or {}).get("value_text")
    for item in measurements:
        item.setdefault("documented_date", documented_date)

    from app.services import scispacy_adapter

    model_statements: List[Dict[str, Any]] = []
    secondary: Dict[str, Any] = {"status": "DISABLED"}
    if scispacy_adapter.mode() == "wsl":
        try:
            model_statements, model_meta = scispacy_adapter.model_statements(sanitized_text)
            secondary = {"status": "COMPLETED", "models": model_meta, "statement_count": len(model_statements),
                         "validation_status": "PUBLISHER_REPORTED_ONLY_NOT_EVALUATED_ON_CLINICAL_CORPUS"}
        except scispacy_adapter.ScispacyUnavailable as exc:
            secondary = {"status": "UNAVAILABLE", "reason": str(exc)}

    return {
        "modality": "REPORT",
        "category": "Narrative Clinical Report",
        "label": summarise_statements(statements),
        "raw_confidence": None,
        "calibrated_confidence": None,
        "calibration_status": "NOT_APPLICABLE_RULE_ENGINE",
        "statements": statements + model_statements,
        "measurements": measurements,
        "attributes": attributes,
        "representation_level": "L1",
        "anatomical_region": None,
        "mapping_status": "L1_GENERIC: Text reports provide symbolic assertions, not 3D spatial coordinates.",
        "model_name": "Rule-Based Clinical Text Baseline",
        "model_version": EXTRACTOR_VERSION,
        "preprocessing_version": "document-parser-v2+deidentification-v2+context-rules-v2",
        "evidence_status": "PENDING_HUMAN_REVIEW",
        "is_demo": False,
        "provenance": {
            "input_hash": file_hash,
            "statement_count": len(statements),
            "secondary_model_ner": secondary,
            "measurement_count": len(measurements),
            "attribute_count": len(attributes),
            "page_count": len(page_starts),
            "pages": page_meta,
            "ocr_page_count": len(ocr_pages),
            "source_format": report_path.suffix.lower(),
            "pipeline_type": "FHIR_STRUCTURED_IMPORT" if structured is not None else "TRANSPARENT_RULE_AND_MEASUREMENT_BASELINE",
            "deidentification_applied": True,
            "validation_status": "BASELINE_NOT_EVALUATED_ON_ANNOTATED_CORPUS",
            "research_notice": "Report extraction identifies text assertions only; it does not formulate independent diagnoses.",
        },
    }
