"""
Transparent clinical-text extraction for MedTwin (rules v2).

The extractor identifies what a report states; it never formulates a
diagnosis. For every recognised entity it records:

- assertion: AFFIRMED or NEGATED
- certainty: CERTAIN, UNCERTAIN or HYPOTHETICAL ("rule out", "evaluate for",
  an advised or planned procedure)
- temporality: CURRENT or HISTORICAL
- experiencer: PATIENT, FAMILY or OTHER (generic population statements printed
  with reference intervals)
- comparison: documented change language (STABLE, INCREASED, NEW, ...)
- the documented anatomical site, if any, and its atlas structure
- the cues that produced each attribute, with offsets

Scoping follows the NegEx/ConText approach: cues act within a clause and a
bounded word window. Rules run on OCR-normalised text (glued words split,
wrapped lines rejoined) and every offset maps back to the source. Billing,
advertising and disclaimer lines produce no statements. The rules have not
been evaluated on an annotated corpus; every output remains PENDING_HUMAN_REVIEW.
"""

from __future__ import annotations

from datetime import date
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.document_parser import parse_clinical_document_pages, parse_clinical_document_with_pages  # noqa: F401
from app.services.ocr_text import normalise, to_normalised, to_source
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
    "recommendations", "summary", "opinion", "interpretation", "advice", "advise",
    "investigations advised", "follow-up advice", "follow up advice", "provisional diagnosis", "pre existing illness",
    "pre-existing illness", "complaints", "examination", "medicine", "observation",
    "gross description", "microscopic description", "nature of specimen", "clinical details", "clinical information",
)
# Sections that state what should happen next, not what was found or done.
PLANNED_SECTIONS = {"PLAN", "RECOMMENDATION", "RECOMMENDATIONS", "ADVICE", "ADVISE", "INVESTIGATIONS ADVISED", "FOLLOW-UP ADVICE", "FOLLOW UP ADVICE"}
HISTORY_SECTIONS = {"HISTORY", "PAST MEDICAL HISTORY", "PRE EXISTING ILLNESS", "PRE-EXISTING ILLNESS"}
# A heading opens a line, or follows a sentence on the same line ("...appeared normal.
# IMPRESSION-..."), and is followed by a colon or a dash, or stands alone on its line.
SECTION_RE = re.compile(
    r"(?:^|(?<=[.;]))[ \t]*(?P<header>" + "|".join(re.escape(name) for name in sorted(SECTION_NAMES, key=len, reverse=True)) + r")[ \t]*(?::|[-–](?![-–])|$)",
    re.IGNORECASE | re.MULTILINE,
)

# Sentence boundaries: semicolons, full stops that are not part of a decimal
# number (including OCR-glued "limits.No"), and the line breaks that end a line
# rather than wrap one (see _line_wraps). Abbreviation full stops are masked
# first (same length, so offsets are unchanged).
BOUNDARY_RE = re.compile(r";|(?<!\d)\.(?!\d)(?=\s|$|[A-Z])")
NEWLINE_RUN = re.compile(r"\n+")
LIST_START = re.compile(r"^\s*(?:[-•*❖▪●►>]|\(?\d{1,2}[.)]|\(?[ivx]{1,4}[.)]\s|[A-Z][A-Za-z /&()'-]{1,40}?\s*:)")
DANGLING_WORDS = frozenset({
    "no", "not", "nor", "neither", "or", "and", "of", "with", "without", "to", "the", "a", "an", "any", "in",
    "for", "from", "is", "are", "was", "were", "be", "by", "as", "at", "on", "than", "upto", "up", "into", "within",
})
# Clinical adjectives that need a following noun ("diaphragmatic", "renal", "pulmonary").
DANGLING_ADJECTIVE = re.compile(r"(?!(?:ab)?normal$|total$|usual$|general$)[A-Za-z]{3,}(?:atic|ical|ic|al|ous|ary)", re.IGNORECASE)
ABBREVIATION_RE = re.compile(r"\b(?:e\.g|i\.e|vs|dr|mrs|mr|ms|approx|cf|fig|resp|incl)\.", re.IGNORECASE)
TERMINATOR_RE = re.compile(
    r"\b(?:but|however|although|though|except|apart\s+from|aside\s+from|otherwise|whereas|yet|nevertheless)\b|[,:](?=\s+(?:but|however|although)\b)"
    # A dash that introduces an explanation starts a new clause ("WITHOUT ... INVAGINATION-likely due to ...").
    r"|\s*[-–—]\s*(?=(?:likely|probably|possibly|suggestive|s/o|due\s+to|\?)(?![A-Za-z]))",
    re.IGNORECASE,
)
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
    r"(?:is|are|was|were|has\s+been|have\s+been)\s+(?:ruled\s+out|excluded|absent)|not\s+(?:seen|identified|present|visuali[sz]ed|demonstrated|detected|appreciated|noted)|"
    r"(?:is|are)\s+absent|unlikely|(?:[-–—:]\s*)?(?:grade\s+)?nil|none\s+(?:seen|noted|identified)|"
    # OCR drops the thin final "l" of "Nil" ("Calcification:Ni."); only right after ":"/"-"
    # and closing the item, where no other reading of "Ni" is possible.
    r"(?<=[-–—:])[ \t]*(?:grade\s+)?ni(?=[ \t]*\.?[ \t]*(?:$|\n))"
)
# "No features suggestive of X" negates X; it is not an uncertain mention of X.
PRE_STRONG_NEGATION = _cue(
    r"no\s+(?:radiological\s+|imaging\s+)?(?:features?|signs?|evidence|findings?)\s+(?:suggestive|suggesting|indicative|characteristic|consistent\s+with)(?:\s+of)?"
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
POSTOPERATIVE = _cue(r"post-?operative|post-?surgical|surgical\s+(?:changes?|clips?|bed)|status\s+post|s/p|post[-\s]*\w*(?:ectomy|ostomy)(?:\s+status)?")
# Planned or advised procedures and tests ("FNAC advised", "follow up with biopsy report").
PRE_RECOMMENDED = _cue(r"advised?|advise[ds]|recommend(?:ed|s|ation)?|suggested|plan(?:ned)?\s+(?:for|to)|follow\s*-?\s*up\s+with|to\s+(?:do|undergo|be\s+done)|referred\s+for|kindly\s+do")
POST_RECOMMENDED = _cue(r"(?:is|are|was)?\s*(?:advised|recommended|suggested|planned)|to\s+(?:rule\s+out|exclude|r/o)|for\s+(?:further\s+)?(?:evaluation|correlation)")
# Generic population statements printed with reference intervals ("may be found in patients
# with colorectal cancer") describe other people, not this patient.
PRE_GENERIC = _cue(
    r"(?:may|can|could)\s+(?:be\s+)?(?:found|seen|observed|elevated|increased|raised|present)\s+in|"
    r"(?:found|seen|observed|elevated|increased|raised|occurs?)\s+in\s+(?:some\s+)?(?:patients|individuals|people|persons|subjects|smokers|cases)|"
    r"(?:patients|individuals|people|persons|subjects)\s+with|in\s+(?:patients|individuals|people)\s+with"
)
STATUS_POST = re.compile(r"status\s+post|s/p|post", re.IGNORECASE)

# Lines that are not clinical statements about the patient: bills, price lists, facility
# advertising and disclaimers. Entity mentions there ("Biopsy 970.00", "All ... Biopsy and
# Laboratory services") are services charged or offered, not procedures performed.
_MONEY = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{2,3})*\.\d{2}(?![\d%])")
BILLING_LINE = re.compile(
    r"\b(?:bill(?:\s*(?:no|date|type|of\s+supply))?|invoice|receipt|charges?|net\s+amount|amount\s+paid|discount|"
    r"mode\s+of\s+payment|received\s+with\s+thanks|gst\s*(?:no|in)|pan\s*no|refund|self\s*pay|tariff)\b",
    re.IGNORECASE,
)
FACILITY_LINE = re.compile(
    r"^\s*(?:facilities|services|our\s+services)\s*[:\-]|\b(?:toll\s*free|helpline|for\s+appointments?|home\s+collection|"
    r"monday\s+to\s+(?:saturday|friday)|24\s*[x/]\s*7|\(24\s*/?\s*7\)|website|e-?mail\s*:|certified\s+unit|nabh|nabl|"
    r"not\s+for\s+medico[-\s]*legal|investigations\s+have\s+their\s+limitations|printing\s+mistakes)\b|"
    # OCR glues words ("All2D,3D,4D Color DopplorFNAC,Biopsy and Laboratory services"), so
    # "all" needs only a non-letter after it.
    r"\ball(?![a-z])[^\n]{0,80}?services?\b|\bservices?\s+available\b|(?:\band|&)\s*laborator(?:y|ies)\s*services?\b",
    re.IGNORECASE,
)
BILLING_PAGE_MIN_MARKERS = 2
# Longer lines are paragraphs (embedded text without hard wraps): exclude by sentence.
FACILITY_LINE_MAX = 200


