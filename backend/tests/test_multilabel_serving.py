"""Multi-label image serving (RSNA ICH kind): sigmoid per label against its validation threshold.

The network is a fixed stand-in returning known logits; no checkpoint or GPU is needed."""

import numpy as np
import torch
from PIL import Image

from app.services import model_inference


class FixedLogits(torch.nn.Module):
    def __init__(self, logits):
        super().__init__()
        self.logits = torch.tensor([logits], dtype=torch.float32)

    def forward(self, batch):
        assert batch.shape[1:] == (3, 32, 32), "short side resized and centre-cropped to the input size"
        return self.logits.repeat(batch.shape[0], 1)


PAYLOAD = {"kind": "image_multilabel_classifier", "label_keys": ["sdh", "any"], "classes": ["subdural", "any intracranial haemorrhage"],
           "thresholds": {"sdh": 0.4, "any": 0.9}, "image_size": 32, "normalization": {"mean": [0.5] * 3, "std": [0.25] * 3}}


def test_every_input_type_a_model_declares_can_be_requested():
    """The request schema's input types must cover MODALITY_LABELS (MURA's XRAY and RSNA's HEAD_CT were once missing)."""
    from typing import get_args

    from app.routers.research_models import ResearchInferenceRequest

    allowed = set(get_args(ResearchInferenceRequest.model_fields["declared_input_type"].annotation))
    assert set(model_inference.MODALITY_LABELS) <= allowed
    registered = {modality for model in model_inference.inference_models() for modality in model.get("supported_modalities", [])
                  if model.get("inference_input", "image_2d") in model_inference.UPLOAD_INPUTS}
    assert registered <= allowed, registered - allowed


def test_labels_are_independent_and_compared_with_their_own_threshold():
    image = Image.fromarray(np.full((40, 64), 120, dtype=np.uint8), mode="L")  # not square, greyscale
    output = model_inference.classify_multilabel(FixedLogits([0.0, 1.0]), PAYLOAD, torch.device("cpu"), image)
    labels = {item["label"]: item for item in output["labels"]}
    assert labels["subdural"]["probability"] == 0.5 and labels["subdural"]["at_or_above_threshold"] is True
    assert round(labels["any intracranial haemorrhage"]["probability"], 4) == 0.7311
    assert labels["any intracranial haemorrhage"]["at_or_above_threshold"] is False, "0.73 is below its 0.9 threshold"
    assert output["positive_labels"] == ["subdural"] and output["type"] == "multilabel_classification"
    assert model_inference.summary_label(output) == "Research model, labels at/above threshold: subdural"
