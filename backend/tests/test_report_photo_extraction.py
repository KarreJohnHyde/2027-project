"""Regression tests for photographed-report extraction failures.

Every fixture is synthetic and de-identified: it reproduces only the layout defects seen
in phone photographs of printed reports (OCR-glued words, wrapped lines, stratified
reference columns, bills, reprinted pages). No patient name, identifier or real value
from any source document appears here.
"""

from datetime import datetime, timezone

from app.models.entities import Case, Finding, InferenceRun, MedicalMeasurement, ModalityType, UploadedFile
from app.services.biomarker_trends import build_series
from app.services.measurement_identity import duplicate_map
from app.services.nlp_processor import extract_clinical_statements, extract_numeric_measurements, split_sentences
from app.services.ocr_text import normalise, to_source


def _statements(text):
    statements = extract_clinical_statements(text)
    for item in statements:
        assert text[item["source_span_start"]:item["source_span_end"]].startswith(item["source_span"][:40])
        assert text[item["entity_start"]:item["entity_end"]] == item["entity_text"]
    return statements


def _by_entity(statements):
    return {item["entity"]: item for item in statements}


def _labs(text):
    return {item["name"]: item for item in extract_numeric_measurements(text)}


# --- OCR normalisation -----------------------------------------------------------------

def test_normalisation_only_inserts_spaces_and_maps_back_exactly():
    source = "Nopleural effusion orpneumothorax. Nodules noted. tor/oright diaphragmatichernia"
    normalised, index = normalise(source)
    assert normalised == "No pleural effusion or pneumothorax. Nodules noted. to r/o right diaphragmatic hernia"
    assert normalised.replace(" ", "") == source.replace(" ", "")
    start = normalised.index("pneumothorax")
    assert source[slice(*to_source(index, start, start + len("pneumothorax")))] == "pneumothorax"


def test_known_words_and_unknown_names_are_not_split():
    text = "Nodules. Notable. Normal echotexture. Corticomedullary differentiation. Haemoglobin. Xyzqwvrt"
    assert normalise(text)[0] == text


# --- Assertion and scope ---------------------------------------------------------------

def test_glued_negations_are_negated_not_affirmed():
    statements = _by_entity(_statements(
        "These changes are associated with mild ground-glass attenuation.Nofocal\n"
        "consolidation or suspiciouspulmonary masslesion.\n"
        "Nopleural effusion orpneumothorax.\n"
    ))
    for entity in ("Consolidation", "Mass", "Lesion", "Pleural effusion", "Pneumothorax"):
        assert statements[entity]["negation"] == "NEGATED", entity
    assert statements["Ground-glass opacity"]["negation"] == "AFFIRMED"


def test_negation_cue_wrapped_onto_the_previous_line_still_applies():
    statements = _by_entity(_statements("Trachea is patent.Cardiac size is within normal limits.No\npericardial effusion.\n"))
    assert statements["Pericardial effusion"]["negation"] == "NEGATED"
    statements = _by_entity(_statements("No granulomas / parasites. No\nevidence of dysplasia/ malignancy.\n"))
    for entity in ("Granuloma", "Dysplasia", "Malignancy"):
        assert statements[entity]["negation"] == "NEGATED", entity


def test_coordinated_negation_covers_every_listed_finding():
    statements = _by_entity(_statements("No calculi /hydronephrosis/Pyelonephritis seen.\nNomass lesion is seen.\n"))
    for entity in ("Calculus", "Hydronephrosis", "Pyelonephritis", "Mass", "Lesion"):
        assert statements[entity]["negation"] == "NEGATED", entity


def test_separate_unbulleted_impression_lines_do_not_share_negation():
    starts = [text for text in ("NO FOCAL LESION IN THE SPLEEN", "GRADE I FATTY LIVER")]
    text = "\n".join(starts) + "\n"
    statements = _by_entity(_statements(text))
    assert statements["Hepatic steatosis"]["negation"] == "AFFIRMED"
    assert statements["Lesion"]["negation"] == "NEGATED"
    assert len(split_sentences(text)) == 2