def nonclinical_ranges(text: str, page_starts: Optional[list[int]] = None) -> list[tuple[int, int, str]]:
    """Source ranges that hold billing, advertising or disclaimer text, with the reason."""
    ranges: list[tuple[int, int, str]] = []
    starts = list(page_starts or [0])
    bounds = [(start, starts[number + 1] if number + 1 < len(starts) else len(text)) for number, start in enumerate(starts)]
    for page_start, page_end in bounds:
        page = text[page_start:page_end]
        if len(BILLING_LINE.findall(page)) >= BILLING_PAGE_MIN_MARKERS and len(_MONEY.findall(page)) >= 2:
            ranges.append((page_start, page_end, "BILLING_DOCUMENT"))
            continue
        cursor = 0
        for line in page.split("\n"):
            start, end = page_start + cursor, page_start + cursor + len(line)
            if len(_MONEY.findall(line)) >= 2:
                ranges.append((start, end, "BILLING_LINE"))
            elif FACILITY_LINE.search(line):
                if len(line) <= FACILITY_LINE_MAX:
                    ranges.append((start, end, "FACILITY_OR_DISCLAIMER_TEXT"))
                else:
                    # A paragraph held on one line: only its advertising or disclaimer sentences.
                    ranges += [(start + first, start + last, "FACILITY_OR_DISCLAIMER_TEXT")
                               for first, last in split_sentences(line) if FACILITY_LINE.search(line[first:last])]
            cursor += len(line) + 1
    return ranges
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


def _section_at(sections: list[tuple[int, str]], offset: int, floor: int = 0) -> Optional[str]:
    """The heading in force at ``offset``. Headings before ``floor`` (the start of the page)
    do not carry over: a packet's next page is often another document, and a stale
    RECOMMENDATION or HISTORY heading would change what is asserted on it."""
    current = None
    for start, name in sections:
        if start <= offset:
            current = name if start >= floor else None
        else:
            break
    return current


def _line_wraps(previous: str, following: str) -> bool:
    """True when a line break continues the sentence ("...normal limits. No" / "pericardial
    effusion."): the line ends without terminal punctuation and either ends on a function or
    negation word, continues in lower case, or is a long line wrapping into a short line that
    finishes the sentence. Other unpunctuated breaks stay boundaries, because separate
    unbulleted impression items must not share negation scope."""
    before, after = previous.rstrip(), following.lstrip()
    if not before or not after or before[-1] in ".;:!?":
        return False
    if LIST_START.match(after) or SECTION_RE.match(after):
        return False
    words = WORD_RE.findall(before)
    if words and words[-1].lower() in DANGLING_WORDS:
        return True
    if words and DANGLING_ADJECTIVE.fullmatch(words[-1]) and len(WORD_RE.findall(after)) <= 3:
        # "...TO R/O RIGHT DIAPHRAGMATIC" / "HERNIA": an adjective cannot end the phrase.
        return True
    if after[0].islower():
        return True
    return len(before) >= 45 and len(after) <= 40 and after.endswith(".") and not re.search(r"\d", after)


def _starts_fragment(text: str, start: int) -> bool:
    """A sentence that opens a line in lower case right after a line that ended a sentence
    ("...appear normal." / "atrophy seen.") or after a blank line (OCR leaves one where it lost
    a line) is a fragment: the words before it were lost. A label or heading line before the
    blank line introduces the text instead."""
    if start >= len(text) or not text[start].islower():
        return False
    line_start = text.rfind("\n", 0, start) + 1
    if text[line_start:start].strip() or line_start == 0:
        return False
    previous = text[:line_start - 1].rstrip()
    if not previous:
        return False
    if previous[-1] in ".;!?":
        return True
    blank_before = text[:line_start - 1].rstrip(" \t").endswith("\n")
    previous_line = previous[previous.rfind("\n") + 1:]
    return blank_before and previous[-1] != ":" and not SECTION_RE.match(previous_line)


def split_sentences(text: str) -> list[tuple[int, int]]:
    masked = ABBREVIATION_RE.sub(lambda match: match.group(0).replace(".", "\x00"), text)
    separators = [(match.start(), match.end()) for match in BOUNDARY_RE.finditer(masked)]
    for match in NEWLINE_RUN.finditer(masked):
        line_start = masked.rfind("\n", 0, match.start()) + 1
        next_end = masked.find("\n", match.end())
        following = masked[match.end(): len(masked) if next_end == -1 else next_end]
        if len(match.group(0)) > 1 or not _line_wraps(masked[line_start:match.start()], following):
            separators.append((match.start(), match.end()))
    spans = []
    cursor = 0
    for start, end in sorted(separators):
        if start > cursor:
            spans.append((cursor, start))
        cursor = max(cursor, end)
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


