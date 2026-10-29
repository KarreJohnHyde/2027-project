"""Masked gated multimodal fusion layer (Equations 8-10 of the IEEE manuscript).

Kept apart from fusion_service so the case-level gate imports without PyTorch: the gate
never evaluates this layer (no validated paired cohort or encoders exist); unit tests
exercise the mathematics with explicit synthetic tensors."""

from typing import Dict, Tuple

import torch
import torch.nn as nn


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
