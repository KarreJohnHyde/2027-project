"""
Masked Gated Multimodal Fusion Module for MedTwin.
Implements Section VI-C (Equations 8-10) and Algorithm 1 (Lines 13-16) of the IEEE manuscript.

STRICT MEDICAL EVIDENCE AND PROTOCOL SAFEGUARDS:
1. If sum(m_k) == 0:
   Abstains immediately before Eq. (9) is evaluated. Returns ABSTAIN(missing input).
2. If sum(m_k) == 1:
   Fusion is NOT RUN. Presents individual modality finding directly without artificial fusion.
3. If sum(m_k) >= 2:
   Fusion runs ONLY when paired-data validation is satisfied.
   Artificial pairing of unrelated public datasets is explicitly prohibited.
"""

from typing import Dict, Any, Tuple
import torch
import torch.nn as nn
from sqlalchemy.orm import Session

from app.models.entities import Finding, MultimodalFusionRecord, EvidenceStatus


class GatedMultimodalFusionLayer(nn.Module):
    """
    Masked Gated Multimodal Fusion as defined in Equations 8-10.
    """
    def __init__(self, d_in_image: int = 64, d_in_ecg: int = 64, d_in_report: int = 64, d_common: int = 64, d_attn: int = 32):
        super().__init__()
        self.d_common = d_common
        # Linear projection matrices W_k
        self.w_image = nn.Linear(d_in_image, d_common, bias=False)
        self.w_ecg = nn.Linear(d_in_ecg, d_common, bias=False)
        self.w_report = nn.Linear(d_in_report, d_common, bias=False)

        # Attention gating parameters W_g, b, v
        self.w_g = nn.Linear(d_common, d_attn, bias=True)
        self.v = nn.Parameter(torch.randn(d_attn, 1))

    def forward(
        self,
        z_dict: Dict[str, torch.Tensor],
        mask_dict: Dict[str, int]
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        """
        Computes attention weights alpha_k and fused representation z_F.
        """
        modalities = ["IMAGE", "ECG", "REPORT"]
        projections = {}
        
        # 1. Project available embeddings: u_k = W_k z_k (Eq. 8a)
        if mask_dict.get("IMAGE", 0) == 1 and "IMAGE" in z_dict:
            projections["IMAGE"] = self.w_image(z_dict["IMAGE"])
        if mask_dict.get("ECG", 0) == 1 and "ECG" in z_dict:
            projections["ECG"] = self.w_ecg(z_dict["ECG"])
        if mask_dict.get("REPORT", 0) == 1 and "REPORT" in z_dict:
            projections["REPORT"] = self.w_report(z_dict["REPORT"])

        active_mods = list(projections.keys())
        if not active_mods:
            raise ValueError("No active modalities available for fusion.")

        # 2. Attention logits e_k = v^T tanh(W_g u_k + b) (Eq. 8b)
        e_dict = {}
        for mod in active_mods:
            u_k = projections[mod]
            e_k = torch.matmul(torch.tanh(self.w_g(u_k)), self.v).squeeze(-1)
            e_dict[mod] = e_k

        # 3. Masked Softmax (Eq. 9):
        # alpha_k = m_k exp(e_k) / sum_j m_j exp(e_j)
        max_e = max(e_dict.values())
        exp_e = {mod: torch.exp(e_dict[mod] - max_e) for mod in active_mods}
        sum_exp = sum(exp_e.values())

        alpha_dict = {mod: float((exp_e[mod] / sum_exp).item()) for mod in active_mods}
        
        # For modalities not present or masked, weight is strictly zero
        full_weights = {mod: alpha_dict.get(mod, 0.0) for mod in modalities}

        # 4. Fused vector z_F = sum_k alpha_k u_k (Eq. 10)
        z_f = torch.zeros_like(list(projections.values())[0])
        for mod in active_mods:
            z_f += alpha_dict[mod] * projections[mod]

        return z_f, full_weights


# Initialize singleton research fusion module
_fusion_module = GatedMultimodalFusionLayer()


def evaluate_multimodal_fusion(
    case_id: int,
    db: Session,
) -> Dict[str, Any]:
    """
    Evaluates multimodal evidence for a case according to Algorithm 1.
    """
    # 1. Fetch valid, associated findings for this case
    findings = db.query(Finding).filter(
        Finding.case_id == case_id,
        Finding.failure_reason.is_(None),
        Finding.review_status.in_([
            EvidenceStatus.PENDING_HUMAN_REVIEW,
            EvidenceStatus.COMPLETED,
        ]),
    ).all()

    # Map findings by modality
    modality_findings = {}
    for f in findings:
        modality_findings[f.modality.value] = f

    # 2. Build modality availability mask m_k in {0, 1}
    mask = {
        "IMAGE": 1 if "IMAGE" in modality_findings else 0,
        "ECG": 1 if "ECG" in modality_findings else 0,
        "REPORT": 1 if "REPORT" in modality_findings else 0
    }
    active_count = sum(mask.values())

    # 3. Condition A: All modalities missing (sum(m_k) == 0)
    # Line 14 of Algorithm 1: return ABSTAIN(missing input), Eq. 9 is NOT evaluated
    if active_count == 0:
        record = MultimodalFusionRecord(
            case_id=case_id,
            modality_mask=mask,
            active_modalities_count=0,
            gated_weights=None,
            fused_status=EvidenceStatus.ABSTAIN,
            fused_prediction=None,
            paired_data_validated=False,
            abstention_reason="ABSTAIN: No valid, associated modalities available for case."
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {
            "id": record.id,
            "case_id": case_id,
            "modality_mask": mask,
            "active_modalities_count": 0,
            "gated_weights": None,
            "fused_status": EvidenceStatus.ABSTAIN.value,
            "fused_prediction": None,
            "paired_data_validated": False,
            "abstention_reason": "ABSTAIN: No valid, associated modalities available for case."
        }

    # 4. Condition B: Single modality available (sum(m_k) == 1)
    # Line 16 of Algorithm 1: fusion is NOT RUN
    if active_count == 1:
        present_mod = [k for k, v in mask.items() if v == 1][0]
        finding = modality_findings[present_mod]
        record = MultimodalFusionRecord(
            case_id=case_id,
            modality_mask=mask,
            active_modalities_count=1,
            gated_weights={present_mod: 1.0, **{k: 0.0 for k in mask if k != present_mod}},
            fused_status=EvidenceStatus.NOT_RUN,
            fused_prediction={
                "dominant_modality": present_mod,
                "finding_label": finding.label,
                "confidence": finding.raw_confidence
            },
            paired_data_validated=False,
            abstention_reason=f"NOT RUN: Single modality ({present_mod}) present. Multi-modality fusion unnecessary."
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return {
            "id": record.id,
            "case_id": case_id,
            "modality_mask": mask,
            "active_modalities_count": 1,
            "gated_weights": record.gated_weights,
            "fused_status": EvidenceStatus.NOT_RUN.value,
            "fused_prediction": record.fused_prediction,
            "paired_data_validated": False,
            "abstention_reason": record.abstention_reason
        }

    # 5. Condition C: At least two modalities present (sum(m_k) >= 2).
    # Findings in one case are not, by themselves, proof that a validated paired
    # fusion cohort and compatible feature encoders exist. The mathematical layer
    # above is unit-testable with explicit synthetic tensors, but the case-level
    # service must not fabricate embeddings or a composite prediction.
    record = MultimodalFusionRecord(
        case_id=case_id,
        modality_mask=mask,
        active_modalities_count=active_count,
        gated_weights=None,
        fused_status=EvidenceStatus.NOT_RUN,
        fused_prediction=None,
        paired_data_validated=False,
        abstention_reason="NOT RUN: Fusion requires genuinely paired same-patient data, compatible validated encoders, and a validated fusion model."
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "id": record.id,
        "case_id": case_id,
        "modality_mask": mask,
        "active_modalities_count": active_count,
        "gated_weights": None,
        "fused_status": EvidenceStatus.NOT_RUN.value,
        "fused_prediction": None,
        "paired_data_validated": False,
        "abstention_reason": record.abstention_reason
    }
