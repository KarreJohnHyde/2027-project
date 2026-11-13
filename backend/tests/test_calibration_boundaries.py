"""Numerical reference tests; no application, database or ML runtime is needed."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

_path = Path(__file__).resolve().parents[1] / "app/services/calibration_service.py"
_spec = importlib.util.spec_from_file_location("review_calibration", _path)
calibration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(calibration)


def test_zero_and_one_confidences_are_counted_with_hand_computed_error():
    ece, bins = calibration.compute_expected_calibration_error([0, 1], [1, 0], 10)
    assert ece == 1
    assert sum(item["count"] for item in bins) == 2
    assert [item["bin_index"] for item in bins] == [1, 10]


def test_internal_boundary_belongs_to_one_bin_and_empty_bins_do_not_change_weight():
    ece, bins = calibration.compute_expected_calibration_error([0, .25, .5, 1], [0, 0, 1, 1], 4)
    assert ece == pytest.approx(.1875)
    assert [item["count"] for item in bins] == [2, 1, 1]
    assert sum(item["count"] for item in bins) == 4


def test_imbalanced_sample_weighting_is_not_an_unweighted_mean_of_bins():
    ece, _ = calibration.compute_expected_calibration_error([.1] * 9 + [.9], [0] * 9 + [1], 2)
    assert ece == pytest.approx(.1)


@pytest.mark.parametrize("confidence,truth", [([], []), ([np.nan], [0]), ([np.inf], [1]), ([-.1], [0]), ([1.1], [1]), ([.2], [.5]), ([.1, .2], [1]), ([[.2, .8]], [[0, 1]]), ([.2], [np.nan]), (1, 0), (np.array([.2 + .1j]), [0])])
def test_ece_invalid_inputs_are_refused(confidence, truth):
    with pytest.raises(ValueError):
        calibration.compute_expected_calibration_error(confidence, truth)


@pytest.mark.parametrize("bins", [0, -1, 1.5, True, np.nan])
def test_invalid_bin_count_is_refused(bins):
    with pytest.raises(ValueError):
        calibration.compute_expected_calibration_error([.2], [0], bins)


def test_binary_and_multilabel_brier_preserve_existing_mean_definition():
    assert calibration.compute_brier_score([.8, .3], [1, 0]) == pytest.approx(.065)
    assert calibration.compute_brier_score([[.8, .3]], [[1, 0]]) == pytest.approx(.065)


def test_explicit_multiclass_brier_uses_class_sum_and_onehot_contract():
    assert calibration.compute_brier_score([[.8, .2], [.1, .9]], [[1, 0], [0, 1]], multiclass=True) == pytest.approx(.05)
    assert calibration.compute_brier_score([[0, 1]], [[1, 0]], multiclass=True) == 2
    with pytest.raises(ValueError, match="one-hot"):
        calibration.compute_brier_score([[.8, .2]], [[1, 1]], multiclass=True)
    with pytest.raises(ValueError, match="sum to one"):
        calibration.compute_brier_score([[.8, .3]], [[1, 0]], multiclass=True)


@pytest.mark.parametrize("prediction,truth", [([], []), ([[.8, .2], [.1, .9]], [0, 1]), ([np.nan], [0]), ([.2], [np.inf]), ([-1], [0]), ([.5], [.5]), ([[[.2]]], [[[0]]])])
def test_brier_invalid_or_broadcastable_shapes_are_refused(prediction, truth):
    with pytest.raises(ValueError):
        calibration.compute_brier_score(prediction, truth)


def test_temperature_matches_manual_softmax_and_preserves_argmax():
    logits = np.array([[2., 0.], [0., 2.]])
    probabilities = calibration.apply_temperature_scaling(logits, 2)
    assert probabilities[0, 0] == pytest.approx(np.e / (np.e + 1))
    assert np.allclose(probabilities.sum(axis=1), 1)
    assert np.array_equal(probabilities.argmax(axis=1), logits.argmax(axis=1))
    assert np.allclose(calibration.apply_temperature_scaling(logits + 10000, 2), probabilities)


def test_temperature_extreme_finite_logits_and_tiny_temperature_are_stable():
    probabilities = calibration.apply_temperature_scaling([1e308, -1e308], 1e-300)
    assert np.array_equal(probabilities, [1., 0.])


@pytest.mark.parametrize("temperature", [0, -1, np.nan, np.inf, True, [1], "invalid"])
def test_invalid_temperature_is_refused(temperature):
    with pytest.raises(ValueError):
        calibration.apply_temperature_scaling([1, 0], temperature)


@pytest.mark.parametrize("logits", [[], [1], [[1]], [np.nan, 0], [np.inf, 0], [[[1, 0]]]])
def test_invalid_logits_are_refused(logits):
    with pytest.raises(ValueError):
        calibration.apply_temperature_scaling(logits)
