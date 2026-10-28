"""HL7 v2 observation-result (ORU) import.

Only result content is read: OBR (the ordered service), OBX (observations) and NTE (comments).
Segments that identify or locate the patient, visit, next of kin, insurer or ordering staff
(PID, PD1, NK1, PV1, PV2, ORC, IN1, GT1, ...) and the sending/receiving fields of MSH are never
rendered, so they cannot reach the stored text, the extraction rules or the database.

As for FHIR, each observation is rendered as one canonical text line, and every measurement's
source span is its line. Codes are the ones documented in OBX-3; MedTwin does not recode them.
Results the sender marked as cannot-be-obtained, deleted or wrong (OBX-11 X/D/W) are rendered
with their status but produce no measurement.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from app.services.fhir_import import _LOINC_TO_ANALYTE, ucum_unit
from app.services.terminology import LOINC

HL7_EXTENSIONS = {".hl7"}
SEGMENT_SPLIT = re.compile(r"\r\n|\r|\n")
RESULT_SEGMENTS = {"OBR", "OBX", "NTE"}
WITHDRAWN_STATUSES = {"X": "cannot be obtained", "D": "deleted", "W": "wrong result"}
STATUS_TEXT = {"F": "final", "C": "corrected", "P": "preliminary", "R": "not verified", "I": "pending", "S": "partial", "A": "amended"}
ABNORMAL_FLAGS = {"H": "HIGH", "HH": "CRITICAL_HIGH", "L": "LOW", "LL": "CRITICAL_LOW", "A": "ABNORMAL", "AA": "CRITICAL",
                  ">": "ABNORMAL", "<": "ABNORMAL", "N": None}
NUMERIC = re.compile(r"^(?P<op><=|>=|<|>)?\s*(?P<value>[-+]?\d+(?:\.\d+)?)$")
REFERENCE = re.compile(
    r"^\s*(?:(?P<low>[-+]?\d+(?:\.\d+)?)\s*-\s*(?P<high>[-+]?\d+(?:\.\d+)?)|(?P<op><=|>=|<|>)\s*(?P<bound>[-+]?\d+(?:\.\d+)?))\s*$"
)
HL7_DATE = re.compile(r"^(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})")


class Hl7Delimiters:
    def __init__(self, msh: str):
        self.field = msh[3]
        encoding = msh[4:8] if len(msh) >= 8 else "^~\\&"
        self.component, self.repetition, self.escape, self.subcomponent = (list(encoding) + ["^", "~", "\\", "&"])[:4]


def is_hl7(content: bytes) -> bool:
    head = content.lstrip(b"\xef\xbb\xbf\r\n\t ")[:3]
    return head in (b"MSH", b"FHS", b"BHS")


def _unescape(value: str, delimiters: Hl7Delimiters) -> str:
    escape = re.escape(delimiters.escape)

    def replace(match: re.Match) -> str:
        code = match.group(1)
        mapping = {"F": delimiters.field, "S": delimiters.component, "T": delimiters.subcomponent,
                   "R": delimiters.repetition, "E": delimiters.escape, ".br": "\n"}
        if code in mapping:
            return mapping[code]
        if code.startswith("X") and re.fullmatch(r"X(?:[0-9A-Fa-f]{2})+", code):
            try:
                return bytes.fromhex(code[1:]).decode("utf-8")
            except UnicodeDecodeError:
                return ""
        return ""  # unsupported formatting escapes (\H\, \N\, \.sp\, ...) carry no text

    return re.sub(rf"{escape}(\.?[A-Za-z]+[0-9A-Fa-f]*){escape}", replace, value)


def _segments(text: str) -> list[tuple[Hl7Delimiters, str, list[str]]]:
    """(delimiters, segment id, fields) for every segment, fields indexed as in the standard (field 1 at [1])."""
    result: list[tuple[Hl7Delimiters, str, list[str]]] = []
    delimiters: Optional[Hl7Delimiters] = None
    for raw in SEGMENT_SPLIT.split(text.lstrip("﻿")):
        segment = raw.strip("\x0b\x1c ")
        if len(segment) < 3:
            continue
        if segment.startswith("MSH") and len(segment) >= 4:
            delimiters = Hl7Delimiters(segment)
            # MSH-1 is the field separator itself, so MSH fields are shifted by one.
            result.append((delimiters, "MSH", ["MSH", delimiters.field] + segment[4:].split(delimiters.field)))
            continue
        if delimiters is None:
            continue
        fields = segment.split(delimiters.field)
        result.append((delimiters, fields[0], fields))
    return result


def _field(fields: list[str], number: int) -> str:
    return fields[number] if len(fields) > number else ""


def _components(value: str, delimiters: Hl7Delimiters) -> list[str]:
    first = value.split(delimiters.repetition)[0]
    return [_unescape(part.split(delimiters.subcomponent)[0], delimiters).strip() for part in first.split(delimiters.component)]


def _coded(value: str, delimiters: Hl7Delimiters) -> tuple[str, Optional[str], Optional[str]]:
    """(display, code, system) from a CE/CWE field, preferring a LOINC triplet (primary or alternate)."""
    parts = _components(value, delimiters) + [""] * 6
    triplets = [(parts[0], parts[1], parts[2]), (parts[3], parts[4], parts[5])]
    chosen = next((triplet for triplet in triplets if triplet[2].upper() in {"LN", "LOINC"} and triplet[0]), triplets[0])
    code, text, system = chosen
    display = text or parts[1] or code or "Unnamed observation"
    system_uri = LOINC if system.upper() in {"LN", "LOINC"} else (system or None)
    return display, code or None, system_uri


def _date(value: str) -> Optional[str]:
    match = HL7_DATE.match(value.strip())
    return f"{match.group('y')}-{match.group('m')}-{match.group('d')}" if match else None


def _reference(value: str) -> tuple[Optional[float], Optional[float], Optional[bool], Optional[bool]]:
    match = REFERENCE.match(value)
    if not match:
        return None, None, None, None
    if match.group("low") is not None:
        low, high = float(match.group("low")), float(match.group("high"))
        return (low, high, True, True) if low <= high else (None, None, None, None)
    bound, op = float(match.group("bound")), match.group("op")
    if op in {"<", "<="}:
        return None, bound, None, op == "<="
    return bound, None, op == ">=", None


def _numeric(value_type: str, value: str, delimiters: Hl7Delimiters) -> Optional[tuple[str, float, str]]:
    """(operator, value, raw value) for NM and single-number SN results; ranges and ratios are not numbers."""
    if value_type == "SN":
        parts = _components(value, delimiters) + ["", "", "", ""]
        comparator, number, separator, second = parts[:4]
        if separator or second or not NUMERIC.match(number or ""):
            return None
        operator = comparator if comparator in {"<", ">", "<=", ">="} else "="
        return operator, float(number), f"{comparator}{number}"
    if value_type not in {"NM", ""}:
        return None
    raw = _unescape(value.split(delimiters.repetition)[0], delimiters).strip()
    match = NUMERIC.match(raw)
    if not match:
        return None
    return match.group("op") or "=", float(match.group("value")), raw


def _observation_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    service_date: Optional[str] = None
    for delimiters, segment_id, fields in _segments(text):
        if segment_id == "OBR":
            service_date = _date(_field(fields, 7)) or _date(_field(fields, 22))
            if any(_components(_field(fields, 4), delimiters)):
                service = _coded(_field(fields, 4), delimiters)[0]
                rows.append({"line": f"Ordered service {service}" + (f" collected {service_date}" if service_date else ""), "value": None})
        elif segment_id == "NTE":
            comment = "\n".join(_unescape(_field(fields, 3), delimiters).split(delimiters.repetition)).strip()
            if comment:
                rows.append({"line": f"Comment: {comment}", "value": None})
        elif segment_id == "OBX":
            value_type = _field(fields, 2).strip().upper()
            display, code, system = _coded(_field(fields, 3), delimiters)
            raw_value = _field(fields, 5)
            unit_parts = _components(_field(fields, 6), delimiters)
            raw_unit = unit_parts[0] or (unit_parts[1] if len(unit_parts) > 1 else "")
            reference_text = _unescape(_field(fields, 7), delimiters).strip()
            flag = _components(_field(fields, 8), delimiters)[0].upper()
            status = _field(fields, 11).strip().upper()
            effective = _date(_field(fields, 14)) or service_date
            code_text = f" [{code}]" if code else ""
            status_text = f" status {WITHDRAWN_STATUSES.get(status) or STATUS_TEXT.get(status)}" if status and status != "F" else ""
            numeric = _numeric(value_type, raw_value, delimiters)
            if numeric is not None:
                operator, value, shown = numeric
                unit = ucum_unit(raw_unit)
                line = f"Observation {display}{code_text}: {shown} {unit}".rstrip()
                if reference_text:
                    line += f" (reference {reference_text})"
                if effective:
                    line += f" effective {effective}"
                if flag:
                    line += f" interpretation {flag}"
                rows.append({
                    "line": line + status_text, "display": display, "code": code, "system": system, "value": value,
                    "raw_value": shown, "raw_unit": raw_unit, "unit": unit, "operator": operator,
                    "reference": _reference(reference_text), "reference_text": reference_text or None,
                    "flag": flag, "effective": effective, "withdrawn": status in WITHDRAWN_STATUSES,
                })
            else:
                if value_type in {"CE", "CWE", "CNE"}:
                    shown_text = _coded(raw_value, delimiters)[0] if raw_value else ""
                else:
                    shown_text = "\n".join(_unescape(raw_value, delimiters).split(delimiters.repetition)).strip()
                if shown_text:
                    rows.append({"line": f"Observation {display}{code_text}: {shown_text}{status_text}", "value": None})
    return rows


def render_hl7_text(content: bytes) -> Optional[str]:
    """The result content of an HL7 v2 message as text, or None when the bytes are not HL7 v2."""
    if not is_hl7(content):
        return None
    text = content.decode("utf-8", errors="replace")
    segments = _segments(text)
    message_types = {"^".join(_components(_field(fields, 9), delimiters)[:2]) for delimiters, segment_id, fields in segments if segment_id == "MSH"}
    lines = [f"HL7 v2 {', '.join(sorted(kind for kind in message_types if kind)) or 'message'} import"]
    lines += [row["line"] for row in _observation_rows(text)]
    return "\n".join(lines)


def hl7_measurements(report_path: Path, sanitized_text: str) -> Optional[list[dict[str, Any]]]:
    """Measurements from an HL7 v2 upload, or None when the file is not HL7 v2."""
    if report_path.suffix.lower() not in HL7_EXTENSIONS:
        return None
    content = report_path.read_bytes()
    if not is_hl7(content):
        return None
    measurements: list[dict[str, Any]] = []
    cursor = 0
    for row in _observation_rows(content.decode("utf-8", errors="replace")):
        if row.get("value") is None:
            continue
        start = sanitized_text.find(row["line"], cursor)
        if start == -1 or row["withdrawn"]:
            continue
        end = start + len(row["line"])
        cursor = end
        analyte = _LOINC_TO_ANALYTE.get(row["code"]) if row.get("system") == LOINC else None
        if analyte:
            name, system_name = analyte.name, analyte.system
        else:
            name = "hl7_" + re.sub(r"[^a-z0-9]+", "_", (row.get("code") or row["display"]).lower()).strip("_")
            system_name = None
        low, high, low_inclusive, high_inclusive = row["reference"]
        documented = low is not None or high is not None
        measurements.append({
            "name": name[:128],
            "display_name": row["display"][:128],
            "value": row["value"],
            "result_operator": row["operator"],
            "unit": row["unit"][:32],
            "raw_value": row["raw_value"][:64],
            "raw_unit": row["raw_unit"][:32],
            "source_span": row["line"][:256],
            "source_span_start": start,
            "source_span_end": end,
            "canonical_code": row.get("code"),
            "code_system": row.get("system"),
            "code_mapping_status": "SOURCE_DOCUMENTED_CODE" if row.get("code") else None,
            "anatomy_system": system_name,
            "association": analyte.association if analyte else None,
            "conversion_status": "AS_DOCUMENTED",
            "reference_low": low,
            "reference_high": high,
            "reference_low_inclusive": low_inclusive,
            "reference_high_inclusive": high_inclusive,
            "reference_text": row["reference_text"][:64] if row["reference_text"] else None,
            "reference_source": "DOCUMENTED_IN_SOURCE" if documented else None,
            "documented_flag": ABNORMAL_FLAGS.get(row["flag"]) if row["flag"] else None,
            "documented_date": row.get("effective"),
            "extraction_method": "HL7_V2_OBX_IMPORT",
        })
    return measurements
