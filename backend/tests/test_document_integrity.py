"""Identifier masking, per-result specimen and per-page dates on multi-page packets.
All names, numbers and addresses below are invented."""
import pytest

from app.services.nlp_processor import (
    _parse_date,
    assign_documented_dates,
    assign_measurement_context,
    date_conflicts,
    deidentify_with_counts,
    extract_documented_attributes,
    extract_numeric_measurements,
    privacy_screen,
)


@pytest.mark.parametrize(
    "line, masked, category",
    [
        ("Patient Name :JOHN EXAMPLE Report Date :12.08.2024", "Patient Name :[REDACTED_NAME] Report Date :12.08.2024", "NAME"),
        ("Name : ALEX EXAMPLE Age/Sex: 45Y/M", "Name : [REDACTED_NAME] Age/Sex: 45Y/M", "NAME"),
        # A surname that is also a header word is part of the name unless it reads as a label.
        ("Patient Name :JOHN WARD Report Date :12.08.2024", "Patient Name :[REDACTED_NAME] Report Date :12.08.2024", "NAME"),
        ("Patient Name: DOE, BILL Age/Sex: 45Y/M", "Patient Name: [REDACTED_NAME] Age/Sex: 45Y/M", "NAME"),
        ("Patient Name: JOHN BILL-SMITH Sex: M", "Patient Name: [REDACTED_NAME] Sex: M", "NAME"),
        ("Patient Name: MARY ANN Age 45 Sex F", "Patient Name: [REDACTED_NAME] Age 45 Sex F", "NAME"),
        ("Patient Name :JOHN EXAMPLE Ward No - 5", "Patient Name :[REDACTED_NAME] Ward No - 5", "NAME"),
        ("[REDACTED_ID] JaneSampleDoe(m) Sample Collected On:29-Aug-2024", "[REDACTED_ID] [REDACTED_NAME](m) Sample Collected On:29-Aug-2024", "NAME"),
        ("Ref.by.Dr Q.RAM PRASAD MD., Date:August29th2024", "Ref.by.[REDACTED_PROVIDER], Date:August29th2024", "PROVIDER"),
        ("REF.BY:DR.Q.RAM PRASAD GARU, Date:AUG292024", "REF.BY:[REDACTED_PROVIDER], Date:AUG292024", "PROVIDER"),
        ("Performed BY:Q.Person", "Performed BY:[REDACTED_PROVIDER]", "PROVIDER"),
        ("MR.NO:654321 DATE:01-02-2024", "[REDACTED_ID] DATE:01-02-2024", "ID"),
        ("Reg-No:123456", "[REDACTED_ID]", "ID"),
        ("Ph:08674-244444", "Ph:[REDACTED_PHONE]", "PHONE"),
        ("Contact98765 43210,", "Contact[REDACTED_PHONE],", "PHONE"),
        ("Diagnostics 12/345,Station Road", "Diagnostics [REDACTED_ADDRESS]", "ADDRESS"),
        ("Scan Centre Townville-521301.", "Scan Centre [REDACTED_ADDRESS].", "ADDRESS"),
    ],
)
def test_header_identifiers_are_masked_and_counted(line, masked, category):
    text, counts = deidentify_with_counts(line)
    assert text == masked
    assert counts == {category: 1}


@pytest.mark.parametrize(
    "line",
    [
        "Trivial MR. MS noted. Mild MR noted.",
        "No DR changes. Drainage tube in situ.",
        "BP 120/80, Pulse 72/min",
        "Cell: 4000-11000",
        "Platelets - 250000 /cumm",
        "Collected On:29-Aug-2024 10:22 AM",
        "Ref. Range: 13-17 g/dL",
        "Caused by: trauma",
        "Test Name : Haemoglobin",
        "Urine pH 6.0 Specific gravity 1.015",
    ],
)
def test_clinical_text_is_not_masked(line):
    assert deidentify_with_counts(line) == (line, {})


def test_privacy_screen_reports_what_was_masked_without_claiming_de_identification():
    screen = privacy_screen([{"page": 1, "identifiers_masked": {"NAME": 1, "PHONE": 2}}, {"page": 2, "identifiers_masked": {}}])
    assert screen["status"] == "IDENTIFIERS_FOUND_AND_MASKED"
    assert screen["identifiers_masked"] == {"NAME": 1, "PHONE": 2}
    assert screen["pages_with_identifiers"] == [1]
    assert screen["verification"] == "NOT_VERIFIED_BY_A_PERSON"
    assert "not a de-identification determination" in screen["notice"]
    assert privacy_screen([{"page": 1, "identifiers_masked": {}}])["status"] == "NO_LABELLED_IDENTIFIER_FOUND"


@pytest.mark.parametrize(
    "raw, iso",
    [("August29th2024", "2024-08-29"), ("AUG292024", "2024-08-29"), ("AUG29T2024", "2024-08-29"), ("29-Aug-2024", "2024-08-29"),
     ("Aug 29, 2024", "2024-08-29")],
)
def test_ocr_glued_month_name_dates_parse(raw, iso):
    assert _parse_date(raw)[0] == iso