def test_uncertainty_after_a_dash_ends_an_earlier_negation():
    statements = _by_entity(_statements(
        "ELEVATED RIGHT HEMIDIAPHRAGM WITHOUT FOCAL DIAPHRAGMATIC IRREGULARITY OR INVAGINATION-likely due toPhrenicnerve palsy.\n"
    ))
    assert statements["Nerve palsy"]["negation"] == "AFFIRMED"
    assert statements["Nerve palsy"]["certainty"] == "UNCERTAIN"
    assert statements["Elevated hemidiaphragm"]["negation"] == "AFFIRMED"


def test_glued_rule_out_keeps_the_finding_hypothetical():
    statements = _by_entity(_statements("Liver is raised high up\nthe diaphragm tor/oright diaphragmatichernia.\n"))
    assert statements["Diaphragmatic hernia"]["certainty"] == "HYPOTHETICAL"


def test_advised_aspiration_is_planned_not_performed():
    statements = _by_entity(_statements("MULTIPLE CYSTIC LESIONS, ONE SHOWING INTERNAL CALCIFICATION-FNAC to rule out Neoplastic. ULTRASOUND CORRELATION ADVISED.\n"))
    assert statements["Fine-needle aspiration"]["certainty"] == "HYPOTHETICAL"
    assert statements["Neoplasm"]["certainty"] == "HYPOTHETICAL"
    assert statements["Lesion"]["certainty"] == "CERTAIN"


def test_recommendation_section_is_planned_and_procedure_section_is_performed():
    statements = _statements(
        "PROCEDURE : BIOPSIES TAKEN FROM ANASTOMOTIC SITE ULCERS AND SENT FOR HPE.\n"
        "RECOMMENDATION : FOLLOW UP WITH BIOPSY REPORT\n"
    )
    biopsies = [item for item in statements if item["entity"] == "Biopsy"]
    assert [item["certainty"] for item in biopsies] == ["CERTAIN", "HYPOTHETICAL"]


def test_facility_advertising_and_bills_produce_no_patient_statements():
    footer = "Facilities: (24/7) All CT Scans and Digital X-Ray.\nAll 2D, 3D, 4D Color Doppler, FNAC, Biopsy and Laboratory services.\n"
    assert _statements(footer) == []
    bill_rows = "1 SMALL BIOPSY - II 970.00 1.0 0.00 970.00\n3 Colonoscopy 5,100.00 1.0 0.00 5,100.00\n"
    assert _statements(bill_rows) == []
    bill_page = "OUT-PATIENT BILL - FINAL BILL OF SUPPLY\nBILL NO. 0000\nColonoscopy\nBiopsy procedure\nNet Amount 100.00\nAmount Paid 100.00\n"
    assert _statements(bill_page) == []


def test_reference_interpretation_text_describes_other_people():
    statements = _statements(
        "Increased levels may be found in\npatients with primary colorectal\ncancer or other malignancies\n"
        "including medullary thyroid\ncarcinoma and breast cancers.\n"
    )
    assert statements and all(item["experiencer"] == "OTHER" for item in statements)


def test_diabetes_association_name_is_not_a_diagnosis():
    assert not [item for item in _statements("American Diabetes Association(ADA) Non-Diabetic : <5.7\n") if item["entity"] == "Diabetes mellitus"]


def test_status_post_belongs_to_the_procedure_it_precedes():
    statements = _by_entity(_statements("Disease S/P loop ileostomy anastomotic site ulcer.\nUTERUS:Posthysterectomy status\n"))
    assert statements["Intestinal stoma procedure"]["temporality"] == "HISTORICAL"
    assert statements["Ulcer"]["temporality"] == "CURRENT"
    assert statements["Hysterectomy"]["temporality"] == "HISTORICAL"