_COORDINATION_GAP = re.compile(r"[\s,/&]*(?:(?:and|or|nor)(?![A-Za-z]))?[\s,/&]*", re.IGNORECASE)


def _post_scope_end(sentence: str, entity_end: int, clause_end: int, entity_spans: tuple[tuple[int, int], ...]) -> int:
    """A cue after an entity ("X - Nil", "X not seen") covers the entities coordinated with
    it ("X and Y are absent") but stops at the next entity that is not: in "regurgitation -
    Grade Trivial ... stenosis - Nil" the "Nil" belongs to the stenosis only."""
    end = entity_end
    for start, stop in entity_spans:
        if start < end or start >= clause_end:
            continue
        if _COORDINATION_GAP.fullmatch(sentence[end:start]):
            end = max(end, stop)
            continue
        return start
    return clause_end


def _assess(
    sentence: str, entity_start: int, entity_end: int, section: Optional[str],
    category: Optional[str] = None, procedure_spans: tuple[tuple[int, int], ...] = (),
    entity_spans: tuple[tuple[int, int], ...] = (),
) -> dict[str, Any]:
    clause_start, clause_end = _clause_bounds(sentence, entity_start, entity_end)
    post_end = _post_scope_end(sentence, entity_end, clause_end, entity_spans)
    cues: list[dict[str, Any]] = []
    consumed: list[tuple[int, int]] = []

    def record(kind: str, hit) -> None:
        cues.append({"type": kind, "text": hit[2], "start": hit[0], "end": hit[1]})
        consumed.append((hit[0], hit[1]))

    negation = "AFFIRMED"
    certainty = "CERTAIN"
    temporality = "CURRENT"
    experiencer = "PATIENT"

    strong_negation = _last_pre_cue(PRE_STRONG_NEGATION, sentence, clause_start, entity_start, consumed)
    if strong_negation:
        record("NEGATION", strong_negation)
        negation = "NEGATED"
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
        negated = _last_pre_cue(PRE_NEGATION, sentence, clause_start, entity_start, consumed) or _first_post_cue(POST_NEGATION, sentence, entity_end, post_end)
        if negated and uncertain and negated[1] <= uncertain[0] < entity_start:
            # The nearer uncertainty cue governs the entity ("without X, likely Y").
            negated = None
        if negated:
            record("NEGATION", negated)
            negation = "NEGATED"
    # The experiencer cue is checked before the historical one because
    # "family history of" contains "history of".
    if category == "PROCEDURE" and certainty == "CERTAIN":
        planned = _last_pre_cue(PRE_RECOMMENDED, sentence, clause_start, entity_start, consumed) or _first_post_cue(POST_RECOMMENDED, sentence, entity_end, clause_end)
        if planned:
            record("PLANNED_OR_RECOMMENDED", planned)
            certainty = "HYPOTHETICAL"
    family = _last_pre_cue(PRE_FAMILY, sentence, clause_start, entity_start, consumed)
    if family:
        record("EXPERIENCER", family)
        experiencer = "FAMILY"
    # A generic population statement covers the whole clause, not only the next few words.
    generic = PRE_GENERIC.search(sentence, clause_start, entity_start)
    if generic and experiencer == "PATIENT":
        record("GENERIC_POPULATION", (generic.start(), generic.end(), generic.group(0)))
        experiencer = "OTHER"
    historical = _last_pre_cue(PRE_HISTORICAL, sentence, clause_start, entity_start, consumed) or _first_post_cue(POST_HISTORICAL, sentence, entity_end, clause_end)
    if historical and STATUS_POST.fullmatch(historical[2].strip()) and any(
        historical[1] <= start and end <= entity_start for start, end in procedure_spans
    ):
        # "S/P loop ileostomy anastomotic site ulcer": the status-post cue belongs to the
        # procedure between it and this entity.
        historical = None
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
    if section in PLANNED_SECTIONS and certainty == "CERTAIN":
        certainty = "HYPOTHETICAL"
        cues.append({"type": "PLANNED_SECTION_CONTEXT", "text": section, "start": None, "end": None})
    if section in HISTORY_SECTIONS and temporality == "CURRENT":
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


def extract_clinical_statements(report_text: str, page_starts: Optional[list[int]] = None) -> List[Dict[str, Any]]:
    """Extract source-linked statements with assertion, certainty and context.

    Rules run on OCR-normalised text (glued words split); every offset and quoted span
    is mapped back to ``report_text`` exactly. Billing, advertising and disclaimer text is
    skipped: a service charged or offered is not a procedure performed or a finding."""
    source_text = report_text
    report_text, index = normalise(source_text)
    excluded = nonclinical_ranges(source_text, page_starts)
    sections = _sections(report_text)
    page_floors = [to_normalised(index, start) for start in (page_starts or [0])]
    statements: List[Dict[str, Any]] = []
    for sentence_start, sentence_end in split_sentences(report_text):
        source_start, source_end = to_source(index, sentence_start, sentence_end)
        if any(start <= source_start and source_end <= end for start, end, _ in excluded) or any(
            source_start < end and start < source_end and reason == "BILLING_DOCUMENT" for start, end, reason in excluded
        ):
            continue
        sentence = report_text[sentence_start:sentence_end]
        floor = max((start for start in page_floors if start <= sentence_start), default=0)
        section = _section_at(sections, sentence_start, floor)
        sites = find_sites(sentence)
        matches = _entity_matches(sentence)
        procedure_spans = tuple((start, end) for start, end, term, _ in matches if term.category == "PROCEDURE")
        entity_spans = tuple(sorted((start, end) for start, end, _, _ in matches))
        fragment = _starts_fragment(report_text, sentence_start)
        for entity_start, entity_end, term, surface in matches:
            entity_source = to_source(index, sentence_start + entity_start, sentence_start + entity_end)
            if any(start <= entity_source[0] and entity_source[1] <= end for start, end, _ in excluded):
                continue
            context = _assess(sentence, entity_start, entity_end, section, term.category, procedure_spans, entity_spans)
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
            if fragment and context["certainty"] == "CERTAIN":
                # Text before this lower-case line start was not read (e.g. OCR missed a line):
                # the assertion's governing words may be lost, so it needs review, not belief.
                context["certainty"] = "UNCERTAIN"
                context["cues"].append({"type": "OCR_FRAGMENT", "text": "", "start": None, "end": None})
            for cue in context["cues"]:
                if cue["start"] is not None:
                    cue["start"], cue["end"] = to_source(index, cue["start"] + sentence_start, cue["end"] + sentence_start)
                    cue["text"] = source_text[cue["start"]:cue["end"]]
            statements.append({
                "entity": term.label,
                "entity_text": source_text[entity_source[0]:entity_source[1]],
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
                "source_span": source_text[source_start:source_end][:256],
                "source_span_start": source_start,
                "source_span_end": source_end,
                "entity_start": entity_source[0],
                "entity_end": entity_source[1],
            })
    return statements