def _packet(*pages: str):
    text = "\n".join(pages)
    starts, cursor = [], 0
    for page in pages:
        starts.append(cursor)
        cursor += len(page) + 1
    measurements = extract_numeric_measurements(text, starts)
    assign_measurement_context(text, starts, measurements)
    attributes = extract_documented_attributes(text)
    assign_documented_dates(attributes, starts, len(text), measurements)
    return {item["name"]: item for item in measurements}, attributes, starts, text


HAEMATOLOGY = "\n".join([
    "HAEMATOLOGY Collected On:29-Aug-2024 10:22 AM",
    "SPECIMEN:WHOLEBLOOD-EDTA",
    "Haemoglobin 13.5 g/dL 13.0-17.0",
    "METHOD:Automated-SLS Haemoglobin Method",
    "Total WBC count 7600 cells/cumm 4000-11000",
    "METHOD:Automated-Flowcytometry",
])
BIOCHEMISTRY = "\n".join([
    "BIOCHEMISTRY Report Date: 15.09.2024",
    "Serum Creatinine 1.1 mg/dl 0.7-1.3",
    "Method:ENZYMATIC",
    "Calcium 9.1 mg/dL 8.5-10.5",
    "Method:ARSENAZO DYE",
    "Specmen:Serum/Piasma",
])


def test_each_result_takes_its_own_pages_specimen_method_and_date():
    rows, *_ = _packet(HAEMATOLOGY, BIOCHEMISTRY)
    # The panel heading's glued "WHOLEBLOOD-EDTA" applies to the haematology page; the serum
    # printed on the next page never reaches it.
    assert rows["hemoglobin"]["specimen"] == rows["white_blood_cell_count"]["specimen"] == "Whole blood (EDTA)"
    assert rows["hemoglobin"]["laboratory_method"] == "Automated-SLS Haemoglobin Method"
    assert rows["white_blood_cell_count"]["laboratory_method"] == "Automated-Flowcytometry"
    assert rows["hemoglobin"]["documented_date"] == "2024-08-29"
    assert rows["creatinine"]["specimen"] == "Serum"  # printed in the test name
    assert rows["calcium"]["specimen"] == "Serum/plasma"  # the OCR-misspelt line under the row
    assert rows["calcium"]["laboratory_method"] == "ARSENAZO DYE"
    assert rows["creatinine"]["documented_date"] == rows["calcium"]["documented_date"] == "2024-09-15"


def test_a_page_without_a_date_does_not_borrow_another_pages_date():
    undated = "\n".join(["CHEMISTRY", "Serum Creatinine 1.1 mg/dl 0.7-1.3"])
    rows, *_ = _packet(undated, HAEMATOLOGY)
    assert rows["creatinine"]["documented_date"] is None
    assert rows["hemoglobin"]["documented_date"] == "2024-08-29"


def test_a_method_between_results_belongs_to_the_result_above_it():
    rows, *_ = _packet("\n".join(["Creatinine 1.0 mg/dL 0.7-1.3", "Method:ENZYMATIC", "Urea 30 mg/dL 15-40"]))
    assert rows["creatinine"]["laboratory_method"] == "ENZYMATIC"  # the line under its own row
    assert rows["urea"]["laboratory_method"] == "NOT_DOCUMENTED"
    heading_only, *_ = _packet("\n".join(["Specimen: serum", "Method: enzymatic assay", "Creatinine 1.0 mg/dL."]))
    assert heading_only["creatinine"]["laboratory_method"] == "enzymatic assay"
    assert heading_only["creatinine"]["specimen"] == "Serum"


def test_dates_on_one_page_far_apart_are_reported_as_a_conflict():
    page = "\n".join(["Collected On:29-Aug-2024", "Report Date: 15.10.2025", "Serum Creatinine 1.1 mg/dl 0.7-1.3"])
    _rows, attributes, starts, text = _packet(page, BIOCHEMISTRY)
    assert date_conflicts(attributes, starts, len(text)) == [{"page": 1, "dates": ["2024-08-29", "2025-10-15"]}]


@pytest.mark.parametrize(
    "sentence, comparison",
    [
        ("Left kidney is normal in size and shows increased echotexture.", None),
        ("The liver shows increased echogenicity.", None),
        ("Previously observed lesion has increased.", "INCREASED"),
        ("The nodule has increased in size.", "INCREASED"),
    ],
)
def test_a_tissue_descriptor_is_not_an_interval_change(sentence, comparison):
    from app.services.nlp_processor import extract_clinical_statements

    assert {statement["comparison"] for statement in extract_clinical_statements(sentence)} == {comparison}


@pytest.mark.parametrize(
    "row, value",
    [
        ("Glycosylated Haemoglobin-HbA1c dtyGSStrdi 7.8*% Up to 6%", 7.8),  # OCR-mangled small-print method
        ("HbA1c Fasting 7.8 %", None),  # an ordinary word is not taken for a method
    ],
)
def test_a_garbled_small_print_method_between_name_and_value(row, value):
    found = [item["value"] for item in extract_numeric_measurements(row) if item["name"] == "hba1c"]
    assert found == ([value] if value is not None else [])
