"""Per-panel specimen/method context, using only synthetic report fragments."""
import pytest

from app.services.nlp_processor import LAB_PANEL_RE, assign_measurement_context, extract_numeric_measurements


def contexts(text, starts=None):
    measurements = extract_numeric_measurements(text, starts)
    assign_measurement_context(text, starts, measurements)
    for row in measurements:
        assert text[row["source_span_start"]:row["source_span_end"]] == row["source_span"]
    return {row["name"]: row for row in measurements}


def test_last_haematology_result_does_not_borrow_next_panel_specimen_or_method():
    text = "\n".join([
        "HAEMATOLOGY", "Specimen: whole blood (EDTA)", "Method: Automated blood count",
        "Hemoglobin 11.9 g/dL 12-15.5", "Platelet count 225 10^3/uL 150-410",
        "BIOCHEMISTRY", "Specimen: Serum", "Method: Enzymatic assay",
        "Glucose 112 mg/dL 70-100", "Urea 38 mg/dL 15-40",
    ])
    rows = contexts(text)
    for name in ("hemoglobin", "platelet_count"):
        assert rows[name]["specimen"] == "Whole blood (EDTA)"
        assert rows[name]["laboratory_method"] == "Automated blood count"
    for name in ("glucose", "urea"):
        assert rows[name]["specimen"] == "Serum"
        assert rows[name]["laboratory_method"] == "Enzymatic assay"


def test_a_new_panel_without_context_stays_undocumented_instead_of_inheriting():
    text = "\n".join([
        "HAEMATOLOGY", "Specimen: whole blood (EDTA)", "Method: Blood count",
        "Platelet count 225 10^3/uL", "BIOCHEMISTRY", "Glucose 112 mg/dL", "Urea 38 mg/dL",
    ])
    rows = contexts(text)
    assert rows["platelet_count"]["specimen"] == "Whole blood (EDTA)"
    for name in ("glucose", "urea"):
        assert rows[name]["specimen"] == "NOT_DOCUMENTED"
        assert rows[name]["laboratory_method"] == "NOT_DOCUMENTED"


def test_below_result_context_within_its_panel_is_preserved():
    text = "\n".join([
        "BIOCHEMISTRY", "Creatinine 1.2 mg/dL", "Method: Enzymatic",
        "Specimen: Serum", "Urea 38 mg/dL", "IMMUNOLOGY", "Specimen: Plasma", "Method: Immunoassay",
    ])
    rows = contexts(text)
    assert rows["creatinine"]["specimen"] == "Serum"
    assert rows["creatinine"]["laboratory_method"] == "Enzymatic"
    assert rows["urea"]["specimen"] == "Serum"
    assert rows["urea"]["laboratory_method"] == "NOT_DOCUMENTED"


def test_explicit_panel_below_last_result_is_a_boundary_even_without_another_result():
    rows = contexts("HAEMATOLOGY\nPlatelet count 225 10^3/uL\nBIOCHEMISTRY\nSpecimen: Serum\nMethod: Enzymatic\n")
    assert rows["platelet_count"]["specimen"] == "NOT_DOCUMENTED"
    assert rows["platelet_count"]["laboratory_method"] == "NOT_DOCUMENTED"


def test_panel_with_dates_is_a_boundary_without_reclassifying_result_names():
    rows = contexts("HAEMATOLOGY\nSpecimen: whole blood (EDTA)\nMethod: Blood count\nPlatelet count 225 10^3/uL\nBIOCHEMISTRY Report Date: 18/06/2026\nGlucose 112 mg/dL\n")
    assert rows["glucose"]["specimen"] == "NOT_DOCUMENTED"
    assert rows["glucose"]["laboratory_method"] == "NOT_DOCUMENTED"
    assert LAB_PANEL_RE.search("Glucose fasting 112 mg/dL") is None
    assert LAB_PANEL_RE.search("Serum creatinine 1.2 mg/dL") is None


def test_page_boundaries_remain_stricter_than_panel_inheritance():
    first = "HAEMATOLOGY\nSpecimen: whole blood (EDTA)\nMethod: Blood count\nPlatelet count 225 10^3/uL"
    second = "Glucose 112 mg/dL"
    text = first + "\n" + second
    rows = contexts(text, [0, len(first) + 1])
    assert rows["platelet_count"]["specimen"] == "Whole blood (EDTA)"
    assert rows["glucose"]["specimen"] == "NOT_DOCUMENTED"
    assert rows["glucose"]["laboratory_method"] == "NOT_DOCUMENTED"


@pytest.mark.parametrize("heading", ["HEMATOLOGY", "CBC", "Complete blood count", "BIOCHEMISTRY", "Liver function tests", "Renal function", "Lipid profile", "Urinalysis"])
def test_explicit_known_panel_heading_matches_whole_line_only(heading):
    assert LAB_PANEL_RE.fullmatch(heading)
    assert LAB_PANEL_RE.fullmatch(heading + ":")