# ---------------------------------------------------------------------------
# Numeric measurements
# ---------------------------------------------------------------------------

# "~" records an approximate printed value ("LVEF ~ 68%"); it is kept as an operator, never as exact.
VALUE = r"(?P<operator><=|>=|<|>|≤|≥|~)?\s*(?P<value>(?<![\d.\-–/])-?\d+(?:\.\d+)?(?!\d|\.\d|\s*[-–]\s*\d))"
SEPARATOR = r"\s*(?:\([^)\n]{1,24}\)\s*)?(?:[:=|]|\bis\b|\bof\b|\bwas\b|\bmeasures?\b|\bmeasuring\b|\bat\b)?\s*"
# Laboratory tables print the assay method between the test name and the result
# ("HDL Cholesterol Method:Enzymatic 48 mg/dL"); OCR often misreads "Method".
# "Method: Enzymatic" between a test name and its value, including OCR-garbled forms
# ("Mothod:", "ehod Direct": a mangled word followed by a known method name), and an
# unlabelled method printed in faint type ("HbA1c ImmunoturbidimetryNGSP/IFCC 7.8 %").
METHOD_CHUNK = (
    r"(?:[ \t]*\(?\s*(?:(?:method|m[a-z][a-z ]{0,5}d)\s*[:=]\s*|[A-Za-z]{2,7}[ \t.:]+(?=(?:direct|calculated|enzymatic|kinetic|eclia|clia|hplc|biuret)\b)"
    r"|(?=[A-Za-z/()\-.]{0,40}?(?:ngsp|ifcc|idms|metr(?:y|ic)|immuno|standardi[sz]|chromatograph)[A-Za-z/()\-.]{0,40}[ \t]+(?:<=|>=|<|>|≤|≥)?\s*\d))"
    r"(?P<method>[A-Za-z][A-Za-z/()\-. ]{0,40}?)(?=[ \t]+(?:<=|>=|<|>|≤|≥)?\s*\d))?"
)
# A flag printed between the value and its unit ("7.8 * %", "175*mg/dL").
FLAG_BETWEEN = r"(?P<preflag>[ \t]*(?:\*{1,2}|↑|↓))?"
FLAG_RE = re.compile(r"[ \t]*(?:\(|\[)?[ \t]*(?P<flag>HH|LL|H|L|High|Low|Abnormal|Critical|\*{1,2}|↑|↓)[ \t]*(?:\)|\])?(?![A-Za-z0-9])")

# Printed reference intervals: ranges, one-sided limits and labelled strata. Numbers may carry
# thousands separators ("150,000 - 450,000") and a percent sign before the dash ("55 % - 90%").
_NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
REF_RANGE = re.compile(
    rf"(?P<low>{_NUM})\s*%?\s*(?:-|–|—|to)\s*(?P<high>{_NUM})"
    rf"|(?:up\s*to|upto|less\s+than|below)\s*(?P<upto>{_NUM})"
    rf"|(?P<op><=|>=|=<|=>|<|>|≤|≥)\s*(?P<bound>{_NUM})"
    rf"|(?P<above>{_NUM})\s*(?:&|and|or)?\s*(?:above|more|over)\b",
    re.IGNORECASE,
)
AGE_UNIT_AFTER = re.compile(r"[ \t]*(?P<unit>yrs?|years?|months?|mths?|mos?|weeks?|wks?|days?)\b\.?[ \t]*\)?[ \t]*:?", re.IGNORECASE)
QUALIFIER_DASH = re.compile(r"[ \t]*[-–—][ \t]*(?=up\s*to|upto|<|>|≤|≥)", re.IGNORECASE)
REFERENCE_KEYWORD = re.compile(
    r"^\s*(?:pregnancy|level|\d?\s*(?:st|nd|rd|th)?\s*trimester|male|female|adults?|children|child|infants?|neonates?|new\s*born|"
    r"adolescents?|elderly|non[-\s]*smokers?|smokers?|therapeutic\s+goal|goal|normal|desirable|borderline|optimal|"
    r"deficient|insufficient|sufficient|potential|non[-\s]*diabetic|pre[-\s]*diabetic|diabetic)\b",
    re.IGNORECASE,
)
# "Method:..." / "Specimen:..." printed in the left column under a test name, including OCR
# variants ("Mothod:", "Methoo.", "Mtod:", "Specmen:", "Spemn:"). The garbled forms need a "t"
# so stratum labels ("Male:", "Mild:") never match.
LEFT_COLUMN_META_PREFIX = r"(?:(?:m[eo]?th?[eo]?d|spe[a-z]{0,4}n|sample\s*type)\s*[:=]|m(?!on)[a-z]?t[a-z]{0,3}[:.])"
# A sub-label printed before an ESR result ("ONE HOUR READING 5 mm/hr").
READING_SUBLABEL = r"(?:(?:one|first|1\s*st|1)\s*h(?:ou)?r\s*(?:reading)?|reading)"
LEFT_COLUMN_META = re.compile(rf"^[ \t]*{LEFT_COLUMN_META_PREFIX}[ \t]*", re.IGNORECASE)
STRATUM_WORD = re.compile(
    r"(?<![A-Za-z])(?:pregnancy|\d?\s*(?:st|nd|rd|th)?\s*trimester|male|female|adults?|children|child|infants?|neonates?|new\s*born|"
    r"adolescents?|elderly|non[-\s]*smokers?|smokers?|therapeutic\s+goal|normal|desirable|borderline|optimal|"
    r"deficient|insufficient|sufficient|potential|non[-\s]*diabetic|pre[-\s]*diabetic|diabetic)\b",
    re.IGNORECASE,
)
ROW_VALUE_FIRST = re.compile(
    rf"^\s*(?:<=|>=|<|>)?\s*{_NUM}\s*\*{{0,2}}(?:\s|$)(?!\s*(?:(?:-|–|—|to)\s*\d|(?:&|and|or)?\s*(?:above|more|over)\b))",
    re.IGNORECASE,
)
VALUE_WITH_UNIT = re.compile(
    rf"{_NUM}\s*\*{{0,2}}\s*(?:mg|g|µg|μg|ug|mcg|ng|pg|mmol|µmol|μmol|umol|nmol|pmol|miu|mlu|µiu|uiu|u|iu|ml|meq)\s*/|{_NUM}\s*\*{{0,2}}\s*(?:fl|pg|%|cells|millions?|lakhs?)\b",
    re.IGNORECASE,
)
_LABEL_NOISE = re.compile(r"\d+\s*(?:st|nd|rd|th)\b|\d+\s*(?:yrs?|years?|months?|mths?|weeks?|wks?|days?)\b", re.IGNORECASE)
SEX_LABEL = re.compile(r"\b(?P<sex>female|women|woman|male|men|man)\b", re.IGNORECASE)
PREGNANCY_LABEL = re.compile(r"pregnan|trimester", re.IGNORECASE)
NORMAL_LABEL = re.compile(r"\b(?:normal|non[-\s]*diabetic|ref(?:erence)?|nr|range|interval|desirable|optimal|healthy)\b", re.IGNORECASE)
DATE_FRAGMENT = re.compile(r"[-/.]\d")
DATE_PREFIX = re.compile(r"\d[-/.]")
AGE_WORDS = (
    (re.compile(r"new\s*born|neonat", re.IGNORECASE), (0.0, 28 / 365)),
    (re.compile(r"infant", re.IGNORECASE), (0.0, 1.0)),
    (re.compile(r"adolescen", re.IGNORECASE), (13.0, 21.0)),
    (re.compile(r"p(?:a)?e?ediatric|peadiatric|child", re.IGNORECASE), (0.0, 18.0)),
    (re.compile(r"elderly|geriatric", re.IGNORECASE), (65.0, math.inf)),
    (re.compile(r"adult", re.IGNORECASE), (18.0, math.inf)),
)
_UNIT_YEARS = {"y": 1.0, "yr": 1.0, "yrs": 1.0, "year": 1.0, "years": 1.0, "month": 1 / 12, "months": 1 / 12, "mth": 1 / 12, "mths": 1 / 12,
               "mo": 1 / 12, "mos": 1 / 12, "week": 1 / 52, "weeks": 1 / 52, "wk": 1 / 52, "wks": 1 / 52, "day": 1 / 365, "days": 1 / 365}
