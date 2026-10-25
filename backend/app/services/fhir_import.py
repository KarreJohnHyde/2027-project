"""FHIR R4 Observation / DiagnosticReport import.

A FHIR JSON upload is rendered into one canonical text line per Observation
(or Observation component). Measurements are taken from the structured
resource, and each one's source span is its rendered line, so the
'exact source text' invariant holds for structured imports as well.
Codes are the ones documented in the resource; MedTwin does not recode them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from app.services.terminology import ANALYTES, LOINC, normalise_unit

FHIR_RESOURCE_TYPES = {"Bundle", "Observation", "DiagnosticReport"}
_UCUM_UNITS = {"mm[hg]": "mmHg", "cel": "°C", "[degf]": "°F", "/min": "/min", "{beats}/min": "bpm", "kg/m2": "kg/m²", "10*9/l": "10^9/L", "10*12/l": "10^12/L"}
_LOINC_TO_ANALYTE = {code: analyte for analyte in ANALYTES for code in analyte.loinc.values()}
_LOINC_TO_ANALYTE.update({"8480-6": None, "8462-4": None})
_INTERPRETATION = {"H": "HIGH", "HH": "CRITICAL_HIGH", "L": "LOW", "LL": "CRITICAL_LOW", "A": "ABNORMAL", "AA": "CRITICAL", "N": None}


def _load(content: bytes) -> Optional[dict]:
    try:
        data = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and data.get("resourceType") in FHIR_RESOURCE_TYPES:
        return data
    return None


def _resources(data: dict) -> list[dict]:
    if data.get("resourceType") == "Bundle":
        return [entry.get("resource") for entry in data.get("entry", []) if isinstance(entry, dict) and isinstance(entry.get("resource"), dict)]
    return [data]


def _coding(concept: Optional[dict]) -> tuple[str, Optional[str], Optional[str]]:
    concept = concept or {}
    codings = concept.get("coding") or []
    loinc = next((coding for coding in codings if coding.get("system") == LOINC), None)
    first = loinc or (codings[0] if codings else {})
    display = concept.get("text") or first.get("display") or first.get("code") or "Unnamed observation"
    return str(display), first.get("code"), first.get("system")


def _effective(resource: dict) -> Optional[str]:
    value = resource.get("effectiveDateTime") or (resource.get("effectivePeriod") or {}).get("start") or resource.get("issued")
    if isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}", value):
        return value[:10]
    return None


def _unit(quantity: dict) -> str:
    raw = str(quantity.get("code") or quantity.get("unit") or "")
    return _UCUM_UNITS.get(raw.lower(), normalise_unit(raw)) if raw else ""


def _observation_lines(resource: dict) -> list[dict[str, Any]]:
    display, code, system = _coding(resource.get("code"))
    effective = _effective(resource)
    rows: list[dict[str, Any]] = []
    parts = [(display, code, system, resource)]
    for component in resource.get("component") or []:
        component_display, component_code, component_system = _coding(component.get("code"))
        parts.append((component_display, component_code, component_system, component))
    for part_display, part_code, part_system, holder in parts:
        quantity = holder.get("valueQuantity")
        reference = (holder.get("referenceRange") or [{}])[0]
        interpretation = ((holder.get("interpretation") or [{}])[0].get("coding") or [{}])[0].get("code")
        code_text = f" [{part_code}]" if part_code else ""
        if isinstance(quantity, dict) and isinstance(quantity.get("value"), (int, float)):
            unit = _unit(quantity)
            comparator = quantity.get("comparator") if quantity.get("comparator") in {"<", "<=", ">", ">="} else "="
            shown_comparator = "" if comparator == "=" else comparator
            line = f"Observation {part_display}{code_text}: {shown_comparator}{quantity['value']} {unit}".rstrip()
            low = (reference.get("low") or {}).get("value")
            high = (reference.get("high") or {}).get("value")
            if low is not None or high is not None:
                line += f" (reference {low if low is not None else ''}-{high if high is not None else ''})"
            if effective:
                line += f" effective {effective}"
            if interpretation:
                line += f" interpretation {interpretation}"
            rows.append({
                "line": line, "display": part_display, "code": part_code, "system": part_system, "value": float(quantity["value"]),
                "raw_value": str(quantity["value"]), "raw_unit": str(quantity.get("unit") or quantity.get("code") or ""), "unit": unit,
                "operator": comparator, "low": low, "high": high, "interpretation": interpretation, "effective": effective,
            })
        elif holder is resource and not resource.get("component"):
            value = holder.get("valueString")
            if not value and holder.get("valueCodeableConcept"):
                value = _coding(holder.get("valueCodeableConcept"))[0]
            if value:
                rows.append({"line": f"Observation {part_display}{code_text}: {value}", "display": part_display, "value": None})
    return rows


def render_fhir_text(content: bytes) -> Optional[str]:
    data = _load(content)
    if data is None:
        return None
    lines = [f"FHIR {data.get('resourceType')} import"]
    for resource in _resources(data):
        kind = resource.get("resourceType")
        if kind == "Observation":
            lines.extend(row["line"] for row in _observation_lines(resource))
        elif kind == "DiagnosticReport":
            display, code, _ = _coding(resource.get("code"))
            lines.append(f"DiagnosticReport {display}{f' [{code}]' if code else ''}")
            if resource.get("conclusion"):
                lines.append(f"CONCLUSION: {resource['conclusion']}")
    return "\n".join(lines)


def fhir_measurements(report_path: Path, sanitized_text: str) -> Optional[list[dict[str, Any]]]:
    """Measurements from a FHIR upload, or None when the file is not FHIR."""
    if report_path.suffix.lower() != ".json":
        return None
    data = _load(report_path.read_bytes())
    if data is None:
        return None
    measurements: list[dict[str, Any]] = []
    cursor = 0
    for resource in _resources(data):
        if resource.get("resourceType") != "Observation":
            continue
        for row in _observation_lines(resource):
            start = sanitized_text.find(row["line"], cursor)
            if start == -1 or row.get("value") is None:
                continue
            end = start + len(row["line"])
            cursor = end
            analyte = _LOINC_TO_ANALYTE.get(row["code"]) if row.get("system") == LOINC else None
            unit = row["unit"]
            if analyte and analyte.name == "heart_rate" and unit == "/min":
                unit = "bpm"
            if row.get("code") == "8480-6":
                name, system_name = "systolic_blood_pressure", "heart"
            elif row.get("code") == "8462-4":
                name, system_name = "diastolic_blood_pressure", "heart"
            elif analyte:
                name, system_name = analyte.name, analyte.system
            else:
                name = "fhir_" + re.sub(r"[^a-z0-9]+", "_", (row.get("code") or row["display"]).lower()).strip("_")
                system_name = None
            measurements.append({
                "name": name[:128],
                "display_name": row["display"][:128],
                "value": row["value"],
                "result_operator": row.get("operator", "="),
                "unit": unit[:32],
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
                "reference_low": float(row["low"]) if row.get("low") is not None else None,
                "reference_high": float(row["high"]) if row.get("high") is not None else None,
                "reference_text": f"{row.get('low', '')}-{row.get('high', '')}" if row.get("low") is not None or row.get("high") is not None else None,
                "reference_source": "DOCUMENTED_IN_SOURCE" if row.get("low") is not None or row.get("high") is not None else None,
                "documented_flag": _INTERPRETATION.get(str(row.get("interpretation") or "").upper()),
                "documented_date": row.get("effective"),
                "extraction_method": "FHIR_OBSERVATION_IMPORT",
            })
    return measurements
