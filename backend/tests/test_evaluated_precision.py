"""Serving reproduces the evaluated precision: float32 for a CPU-evaluated checkpoint, CUDA autocast otherwise."""

import pytest

torch = pytest.importorskip("torch")

from app.services.model_inference import evaluated_precision  # noqa: E402


def test_a_cpu_evaluated_checkpoint_is_served_in_float32_and_described_truthfully():
    context, note = evaluated_precision(torch.device("cpu"), {"evaluation_device": "cpu"})
    assert "float32, as in the held-out evaluation" in note and "differs" not in note
    with context:
        assert (torch.ones(2, 2) @ torch.ones(2, 2)).dtype == torch.float32


def test_a_gpu_evaluated_checkpoint_on_cpu_declares_the_difference():
    _, note = evaluated_precision(torch.device("cpu"), {"evaluation_device": None})
    assert "differs from the evaluated bfloat16 CUDA configuration" in note
    _, legacy = evaluated_precision(torch.device("cpu"))
    assert legacy == note