AGE_IN_LABEL = re.compile(
    rf"(?P<op><=|>=|<|>|≤|≥)?\s*(?P<a>{_NUM})\s*(?P<ua>yrs?|years?|months?|mths?|mos?|weeks?|wks?|days?)?\s*(?:(?:-|–|to)\s*(?P<b>{_NUM})\s*(?P<ub>yrs?|years?|months?|mths?|mos?|weeks?|wks?|days?))?",
    re.IGNORECASE,
)


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _years(value: float, unit: Optional[str]) -> float:
    return value * _UNIT_YEARS.get((unit or "years").lower(), 1.0)


def _label_age(label: str) -> Optional[tuple[float, float]]:
    """Age bounds stated in a reference-interval label, in years."""
    for match in AGE_IN_LABEL.finditer(label):
        if not (match.group("ua") or match.group("ub")):
            continue
        a = _years(_num(match.group("a")), match.group("ua") or match.group("ub"))
        if match.group("b") is not None:
            return a, _years(_num(match.group("b")), match.group("ub"))
        op = match.group("op")
        if op in {">", ">=", "≥"}:
            return a, math.inf
        if op in {"<", "<=", "≤"}:
            return 0.0, a
        return a, _years(_num(match.group("a")) + 1, match.group("ua"))
    for pattern, bounds in AGE_WORDS:
        if pattern.search(label):
            return bounds
    return None


def _range_bounds(match: re.Match) -> tuple[Optional[float], Optional[float], Optional[bool], Optional[bool]]:
    if match.group("low") is not None:
        low, high = _num(match.group("low")), _num(match.group("high"))
        return (low, high, True, True) if low <= high else (None, None, None, None)
    if match.group("upto") is not None:
        return None, _num(match.group("upto")), None, True
    if match.group("above") is not None:
        return _num(match.group("above")), None, True, None
    bound, op = _num(match.group("bound")), match.group("op")
    if op in {"<", "<=", "=<", "≤"}:
        return None, bound, None, op != "<"
    return bound, None, op != ">", None


def _clean_label(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" \t\n:;,.-–—()[]")).strip()[:64]


def _reference_block(text: str, start: int, line_end: int) -> str:
    """The printed reference column for one result: the rest of its row plus continuation
    lines that hold further strata ("Female: 0.55-1.02", "55-87 yrs: 0.5-8.9", "Pregnancy:")."""
    first = text[start:line_end]
    # On a prose line the next result or sentence ends this result's reference column.
    stop = re.search(rf"(?<![\d.])\.(?=\s+[A-Za-z])|;|(?<=\s)(?:{VALUE_WITH_UNIT.pattern})", first, re.IGNORECASE)
    if stop:
        return first[:stop.start()]
    lines = [first]
    position = line_end + 1
    for _ in range(10):
        if position >= len(text):
            break
        newline = text.find("\n", position)
        end = len(text) if newline == -1 else newline
        line = text[position:end]
        first_range = REF_RANGE.search(line)
        value_unit = VALUE_WITH_UNIT.search(line)
        if not line.strip() or ROW_VALUE_FIRST.match(line):
            break
        if value_unit and (first_range is None or value_unit.start() < first_range.start()):
            break
        meta = LEFT_COLUMN_META.match(line)
        if meta:
            # The left column prints the assay and specimen under the test name, beside the
            # next strata: keep only the reference column; a line with none is skipped.
            line = _reference_column(line, meta.end())
            if line is None:
                position = end + 1
                continue
            first_range = REF_RANGE.search(line)
        if first_range is None:
            if not REFERENCE_KEYWORD.match(line):
                break
        elif re.search(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])", _LABEL_NOISE.sub(" ", line[:first_range.start()])):
            break  # a bare number before the first range starts a new result row
        lines.append(line)
        position = end + 1
    return "\n".join(lines)


def _reference_column(line: str, meta_end: int) -> Optional[str]:
    """The reference-column part of a "Method:..."/"Specimen:..." line: from the first stratum
    keyword, or from the label token joined to the first range ("1Month:5000-19000",
    ":51to60-Upto12"); None when the line holds only the assay or specimen."""
    starts = []
    keyword = STRATUM_WORD.search(line, meta_end)
    if keyword:
        starts.append(keyword.start())
    first_range = REF_RANGE.search(line, meta_end)
    if first_range:
        label = re.search(r"(?:[A-Za-z0-9-]*[:=])?[ \t]*$", line[meta_end:first_range.start()])
        starts.append(meta_end + label.start() if label else first_range.start())
    if not starts:
        return None
    return line[min(starts):]


