"""MedTwin 2.0 capability tests.

All inputs are deterministic, synthetic, test-only fixtures. None of them is
presented anywhere in the application as patient evidence.
"""

from io import BytesIO
import json

import numpy as np
import pytest
from sqlalchemy import create_engine, inspect, text

from app.config import ANATOMY_MANIFEST_PATH
from app.models.entities import User, UserRole
from app.services.auth import get_password_hash
from app.services.clinical_calculators import ckd_epi_2021
from app.services.evaluation_metrics import (
    EvaluationInputError,
    evaluate_classification,
    evaluate_detection,
    evaluate_forecast,
    evaluate_lab_extraction,
    evaluate_regression,
    evaluate_segmentation,
    evaluate_segmentation_batch,
    evaluate_survival,
)
from app.services.nlp_processor import extract_clinical_statements, extract_documented_attributes, extract_numeric_measurements, split_sentences
from app.security import SlidingWindowLimiter
from tests.conftest import get_auth_headers


def _statement(text_value: str, entity: str) -> dict:
    matches = [item for item in extract_clinical_statements(text_value) if item["entity"] == entity]
    assert matches, f"{entity} not extracted from {text_value!r}"
    return matches[0]


def _case(client, headers, pseudonym: str, exam_dates=()):
    response = client.post(
        "/api/v1/cases",
        json={"pseudonymous_id": pseudonym, "examinations": [{"exam_date": date, "modality": "REPORT"} for date in exam_dates]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _upload(client, headers, case_id: int, name: str, content: bytes, mime: str, examination_id=None):
    data = {"deidentified": "true", "is_associated": "true"}
    if examination_id is not None:
        data["examination_id"] = str(examination_id)
    return client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (name, content, mime)}, data=data, headers=headers)


