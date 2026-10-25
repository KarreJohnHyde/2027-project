"""Focused policy tests for classification data adequacy and imbalance handling."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml_training.classify import (  # noqa: E402
    class_imbalance_plan,
    class_weight_tensor,
    classification_limitations,
    classification_readiness,
    require_exploratory_opt_in,
)
from scripts.dataset_task_audit import apply_task_readiness  # noqa: E402


def _row(label: str, split: str) -> dict:
    return {"label": label, "split": split}


def test_dataset_audit_marks_rare_classes_exploratory_without_blocking_training() -> None:
    entry = {
        "flags": ["TASK_SUPPORTED_BY_LABELS", "LEAKAGE_RISK"],
        "training_eligible": True,
    }

    result = apply_task_readiness(
        entry,
        {"classes_below_minimum": ["Angiectasia", "Ulcer"]},
    )

    assert result["flags"].count("INSUFFICIENT_SAMPLES") == 1
    assert result["training_eligible"] is True
    assert result["validation_ready"] is False
    assert result["readiness"] == "EXPLORATORY_TRAINING_ONLY"


def test_dataset_audit_keeps_adequate_kvasir_style_task_ready() -> None:
    entry = {
        "flags": ["TASK_SUPPORTED_BY_LABELS", "LEAKAGE_RISK"],
        "training_eligible": True,
    }

    result = apply_task_readiness(entry, {"classes_below_minimum": []})

    assert result["validation_ready"] is True
    assert result["readiness"] == "READY_FOR_TRAINING"
    assert "INSUFFICIENT_SAMPLES" not in result["flags"]


def test_classifier_requires_explicit_opt_in_and_records_rare_class_counts() -> None:
    rows = [
        *[_row("common", "train") for _ in range(4)],
        _row("rare", "train"),
        _row("common", "val"),
        _row("rare", "val"),
        _row("common", "test"),
    ]
    readiness = classification_readiness(
        {"training_eligible": True, "flags": ["TASK_SUPPORTED_BY_LABELS"]},
        {"minimum_samples_per_class": 4, "classes_below_minimum": ["rare"]},
        rows,
        ["common", "rare"],
    )

    assert readiness["validation_ready"] is False
    assert readiness["run_scope"] == "EXPLORATORY_ONLY"
    assert readiness["effective_flags"] == ["TASK_SUPPORTED_BY_LABELS", "INSUFFICIENT_SAMPLES"]
    assert readiness["classes_below_minimum"] == [
        {
            "class": "rare",
            "total": 2,
            "train": 1,
            "val": 1,
            "test": 0,
            "minimum_required": 4,
        }
    ]
    with pytest.raises(SystemExit, match="--exploratory"):
        require_exploratory_opt_in(readiness, exploratory=False)
    require_exploratory_opt_in(readiness, exploratory=True)


def test_inverse_frequency_weights_use_training_counts_only_and_are_ordered() -> None:
    train_rows = [
        *[_row("common", "train") for _ in range(4)],
        _row("rare", "train"),
    ]

    plan = class_imbalance_plan(train_rows, ["common", "rare"], "inverse_frequency")
    tensor = class_weight_tensor(plan, ["common", "rare"], torch.device("cpu"))

    assert plan["formula"] == "w_c = N_train / (K * n_train,c)"
    assert plan["training_counts"] == {"common": 4, "rare": 1}
    assert plan["weights_by_class"] == pytest.approx({"common": 0.625, "rare": 2.5})
    assert tensor is not None
    assert tensor.tolist() == pytest.approx([0.625, 2.5])


def test_unweighted_mode_remains_available_and_missing_training_class_fails_closed() -> None:
    train_rows = [_row("common", "train"), _row("rare", "train")]

    plan = class_imbalance_plan(train_rows, ["common", "rare"], "none")

    assert plan["enabled"] is False
    assert plan["weights_by_class"] is None
    assert class_weight_tensor(plan, ["common", "rare"], torch.device("cpu")) is None
    with pytest.raises(ValueError, match="missing: rare"):
        class_imbalance_plan([_row("common", "train")], ["common", "rare"], "inverse_frequency")


def test_rare_class_and_weighting_limitations_are_explicit() -> None:
    readiness = {
        "validation_ready": False,
        "minimum_samples_per_class": 20,
        "classes_below_minimum": [
            {"class": "Ulcer", "total": 6, "train": 4, "val": 1, "test": 1},
        ],
    }
    imbalance = {
        "enabled": True,
        "strategy": "inverse_frequency",
    }

    limitations = classification_limitations(readiness, imbalance)

    assert "INSUFFICIENT_SAMPLES" in limitations[0]
    assert "Ulcer (total=6, train=4, val=1, test=1)" in limitations[0]
    assert any("does not create rare-class evidence" in item for item in limitations)