def _parse_reference_options(block: str) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    pending: Optional[dict[str, Any]] = None
    current_sex: Optional[str] = None
    cursor = 0

    def attach_between(between: str) -> str:
        """Assign text between two ranges: a leading "-Label" closes the previous option's
        label; text ending in ':' labels the next one; anything else continues the previous."""
        first, _, rest = between.partition("\n")
        post = re.match(r"^[^A-Za-z\n]*[-–—]\s*(?P<label>[A-Za-z].*)$", first)
        pre = ""
        if post and options:
            options[-1]["label"] = _clean_label(options[-1]["label"] + " " + post.group("label"))
            first = ""
        remainder = (first + "\n" + rest).strip() if rest else first.strip()
        if remainder.endswith(":") or not options:
            pre = remainder
        elif remainder and options and options[-1]["label"]:
            options[-1]["label"] = _clean_label(options[-1]["label"] + " " + remainder)
        else:
            pre = remainder
        return pre

    for match in REF_RANGE.finditer(block):
        if match.start() < cursor:
            continue
        if DATE_FRAGMENT.match(block, match.end()) or (
                match.start() >= 2 and block[match.start()].isdigit() and DATE_PREFIX.fullmatch(block, match.start() - 2, match.start())):
            continue  # part of a printed date ("03-12-2026"), not an interval
        between = block[cursor:match.start()]
        age_unit = AGE_UNIT_AFTER.match(block, match.end())
        dash = QUALIFIER_DASH.match(block, match.end())
        is_age_qualifier = age_unit is not None and (match.group("low") is not None or match.group("op") is not None or match.group("upto") is not None)
        if is_age_qualifier or (dash is not None and (match.group("low") is not None or match.group("op") is not None)):
            pre = attach_between(between)
            low, high, _, _ = _range_bounds(match)
            unit = age_unit.group("unit") if is_age_qualifier else None
            # Strata written "17 to 50 - Upto 10" are age bands in years.
            pending = {
                "label": _clean_label(f"{pre} {match.group(0)} {unit or ''}"),
                "age": (_years(low, unit) if low is not None else 0.0, _years(high, unit) if high is not None else math.inf),
            }
            cursor = age_unit.end() if is_age_qualifier else dash.end()
            continue
        pre = attach_between(between)
        if pre.endswith(":"):
            pre = pre[:-1]
        if ":" in pre:
            pre = pre.rsplit(":", 1)[1] if pre.rsplit(":", 1)[1].strip() else pre.replace(":", " ")
        label = _clean_label(f"{pending['label'] if pending else ''} {pre}")
        low, high, low_inclusive, high_inclusive = _range_bounds(match)
        if low is None and high is None:
            cursor = match.end()
            continue
        sex_match = SEX_LABEL.search(label)
        if sex_match:
            current_sex = "female" if sex_match.group("sex").lower() in {"female", "women", "woman"} else "male"
            sex = current_sex
        elif pending and not re.search(r"[A-Za-z]{3,}", _LABEL_NOISE.sub(" ", label).replace("to", " ")):
            sex = current_sex  # "51 to 60 - Upto 12" continues the sex stratum above it
        else:
            sex = None
        options.append({
            "label": label,
            "low": low, "high": high, "low_inclusive": low_inclusive, "high_inclusive": high_inclusive,
            "text": match.group(0),
            "sex": sex,
            "age": pending["age"] if pending else None,
        })
        pending = None
        cursor = match.end()
    trailing = block[cursor:]
    tail = re.match(r"^[^A-Za-z\n]*[-–—]\s*(?P<label>[A-Za-z][^\n]*)", trailing)
    if tail and options:
        options[-1]["label"] = _clean_label(options[-1]["label"] + " " + tail.group("label"))
    for option in options:
        label = option["label"]
        option["pregnancy"] = bool(PREGNANCY_LABEL.search(label))
        if option["age"] is None:
            option["age"] = _label_age(label)
        option["normal"] = bool(NORMAL_LABEL.search(label))
        words = re.sub(r"(?i)\b(?:male|female|men|women|man|woman|adults?|children|child|infants?|neonates?|new\s*born|adolescents?|elderly|yrs?|years?|months?|weeks?|days?|to)\b", " ", _LABEL_NOISE.sub(" ", label))
        option["band"] = (not option["sex"] and option["age"] is None and not option["pregnancy"] and not option["normal"]
                          and bool(re.search(r"[A-Za-z]{3,}", words)))
    return options


def _contains(option: dict[str, Any], value: float) -> bool:
    low, high = option["low"], option["high"]
    if low is not None and (value < low or (value == low and option["low_inclusive"] is False)):
        return False
    if high is not None and (value > high or (value == high and option["high_inclusive"] is False)):
        return False
    return True


def select_reference_interval(options: list[dict[str, Any]], value: float, sex: Optional[str], age: Optional[float]) -> tuple[Optional[dict[str, Any]], str, Optional[str]]:
    """Choose the printed interval that applies to this patient, or none.

    Returns (option, selection status, documented category). Strata are chosen only from
    the documented sex and age; pregnancy strata, smoking-status strata and decision bands
    are never assumed. Without the deciding context nothing is selected (indeterminate)."""
    if not options:
        return None, "NO_INTERVAL_PRINTED", None
    containing = [option for option in options if (option["band"] or option["normal"]) and _contains(option, value)]
    category = containing[0]["label"] if len(containing) == 1 and containing[0]["label"] else None
    if len(options) == 1:
        only = options[0]
        if not only["label"] or only["normal"]:
            return only, "SINGLE_PRINTED_INTERVAL", category
        if only["band"]:
            return None, "CATEGORY_BAND_NOT_A_REFERENCE_INTERVAL", category
    if any(option["band"] for option in options) and not any(option["sex"] or option["age"] for option in options):
        normal = [option for option in options if option["normal"]]
        if len(normal) == 1:
            return normal[0], "NORMAL_BAND_PRINTED_WITH_CATEGORIES", category
        return None, "CATEGORY_BANDS_ONLY", category
    candidates = [option for option in options if not option["pregnancy"] and not option["band"]]
    if any(option["pregnancy"] for option in options) and sex != "male" and (age is None or 10 <= age <= 55):
        return None, "PREGNANCY_STATUS_NOT_DOCUMENTED", category
    if any(option["sex"] for option in candidates):
        if sex is None:
            return None, "SEX_NOT_DOCUMENTED", category
        candidates = [option for option in candidates if option["sex"] in {None, sex}]
    if any(option["age"] for option in candidates):
        if age is None:
            return None, "AGE_NOT_DOCUMENTED", category
        candidates = [option for option in candidates if option["age"] is None or option["age"][0] <= age <= option["age"][1]]
        aged = [option for option in candidates if option["age"] is not None]
        if aged and len(aged) < len(candidates) and any(option["sex"] for option in aged):
            candidates = aged
    distinct = {(option["low"], option["high"], option["low_inclusive"], option["high_inclusive"]) for option in candidates}
    if len(distinct) == 1:
        used = [part for part, present in (("SEX", any(option["sex"] for option in options)), ("AGE", any(option["age"] for option in options))) if present]
        status = ("SELECTED_BY_DOCUMENTED_" + "_AND_".join(used)) if used else "IDENTICAL_PRINTED_INTERVALS"
        return candidates[0], status, category
    return None, "AMBIGUOUS_PRINTED_STRATA" if candidates else "NO_STRATUM_MATCHES_DOCUMENTED_CONTEXT", category