# --- Laboratory rows ---------------------------------------------------------------------

LIPIDS = (
    "Fasting Lipid Profile-FLP\n"
    "Serum Cholesterol 201mg/dL 0-200\n"
    "Method:Enzymatic\n"
    "Serum Triglycerides 162*mg/dL 60-150\n"
    "Serum HDL Cholesterol Method:Enzymatic 51mg/dL >45\n"
    "SerumLDL Cholesterol Methocd:Direct 112*mg/dL <100mg/dL\n"
    "Serum VLDL Cholesterol Method:Calculated 32mg/dl 20-40\n"
    "Total Cholesterol/ HDL Ratio 3.9 <4.5\n"
)


def test_lipid_analytes_stay_distinct_with_their_printed_limits():
    labs = _labs(LIPIDS)
    assert [labs[name]["value"] for name in ("cholesterol_total", "triglycerides", "hdl_cholesterol", "ldl_cholesterol", "vldl_cholesterol", "cholesterol_hdl_ratio")] == [201, 162, 51, 112, 32, 3.9]
    assert sum(1 for item in extract_numeric_measurements(LIPIDS) if item["name"] == "cholesterol_total") == 1
    assert (labs["cholesterol_total"]["reference_low"], labs["cholesterol_total"]["reference_high"]) == (0, 200)
    assert (labs["hdl_cholesterol"]["reference_low"], labs["hdl_cholesterol"]["reference_low_inclusive"]) == (45, False)
    assert (labs["ldl_cholesterol"]["reference_high"], labs["ldl_cholesterol"]["reference_high_inclusive"]) == (100, False)
    assert labs["triglycerides"]["documented_flag"] == "ABNORMAL"
    assert labs["hdl_cholesterol"]["laboratory_method"] == "Enzymatic"


def test_hdl_split_across_lines_is_never_total_cholesterol():
    labs = _labs("Serum HDL\nCholesterol 48 mg/dL\n")
    assert "cholesterol_total" not in labs
    assert labs["hdl_cholesterol"]["value"] == 48


def test_hba1c_with_flag_before_unit_and_printed_control_bands():
    labs = _labs(
        "Glycosylated Haemoglobin-HbA1c 6.9 * % Up to 6 % - Normal Non Diabetic\nLevel\n"
        "6.01 - 7.00 - Good Control (GOAL)\n7.01 to 8.00 - Fair Control\n8.01 & above - Poor Control\n"
    )
    assert "hemoglobin" not in labs
    hba1c = labs["hba1c"]
    assert (hba1c["value"], hba1c["documented_flag"], hba1c["reference_high"]) == (6.9, "ABNORMAL", 6)
    assert hba1c["reference_selection"] == "NORMAL_BAND_PRINTED_WITH_CATEGORIES"
    assert hba1c["documented_category"].startswith("Good Control")
    assert len(hba1c["reference_options"]) == 4


SEX_STRATIFIED_CREATININE = "Serum Creatinine 1.10mg/dL Male:0.70-1.30\nMethod:Jaffe Kinetic Female:0.55-1.02\n"


def test_sex_stratified_interval_uses_the_documented_sex_only():
    female = _labs("Age/Sex: 70 Y / F\n" + SEX_STRATIFIED_CREATININE)["creatinine"]
    assert (female["reference_low"], female["reference_high"]) == (0.55, 1.02)
    assert female["reference_selection"] == "SELECTED_BY_DOCUMENTED_SEX"
    male = _labs("Age/Sex: 70 Y / M\n" + SEX_STRATIFIED_CREATININE)["creatinine"]
    assert (male["reference_low"], male["reference_high"]) == (0.70, 1.30)
    unknown = _labs(SEX_STRATIFIED_CREATININE)["creatinine"]
    assert unknown["reference_low"] is None and unknown["reference_high"] is None
    assert unknown["reference_selection"] == "SEX_NOT_DOCUMENTED"
    assert len(unknown["reference_options"]) == 2


