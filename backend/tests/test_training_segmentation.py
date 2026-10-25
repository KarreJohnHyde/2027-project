"""Regression tests for the executable segmentation training data path."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml_training.common import cross_split_component_summary  # noqa: E402
from ml_training.segment import SegmentationSet  # noqa: E402
from scripts.dataset_task_audit import mark_crossing_components  # noqa: E402


def test_segmentation_augmentation_does_not_use_closed_pil_file(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    mask_path = tmp_path / "mask.png"
    Image.fromarray(np.arange(64, dtype=np.uint8).reshape(8, 8)).save(image_path)
    Image.fromarray((np.arange(64).reshape(8, 8) % 3).astype(np.uint8)).save(mask_path)

    dataset = SegmentationSet(
        [{"path": str(image_path), "mask_path": str(mask_path)}],
        size=16,
        train=True,
    )

    image, mask = dataset[0]

    assert image.shape == (1, 16, 16)
    assert mask.shape == (1, 16, 16)
    assert image.isfinite().all()
    assert set(mask.unique().tolist()) <= {0, 1, 2}


def test_cross_split_leakage_excludes_entire_transitive_component() -> None:
    rows = [
        {"group_id": "shared", "split": "train", "cross_split_duplicate": "1"},
        {"group_id": "shared", "split": "test", "cross_split_duplicate": "1"},
        # This row is connected through the component even when it is not the
        # endpoint of a directly confirmed cross-split pair.
        {"group_id": "shared", "split": "test", "cross_split_duplicate": "0"},
        {"group_id": "isolated", "split": "test", "cross_split_duplicate": "0"},
    ]

    summary = cross_split_component_summary(rows)

    assert summary["group_ids"] == {"shared"}
    assert summary["near_duplicate_components_crossing_splits"] == 1
    assert summary["images_in_crossing_components"] == 3
    assert summary["test_images_in_crossing_components"] == 2


def test_audit_marks_every_member_of_a_crossing_component() -> None:
    samples = [
        {"group_id": 7, "split": "train"},
        {"group_id": 7, "split": "test"},
        {"group_id": 7, "split": "test"},
        {"group_id": 8, "split": "test"},
    ]

    groups, members = mark_crossing_components(samples, {0, 1})

    assert groups == {7}
    assert members == {0, 1, 2}
    assert [sample["cross_split_duplicate"] for sample in samples] == [1, 1, 1, 0]