def _analyse(client, headers, upload_id: int):
    response = client.post(f"/api/v1/uploads/{upload_id}/analysis-jobs", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------- text rules

def test_sentence_split_keeps_decimals_and_abbreviations():
    report = "Hemoglobin 13.5 g/dL, e.g. stable. Nodule vs. scar. Creatinine 1.1 mg/dL."
    sentences = [report[start:end] for start, end in split_sentences(report)]
    assert sentences == ["Hemoglobin 13.5 g/dL, e.g. stable", "Nodule vs. scar", "Creatinine 1.1 mg/dL"]


@pytest.mark.parametrize(
    "sentence, entity, expected",
    [
        ("No evidence of pneumothorax.", "Pneumothorax", {"negation": "NEGATED", "certainty": "CERTAIN"}),
        ("History of atrial fibrillation.", "Atrial fibrillation", {"temporality": "HISTORICAL"}),
        ("Rule out pulmonary embolism.", "Pulmonary embolism", {"certainty": "HYPOTHETICAL", "negation": "AFFIRMED"}),
        ("Suspected consolidation.", "Consolidation", {"certainty": "UNCERTAIN"}),
        ("Findings consistent with pneumonia.", "Pneumonia", {"certainty": "UNCERTAIN"}),
        ("Hepatic steatosis cannot be excluded.", "Hepatic steatosis", {"certainty": "UNCERTAIN", "negation": "AFFIRMED"}),
        ("Fracture is unlikely.", "Fracture", {"negation": "NEGATED"}),
        ("The nodule is stable compared with prior study.", "Nodule", {"comparison": "STABLE"}),
        ("Previously observed lesion has increased.", "Lesion", {"comparison": "INCREASED", "temporality": "CURRENT"}),
        ("The pancreatitis has resolved.", "Pancreatitis", {"comparison": "RESOLVED", "temporality": "HISTORICAL"}),
        ("Family history of colon cancer.", "Malignancy", {"experiencer": "FAMILY"}),
        ("Postoperative change after cholecystectomy.", "Hepatobiliary surgery", {"temporality": "HISTORICAL"}),
    ],
)
def test_context_rules_do_not_turn_hedges_into_diagnoses(sentence, entity, expected):
    statement = _statement(sentence, entity)
    for key, value in expected.items():
        assert statement[key] == value, (sentence, key, statement[key])


def test_negation_scope_ends_at_terminator():
    statement = _statement("No hydronephrosis; however, a renal calculus is present.", "Urinary tract calculus")
    assert statement["negation"] == "AFFIRMED"


def test_documented_site_resolves_to_atlas_structure_with_laterality():
    statement = _statement("A nodule in the right upper lobe.", "Nodule")
    assert statement["anatomy_system"] == "lungs"
    assert statement["atlas_structure_id"] == "visceral.superior_lobe_of_right_lung"
    kidney = _statement("Calculus in the left kidney.", "Calculus")
    assert kidney["anatomy_system"] == "kidneys"
    assert kidney["atlas_structure_id"] == "visceral.kidney_l"


@pytest.mark.parametrize(
    "text_value",
    ["Collected: 2026-02-03.", "Hemoglobin 13.2 g/dL (13.0-17.0).", "Platelets 250 (150.0-400.0).", "Record of prior imaging reviewed."],
)
def test_deidentification_keeps_dates_ranges_and_prose(text_value):
    from app.services.nlp_processor import deidentify_text

    assert deidentify_text(text_value) == text_value


@pytest.mark.parametrize(
    "text_value, marker",
    [("Call +1 (555) 123-4567 today.", "[REDACTED_PHONE]"), ("MRN: 00123456", "[REDACTED_ID]"), ("Contact a.b@example.org", "[REDACTED_EMAIL]")],
)
def test_deidentification_masks_identifiers(text_value, marker):
    from app.services.nlp_processor import deidentify_text

    assert marker in deidentify_text(text_value)


def test_measurements_capture_documented_reference_flag_and_code_without_inference():
    report = (
        "Hemoglobin 11.2 g/dL L (13.0-17.0). Creatinine 1.8 mg/dL H (0.7-1.3). LVEF 55-60%. "
        "The lesion has increased from 8 mm. A 1.4 x 0.9 cm nodule. INR 1.1. Heart rate | 72 bpm."
    )
    by_name = {item["name"]: item for item in extract_numeric_measurements(report)}
    assert by_name["hemoglobin"]["reference_low"] == 13.0 and by_name["hemoglobin"]["reference_high"] == 17.0
    assert by_name["hemoglobin"]["documented_flag"] == "LOW"
    assert by_name["hemoglobin"]["canonical_code"] == "718-7"
    assert by_name["hemoglobin"]["result_operator"] == "="
    assert by_name["creatinine"]["documented_flag"] == "HIGH"
    assert "ejection_fraction" not in by_name, "a documented range must not be reduced to one value"
    assert "lesion_size" not in by_name, "a prior value referenced with 'from' is not the current size"
    assert by_name["nodule_size"]["value"] == 14.0 and by_name["nodule_size"]["unit"] == "mm"
    assert by_name["inr"]["unit"] == "{ratio}"
    assert by_name["heart_rate"]["value"] == 72.0
    for item in by_name.values():
        assert report[item["source_span_start"]:item["source_span_end"]] == item["source_span"]


def test_documented_dates_and_age_are_parsed_conservatively():
    attributes = extract_documented_attributes("Collected: 2026-01-12. Sample date 03/04/2026. Age: 93. 54-year-old female.")
    sampling = [item for item in attributes if item["name"] == "sampling_date"]
    assert sampling[0]["value_text"] == "2026-01-12"
    assert sampling[1]["value_text"] is None and sampling[1]["parse_status"] == "AMBIGUOUS_DAY_MONTH_ORDER"
    ages = {item["raw_text"]: item for item in attributes if item["name"] == "age_years"}
    assert ages["93"]["value_number"] is None and ages["93"]["value_text"] == "90+"
    assert any(item["name"] == "sex" and item["value_text"] == "female" for item in attributes)


# ----------------------------------------------------------- calculators

def test_ckd_epi_2021_matches_published_reference_values():
    # NKF CKD-EPI 2021 calculator: 50-year-old, serum creatinine 1.0 mg/dL.
    assert round(ckd_epi_2021(1.0, 50, "male")) == 92
    assert round(ckd_epi_2021(1.0, 50, "female")) == 69


def test_egfr_requires_every_documented_input(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-EGFR")
    upload = _upload(client, headers, case["id"], "renal.txt", b"Creatinine 1.0 mg/dL. 50-year-old.", "text/plain").json()
    _analyse(client, headers, upload["id"])
    missing = client.get(f"/api/v1/cases/{case['id']}/calculations/egfr", headers=headers).json()
    assert missing["status"] == "INSUFFICIENT_EVIDENCE"
    assert missing["results"][0]["value"] is None
    assert "SEX_NOT_DOCUMENTED" in missing["results"][0]["missing_or_invalid_inputs"]

    complete = _upload(client, headers, case["id"], "renal-2.txt", b"Creatinine 88.42 umol/L. Age/Sex: 50/M.", "text/plain").json()
    _analyse(client, headers, complete["id"])
    result = client.get(f"/api/v1/cases/{case['id']}/calculations/egfr", headers=headers).json()
    computed = [item for item in result["results"] if item["status"] == "COMPUTED_FROM_DOCUMENTED_INPUTS"]
    assert computed and all(round(item["value"]) == 92 for item in computed)
    assert computed[0]["interpretation"] is None


def test_egfr_refuses_an_age_its_own_document_contradicts(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-EGFR-AGES")
    packet = b"Creatinine 1.2 mg/dL. Age: 75yrs & Sex: Female\nAge&Sex: 5Yrs/Female"
    upload = _upload(client, headers, case["id"], "packet.txt", packet, "text/plain").json()
    _analyse(client, headers, upload["id"])
    result = client.get(f"/api/v1/cases/{case['id']}/calculations/egfr", headers=headers).json()["results"][0]
    assert result["value"] is None
    assert "AGE_CONFLICTING (5, 75)" in result["missing_or_invalid_inputs"]


# --------------------------------------------------------------- trends

def test_biomarker_trend_statistics_are_tiered_and_unit_safe(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-TRENDS", ["2025-01-01T09:00:00Z", "2025-04-01T09:00:00Z", "2025-07-01T09:00:00Z"])
    exams = case["examinations"]
    for exam, value_line in zip(exams, (b"Creatinine 1.0 mg/dL.", b"Creatinine 106.1 umol/L.", b"Creatinine 1.4 mg/dL.")):
        line = b"Specimen: serum\nMethod: enzymatic assay\n" + value_line
        upload = _upload(client, headers, case["id"], f"cr-{exam['id']}.txt", line, "text/plain", exam["id"]).json()
        _analyse(client, headers, upload["id"])
    series = {item["name"]: item for item in client.get(f"/api/v1/cases/{case['id']}/biomarker-trends", headers=headers).json()["series"]}
    creatinine = series["creatinine"]
    assert creatinine["unit"] == "mg/dL"
    assert creatinine["conversions"] == ["µmol/L -> mg/dL"]
    assert pytest.approx(creatinine["points"][1]["value"], rel=1e-3) == 1.2
    analysis = creatinine["analysis"]
    assert analysis["n"] == 3 and analysis["status"] == "COMPUTED"
    assert pytest.approx(analysis["absolute_change"], rel=1e-6) == 0.4
    assert analysis["ols"]["status"] == "COMPUTED" and analysis["theil_sen"]["status"] == "COMPUTED"
    assert analysis["mann_kendall"]["status"] == "INSUFFICIENT_OBSERVATIONS"
    assert analysis["interpretation"] is None


def test_biomarker_trend_abstains_when_lab_context_is_not_documented(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-TREND-CONTEXT", ["2025-01-01T09:00:00Z", "2025-02-01T09:00:00Z"])
    for exam, line in zip(case["examinations"], (b"Creatinine 1.0 mg/dL.", b"Creatinine 1.2 mg/dL.")):
        upload = _upload(client, headers, case["id"], f"missing-{exam['id']}.txt", line, "text/plain", exam["id"]).json()
        _analyse(client, headers, upload["id"])
    series = {item["name"]: item for item in client.get(f"/api/v1/cases/{case['id']}/biomarker-trends", headers=headers).json()["series"]}
    assert series["creatinine"]["analysis"]["status"] == "COMPARABILITY_NOT_ESTABLISHED"
    assert set(series["creatinine"]["comparability_blockers"]) == {"SPECIMEN_NOT_DOCUMENTED", "LABORATORY_METHOD_NOT_DOCUMENTED"}


# ------------------------------------------------------------- anatomy map

def test_anatomy_mapping_requires_clinician_confirmation_for_regions(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-ANATOMY-MAP")
    report = b"A nodule in the right upper lobe. Family history of colon cancer. HbA1c 7.4 %. Creatinine 1.2 mg/dL."
    upload = _upload(client, headers, case["id"], "map.txt", report, "text/plain").json()
    job = _analyse(client, headers, upload["id"])
    evidence = client.get(f"/api/v1/cases/{case['id']}/anatomy-evidence", headers=headers).json()
    lungs = evidence["systems"]["lungs"]
    nodule = next(item for item in lungs["items"] if item["label"] == "Nodule")
    assert nodule["mapping_category"] == "SCHEMATIC_ORGAN_ASSOCIATION"
    assert nodule["mapping_state"] == "SCHEMATIC_ORGAN_ONLY"
    assert nodule["candidate_atlas_structure_id"] == "visceral.superior_lobe_of_right_lung"
    assert nodule["atlas_structure_id"] is None and nodule["clinician_confirmation"] is None
    assert len(nodule["source_hash"]) == 64 and nodule["extractor_version"]
    assert evidence["mapping_states"] == ["SPATIALLY_REGISTERED", "REGION_VERIFIED", "SCHEMATIC_ORGAN_ONLY", "NOT_MAPPABLE"]
    assert lungs["state_counts"]["SCHEMATIC_ORGAN_ONLY"] >= 1
    assert lungs["highlight"]["spatially_registered"] == []
    assert any(item["reason"] == "FAMILY_HISTORY_NOT_PATIENT_EVIDENCE" for item in evidence["excluded"])
    hba1c = next(item for item in evidence["unsupported"] if item["label"] == "Hemoglobin A1c")
    assert hba1c["reason"].startswith("Metabolic marker")
    assert evidence["systems"]["pancreas"]["counts"]["SCHEMATIC_ORGAN_ASSOCIATION"] == 0
    assert any(item["label"] == "Creatinine" for item in evidence["systems"]["kidneys"]["items"])

    finding_id = job["findings"][0]["id"]
    review = client.post(f"/api/v1/reviews/{finding_id}", json={"review_status": "CONFIRMED"}, headers=headers)
    assert review.status_code in (200, 201), review.text
    confirmed = client.get(f"/api/v1/cases/{case['id']}/anatomy-evidence", headers=headers).json()
    nodule = next(item for item in confirmed["systems"]["lungs"]["items"] if item["label"] == "Nodule")
    assert nodule["mapping_category"] == "VERIFIED_ANATOMICAL_REGION"
    assert nodule["mapping_state"] == "REGION_VERIFIED"
    assert nodule["clinician_confirmation"]["status"] == "CONFIRMED"
    assert nodule["clinician_confirmation"]["scope"] == "FINDING_LEVEL"
    assert nodule["clinician_confirmation"]["original_output_preserved"] is True
    assert confirmed["systems"]["lungs"]["highlight"]["verified_structures"] == ["visceral.superior_lobe_of_right_lung"]


# -------------------------------------------------------------- prognosis

def test_prognosis_registry_covers_ten_organs_without_forecasts(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    registry = client.get("/api/v1/prognosis/capabilities", headers=headers).json()
    assert {item["organ_system"] for item in registry["capabilities"]} == {"heart", "lungs", "brain", "liver", "pancreas", "intestines", "nervous", "skeletal", "hybrid", "kidneys"}
    for capability in registry["capabilities"]:
        assert capability["trained_model_status"] == "NOT_TRAINED"
        assert capability["forecast_2d"]["status"] == capability["forecast_3d"]["status"] == "UNAVAILABLE"
        for field in ("outcome_variables", "suitable_data", "candidate_models", "applicable_population", "required_inputs", "forecast_horizon", "uncertainty_method", "treatment_comparison"):
            assert field in capability

    case = _case(client, headers, "CASE-PROGNOSIS", ["2025-01-01T09:00:00Z"])
    upload = _upload(client, headers, case["id"], "renal.txt", b"Creatinine 1.3 mg/dL.", "text/plain", case["examinations"][0]["id"]).json()
    _analyse(client, headers, upload["id"])
    result = client.post("/api/v1/prognosis/evaluate", json={"case_id": case["id"], "organ_system": "kidneys", "horizon_days": 365, "intervention_id": "sglt2"}, headers=headers).json()
    assert result["observed"]["status"] == "OBSERVED"
    assert result["scenarios"]["A"]["forecast"] is None and result["scenarios"]["B"]["forecast"] is None
    assert "MODEL_NOT_VALIDATED" in result["scenarios"]["A"]["reason_codes"]
    assert "ESTIMAND_UNDEFINED" in result["scenarios"]["B"]["reason_codes"]
    assert result["treatment_effect"]["estimate"] is None
    history = client.get(f"/api/v1/cases/{case['id']}/prognosis-evaluations", headers=headers).json()
    assert history[0]["id"] == result["evaluation_id"]
    provenance = client.get(f"/api/v1/cases/{case['id']}/provenance", headers=headers).json()
    assert "PROGNOSIS_EVALUATION_REQUESTED" in {event["action"] for event in provenance}


def test_model_registry_uses_the_medtwin2_state_vocabulary(client, test_users):
    from app.services.model_registry import REGISTRY_STATES

    models = client.get("/api/v1/models", headers=get_auth_headers(test_users["clinician_a"])).json()["models"]
    states = {model["model_id"]: model["registry_state"] for model in models}
    assert set(states.values()) <= set(REGISTRY_STATES)
    assert states["mura_study_baseline"] == "CHECKPOINT_MISSING"
    assert states["medcat_adapter"] == "DEPENDENCY_MISSING"
    assert not any(model["activation"]["eligible"] for model in models)


def test_risk_registry_computes_no_score(client, test_users):
    registry = client.get("/api/v1/risk/registry", headers=get_auth_headers(test_users["clinician_a"])).json()
    assert registry["models"] and all(model["output"] is None and model["status"] == "NOT_COMPUTED" for model in registry["models"])


# ------------------------------------------------------------- evaluation

def test_classification_metrics_match_hand_computed_values():
    result = evaluate_classification(b"y_true,y_score\n0,0.1\n0,0.4\n1,0.35\n1,0.8\n")
    assert pytest.approx(result["metrics"]["auroc"]) == 0.75
    assert pytest.approx(result["metrics"]["auprc_average_precision"], abs=1e-4) == 0.8333
    assert result["confusion_matrix"] == {"tp": 1, "fp": 0, "tn": 2, "fn": 1}
    assert result["metrics"]["sensitivity_recall"] == 0.5 and result["metrics"]["specificity"] == 1.0
    assert result["confidence_intervals_95"]["status"] == "NOT_COMPUTED_SMALL_SAMPLE"
    # Eq. (12): Brier = mean((p - y)^2) = (0.01 + 0.16 + 0.4225 + 0.04) / 4; ECE over 10 equal-width
    # bins, one row per bin here, = (0.1 + 0.4 + 0.65 + 0.2) / 4.
    assert pytest.approx(result["metrics"]["brier_score"]) == 0.158125
    assert pytest.approx(result["calibration"]["expected_calibration_error"]) == 0.3375


def test_bootstrap_intervals_are_reproducible_and_cluster_aware():
    rng = np.random.default_rng(7)
    rows = ["y_true,y_score,group_id"]
    for index in range(60):
        label = index % 2
        rows.append(f"{label},{min(1, max(0, 0.3 + 0.4 * label + rng.normal(0, 0.2))):.4f},p{index // 3}")
    content = "\n".join(rows).encode()
    first = evaluate_classification(content, rounds=300, seed=11)
    second = evaluate_classification(content, rounds=300, seed=11)
    assert first["confidence_intervals_95"]["auroc"] == second["confidence_intervals_95"]["auroc"]
    assert first["bootstrap"]["unit"] == "group_id" and first["n_groups"] == 20
    low, high = first["confidence_intervals_95"]["auroc"]["low"], first["confidence_intervals_95"]["auroc"]["high"]
    assert low <= first["metrics"]["auroc"] <= high


def test_regression_survival_and_segmentation_metrics():
    regression = evaluate_regression(b"y_true,y_pred,lower,upper\n1,2,0,3\n2,2,1,3\n3,5,4,6\n", alpha=0.1)
    assert pytest.approx(regression["metrics"]["mae"]) == 1.0
    assert pytest.approx(regression["metrics"]["rmse"]) == np.sqrt(5 / 3)
    assert pytest.approx(regression["prediction_intervals"]["coverage"]) == 2 / 3
    survival = evaluate_survival(b"time,event,risk_score\n1,1,0.9\n2,1,0.5\n3,0,0.1\n")
    assert survival["metrics"]["harrell_c_index"] == 1.0

    from PIL import Image

    def png(mask):
        buffer = BytesIO()
        Image.fromarray((mask * 255).astype(np.uint8)).save(buffer, format="PNG")
        return buffer.getvalue()

    reference = np.zeros((20, 20), dtype=np.uint8)
    reference[5:15, 5:15] = 1
    shifted = np.zeros_like(reference)
    shifted[5:15, 7:17] = 1
    identical = evaluate_segmentation(png(reference), png(reference))
    assert identical["metrics"]["dice"] == 1.0 and identical["metrics"]["hausdorff"] == 0.0
    moved = evaluate_segmentation(png(reference), png(shifted), spacing=(0.5, 0.5), unit="mm")
    assert pytest.approx(moved["metrics"]["dice"]) == 0.8
    assert pytest.approx(moved["metrics"]["hausdorff"]) == 1.0


def test_evaluation_runs_are_persisted_with_input_hash(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    content = b"y_true,y_score\n0,0.1\n0,0.4\n1,0.35\n1,0.8\n"
    response = client.post("/api/v1/evaluation/classification", files={"file": ("held_out.csv", content, "text/csv")}, data={"dataset_label": "synthetic test fixture"}, headers=headers)
    assert response.status_code == 200, response.text
    run = response.json()
    assert len(run["input_sha256"]) == 64
    listed = client.get("/api/v1/evaluation/runs", headers=headers).json()
    assert listed[0]["run_id"] == run["run_id"]
    bad = client.post("/api/v1/evaluation/classification", files={"file": ("bad.csv", b"y_true,y_score\n2,0.1\n0,0.3\n", "text/csv")}, headers=headers)
    assert bad.status_code == 422
    assert run["evaluation_context"]["reporting_status"] == "EXPLORATORY"


def test_validation_kit_formats_are_accepted_and_context_gates_reporting(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    kit_rows = b"patient_id,y_true,score\np1,0,0.1\np1,0,0.4\np2,1,0.35\np2,1,0.8\n"
    context = {"dataset_label": "synthetic test fixture", "dataset_version": "1", "split": "test", "checkpoint": "sha256:" + "0" * 64}
    response = client.post("/api/v1/evaluation/classification", files={"file": ("kit.csv", kit_rows, "text/csv")}, data=context, headers=headers)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["n_groups"] == 2 and pytest.approx(run["metrics"]["auroc"]) == 0.75
    assert run["evaluation_context"]["reporting_status"] == "EXPLORATORY"
    assert {
        "model_id",
        "checkpoint_sha256_zero",
        "dataset_not_registered",
    }.issubset(run["evaluation_context"]["reporting_blockers"])
    assert run["accuracy_target"]["ci_lower_bound_exceeds"] is None  # no interval at n = 4, so no claim
    validation_split = client.post("/api/v1/evaluation/classification", files={"file": ("kit.csv", kit_rows, "text/csv")}, data={**context, "split": "validation"}, headers=headers).json()
    assert "held_out_test_split" in validation_split["evaluation_context"]["reporting_blockers"]
    revision = run["evaluation_context"]["code_revision"]
    assert revision["source"] in {"git", "MEDTWIN_CODE_COMMIT", "NOT_RECORDED"}
    assert (revision["commit"] is None) == ("CODE_COMMIT_NOT_RECORDED" in run["evaluation_context"]["reproducibility_warnings"])


def test_traceability_matrix_cites_only_real_code_and_tests():
    """Every module path, test reference and artifact in the matrix must exist."""
    from app.config import PROJECT_ROOT
    import re

    matrix = json.loads((PROJECT_ROOT / "docs" / "research" / "traceability.json").read_text(encoding="utf-8"))
    allowed = set(matrix["status_definitions"])
    assert allowed == {"IMPLEMENTED_AND_TESTED", "IMPLEMENTED_NOT_VALIDATED", "PARTIALLY_IMPLEMENTED", "PROPOSED_ONLY", "UNSUPPORTED"}
    ids = [claim["id"] for claim in matrix["claims"]]
    assert len(ids) == 56
    assert len(ids) == len(set(ids))
    assert matrix["manuscript"].startswith("MedTwin_2_Software_Only_IEEE_Revised_Research_Draft.docx")
    assert "Eq. 1-16" in matrix["earlier_manuscript_traceability"]
    assert "Eq. 1-12" in matrix["earlier_manuscript_traceability"]
    assert {claim["equation"] for claim in matrix["claims"] if claim.get("equation")} == {
        "Eq. (1)", "Eq. (2)", "Eq. (3)", "Eq. (4)", "Eq. (5)",
        "Eq. (5)-(6)", "Eq. (7)-(9)", "Eq. (10)", "Eq. (11)", "Eq. (12)",
    }
    for claim in matrix["claims"]:
        assert claim["status"] in allowed, claim["id"]
        for module in filter(None, (part.strip() for part in claim["module"].split(";"))):
            assert (PROJECT_ROOT / module).is_file(), f"{claim['id']}: {module}"
        for item in claim["evidence"]:
            path, _, test = item.partition("::")
            assert (PROJECT_ROOT / path).is_file(), f"{claim['id']}: {path}"
            if test:
                source = (PROJECT_ROOT / path).read_text(encoding="utf-8")
                assert re.search(rf"^def {re.escape(test)}\(", source, re.MULTILINE), f"{claim['id']}: {item}"
        if claim["status"] == "IMPLEMENTED_AND_TESTED":
            assert claim["evidence"], f"{claim['id']} is marked tested without evidence"


def test_forecast_errors_are_reported_per_target_and_horizon():
    rows = b"patient_id,target,horizon,y_true,y_pred\np1,egfr,90d,60,58\np2,egfr,90d,50,53\np1,hba1c,180d,7.0,7.5\n"
    result = evaluate_forecast(rows)
    groups = {(group["target"], group["horizon"]): group for group in result["per_target_and_horizon"]}
    assert pytest.approx(groups[("egfr", "90d")]["mae"]) == 2.5
    assert pytest.approx(groups[("egfr", "90d")]["rmse"]) == (6.5) ** 0.5
    assert pytest.approx(groups[("hba1c", "180d")]["mae"]) == 0.5
    assert "mae" not in result["metrics"]  # never pooled across targets with different units


def test_lab_extraction_audit_counts_missed_values_and_rejects_duplicates():
    header = b"patient_id,source_id,analyte_code,reference_value,predicted_value,reference_unit,predicted_unit\n"
    result = evaluate_lab_extraction(header + b"p1,r1,2160-0,1.1,1.1,mg/dL,mg/dl\np1,r1,718-7,13.5,,g/dL,g/dL\np2,r2,2160-0,0.9,0.95,mg/dL,mg/dL\n", abs_tolerance=0.0)
    assert result["metrics"]["matched_correct"] == 1
    assert pytest.approx(result["metrics"]["extracted_numeric_rate"]) == 2 / 3
    with pytest.raises(EvaluationInputError):
        evaluate_lab_extraction(header + b"p1,r1,2160-0,1.1,1.1,mg/dL,mg/dL\np1,r1,2160-0,1.1,1.1,mg/dL,mg/dL\n")


def _png(array) -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.fromarray(np.asarray(array, dtype=np.uint8)).save(buffer, format="PNG")
    return buffer.getvalue()


def _bmp(array) -> bytes:
    from PIL import Image

    buffer = BytesIO()
    Image.fromarray(np.asarray(array, dtype=np.uint8)).save(buffer, format="BMP")
    return buffer.getvalue()


def test_segmentation_follows_the_kit_empty_mask_convention_and_rejects_soft_masks():
    empty = _png(np.zeros((8, 8)))
    assert evaluate_segmentation(empty, empty)["metrics"]["dice"] == 1.0
    square = np.zeros((8, 8))
    square[2:6, 2:6] = 255
    assert evaluate_segmentation(_png(square), empty)["metrics"]["dice"] == 0.0
    soft = square.copy()
    soft[2, 2] = 128
    with pytest.raises(EvaluationInputError):
        evaluate_segmentation(_png(soft), _png(square))


def test_segmentation_batch_reports_nonempty_only_means():
    import zipfile

    square = np.zeros((8, 8))
    square[2:6, 2:6] = 255
    shifted = np.zeros((8, 8))
    shifted[2:6, 3:7] = 255
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.csv", "patient_id,reference_mask,predicted_mask\np1,ref/a.png,pred/a.png\np2,ref/b.png,pred/b.png\n")
        archive.writestr("ref/a.png", _png(square))
        archive.writestr("pred/a.png", _png(shifted))
        archive.writestr("ref/b.png", _png(np.zeros((8, 8))))
        archive.writestr("pred/b.png", _png(np.zeros((8, 8))))
    result = evaluate_segmentation_batch(buffer.getvalue())
    metrics = result["metrics"]
    assert pytest.approx(metrics["mean_dice_nonempty_reference"]) == 0.75  # 2*12/(16+16)
    assert pytest.approx(metrics["mean_dice"]) == (0.75 + 1.0) / 2
    assert metrics["n_empty_reference_masks"] == 1


def test_coco_detection_uses_the_standard_evaluator(client, test_users):
    reference = {
        "images": [{"id": 1, "width": 100, "height": 100}, {"id": 2, "width": 100, "height": 100}],
        "categories": [{"id": 1, "name": "fixture_box"}],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 10, 40, 40], "iscrowd": 0},
            {"id": 2, "image_id": 2, "category_id": 1, "bbox": [20, 20, 30, 30], "iscrowd": 0},
        ],
    }
    exact = [{"image_id": 1, "category_id": 1, "bbox": [10, 10, 40, 40], "score": 0.9}, {"image_id": 2, "category_id": 1, "bbox": [20, 20, 30, 30], "score": 0.8}]
    result = evaluate_detection(json.dumps(exact).encode(), json.dumps(reference).encode())
    assert pytest.approx(result["metrics"]["map_50_95"]) == 1.0
    assert result["reference_area_derived_from_bbox"] == 2
    missed = evaluate_detection(json.dumps(exact[:1]).encode(), json.dumps(reference).encode())
    assert missed["metrics"]["ar_100"] == pytest.approx(0.5)
    headers = get_auth_headers(test_users["clinician_a"])
    response = client.post(
        "/api/v1/evaluation/detection/coco",
        files={"predictions": ("pred.json", json.dumps(exact).encode(), "application/json"), "annotations": ("ref.json", json.dumps(reference).encode(), "application/json")},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["task_type"] == "detection"


# ---------------------------------------------------------------- imaging

def _dicom_bytes(patient_name: str = "") -> bytes:
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = CTImageStorage
    dataset.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    dataset.Modality = "CT"
    dataset.BodyPartExamined = "CHEST"
    dataset.PatientName = patient_name
    dataset.Rows, dataset.Columns = 8, 8
    dataset.PixelSpacing = [0.7, 0.6]
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.BitsAllocated, dataset.BitsStored, dataset.HighBit, dataset.PixelRepresentation = 16, 16, 15, 1
    dataset.RescaleSlope, dataset.RescaleIntercept = 1, -1024
    dataset.PixelData = (np.arange(64, dtype=np.int16) * 20).tobytes()
    buffer = BytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def test_dicom_upload_metadata_render_and_identifier_warning(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-DICOM")
    upload = _upload(client, headers, case["id"], "slice.dcm", _dicom_bytes("Synthetic^Fixture"), "application/dicom")
    assert upload.status_code == 201, upload.text
    metadata = client.get(f"/api/v1/uploads/{upload.json()['id']}/imaging/metadata", headers=headers).json()
    assert metadata["container"] == "DICOM" and metadata["modality_tag"] == "CT"
    assert metadata["spacing_mm"] == [0.6, 0.7]
    assert metadata["body_part_systems"] == ["lungs", "heart"]
    assert metadata["deidentification_warnings"] == ["PatientName is present and non-empty"]
    assert "PatientName" not in json.dumps(metadata.get("technical_tags", {}))
    assert metadata["inference"]["status"] == "MODEL_NOT_VALIDATED"
    rendered = client.get(f"/api/v1/uploads/{upload.json()['id']}/imaging/render", headers=headers)
    assert rendered.status_code == 200 and rendered.content.startswith(b"\x89PNG")
    info = json.loads(rendered.headers["X-MedTwin-Render"])
    assert info["rescale"]["units"] == "HU" and info["pixel_spacing_mm"] == [0.6, 0.7]


def test_nifti_volume_metadata_and_slices(client, test_users):
    import nibabel as nib

    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-NIFTI")
    volume = nib.Nifti1Image(np.arange(4 * 5 * 6, dtype=np.int16).reshape(4, 5, 6), affine=np.diag([0.8, 0.9, 2.0, 1.0]))
    upload = _upload(client, headers, case["id"], "volume.nii", volume.to_bytes(), "application/octet-stream")
    assert upload.status_code == 201, upload.text
    metadata = client.get(f"/api/v1/uploads/{upload.json()['id']}/imaging/metadata", headers=headers).json()
    assert metadata["dimensions"] == [4, 5, 6]
    assert metadata["spacing_mm"] == [0.8, 0.9, 2.0]
    assert metadata["orientation"] == "RAS"
    sagittal = client.get(f"/api/v1/uploads/{upload.json()['id']}/imaging/render?axis=sagittal&index=1", headers=headers)
    assert sagittal.status_code == 200
    assert json.loads(sagittal.headers["X-MedTwin-Render"])["slice_count"] == 4


def test_content_signature_must_match_extension(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-SIGNATURE")
    disguised = _upload(client, headers, case["id"], "scan.png", b"%PDF-1.7 not an image", "image/png")
    assert disguised.status_code == 415
    no_preamble = _upload(client, headers, case["id"], "bare.dcm", b"\x08\x00\x05\x00" + b"\0" * 200, "application/dicom")
    assert no_preamble.status_code == 415


def test_bmp_microscopy_upload_is_validated_and_readable(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-BMP")
    image = np.arange(8 * 9, dtype=np.uint8).reshape(8, 9)
    upload = _upload(client, headers, case["id"], "cell.bmp", _bmp(image), "image/bmp")
    assert upload.status_code == 201, upload.text
    metadata = client.get(f"/api/v1/uploads/{upload.json()['id']}/imaging/metadata", headers=headers)
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["container"] == "BMP"
    assert metadata.json()["dimensions"] == [9, 8]
    disguised = _upload(client, headers, case["id"], "fake.bmp", b"not a bitmap", "image/bmp")
    assert disguised.status_code == 415


def test_modality_registry_separates_formats_from_model_coverage(client, test_users):
    registry = client.get("/api/v1/modalities", headers=get_auth_headers(test_users["clinician_a"])).json()
    modalities = {item["id"]: item for item in registry["modalities"]}
    for required in ("CT", "MRI", "XRAY", "US", "PET", "XA", "ENDOSCOPY", "MICROSCOPY", "ECG", "EEG", "DOCUMENT", "FHIR", "HL7V2"):
        assert modalities[required]["file_support_status"] == "SUPPORTED"
        assert modalities[required]["validated_tasks"] == []
    dicom_series = next(item for item in modalities["CT"]["supported_file_formats"] if item["format"] == "DICOM_SERIES")
    assert dicom_series["available"] is True
    assert dicom_series["upload_accepted"] is True
    assert "SeriesInstanceUID" in dicom_series["note"]
    assert "ImagePositionPatient" in dicom_series["note"]
    assert "No atomic series upload" in dicom_series["note"]
    wfdb = next(item for item in modalities["ECG"]["supported_file_formats"] if item["format"] == "WFDB")
    assert wfdb["available"] is True
    assert wfdb["library"] == "numpy"
    assert "plain WFDB format 16" in wfdb["note"]
    nifti = next(item for item in modalities["CT"]["supported_file_formats"] if item["format"] == "NIFTI")
    assert "NIfTI-1 only" in nifti["note"]
    pdf = next(item for item in modalities["DOCUMENT"]["supported_file_formats"] if item["format"] == "PDF")
    assert "RapidOCR" in pdf["note"]


def test_fhir_observations_import_with_codes_ranges_and_dates(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = _case(client, headers, "CASE-FHIR")
    bundle = {
        "resourceType": "Bundle",
        "entry": [
            {"resource": {"resourceType": "Observation", "code": {"coding": [{"system": "http://loinc.org", "code": "718-7", "display": "Hemoglobin"}]},
                          "valueQuantity": {"value": 12.1, "comparator": "<", "unit": "g/dL", "code": "g/dL"}, "effectiveDateTime": "2026-02-03T08:00:00Z",
                          "referenceRange": [{"low": {"value": 13.0}, "high": {"value": 17.0}}], "interpretation": [{"coding": [{"code": "L"}]}]}},
            {"resource": {"resourceType": "Observation", "code": {"text": "Blood pressure panel"}, "effectiveDateTime": "2026-02-03",
                          "component": [
                              {"code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"}]}, "valueQuantity": {"value": 131, "code": "mm[Hg]"}},
                              {"code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure"}]}, "valueQuantity": {"value": 84, "code": "mm[Hg]"}},
                          ]}},
        ],
    }
    upload = _upload(client, headers, case["id"], "observations.json", json.dumps(bundle).encode(), "application/fhir+json").json()
    _analyse(client, headers, upload["id"])
    measurements = {item["name"]: item for item in client.get(f"/api/v1/cases/{case['id']}/measurements", headers=headers).json()}
    assert measurements["hemoglobin"]["canonical_code"] == "718-7"
    assert measurements["hemoglobin"]["result_operator"] == "<"
    assert measurements["hemoglobin"]["documented_range_position"] == "INDETERMINATE_CENSORED_RESULT"
    assert measurements["hemoglobin"]["documented_flag"] == "LOW" and measurements["hemoglobin"]["documented_date"] == "2026-02-03"
    assert measurements["systolic_blood_pressure"]["unit"] == "mmHg" and measurements["diastolic_blood_pressure"]["value"] == 84
    assert all(item["extraction_method"] == "FHIR_OBSERVATION_IMPORT" for item in measurements.values())
    text_payload = client.get(f"/api/v1/uploads/{upload['id']}/text", headers=headers).json()
    span = measurements["hemoglobin"]
    assert text_payload["text"][span["source_span_start"]:span["source_span_end"]] == span["source_span"]


# ------------------------------------------------------- access and safety

def test_case_membership_viewer_reads_but_cannot_write(client, test_users, db_session):
    owner = get_auth_headers(test_users["clinician_a"])
    viewer = get_auth_headers(test_users["clinician_b"])
    case = _case(client, owner, "CASE-SHARED")
    assert client.get(f"/api/v1/cases/{case['id']}", headers=viewer).status_code == 403
    granted = client.post(f"/api/v1/cases/{case['id']}/members", json={"username": "clinician_b", "role": "VIEWER"}, headers=owner)
    assert granted.status_code == 201, granted.text
    assert client.get(f"/api/v1/cases/{case['id']}", headers=viewer).status_code == 200
    assert case["id"] in {item["id"] for item in client.get("/api/v1/cases", headers=viewer).json()}
    assert _upload(client, viewer, case["id"], "viewer.txt", b"Heart rate 70 bpm.", "text/plain").status_code == 403
    assert client.post(f"/api/v1/cases/{case['id']}/members", json={"username": "clinician_b", "role": "EDITOR"}, headers=viewer).status_code == 403
    client.post(f"/api/v1/cases/{case['id']}/members", json={"username": "clinician_b", "role": "EDITOR"}, headers=owner)
    assert _upload(client, viewer, case["id"], "editor.txt", b"Heart rate 70 bpm.", "text/plain").status_code == 201
    revoked = client.delete(f"/api/v1/cases/{case['id']}/members/{test_users['clinician_b'].id}", headers=owner)
    assert revoked.status_code == 204
    assert client.get(f"/api/v1/cases/{case['id']}", headers=viewer).status_code == 403


def test_migrations_add_columns_to_an_existing_v1_schema():
    from app.migrations import MIGRATIONS, run_migrations

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE clinical_report_statements (id INTEGER PRIMARY KEY, entity VARCHAR(128))"))
        connection.execute(text("CREATE TABLE medical_measurements (id INTEGER PRIMARY KEY, name VARCHAR(128))"))
        connection.execute(text("INSERT INTO clinical_report_statements (id, entity) VALUES (1, 'kept')"))
    applied = run_migrations(engine)
    assert applied == [version for version, _ in MIGRATIONS]
    columns = {item["name"] for item in inspect(engine).get_columns("clinical_report_statements")}
    assert {"certainty", "atlas_structure_id", "cues"} <= columns
    assert run_migrations(engine) == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT entity FROM clinical_report_statements WHERE id = 1")).scalar() == "kept"


def test_sliding_window_limiter_blocks_then_recovers():
    limiter = SlidingWindowLimiter()
    assert all(limiter.allow("login:1.2.3.4", 3, now=float(index)) for index in range(3))
    assert not limiter.allow("login:1.2.3.4", 3, now=3.0)
    assert limiter.allow("login:5.6.7.8", 3, now=3.0)
    assert limiter.allow("login:1.2.3.4", 3, now=61.0)


def test_security_headers_and_readiness(client, test_users):
    response = client.get("/api/v1/system/readiness")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["checks"]["database"]["ready"] is True


def test_research_analytics_charts_carry_provenance(client, test_users):
    payload = client.get("/api/v1/analytics/research", headers=get_auth_headers(test_users["clinician_a"])).json()
    charts = [item for section in payload["sections"].values() for item in section]
    assert charts
    for item in charts:
        for key in ("source", "sample_count", "analysis_population", "metric_definition", "limitations"):
            assert key in item["provenance"], (item["id"], key)
        if item["status"] == "NOT_AVAILABLE":
            assert item["data"] == []
    class_chart = next(item for item in payload["sections"]["datasets"] if item["id"] == "class_distribution")
    assert class_chart["status"] == "NOT_AVAILABLE"


@pytest.mark.skipif(not ANATOMY_MANIFEST_PATH.exists(), reason="anatomy manifest not generated in this checkout")
def test_anatomy_systems_list_the_ten_required_workspaces(client, test_users):
    payload = client.get("/api/v1/anatomy/systems", headers=get_auth_headers(test_users["clinician_a"])).json()
    assert [system["id"] for system in payload["systems"]] == ["heart", "lungs", "brain", "liver", "pancreas", "intestines", "nervous", "skeletal", "hybrid", "kidneys"]
    assert all(system["variants"] for system in payload["systems"])
    assert payload["representation_level"] == "L1_GENERIC_REFERENCE"


@pytest.mark.skipif(not ANATOMY_MANIFEST_PATH.exists(), reason="anatomy manifest not generated in this checkout")
def test_registration_review_records_the_reviewed_transform(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    review = client.post("/api/v1/anatomy/registration-reviews", json={"layer_id": "skeleton-projectkaizen-comparison", "decision": "NEEDS_LANDMARKS"}, headers=headers)
    assert review.status_code == 201, review.text
    body = review.json()
    assert body["transform"]["status"] == "UNREGISTERED_BBOX_SCALED"
    assert body["decision"] == "NEEDS_LANDMARKS"
    assert client.post("/api/v1/anatomy/registration-reviews", json={"layer_id": "skeleton", "decision": "REJECTED"}, headers=headers).status_code == 404