TSH = (
    "TSH(Thyroid Stimulating Hormone) 3.10mlU/L 21Weeks-20yrs:0.7-6.4\n21-54yrs:0.4-4.2\n55-87yrs:0.5-8.9\n"
    "Pregnancy:\n1st Trimester:0.3-4.5\n2ndTrimester:0.5-4.6\n3rd Trimester:0.8-5.2\n"
)


def test_age_stratified_interval_and_unknown_pregnancy_status():
    older = _labs("Age: 70 yrs Sex: Female\n" + TSH)["tsh"]
    assert (older["unit"], older["reference_low"], older["reference_high"]) == ("mIU/L", 0.5, 8.9)
    assert older["reference_selection"] == "SELECTED_BY_DOCUMENTED_AGE"
    younger = _labs("Age: 30 yrs Sex: Female\n" + TSH)["tsh"]
    assert younger["reference_low"] is None and younger["reference_selection"] == "PREGNANCY_STATUS_NOT_DOCUMENTED"
    man = _labs("Age: 30 yrs Sex: Male\n" + TSH)["tsh"]
    assert (man["reference_low"], man["reference_high"]) == (0.4, 4.2)


def test_documented_egfr_with_its_unit_on_the_next_line():
    egfr = _labs("eGFR-Creatinine Clearance 52.40 >90\nmL/min/1.73m2\n")["egfr_documented"]
    assert (egfr["value"], egfr["unit"], egfr["reference_low"], egfr["reference_low_inclusive"]) == (52.4, "mL/min/1.73m²", 90, False)


def test_calculated_and_qualified_analytes_are_not_their_generic_neighbours():
    labs = _labs(
        "Age / Sex : 40 Yr / Male\n"
        "Estimated Average Glucose 110.20 mg/dL\n"
        "Direct Bilirubin 0.10 mg/dL Adult:0.0 - 0.3\n"
        "Indirect Bilirubin 0.50 mg/dL Adult:0.0 - 1.1 Neonates:0.6 - 10.5\n"
        "Mean Corpuscular Haemoglobin (MCH) 26.0 pg Male:25.7 - 32.2\n"
        "Haemoglobin 12.1 g/dL Male: 13.7 - 17.5 Female: 11.2 - 15.7 New Born: 14.0 - 22.0\n"
    )
    assert "glucose" not in labs and labs["estimated_average_glucose"]["value"] == 110.2
    assert "bilirubin_total" not in labs and labs["bilirubin_indirect"]["value"] == 0.5
    assert (labs["bilirubin_indirect"]["reference_low"], labs["bilirubin_indirect"]["reference_high"]) == (0.0, 1.1)
    assert labs["mch"]["value"] == 26.0
    assert (labs["hemoglobin"]["value"], labs["hemoglobin"]["reference_low"], labs["hemoglobin"]["reference_high"]) == (12.1, 13.7, 17.5)


def test_blood_count_units_printed_per_cubic_millimetre():
    labs = _labs("Total WBC Count 7200 cells/cumm\nPlatelet Count 2.10 lakhs/cumm 1.5 - 4.1\nTotal RBC Count 4.20 million/cumm\nPacked Cell Volume 38.0 %\n")
    assert (labs["white_blood_cell_count"]["unit"], labs["platelet_count"]["unit"], labs["red_blood_cell_count"]["unit"]) == ("/µL", "10^5/µL", "10^12/L")
    assert labs["hematocrit"]["value"] == 38.0
    assert (labs["platelet_count"]["reference_low"], labs["platelet_count"]["reference_high"]) == (1.5, 4.1)


