"""Tabular research classifiers: grouped splits, calibration-error boundaries and registry summaries.

The split and ECE tests use synthetic arrays generated here; the last test reads the committed evaluation reports."""

import numpy as np
import pandas as pd
import pytest

tabular = pytest.importorskip("ml_training.tabular")

from app.services import model_inference  # noqa: E402


def test_rows_of_one_person_never_cross_splits():
    rng = np.random.default_rng(0)
    groups = pd.Series([f"p{index // 3}" for index in range(600)])
    y = pd.Series((rng.random(600) < 0.3).astype(int))
    parts = tabular.split(y, groups)
    assert set(parts) == {"train", "val", "test"}
    for group, members in groups.groupby(groups).groups.items():
        assert len(set(parts[list(members)])) == 1, group
    shares = {part: float(np.mean(parts == part)) for part in ("train", "val", "test")}
    assert 0.6 < shares["train"] < 0.8 and 0.1 < shares["val"] < 0.2 and 0.1 < shares["test"] < 0.2


def test_ece_bins_confidence_zero_and_one():
    y = np.array([0, 0, 1, 1])
    assert tabular.ece(y, np.array([0.0, 0.0, 1.0, 1.0])) == 0.0
    assert tabular.ece(y, np.array([1.0, 1.0, 0.0, 0.0])) == pytest.approx(1.0)
    assert tabular.ece(np.array([1, 0]), np.array([0.5, 0.5])) == pytest.approx(0.0)


def test_registered_tabular_models_have_held_out_summaries():
    models = [model for model in model_inference._load_registry()["models"] if model["task"] == "tabular_classification"]
    if not models:
        pytest.skip("no tabular models registered in this checkout")
    for model in models:
        summary = model_inference.evaluation_summary(model)
        assert summary["test_n"] > 0 and 0.0 <= summary["auroc"] <= 1.0, model["model_id"]
        assert model["artifact_bundle"]["dataset_license"] == "CC BY 4.0"
        assert model["validation_readiness"]["run_scope"] in {"RESEARCH", "EXPLORATORY_ONLY"}
