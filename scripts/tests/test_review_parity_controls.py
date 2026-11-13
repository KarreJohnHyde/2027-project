"""Numerical comparators used by the bounded parity audit, without loading weights."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location("review_parity_controls", Path(__file__).resolve().parents[1] / "review_parity_controls.py")
parity = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parity)


def test_exact_tensor_parity_records_all_elements():
    values = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    result = parity.numeric_comparison(values, values.copy(), 0.0)
    assert result["within_tolerance"] and result["differing_elements"] == 0
    assert result["elements"] == 24 and result["shape"] == [2, 3, 4]


def test_report_retains_small_and_material_differences():
    result = parity.numeric_comparison([0.1, 0.5], [0.101, 0.51], 0.003)
    assert not result["within_tolerance"] and result["differing_elements"] == 2
    assert result["max_abs_difference"] == pytest.approx(0.01)


@pytest.mark.parametrize("left,right", [([], []), ([1], [1, 2]), ([float("nan")], [0]), ([0], [float("inf")])])
def test_invalid_numeric_comparisons_do_not_become_success(left, right):
    with pytest.raises(ValueError):
        parity.numeric_comparison(left, right, 0.003)


def test_threshold_equality_uses_serving_greater_or_equal_rule():
    assert parity.threshold_disagreements([0.5, 0.299], [0.499, 0.301], [0.5, 0.3]) == 2


def test_threshold_comparison_rejects_broadcast_and_nan():
    with pytest.raises(ValueError):
        parity.threshold_disagreements([0.5, 0.4], [0.5, 0.4], [0.5])
    with pytest.raises(ValueError):
        parity.threshold_disagreements([float("nan")], [0.5], [0.5])
