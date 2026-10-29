"""OCR-aware text normalisation with an exact offset map back to the source text.

Phone photographs of printed reports often lose the spaces between words
("Nopleural effusion orpneumothorax", "suspiciouspulmonary masslesion"). Rules
match whole words, so glued tokens hide negation cues and finding terms.

``normalise`` inserts single spaces inside alphabetic runs only when the run is
not itself a known word and splits completely into known words: medical terms
taken from the terminology plus common English words (wordninja's frequency
list). Nothing else changes. The returned offset map sends every normalised
character back to the source, so evidence spans always quote the text exactly
as it was read from the page.
"""

from __future__ import annotations

import bisect
import math
import re
from functools import lru_cache
from typing import Optional

ALPHA_RUN = re.compile(r"[A-Za-z]{5,}")
# A word glued to a number ("stroke6yearsback", "InAugust2023") hides it from word-boundary
# rules. Only runs of four lower-case letters are split off, so D3, B12, HbA1c, eGFR, C5 and
# units after a value (5mg, 80mmHg) stay as read.
DIGIT_JOIN = re.compile(r"(?<=[a-z]{4})(?=\d)|(?<=\d)(?=[a-z]{4})")
# A lone capital ending a run after four lower-case letters is its own word ("VitaminD3",
# "HepatitisB"); otherwise the segmenter reads "VitaminD" as "Vita minD". pH, mmHg, eGFR and
# HbA1c do not qualify.
CAPITAL_TAIL = re.compile(r"(?<=[a-z]{4})(?=[A-Z](?![A-Za-z]))")
COMMON_RANK_LIMIT = 40_000  # pieces must be among the most frequent English words
WHOLE_WORD_RANK_LIMIT = 200_000  # a run that is itself a reasonably common word is kept
# Pieces of three letters or fewer must be function words: a domain prefix plus a short
# leftover ("spondylo" + "tic") is not a word boundary.
SHORT_WORDS = frozenset({
    "no", "or", "of", "in", "is", "to", "at", "on", "an", "as", "by", "be", "up", "it", "if", "so", "do",
    "mm", "cm", "a", "i", "and", "the", "for", "not", "are", "was", "has", "had", "may", "can", "but", "nor",
    "few", "all", "any", "one", "two", "per", "due", "low", "mid", "end", "top", "its", "how", "see", "new",
    "out", "off", "via", "yet", "now", "too", "non", "six", "ten",
})

# Medical vocabulary the general English list lacks or would split ("hydron ep hro s is").
EXTRA_DOMAIN_WORDS = """
abdomen abdominal adenopathy angulation anastomotic aspiration attenuation bilateral biliary bilirubin
bronchi bronchiectasis calcification calculi calculus cardiac cardiomegaly cholesterol cirrhosis colonic
consolidation corticomedullary creatinine cystic diaphragm diaphragmatic dysplasia echotexture echogenicity
effusion eosinophils erythrocytes fibrotic gallbladder glycosylated granulomas haemoglobin hemoglobin
haematocrit hematocrit hemidiaphragm hepatic honeycombing hydronephrosis hypodense hypoechoic hyperechoic
hysterectomy ileostomy interstitial intrahepatic kyphotic lymph lymphocytes malignancy mediastinal medullary
monocytes neoplastic neutrophils nephritis parenchyma parenchymal paratracheal pericardial phrenic pleural
pneumothorax portal pretracheal pyelonephritis radicals reticular retrosternal splenic subcentimetric
subpleural thyroid trachea triglycerides ultrasonography vertebral hdl ldl vldl tsh egfr crp esr mcv mch
mchc rdw hba1c fnac cect hpe ihc cmv spondylotic spondylosis osteophytes desiccation myelomalacia
hyperintense hypointense ischaemic ischemic diastolic systolic regurgitation vegetation malformation
invagination echocardiography laryngoscopy endoscopy colonoscopy anastomotic ileostomy cryptitis
haemogram hemogram neutrophils lymphocytes eosinophils basophils monocytes platelet corpuscular
""".split()


