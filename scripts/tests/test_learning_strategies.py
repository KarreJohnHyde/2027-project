import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml_training.learning_strategies import OfflineQPolicy, assert_disjoint_groups, fit_feature_learners, eligibility


def test_subject_leakage_is_rejected():
    assert_disjoint_groups(["a"], ["b"], ["c"])
    with pytest.raises(ValueError, match="leakage"):
        assert_disjoint_groups(["a"], ["b"], ["a"])


def test_q_learning_respects_masks_bootstraps_and_defers_unknown_states():
    policy = OfflineQPolicy(alpha=1, gamma=0.5)
    assert policy.select("unknown", [True, True, True]) == 2
    with pytest.raises(ValueError, match="forbidden"):
        policy.update("s", 0, 1, allowed=[False, True, True])
    policy.update("next", 1, 2, allowed=[True, True, True])
    policy.update("s", 0, 1, allowed=[True, True, True], next_state="next", next_allowed=[False, True, True], terminal=False)
    assert policy.q["s"][0] == 2
    assert policy.select("s", [True, True, True]) == 0
    assert policy.select("s", [False, True, True]) == 2
    policy.update("negative", 0, -1, allowed=[True, True, True])
    assert policy.select("negative", [True, True, True]) == 2
    assert eligibility([np.array([0.8, 0.2]), np.array([0.5, 0.5])]) == [True, False, True]


def test_unlabeled_training_and_novelty_are_independent_of_test_data():
    rng = np.random.default_rng(4)
    train = np.r_[rng.normal(-2, 0.3, (40, 5)), rng.normal(2, 0.3, (40, 5))]
    labels = np.full(80, -1)
    labels[:4], labels[40:44] = 0, 1
    fitted = fit_feature_learners(train, labels, components=3)
    assert fitted["labeled_rows"] == 8 and fitted["unlabeled_rows"] == 72
    assert fitted["pseudo_labeled_rows"] > 0
    before = fitted["transform"][0].mean_.copy()
    encoded = fitted["transform"].transform(np.full((2, 5), 1e6))
    fitted["novelty"].score_samples(encoded)
    assert np.array_equal(before, fitted["transform"][0].mean_)
    with pytest.raises(ValueError, match="finite"):
        fit_feature_learners([[np.nan], [1]], [0, 1])