def test_age_banded_sex_strata_and_smoking_bands():
    esr = _labs(
        "AGE / SEX : 40 Yr / Male\nErythrocytes Sedimentation Rate (ESR) 20 mm/hour Male:17 to 50 -Upto 10\n"
        ": 51 to 60 -Upto 12\n:>70 -Upto 30\nFemale: 17 to 50 -Upto 12\n"
    )["esr"]
    assert (esr["reference_high"], esr["reference_selection"]) == (10, "SELECTED_BY_DOCUMENTED_SEX_AND_AGE")
    cea = _labs("CEA 1.4 ng/mL Non smokers < 3\nSmokers < 5\n")["cea"]
    assert cea["reference_high"] is None and cea["reference_selection"] == "CATEGORY_BANDS_ONLY"


# --- Reprinted pages ---------------------------------------------------------------------

def test_reprinted_results_are_one_observation_with_every_occurrence_kept(db_session, test_users):
    clinician = test_users["clinician_a"]
    case = Case(pseudonymous_id="REPRINT-TEST", created_by_id=clinician.id)
    db_session.add(case)
    db_session.flush()
    upload = UploadedFile(case_id=case.id, filename="packet.pdf", stored_filename="packet.pdf", file_path="/fixture/packet.pdf",
                          file_hash="0" * 64, file_size_bytes=1, mime_type="application/pdf", modality=ModalityType.REPORT)
    db_session.add(upload)
    db_session.flush()
    run = InferenceRun(case_id=case.id, file_id=upload.id, modality=ModalityType.REPORT, model_name="fixture",
                       model_version="1", preprocessing_version="1")
    db_session.add(run)
    db_session.flush()
    finding = Finding(inference_run_id=run.id, case_id=case.id, modality=ModalityType.REPORT, category="Clinical report",
                      label="fixture", mapping_status="NOT_MAPPED")
    db_session.add(finding)
    db_session.flush()

    def row(page, value, date="2026-01-10"):
        item = MedicalMeasurement(case_id=case.id, source_file_id=upload.id, finding_id=finding.id, name="c_reactive_protein",
                                  display_name="C-reactive protein", value=value, unit="mg/L", raw_value=str(value), raw_unit="mg/L",
                                  source_span=f"CRP {value} mg/L", source_span_start=0, source_span_end=10, source_page=page,
                                  documented_date=date, specimen="Serum", laboratory_method="Immunoassay",
                                  created_at=datetime.now(timezone.utc))
        db_session.add(item)
        db_session.flush()
        return item

    first, reprint, other_page_reprint, new_value = row(1, 12.0), row(4, 12.0), row(6, 12.0), row(7, 9.0)
    assert duplicate_map([first, reprint, other_page_reprint, new_value]) == {reprint.id: first.id, other_page_reprint.id: first.id}
    series = next(item for item in build_series(db_session, case.id) if item["name"] == "c_reactive_protein")
    assert [point["measurement_id"] for point in series["points"]] == [first.id, new_value.id]
    assert {item["reason"] for item in series["excluded"]} == {f"DUPLICATE_SOURCE_OCCURRENCE_OF_M{first.id}"}


# --- Neurology, echocardiography and haematology layouts -----------------------------------

def test_no_features_suggestive_of_is_a_negation():
    statements = _by_entity(_statements(
        "Spinal cord shows normal signal intensity with no features suggestive of myelomalacia / cord atrophy seen.\n"
    ))
    assert statements["Spinal cord change"]["negation"] == "NEGATED"


def test_nil_after_a_finding_negates_it():
    statements = _statements("Mitral stenosis - Nil\nAortic regurgitation - Grade Nil\nTrivial Mitral regurgitation.\n")
    assessed = [(item["entity_text"].lower(), item["negation"]) for item in statements]
    assert ("mitral stenosis", "NEGATED") in assessed
    assert ("aortic regurgitation", "NEGATED") in assessed
    assert ("mitral regurgitation", "AFFIRMED") in assessed