@lru_cache(maxsize=1)
def _vocabulary() -> tuple[dict[str, float], frozenset[str], float, float]:
    import wordninja
    from app.services.terminology import ANALYTES, ENTITY_TERMS, SITE_TERMS

    model = wordninja.DEFAULT_LANGUAGE_MODEL
    wordcost: dict[str, float] = model._wordcost
    size = len(wordcost)
    common_cost = math.log(COMMON_RANK_LIMIT * math.log(size))
    whole_cost = math.log(WHOLE_WORD_RANK_LIMIT * math.log(size))
    domain = set(EXTRA_DOMAIN_WORDS)
    # Literal words of the terminology patterns, with optional letters both dropped and kept
    # ("ha?emoglobin" gives hemoglobin and haemoglobin, "effusions?" gives both numbers).
    sources = [term.pattern for term in ENTITY_TERMS] + [term.pattern for term in SITE_TERMS] + [analyte.aliases for analyte in ANALYTES]
    for source in sources:
        lower = source.lower()
        for variant in (re.sub(r"([a-z])\?", "", lower), re.sub(r"([a-z])\?", r"\1", lower)):
            domain.update(re.findall(r"(?<!\\)[a-z]{4,}", variant))
    return wordcost, frozenset(domain), common_cost, whole_cost


def _segment(token: str) -> Optional[list[str]]:
    """Split one alphabetic run into known words, or None to leave it untouched."""
    wordcost, domain, common_cost, whole_cost = _vocabulary()
    lower = token.lower()
    if lower in domain or wordcost.get(lower, math.inf) <= whole_cost:
        return None

    def cost(word: str) -> float:
        if word in domain:
            return 0.5
        if len(word) <= 3 and word not in SHORT_WORDS:
            return math.inf
        value = wordcost.get(word, math.inf)
        return value if value <= common_cost else math.inf

    best = [0.0] + [math.inf] * len(lower)
    back = [0] * (len(lower) + 1)
    for end in range(1, len(lower) + 1):
        for start in range(max(0, end - 24), end):
            candidate = best[start] + cost(lower[start:end])
            if candidate < best[end]:
                best[end], back[end] = candidate, start
    if math.isinf(best[-1]):
        return None
    pieces: list[str] = []
    end = len(lower)
    while end > 0:
        start = back[end]
        pieces.append(token[start:end])
        end = start
    pieces.reverse()
    return pieces if len(pieces) > 1 else None


# Clinical shorthand glued to its neighbours ("tor/oright" = "to r/o right").
SHORTHAND = re.compile(r"(?i)r/o|s/o|h/o|c/o|s/p")


def _shorthand_insertions(text: str) -> set[int]:
    points: set[int] = set()
    for match in SHORTHAND.finditer(text):
        start, end = match.start(), match.end()
        if start and text[start - 1].isalpha():
            # Only the glued word "to" may precede it ("tor/o"); "other/order" is left alone.
            if text[max(0, start - 2):start].lower() != "to" or (start >= 3 and text[start - 3].isalpha()):
                continue
            points.add(start)
        if end < len(text) and text[end].isalpha():
            points.add(end)
    return points


def normalise(text: str) -> tuple[str, Optional[list[int]]]:
    """Return (normalised text, offset map). The map is None when nothing changed;
    otherwise ``index[i]`` is the source offset of normalised character ``i`` and the
    final element is ``len(text)``. Inserted spaces map to the following character."""
    insertions: set[int] = _shorthand_insertions(text) | {match.start() for pattern in (DIGIT_JOIN, CAPITAL_TAIL) for match in pattern.finditer(text)}
    runs = []
    for match in ALPHA_RUN.finditer(text):
        # A run split by a shorthand insertion ("S/Ploopileostomy") is segmented after it.
        cuts = [match.start()] + sorted(point for point in insertions if match.start() < point < match.end()) + [match.end()]
        runs += [(start, end) for start, end in zip(cuts, cuts[1:]) if end - start >= 5]
    for start, end in runs:
        pieces = _segment(text[start:end])
        if pieces is None:
            continue
        position = start
        for piece in pieces[:-1]:
            position += len(piece)
            insertions.add(position)
    if not insertions:
        return text, None
    parts: list[str] = []
    index: list[int] = []
    cursor = 0
    for position in sorted(insertions):
        parts.append(text[cursor:position])
        index.extend(range(cursor, position))
        parts.append(" ")
        index.append(position)
        cursor = position
    parts.append(text[cursor:])
    index.extend(range(cursor, len(text)))
    index.append(len(text))
    return "".join(parts), index


def to_normalised(index: Optional[list[int]], offset: int) -> int:
    """Map a source offset to the first normalised offset at or after it."""
    if index is None:
        return offset
    return bisect.bisect_left(index, offset)


def to_source(index: Optional[list[int]], start: int, end: int) -> tuple[int, int]:
    """Map a normalised [start, end) span back to source offsets."""
    if index is None:
        return start, end
    if end <= start:
        return index[start], index[start]
    return index[start], index[end - 1] + 1