LEADING_FLAG = re.compile(r"^[^\n\d]*?(?<![A-Za-z])(?P<flag>HH|LL|H|L|(?i:high|low))(?![A-Za-z])[ \t]*(?=[<>≤≥]?[ \t]*\d)")
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


def _analyte_patterns(analyte) -> tuple[re.Pattern, Optional[re.Pattern], tuple[re.Pattern, ...]]:
    """The inline pattern, a pattern for a unit printed alone on the next line
    ("eGFR 41.05 >90" / "mL/min/1.73m2") when the analyte needs a unit, and the cross-line
    patterns for a result printed on a "Method:"/"Specimen:" line beside its test name's row.

    Photographed tables drift: the result column of a three-line cell (name, method, specimen)
    lands on the line above the name ("Specimen:... 69.7 fL Male:79.0-92.2" / "Mean Corpuscular
    Volume (MCV) Female:...") or below it ("CEA" / "Method:ECLIA 1.1 ng/mL Non smokers <3").
    Only a result whose unit belongs to the analyte, on a line led by the method or specimen
    label, is paired across lines."""
    head = rf"(?P<label>\b(?:{analyte.aliases})){METHOD_CHUNK}{SEPARATOR}{VALUE}{FLAG_BETWEEN}"
    if analyte.units is None:
        return re.compile(rf"{head}(?!\s*[A-Za-z%])", re.IGNORECASE), None, ()
    inline = re.compile(rf"{head}\s*(?P<unit>{analyte.units})(?![A-Za-z0-9_])", re.IGNORECASE)
    wrapped = re.compile(rf"{head}(?P<rest>[ \t]+[^\n]{{0,32}})?[ \t]*\n[ \t]*(?P<unit>{analyte.units})[ \t]*(?=\n|$)", re.IGNORECASE)
    result = rf"^[ \t]*(?:{LEFT_COLUMN_META_PREFIX}|{READING_SUBLABEL})[^\n\d]*?(?<![A-Za-z]){VALUE}{FLAG_BETWEEN}\s*(?P<unit>{analyte.units})(?![A-Za-z0-9_])"
    above = re.compile(rf"{result}[^\n]*\n[ \t]*(?P<label>\b(?:{analyte.aliases}))", re.IGNORECASE | re.MULTILINE)
    # Up to two method/specimen lines may sit between the name and its result line.
    below = re.compile(
        rf"^[ \t]*(?P<label>\b(?:{analyte.aliases}))[^\n\d]*\n(?:[ \t]*{LEFT_COLUMN_META_PREFIX}[^\n\d]*\n){{0,2}}{result}",
        re.IGNORECASE | re.MULTILINE,
    )
    return inline, wrapped, (above, below)


ANALYTE_PATTERNS = [(analyte, *_analyte_patterns(analyte)) for analyte in ANALYTES]


def _option_record(option: dict[str, Any]) -> dict[str, Any]:
    age = option.get("age")
    return {
        "label": option["label"] or None, "text": option["text"],
        "low": option["low"], "high": option["high"],
        "low_inclusive": option["low_inclusive"], "high_inclusive": option["high_inclusive"],
        "sex": option["sex"], "pregnancy": option["pregnancy"], "category_band": option["band"],
        "age_years": None if age is None else [age[0], None if math.isinf(age[1]) else age[1]],
    }


def _reference_and_flag(
    text: str, position: int, value: float, preflag: Optional[str] = None,
    sex: Optional[str] = None, age: Optional[float] = None, line_end: Optional[int] = None,
) -> dict[str, Any]:
    """Read the documented flag and printed reference interval that follow a value.

    Every printed stratum is kept (``reference_options``); an interval is selected only
    when it applies unambiguously to the documented sex and age of this report."""
    result: dict[str, Any] = {
        "reference_low": None, "reference_high": None,
        "reference_low_inclusive": None, "reference_high_inclusive": None,
        "reference_text": None, "reference_source": None, "documented_flag": None,
        "reference_options": None, "reference_selection": None, "documented_category": None,
    }
    if preflag and preflag.strip():
        result["documented_flag"] = FLAG_NAMES.get(preflag.strip())
    cursor = position
    if line_end is None:
        newline = text.find("\n", position)
        line_end = len(text) if newline == -1 else newline
    flag = FLAG_RE.match(text, cursor, line_end)
    if flag:
        if result["documented_flag"] is None:
            result["documented_flag"] = FLAG_NAMES.get(flag.group("flag").upper(), FLAG_NAMES.get(flag.group("flag")))
        cursor = flag.end()
    block = _reference_block(text, cursor, line_end)
    # Some laboratories print the flag after the unit, at the head of the reference column
    # ("78.6 %  H 40 - 60"); it is the documented flag, not a stratum label.
    leading = LEADING_FLAG.match(block)
    if leading:
        if result["documented_flag"] is None:
            result["documented_flag"] = FLAG_NAMES.get(leading.group("flag").upper())
        block = block[:leading.start("flag")] + block[leading.end():]
    options = _parse_reference_options(block)
    if not options:
        return result
    selected, status, category = select_reference_interval(options, value, sex, age)
    result.update(
        reference_options=[_option_record(option) for option in options],
        reference_selection=status,
        documented_category=category,
    )
    if selected is not None:
        label = selected["label"]
        result.update(
            reference_low=selected["low"], reference_high=selected["high"],
            reference_low_inclusive=selected["low_inclusive"], reference_high_inclusive=selected["high_inclusive"],
            reference_text=(f"{label}: {selected['text']}" if label else selected["text"])[:64],
            reference_source="DOCUMENTED_IN_SOURCE",
        )
    return result


def _patient_context(attributes: list[dict[str, Any]], page_bounds: list[tuple[int, int]], offset: int) -> tuple[Optional[str], Optional[float]]:
    """Sex and age documented on the same page as the value, else once for the whole document."""
    page = next(((start, end) for start, end in page_bounds if start <= offset < end), None)

    def unique(name: str, field: str):
        values = {item[field] for item in attributes if item["name"] == name and item[field] is not None}
        if page is not None:
            on_page = {item[field] for item in attributes if item["name"] == name and item[field] is not None and page[0] <= item["source_span_start"] < page[1]}
            if len(on_page) == 1:
                return next(iter(on_page))
            if on_page:
                return None
        return next(iter(values)) if len(values) == 1 else None

    return unique("sex", "value_text"), unique("age_years", "value_number")


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
        "reference_options": None,
        "reference_selection": None,
        "documented_category": None,
    }
    record.update(extra)
    return record


