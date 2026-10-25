"""Image input validation and preprocessing for MedTwin.

No trained image checkpoint is bundled with this repository. This module therefore
validates supported files and records preprocessing metadata, but it deliberately
does not emit a diagnostic class, confidence, or attribution map.
"""

from pathlib import Path
from typing import Dict, Any, Tuple
from PIL import Image
import torch
import torchvision.transforms as T

from app.models.entities import RepresentationLevel


def preprocess_image(image_path: Path) -> Tuple[torch.Tensor, Tuple[int, int]]:
    """
    Validates image readability and applies standardized normalization.
    """
    try:
        with Image.open(image_path) as img:
            img.verify()
    except Exception as e:
        raise ValueError(f"Corrupted or unreadable image file: {str(e)}")

    with Image.open(image_path) as img:
        img_rgb = img.convert("RGB")
        original_size = img_rgb.size # (width, height)

        # Standard transformation: 224x224, normalized with ImageNet stats
        transform = T.Compose([
            T.Resize((224, 224)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        tensor = transform(img_rgb).unsqueeze(0) # (1, 3, 224, 224)

    return tensor, original_size


def analyze_medical_image(image_path: Path, file_hash: str) -> Dict[str, Any]:
    """Validate and preprocess an image without claiming unavailable inference."""
    tensor, orig_size = preprocess_image(image_path)
    reason = "No compatible, validated image-classification checkpoint is configured."

    return {
        "modality": "IMAGE",
        "category": "Medical Image Input",
        "label": "MODEL_UNAVAILABLE",
        "probabilities": {},
        "raw_confidence": None,
        "calibrated_confidence": None,
        "calibration_status": "NOT_APPLICABLE_MODEL_UNAVAILABLE",
        "visual_explanation_path": None,
        "explanation_type": None,
        "representation_level": RepresentationLevel.L1_GENERIC.value,
        "anatomical_region": None,
        "mapping_status": "MAPPING_UNSUPPORTED: generic L1 anatomy only; no registration evidence",
        "model_name": "UNCONFIGURED",
        "model_version": "NONE",
        "preprocessing_version": "Resize(224x224)+ImageNetNorm",
        "evidence_status": "NOT_RUN",
        "failure_reason": reason,
        "is_demo": False,
        "provenance": {
            "original_dimensions": f"{orig_size[0]}x{orig_size[1]}",
            "preprocessed_shape": list(tensor.shape),
            "input_hash": file_hash,
            "inference_status": "NOT_RUN",
            "reason": reason,
        }
    }
