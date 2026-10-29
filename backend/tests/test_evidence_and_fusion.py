"""
Evidence Integrity, Multimodal Fusion, and Gating Tests for MedTwin.
Directly validates the requirements specified in the IEEE manuscript:
1. Fusion abstains explicitly when no modality is valid (Eq. 9 not evaluated).
2. Single-modality cases do not pretend to have a multimodal fused result (NOT RUN).
3. Gated attention weights sum to 1.0; masked modalities receive 0.0 weight.
4. Report disagreement creates a review flag without automatically modifying either source.
5. Registration Gate enforces held-out TRE <= tau_TRE; failures yield NULL region and L1.
6. Forecasting requires at least 3 dated observations; rejects single examination inferences.
7. Unassociated files cannot enter case-level processing.
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
import torch
import pytest

from app.models.entities import (
    Case, Examination, UploadedFile, Finding, ClinicalReportStatement,
    ModalityType, EvidenceStatus, RepresentationLevel, LabInvestigationReport
)
from app.services.fusion_layer import GatedMultimodalFusionLayer
from app.services.fusion_service import evaluate_multimodal_fusion
from app.services.concordance_service import evaluate_report_concordance
from app.services.registration_service import (
    fit_rigid_transform_arun,
    compute_target_registration_error,
    evaluate_registration_gate
)
from app.services.forecasting_service import evaluate_case_forecasting
from app.services.ecg_processor import analyze_ecg_record, parse_and_validate_ecg, ECGQualityError
from app.services.image_processor import analyze_medical_image
from app.services.calibration_service import (
    compute_brier_score,
    compute_expected_calibration_error,
    apply_temperature_scaling
)
from tests.conftest import get_auth_headers


def test_fusion_abstention_on_zero_modalities(db_session, test_users):
    """
    IEEE Paper line 14: If sum(m_k) == 0, fusion returns ABSTAIN(missing input).
    Eq. 9 is NEVER evaluated.
    """
    user = test_users["clinician_a"]
    case = Case(pseudonymous_id="CASE-FUSION-ZERO", created_by_id=user.id)
    db_session.add(case)
    db_session.commit()

    result = evaluate_multimodal_fusion(case.id, db_session)
    assert result["fused_status"] == EvidenceStatus.ABSTAIN.value
    assert result["active_modalities_count"] == 0
    assert result["gated_weights"] is None
    assert "ABSTAIN" in result["abstention_reason"]


def test_fusion_not_run_on_single_modality(db_session, test_users):
    """
    IEEE Paper line 16: If sum(m_k) == 1, fusion is NOT RUN.
    Single-modality cases must not pretend to have a multimodal fused result.
    """
    user = test_users["clinician_a"]
    case = Case(pseudonymous_id="CASE-FUSION-ONE", created_by_id=user.id)
    db_session.add(case)
    db_session.commit()

    # Add single image finding
    finding_img = Finding(
        case_id=case.id,
        modality=ModalityType.IMAGE,
        category="Musculoskeletal Radiograph",
        label="Fracture / Cortical Disruption",
        raw_confidence=0.88,
        representation_level=RepresentationLevel.L1_GENERIC,
        mapping_status="L1",
        is_demo=True
    )
    db_session.add(finding_img)
    db_session.commit()

    result = evaluate_multimodal_fusion(case.id, db_session)
    assert result["fused_status"] == EvidenceStatus.NOT_RUN.value
    assert result["active_modalities_count"] == 1
    assert "Single modality" in result["abstention_reason"]
    assert result["fused_prediction"]["finding_label"] == "Fracture / Cortical Disruption"


def test_masked_gated_fusion_weights_sum_to_one(db_session, test_users):
    """
    Equations 8-10: When at least two modalities exist, gated weights alpha_k
    sum to exactly 1.0, and unavailable modalities have exactly 0.0 weight.
    """
    user = test_users["clinician_a"]
    case = Case(pseudonymous_id="CASE-FUSION-TWO", created_by_id=user.id)
    db_session.add(case)
    db_session.commit()

    # Add Image and ECG findings (REPORT is missing)
    finding_img = Finding(
        case_id=case.id,
        modality=ModalityType.IMAGE,
        category="Musculoskeletal Radiograph",
        label="Normal",
        raw_confidence=0.92,
        representation_level=RepresentationLevel.L1_GENERIC,
        mapping_status="L1",
        is_demo=True
    )
    finding_ecg = Finding(
        case_id=case.id,
        modality=ModalityType.ECG,
        category="Cardiac Rhythm",
        label="Normal Sinus Rhythm",
        raw_confidence=0.95,
        representation_level=RepresentationLevel.L1_GENERIC,
        mapping_status="L1",
        is_demo=True
    )
    db_session.add_all([finding_img, finding_ecg])
    db_session.commit()

    result = evaluate_multimodal_fusion(case.id, db_session)
    assert result["fused_status"] == EvidenceStatus.NOT_RUN.value
    assert result["active_modalities_count"] == 2
    assert result["gated_weights"] is None
    assert result["fused_prediction"] is None
    assert result["paired_data_validated"] is False

    # Test the equation with explicit synthetic tensors. The case service never
    # fabricates embeddings or a composite prediction.
    layer = GatedMultimodalFusionLayer()
    _, weights = layer(
        {"IMAGE": torch.ones(64), "ECG": torch.ones(64)},
        {"IMAGE": 1, "ECG": 1, "REPORT": 0},
    )
    assert weights["REPORT"] == 0.0 # Missing modality gets zero weight
    assert weights["IMAGE"] > 0.0
    assert weights["ECG"] > 0.0
    assert abs((weights["IMAGE"] + weights["ECG"] + weights["REPORT"]) - 1.0) < 1e-5


def test_report_concordance_flags_discordance_without_overwriting(db_session, test_users):
    """
    Algorithm 1 Line 17:
    Model finding disagrees with report statement -> flag REVIEW_DISCORDANCE.
    NEVER overwrite either original source.
    """
    user = test_users["clinician_a"]
    case = Case(pseudonymous_id="CASE-CONCORD-01", created_by_id=user.id)
    db_session.add(case)
    db_session.commit()

    # Model detected fracture
    finding_img = Finding(
        case_id=case.id,
        modality=ModalityType.IMAGE,
        category="Musculoskeletal Radiograph",
        label="Fracture / Structural Abnormality",
        raw_confidence=0.87,
        representation_level=RepresentationLevel.L1_GENERIC,
        mapping_status="L1",
        is_demo=True
    )
    db_session.add(finding_img)
    db_session.flush()

    # Clinical report negated fracture
    stmt = ClinicalReportStatement(
        finding_id=finding_img.id,
        case_id=case.id,
        entity="Fracture / Cortical Disruption",
        negation="NEGATED", # "No acute fracture identified"
        temporality="CURRENT",
        source_span="No acute fracture identified along the radial margin."
    )
    db_session.add(stmt)
    db_session.commit()

    concordance = evaluate_report_concordance(case.id, db_session)
    assert concordance["total_comparisons"] == 1
    assert concordance["discordant_count"] == 1
    
    item = concordance["items"][0]
    assert item["review_flag"] == "REVIEW_DISCORDANCE"
    assert item["is_discordant"] is True
    assert item["neither_source_overwritten"] is True

    # Verify both original sources remain unaltered
    refreshed_finding = db_session.query(Finding).filter(Finding.id == finding_img.id).first()
    refreshed_stmt = db_session.query(ClinicalReportStatement).filter(ClinicalReportStatement.id == stmt.id).first()
    assert refreshed_finding.label == "Fracture / Structural Abnormality"
    assert refreshed_stmt.negation == "NEGATED"


def test_anatomical_registration_gate_held_out_tre():
    """
    Equations 11-12 & Fig. 4:
    Registration gate tests held-out TRE against tau_TRE.
    - If TRE <= tau_TRE -> Grants L2 level and region.
    - If TRE > tau_TRE -> Reverts to L1 Generic, region is NULL.
    - Empty held-out landmarks -> Fails gate, region is NULL.
    """
    # 1. Ground truth transform: 90 deg rotation around Z + translation [5, 10, -3]
    R_true = np.array([
        [0.0, -1.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0]
    ])
    t_true = np.array([5.0, 10.0, -3.0])

    # 6 landmarks in model frame
    src_pts = np.array([
        [10.0, 0.0, 0.0],
        [0.0, 10.0, 0.0],
        [0.0, 0.0, 10.0],
        [10.0, 10.0, 0.0],
        [5.0, 5.0, 5.0],
        [-5.0, 8.0, 2.0]
    ])

    # Generate perfect target points with tiny noise (TRE < 1mm)
    tgt_pts_clean = (np.dot(R_true, src_pts.T)).T + t_true + np.random.normal(0, 0.05, src_pts.shape)

    # Low TRE alone is insufficient: unverified caller coordinates stay L1.
    unverified = evaluate_registration_gate(
        src_pts.tolist(),
        tgt_pts_clean.tolist(),
        tau_tre=5.0
    )
    assert unverified["registration_quality_passed"] is True
    assert unverified["passed_gate"] is False
    assert unverified["representation_level"] == "L1"
    assert unverified["assigned_region"] is None

    # A research-only L2 gate additionally requires explicit reviewed provenance,
    # an anatomical target and a declaration that Q was independent of fitting.
    gate_pass = evaluate_registration_gate(
        src_pts.tolist(),
        tgt_pts_clean.tolist(),
        tau_tre=5.0,
        requested_region="Synthetic test region",
        evidence_manifest_id="fixture-manifest-sha256",
        landmarks_are_independently_held_out=True,
    )
    assert gate_pass["passed_gate"] is True
    assert gate_pass["representation_level"] == "L2"
    assert gate_pass["assigned_region"] == "Synthetic test region"
    assert gate_pass["tre_error"] < 5.0

    # Generate heavily perturbed target points with high independent noise (simulating registration failure with TRE > 10mm)
    tgt_pts_noisy = tgt_pts_clean + np.random.normal(0.0, 15.0, src_pts.shape)
    gate_fail = evaluate_registration_gate(
        src_pts.tolist(),
        tgt_pts_noisy.tolist(),
        tau_tre=5.0
    )
    assert gate_fail["passed_gate"] is False
    assert gate_fail["representation_level"] == "L1"
    assert gate_fail["assigned_region"] is None
    assert "MAPPING_UNSUPPORTED" in gate_fail["mapping_status"]

    # Test Gate: Empty or insufficient points (< 4 landmarks)
    gate_insufficient = evaluate_registration_gate([[1, 2, 3]], [[1, 2, 3]])
    assert gate_insufficient["passed_gate"] is False
    assert gate_insufficient["representation_level"] == "L1"
    assert gate_insufficient["assigned_region"] is None


def test_forecasting_eligibility_enforcement(db_session, test_users):
    """
    Equations 13-14 & Algorithm 1 Line 18:
    Forecasting requires >= 3 dated observations.
    Single examination -> NOT ELIGIBLE.
    Two examinations -> NOT ELIGIBLE.
    Examination dates without source-linked numeric values remain NOT_ELIGIBLE.
    """
    user = test_users["clinician_a"]
    case = Case(pseudonymous_id="CASE-FORECAST-01", created_by_id=user.id)
    db_session.add(case)
    db_session.commit()

    now = datetime.now(timezone.utc)

    # 1. Single examination
    exam1 = Examination(case_id=case.id, exam_date=now - timedelta(days=200), modality=ModalityType.IMAGE)
    db_session.add(exam1)
    db_session.commit()

    fc_single = evaluate_case_forecasting(case.id, db_session)
    assert fc_single["eligibility_status"] == EvidenceStatus.NOT_ELIGIBLE.value
    assert "No source-linked numeric observations" in fc_single["ineligibility_reason"]
    assert fc_single["predicted_value"] is None

    # 2. Two examinations (< L_min = 3)
    exam2 = Examination(case_id=case.id, exam_date=now - timedelta(days=100), modality=ModalityType.IMAGE)
    db_session.add(exam2)
    db_session.commit()

    fc_two = evaluate_case_forecasting(case.id, db_session)
    assert fc_two["eligibility_status"] == EvidenceStatus.NOT_ELIGIBLE.value
    assert "No source-linked numeric observations" in fc_two["ineligibility_reason"]

    # 3. Three dated examinations still do not constitute three measurements
    exam3 = Examination(case_id=case.id, exam_date=now, modality=ModalityType.IMAGE)
    db_session.add(exam3)
    db_session.commit()

    fc_three = evaluate_case_forecasting(case.id, db_session)
    assert fc_three["eligibility_status"] == EvidenceStatus.NOT_ELIGIBLE.value
    assert fc_three["observations_count"] == 0
    assert fc_three["predicted_value"] is None
    assert fc_three["baseline_persistence"] is None
    assert fc_three["baseline_linear"] is None
    assert fc_three["mae_estimate"] is None
    assert fc_three["rmse_estimate"] is None
    assert "FORECAST UNAVAILABLE" in fc_three["notice"]

    # 4. Three dated, comparable lab results satisfy the data gate, but without a
    #    validated forecasting model no forecast or extrapolation is produced.
    for offset, value in ((300, 1.0), (200, 1.1), (100, 1.3)):
        db_session.add(LabInvestigationReport(
            case_id=case.id, lab_name="Test Fixture Laboratory", report_title="fixture", sample_type="Serum",
            collection_time=(now - timedelta(days=offset)).isoformat(),
            test_results_json={"results": [{"code": "CREAT", "test_name": "Creatinine", "unit": "mg/dL", "result_value": value}]},
        ))
    db_session.commit()
    fc_data = evaluate_case_forecasting(case.id, db_session, target_metric="CREAT", unit="mg/dL")
    assert fc_data["data_eligibility"] == "SUFFICIENT_OBSERVATIONS"
    assert fc_data["eligibility_status"] == EvidenceStatus.NOT_ELIGIBLE.value
    assert fc_data["ineligibility_reason"].startswith("MODEL_NOT_VALIDATED")
    assert fc_data["predicted_value"] is None and fc_data["baseline_linear"] is None
    assert [item["value"] for item in fc_data["chronological_series"]] == [1.0, 1.1, 1.3]


def test_valid_inputs_do_not_create_unconfigured_model_predictions(tmp_path):
    """Valid files are previewed, but unavailable models never emit diagnoses."""
    from PIL import Image

    image_path = tmp_path / "valid.png"
    Image.new("L", (32, 32), color=128).save(image_path)
    image_result = analyze_medical_image(image_path, "image-hash")
    assert image_result["evidence_status"] == EvidenceStatus.NOT_RUN.value
    assert image_result["label"] == "MODEL_UNAVAILABLE"
    assert image_result["raw_confidence"] is None
    assert image_result["visual_explanation_path"] is None

    ecg_path = tmp_path / "valid_ecg.csv"
    with open(ecg_path, "w") as handle:
        handle.write("time,Lead_I\n")
        for idx in range(100):
            handle.write(f"{idx * 0.004},{np.sin(idx / 8):.6f}\n")
    ecg_result = analyze_ecg_record(ecg_path, "ecg-hash")
    assert ecg_result["evidence_status"] == EvidenceStatus.NOT_RUN.value
    assert ecg_result["label"] == "MODEL_UNAVAILABLE"
    assert ecg_result["raw_confidence"] is None
    assert ecg_result["signal_metadata"]["signal_quality"] == "INPUT_VALIDATION_PASSED_NONDIAGNOSTIC"


def test_ecg_quality_rejection_rules(tmp_path):
    """
    ECG quality checks: flatlines and corrupted signals MUST be rejected.
    """
    # 1. Flatline test file
    flatline_file = tmp_path / "flatline_ecg.csv"
    with open(flatline_file, "w") as f:
        f.write("time,Lead_I,Lead_II\n")
        for i in range(100):
            f.write(f"{i*0.004},0.000000,0.000000\n")

    with pytest.raises(ECGQualityError) as exc_info:
        parse_and_validate_ecg(flatline_file)
    assert "flatline" in str(exc_info.value).lower()

    # 2. Extreme amplitude test file (> 10 mV)
    extreme_file = tmp_path / "extreme_ecg.csv"
    with open(extreme_file, "w") as f:
        f.write("time,Lead_I,Lead_II\n")
        for i in range(100):
            amp = 25.0 if i == 50 else 0.5
            f.write(f"{i*0.004},{amp},{amp}\n")

    with pytest.raises(ECGQualityError) as exc_extreme:
        parse_and_validate_ecg(extreme_file)
    assert "amplitude exceeds physiological limit" in str(exc_extreme.value)


def test_calibration_brier_and_ece():
    """
    Equation 15: Brier Score and Expected Calibration Error (ECE) calculations.
    """
    probs = np.array([0.9, 0.8, 0.7, 0.4, 0.2, 0.1])
    labels = np.array([1, 1, 1, 0, 0, 0])

    bs = compute_brier_score(probs, labels)
    assert 0.0 <= bs <= 1.0

    confidences = np.array([0.9, 0.8, 0.7, 0.6, 0.8, 0.9])
    correctness = np.array([1, 1, 1, 0, 0, 1])

    ece, bin_stats = compute_expected_calibration_error(confidences, correctness, num_bins=5)
    assert 0.0 <= ece <= 1.0
    assert len(bin_stats) > 0

    # Temperature scaling test
    logits = np.array([[2.0, 1.0, 0.1]])
    scaled_probs = apply_temperature_scaling(logits, temperature=1.5)
    assert np.allclose(np.sum(scaled_probs, axis=-1), 1.0)


def test_unassociated_files_excluded_from_case_fusion(db_session, test_users):
    """
    IEEE Paper line 6: If assoc == false, file marked UNASSOCIATED and EXCLUDED from fusion.
    """
    user = test_users["clinician_a"]
    case = Case(pseudonymous_id="CASE-UNASSOC-TEST", created_by_id=user.id)
    db_session.add(case)
    db_session.commit()

    # Upload unassociated image file
    unassoc_file = UploadedFile(
        case_id=case.id,
        filename="unassociated_image.png",
        stored_filename="mock_stored_123.png",
        file_path="mock/path/unassociated.png",
        modality=ModalityType.IMAGE,
        file_size_bytes=1024,
        file_hash="deadbeef123456",
        mime_type="image/png",
        is_associated=False  # NOT ASSOCIATED!
    )
    db_session.add(unassoc_file)
    db_session.commit()

    result = evaluate_multimodal_fusion(case.id, db_session)
    # Since only unassociated file exists, active modalities count must be 0 -> ABSTAIN
    assert result["fused_status"] == EvidenceStatus.ABSTAIN.value
    assert result["active_modalities_count"] == 0


def test_invalid_file_extension_rejection(client, test_users):
    """
    IEEE Paper line 2: Rejects unsupported file formats (e.g. executable or malicious scripts).
    """
    headers = get_auth_headers(test_users["clinician_a"])
    case_res = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-BAD-EXT"}, headers=headers)
    case_id = case_res.json()["id"]

    # Upload executable file
    files = {"file": ("malicious.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/x-msdownload")}
    data = {"modality": "IMAGE", "is_associated": "true", "deidentified": "true"}

    response = client.post(f"/api/v1/cases/{case_id}/uploads", files=files, data=data, headers=headers)
    assert response.status_code == 400
    assert "not permitted" in response.json()["detail"].lower()