def extract_numeric_measurements(report_text: str, page_starts: Optional[list[int]] = None) -> List[Dict[str, Any]]:
    """Extract explicit name/value/unit triples with exact offsets and no inference.

    Rules run on OCR-normalised text; offsets and quoted spans refer to ``report_text``.
    Printed reference strata are resolved against the sex and age documented on the same
    page (else once in the document)."""
    source_text = report_text
    report_text, index = normalise(source_text)
    measurements: List[Dict[str, Any]] = []
    claimed: list[tuple[int, int]] = []
    attributes = extract_documented_attributes(report_text)
    normalised_starts = [to_normalised(index, start) for start in (page_starts or [0])]
    page_bounds = [(start, normalised_starts[number + 1] if number + 1 < len(normalised_starts) else len(report_text) + 1)
                   for number, start in enumerate(normalised_starts)]

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

    for analyte, inline, wrapped, cross_line in ANALYTE_PATTERNS:
        forbid = re.compile(analyte.forbid_prefix, re.IGNORECASE) if analyte.forbid_prefix else None
        candidates = [(match, "inline") for match in inline.finditer(report_text)]
        if wrapped is not None:
            candidates += [(match, "wrapped") for match in wrapped.finditer(report_text)]
        for pattern in cross_line:
            for match in pattern.finditer(report_text):
                # A name row that carries its own result is not paired with a neighbouring line.
                if not (inline.match(report_text, match.start("label")) or wrapped.match(report_text, match.start("label"))):
                    candidates.append((match, "cross_line"))
        for match, layout in sorted(candidates, key=lambda item: item[0].start()):
            # The quoted span runs from the test name or the result, whichever is first.
            span_start = min(match.start("label"), match.start("operator") if match.group("operator") else match.start("value"))
            if not free(span_start, match.end()):
                continue
            if forbid and forbid.search(report_text, max(0, match.start("label") - 40), match.start("label")):
                continue
            raw_value = match.group("value")
            raw_unit = match.group("unit") if analyte.units is not None else ""
            unit = normalise_unit(raw_unit) if analyte.units is not None else analyte.unitless_unit
            code = loinc_for(analyte, unit)
            value = float(raw_value)
            sex, age = _patient_context(attributes, page_bounds, match.start())
            if layout == "wrapped":
                # The interval sits between the value and the wrapped unit line.
                reference_start = match.end("preflag") if match.group("preflag") else match.end("value")
                reference = _reference_and_flag(report_text, reference_start, value, match.group("preflag"), sex, age,
                                                line_end=report_text.rfind("\n", 0, match.start("unit")))
            elif layout == "cross_line":
                reference = _reference_and_flag(report_text, match.end("unit"), value, match.group("preflag"), sex, age)
            else:
                reference = _reference_and_flag(report_text, match.end(), value, match.group("preflag"), sex, age)
            method = (match.group("method") or "").strip() if layout != "cross_line" else ""
            extra = {"laboratory_method": method[:128]} if method else {}
            measurements.append(_measurement(
                analyte.name, analyte.display, value, unit, raw_value, raw_unit,
                span_start, match.end(), report_text,
                result_operator=_result_operator(match.group("operator")),
                canonical_code=code, code_system=LOINC if code else None, code_mapping_status=LOINC_MAPPING_STATUS if code else None,
                anatomy_system=analyte.system, association=analyte.association,
                **reference, **extra,
            ))
            claimed.append((span_start, match.end()))

    for item in measurements:
        start, end = to_source(index, item["source_span_start"], item["source_span_end"])
        item.update(source_span_start=start, source_span_end=end, source_span=source_text[start:end][:256])
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
    r"|\bage(?:\s*(?:/|&|and)\s*(?:sex|gender))?\s*[:=]?\s*(?P<age2>\d{1,3})(?!\d)"
    r"|\(\s*[mf]\s*,\s*(?P<age3>\d{1,3})\s*y(?:rs?|ears?)?\s*\)"
    # Years-months-days ages printed by laboratory systems ("61 Y 4 M 2 D", "52 Yr 3 M", "52Yr3M").
    r"|\b(?P<age4>\d{1,3})\s*(?:y|yrs?|years?)\s*\d{1,2}\s*m(?:onths?)?(?:\s*\d{1,2}\s*d(?:ays?)?)?\b",
    re.IGNORECASE,
)
SEX_RE = re.compile(
    r"\b(?:sex|gender)\s*[:=]?\s*(?P<sex>male|female|m|f)\b"
    r"|\bage(?:\s*/\s*sex)?\s*[:=]?\s*\d{1,3}\s*(?:y(?:ears?|rs?)?)?\s*/\s*(?P<sex2>m|f|male|female)\b"
    r"|\b\d{1,3}\s*[-\s]?(?:years?|yrs?|y/o|yo)[-\s]*(?:old)?\s+(?P<sex3>male|female|man|woman|boy|girl)\b"
    r"|\(\s*(?P<sex4>[mf])\s*,\s*\d{1,3}\s*y"
    r"|\bage\s*(?:/|&|and)\s*(?:sex|gender)\s*[:=]?[^\n]{0,24}?\b(?P<sex5>male|female)\b"
    r"|\b(?:gender|sex)\s*/\s*age\s*[:=]?\s*(?P<sex6>male|female)\b",
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
        raw = match.group("age") or match.group("age2") or match.group("age3") or match.group("age4")
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
        raw = (match.group("sex") or match.group("sex2") or match.group("sex3") or match.group("sex4") or match.group("sex5") or match.group("sex6")).lower()
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
            if line.get("gap_before"):
                safe_text_lines.append("")  # ocr.LOST_LINE_GAP: a line was not read here
                line_cursor += 1
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
    from app.services.hl7_import import hl7_measurements

    statements = extract_clinical_statements(sanitized_text, page_starts)
    excluded_segments = nonclinical_ranges(sanitized_text, page_starts)
    structured = fhir_measurements(report_path, sanitized_text)
    if structured is None:
        structured = hl7_measurements(report_path, sanitized_text)
    measurements = structured if structured is not None else extract_numeric_measurements(sanitized_text, page_starts)
    measurement_context = extract_measurement_context(sanitized_text)
    for measurement in measurements:
        for key, value in measurement_context.items():
            # A method printed on the result row takes precedence over a document-wide one.
            if measurement.get(key) in (None, "", "NOT_DOCUMENTED"):
                measurement[key] = value
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
            "nonclinical_segments_excluded": {
                reason: sum(1 for *_, kind in excluded_segments if kind == reason)
                for reason in sorted({kind for *_, kind in excluded_segments})
            },
            "ocr_normalisation": "glued-word segmentation and line-wrap rejoining; spans quote the source text",
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
