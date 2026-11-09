"""Extraction gaps found on the owner's photographed packets, reproduced with synthetic text only."""
import pytest

from app.services.nlp_processor import extract_clinical_statements, extract_numeric_measurements, extract_qualitative_results
from app.services.terminology import convert


def values(text: str) -> dict:
    return {item["name"]: (item["value"], item["unit"]) for item in extract_numeric_measurements(text)}


def test_printed_ecg_values_including_the_qt_qtc_pair():
    found = values("12 LEAD ECG\nVent. rate 72 BPM\nPR interval 160 ms\nQRS duration 92 ms\nQT/QTc 380/412 ms\n")
    assert found == {"ventricular_rate": (72.0, "bpm"), "pr_interval": (160.0, "ms"), "qrs_duration": (92.0, "ms"),
                     "qt_interval": (380.0, "ms"), "qtc_interval": (412.0, "ms")}


def test_qrs_axis_is_not_a_duration():
    assert "qrs_duration" not in values("QRS axis 45 degrees\n")


def test_echo_m_mode_dimensions_and_their_unit_conversion():
    found = values("M-MODE\nIVSd 1.1 cm\nLVIDd 4.9 cm\nLVPWd 1.0 cm\nLVIDs 3.2 cm\nFS 35 %\nLA 3.6 cm\nAO 2.9 cm\nEF 62 %\n")
    assert found["ivs_diastole"] == (1.1, "cm") and found["lvid_diastole"] == (4.9, "cm") and found["lvid_systole"] == (3.2, "cm")
    assert found["lvpw_diastole"] == (1.0, "cm") and found["fractional_shortening"] == (35.0, "%")
    assert found["left_atrium_diameter"] == (3.6, "cm") and found["aortic_root_diameter"] == (2.9, "cm") and found["ejection_fraction"] == (62.0, "%")
    assert convert("lvid_diastole", 4.9, "cm", "mm") == pytest.approx(49.0)


@pytest.mark.parametrize("text,name,value", [
    ("COMPLETE BLOOD COUNT\nRDW (SD)    42.5   fL   39.0 - 46.0\n", "rdw_sd", 42.5),
    ("ESR\nONE HOUR READING     15     mm/hr     0 - 20\n", "esr", 15.0),
    ("FIRST HOUR READING 22 mm/hr\n", "esr", 22.0),
])
def test_cbc_and_esr_label_variants(text, name, value):
    assert values(text)[name][0] == value


URINE = ("URINE ROUTINE EXAMINATION\nPHYSICAL EXAMINATION\nColour      Pale yellow\nAppearance   Clear\n"
         "CHEMICAL EXAMINATION\nProtein      Nil\nGlucose      Trace\nKetone bodies   Absent\n"
         "MICROSCOPIC EXAMINATION\nPus cells    2-3  /hpf\nRBCs     Nil  /hpf\nEpithelial cells   Few\n"
         "LIVER FUNCTION TEST\nTotal protein   7.1 g/dL\n")


def test_urinalysis_rows_are_statements_with_the_printed_result():
    rows = {item["entity"]: item for item in extract_qualitative_results(URINE)}
    assert rows["Urine protein"]["negation"] == "NEGATED" and rows["Urine ketones"]["negation"] == "NEGATED"
    assert rows["Urine glucose"]["negation"] == "AFFIRMED" and rows["Urine glucose"]["cues"][0]["text"] == "Trace"
    assert rows["Urine pus cells"]["cues"][0]["text"] == "2-3  /hpf" and rows["Urine red cells"]["negation"] == "NEGATED"
    assert rows["Urine colour"]["cues"][0]["text"] == "Pale yellow" and rows["Urine epithelial cells"]["cues"][0]["text"] == "Few"
    for item in rows.values():
        assert URINE[item["source_span_start"]:item["source_span_end"]] == item["source_span"]
        cue = item["cues"][0]
        assert URINE[cue["start"]:cue["end"]] == cue["text"]
    # The liver panel's numeric total protein is a measurement, not a urine row.
    assert len([item for item in rows.values() if item["entity"] == "Urine protein"]) == 1
    assert values(URINE)["total_protein"] == (7.1, "g/dL")


def test_no_urine_statement_without_a_urine_section():
    assert extract_qualitative_results("LIVER FUNCTION TEST\nProtein      Nil\n") == []


def test_symptoms_are_extracted_with_their_assertion():
    found = {item["entity"]: item["negation"] for item in extract_clinical_statements(
        "HISTORY:\nComplaints of memory impairment, neck pain and numbness of the left hand. Headache for two weeks. "
        "Denies chest pain or palpitations.\n")}
    assert found["Memory impairment"] == found["Neck pain"] == found["Numbness or tingling"] == found["Headache"] == "AFFIRMED"
    assert found["Chest pain"] == found["Palpitations"] == "NEGATED"


def test_a_glued_copy_with_ocr_letter_drops_still_yields_the_findings():
    found = {item["entity"]: item for item in extract_clinical_statements("FINDINGS:\nRighthighparietallobeHemorrhagiccontusonwithmildperilesonaldema\n")}
    assert found["Cerebral contusion"]["laterality"] == "right" and found["Cerebral oedema"]["negation"] == "AFFIRMED"


def test_prefixed_urine_rows_count_and_other_specimens_and_pages_end_the_section():
    rows = extract_qualitative_results("URINE ROUTINE\nUrine protein: Nil\nCSF ANALYSIS\nProtein   Negative\n")
    assert [item["entity"] for item in rows] == ["Urine protein"] and rows[0]["negation"] == "NEGATED"
    text = "URINE ROUTINE\nProtein   Nil\nPAGE TWO\nProtein   Trace\n"
    assert len(extract_qualitative_results(text, page_starts=[0, text.index("PAGE TWO")])) == 1


def test_a_posterior_wall_outside_the_heart_is_not_an_lv_measurement():
    assert "lvpw_diastole" not in values("Gallbladder posterior wall 3 mm thick.\n")
    assert values("LV posterior wall 1.0 cm\n")["lvpw_diastole"] == (1.0, "cm")