def test_brain_spine_and_echo_findings_are_recognised():
    statements = _by_entity(_statements(
        "Few punctate T2 hyperintense foci are observed in bilateral corona radiata - small vessel ischaemic changes.\n"
        "Mild spondylotic changes otherwise no abnormality noted. Mild disc bulge is observed at C5-C6 level.\n"
        "Grade I LV diastolic dysfunction. No regional wall motion abnormality of LV. No clot / vegetation.\n"
    ))
    assert statements["T2 hyperintense foci"]["negation"] == "AFFIRMED"
    assert statements["White matter change"]["anatomy_system"] == "brain"
    assert statements["Spondylosis or osteophytes"]["negation"] == "AFFIRMED"
    assert statements["Disc degeneration or bulge"]["negation"] == "AFFIRMED"
    assert statements["Diastolic dysfunction"]["negation"] == "AFFIRMED"
    assert statements["Regional wall motion abnormality"]["negation"] == "NEGATED"
    assert statements["Intracardiac clot or vegetation"]["negation"] == "NEGATED"


def test_planned_investigations_and_history_sections():
    statements = _by_entity(_statements(
        "Pre Existing Illness:\nHistory of stroke years back\n\nInvestigations Advised:\nColonoscopy\n"
    ))
    assert statements["Stroke"]["temporality"] == "HISTORICAL"
    assert statements["Endoscopic procedure"]["certainty"] == "HYPOTHETICAL"


def test_throat_endoscopy_is_not_gastrointestinal():
    statement = _by_entity(_statements("VIDEO ENDOSCOPY REPORT OF THROAT\n"))["ENT endoscopy"]
    assert statement["anatomy_system"] is None


def test_haematology_units_comma_intervals_flags_and_lab_age_format():
    labs = _labs(
        "Gender / Age : Male / 40 Y 2 M 3 D\n"
        "HAEMOGLOBIN (HB) 15.1 gm/dL 14 - 17\n"
        "RBC COUNT 5.10 millioncells/µL 4.5 - 5.6\n"
        "TOTAL WBC COUNT 7900 cells/µL 4,400 - 11,000\n"
        "NEUTROPHILS 71.0 % H 40 - 60\n"
        "ABSOLUTE NEUTROPHIL COUNT 5600 Cell/Cumm 1,800 - 6,800\n"
        "PLATELET COUNT 240000 cells/µL 150,000 - 450,000\n"
        "MEAN PLATELET VOLUME (MPV) 9.0 fL 7.5 - 12\n"
        "CK - NAC / CPK 120 U/L 55 - 170\n"
    )
    assert (labs["hemoglobin"]["unit"], labs["hemoglobin"]["reference_low"]) == ("g/dL", 14)
    assert labs["red_blood_cell_count"]["unit"] == "10^12/L"
    assert (labs["white_blood_cell_count"]["reference_low"], labs["white_blood_cell_count"]["reference_high"]) == (4400, 11000)
    assert (labs["neutrophils_percent"]["documented_flag"], labs["neutrophils_percent"]["reference_high"]) == ("HIGH", 60)
    assert labs["absolute_neutrophil_count"]["value"] == 5600 and "neutrophils_percent" in labs
    assert (labs["platelet_count"]["reference_low"], labs["platelet_count"]["reference_high"]) == (150000, 450000)
    assert labs["mpv"]["value"] == 9.0 and labs["creatine_kinase"]["value"] == 120


def test_approximate_values_are_never_recorded_as_exact():
    labs = _labs("Normal LV systolic function LVEF ~ 68%.\nEF 68.0 % 55 % - 90%\n")
    approximate = [item for item in extract_numeric_measurements("LVEF ~ 68%.\n") if item["name"] == "ejection_fraction"]
    assert approximate and approximate[0]["result_operator"] == "~"
    assert (labs["ejection_fraction"]["reference_low"], labs["ejection_fraction"]["reference_high"]) in {(55, 90), (None, None)}
