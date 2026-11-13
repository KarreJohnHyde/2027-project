"""Synthetic regression controls for actual review-workflow OCR row failures."""
import pytest

from app.services.nlp_processor import extract_numeric_measurements
from app.services.ocr_text import normalise, to_normalised, to_source


@pytest.mark.parametrize("source,name,value,unit,low,high", [
    ("FastingGlucose112mg/dL70-100H", "glucose", 112., "mg/dL", 70., 100.),
    ("SerumCreatinine1.2mg/dL0.6-1.1H", "creatinine", 1.2, "mg/dL", .6, 1.1),
    ("Hemoglobin12.8g/dL12-16", "hemoglobin", 12.8, "g/dL", 12., 16.),
    ("Glucose5.2mmol/L3.5-6.0", "glucose", 5.2, "mmol/L", 3.5, 6.),
    ("TotalLeucocyteCount6.810^3/uL4.0-11.0", "white_blood_cell_count", 6.8, "10^9/L", 4., 11.),
    ("PlateletCount22510^3/uL150-410", "platelet_count", 225., "10^9/L", 150., 410.),
    ("Urea38mg/dL15-40", "urea", 38., "mg/dL", 15., 40.),
])
def test_catalogued_unit_glued_to_printed_reference_recovers_exact_source(source, name, value, unit, low, high):
    found = extract_numeric_measurements(source)
    assert len(found) == 1
    item = found[0]
    assert (item["name"], item["value"], item["unit"]) == (name, value, unit)
    assert item["reference_low"] == low and item["reference_high"] == high
    assert source[item["source_span_start"]:item["source_span_end"]] == item["source_span"]
    assert any(item["source_span"].endswith(suffix) for suffix in ("mg/dL", "g/dL", "mmol/L", "10^3/uL"))


def test_insertions_preserve_every_original_character_and_monotone_offsets():
    source = "FastingGlucose112mg/dL70-100H\nSerumCreatinine1.2mg/dL0.6-1.1H"
    normalized, mapping = normalise(source)
    assert "mg/dL 70-100H" in normalized
    assert "mg/dL 0.6-1.1H" in normalized
    assert mapping[-1] == len(source)
    assert mapping == sorted(mapping)
    assert normalized.replace(" ", "") == source
    for substring in ("112mg/dL", "1.2mg/dL"):
        start = source.index(substring)
        norm_start = to_normalised(mapping, start)
        norm_end = to_normalised(mapping, start + len(substring))
        recovered_start, recovered_end = to_source(mapping, norm_start, norm_end)
        assert source[recovered_start:recovered_end].strip() == substring


@pytest.mark.parametrize("source", [
    "Glucose9.mg/dL70-100",             # unreadable decimal: never repair it to 9
    "Glucose112mystery70-100",          # no compatible unit
    "Glucose112mmHg70-100",             # unit belongs to a different measurement
    "Uncatalogued112mg/dL70-100",       # no catalogued analyte
    "Glucose112mg/dL70-",               # incomplete printed interval
    "Glucose112mg/dL70-100garbled",      # no complete range terminator
])
def test_ambiguous_rows_are_not_recovered_by_unit_boundary_rule(source):
    assert extract_numeric_measurements(source) == []


@pytest.mark.parametrize("source,raw", [("WBC6.810/uL4.0-11.0", "6.810"), ("PlateletCount22510/uL150-410", "22510")])
def test_missing_exponent_is_not_guessed_and_per_microlitre_value_is_preserved(source, raw):
    # /uL is itself a valid count unit. Preserve its literal numeric value; do
    # not reinterpret missing exponent digits as a scaled 10^3/uL measurement.
    found = extract_numeric_measurements(source)
    assert len(found) == 1
    assert found[0]["raw_value"] == raw
    assert found[0]["raw_unit"] == "/uL"
    assert found[0]["value"] == float(raw)


def test_hba1c_and_b12_labels_and_original_spaced_rows_are_not_rewritten():
    for source in ("HbA1c 6.2 %", "Vitamin B12 400 pg/mL", "Glucose 112 mg/dL 70-100"):
        normalized, _ = normalise(source)
        assert normalized == source


def test_multiple_rows_do_not_borrow_reference_values_across_analytes():
    source = "FastingGlucose112mg/dL70-100H\nSerumCreatinine1.2mg/dL0.6-1.1H"
    found = {item["name"]: item for item in extract_numeric_measurements(source)}
    assert set(found) == {"glucose", "creatinine"}
    assert found["glucose"]["reference_low"] == 70
    assert found["creatinine"]["reference_low"] == .6
