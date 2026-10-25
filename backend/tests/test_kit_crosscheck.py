import json
import sys
from pathlib import Path

import pytest
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml_training.kit_crosscheck import (
    COMPONENT_LIMITATION,
    component_conservative_subset,
    detection_reference,
    detection_results,
    model_card_with_component_rescore,
    report_with_component_rescore,
    segmentation_card_with_component_rescore,
    segmentation_report_with_component_rescore,
)


def test_yolo_manifest_builds_the_same_pixel_reference_used_by_training(tmp_path):
    image_path = tmp_path / "scan.png"
    label_path = tmp_path / "scan.txt"
    Image.new("L", (100, 80)).save(image_path)
    label_path.write_text("0 0.5 0.5 0.2 0.25\n", encoding="utf-8")
    rows = [{
        "entry": "test/images/scan.png",
        "path": str(image_path),
        "label_file": str(label_path),
        "boxes": "1",
        "split": "test",
    }]

    reference, image_ids, category_id = detection_reference(rows, "kidney_stone")

    assert image_ids == {"test/images/scan.png": 1}
    assert category_id == 1
    assert reference["categories"] == [{"id": 1, "name": "kidney_stone"}]
    assert reference["images"] == [{"id": 1, "width": 100, "height": 80, "file_name": "test/images/scan.png"}]
    assert reference["annotations"][0]["bbox"] == pytest.approx([40.0, 30.0, 20.0, 20.0])
    assert reference["annotations"][0]["area"] == pytest.approx(400.0)


def test_coco_manifest_filters_category_and_uses_manifest_image_ids(tmp_path):
    annotations_path = tmp_path / "annotations.json"
    annotations_path.write_text(json.dumps({
        "images": [
            {"id": 7, "file_name": "one.png", "width": 10, "height": 10},
            {"id": 8, "file_name": "two.png", "width": 10, "height": 10},
        ],
        "categories": [{"id": 3, "name": "stenosis"}, {"id": 4, "name": "artifact"}],
        "annotations": [
            {"id": 1, "image_id": 7, "category_id": 3, "bbox": [1, 2, 3, 4], "area": 12, "iscrowd": 0},
            {"id": 2, "image_id": 7, "category_id": 4, "bbox": [1, 1, 2, 2], "area": 4, "iscrowd": 0},
            {"id": 3, "image_id": 8, "category_id": 3, "bbox": [0, 0, 1, 1], "area": 1, "iscrowd": 0},
        ],
    }), encoding="utf-8")
    rows = [{
        "entry": "data/test/one.png",
        "annotation_file": str(annotations_path),
        "image_id": "7",
        "split": "test",
    }]

    reference, image_ids, category_id = detection_reference(rows, "stenosis")

    assert image_ids == {"data/test/one.png": 7}
    assert category_id == 3
    assert [item["id"] for item in reference["images"]] == [7]
    assert [item["id"] for item in reference["annotations"]] == [1]
    assert reference["categories"] == [{"id": 3, "name": "stenosis"}]


def test_detection_results_require_exact_manifest_coverage():
    predictions = [{"entry": "test/a.png", "boxes": [{"bbox": [1, 2, 5, 8], "score": 0.75}]}]

    results = detection_results(predictions, {"test/a.png": 11}, 2)

    assert results == [{"image_id": 11, "category_id": 2, "bbox": [1.0, 2.0, 4.0, 6.0], "score": 0.75}]
    with pytest.raises(ValueError, match="do not match the test manifest"):
        detection_results(predictions, {"test/a.png": 11, "test/b.png": 12}, 2)


def test_yolo_manifest_rejects_declared_count_or_normalisation_errors(tmp_path):
    image_path = tmp_path / "scan.png"
    label_path = tmp_path / "scan.txt"
    Image.new("L", (100, 80)).save(image_path)
    rows = [{"entry": "scan.png", "path": str(image_path), "label_file": str(label_path), "boxes": "2"}]
    label_path.write_text("0 0.5 0.5 0.2 0.25\n", encoding="utf-8")

    with pytest.raises(ValueError, match="declares 2 boxes but has 1"):
        detection_reference(rows, "target")

    rows[0]["boxes"] = "1"
    label_path.write_text("0 1.2 0.5 0.2 0.25\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a valid normalised box"):
        detection_reference(rows, "target")


def test_component_subset_excludes_every_test_member_of_a_crossing_transitive_group():
    rows = [
        {"entry": "train/shared-a.png", "group_id": "shared", "split": "train", "cross_split_duplicate": "1"},
        {"entry": "test/shared-b.png", "group_id": "shared", "split": "test", "cross_split_duplicate": "1"},
        {"entry": "test/shared-c.png", "group_id": "shared", "split": "test", "cross_split_duplicate": "0"},
        {"entry": "test/isolated.png", "group_id": "isolated", "split": "test", "cross_split_duplicate": "0"},
    ]
    predictions = [
        {"entry": "test/shared-b.png", "boxes": []},
        {"entry": "test/shared-c.png", "boxes": []},
        {"entry": "test/isolated.png", "boxes": []},
    ]

    selected_rows, selected_predictions, summary = component_conservative_subset(rows, predictions)

    assert [row["entry"] for row in selected_rows] == ["test/isolated.png"]
    assert [item["entry"] for item in selected_predictions] == ["test/isolated.png"]
    assert summary == {
        "near_duplicate_components_crossing_splits": 1,
        "images_in_crossing_components": 3,
        "test_images_in_crossing_components": 2,
        "exclusion_rule": "exclude every test image in a transitive near-duplicate component that spans publisher splits",
        "official_test_images": 3,
        "excluded_test_images": 2,
        "retained_test_images": 1,
    }
    with pytest.raises(ValueError, match="do not match the test manifest"):
        component_conservative_subset(rows, predictions[1:])


def test_component_rescore_preserves_official_test_and_supersedes_only_old_subset():
    official = {"n_images": 300, "reference_boxes": 386, "metrics": {"map_50_95": 0.06}}
    report = {
        "test": official,
        "leakage_check": {"test_images_with_cross_split_duplicate": 4},
        "test_without_cross_split_duplicates": {"n_images": 296, "metrics": {"map_50_95": 0.05}},
        "limitations": ["existing"],
    }
    result = {
        "source": {"held_out_predictions": "artifacts/run/predictions_test.json"},
        "selection": {
            "near_duplicate_components_crossing_splits": 11,
            "images_in_crossing_components": 54,
            "test_images_in_crossing_components": 10,
            "exclusion_rule": "exclude every test image in a transitive near-duplicate component that spans publisher splits",
            "excluded_test_images": 10,
        },
        "conservative_component_subset": {
            "n_images": 290,
            "reference_boxes": 372,
            "metrics": {"map_50_95": 0.055, "ap_50": 0.19},
        },
    }

    updated = report_with_component_rescore(report, result, "docs/validation/models/model.component_rescore.json")

    assert report["test"] == official
    assert updated["test"] == official
    assert updated["test_without_cross_split_duplicates"]["n_images"] == 290
    assert updated["legacy_test_without_direct_cross_split_duplicate_endpoints"]["n_images"] == 296
    assert updated["leakage_check"]["test_images_in_crossing_components"] == 10
    assert updated["limitations"] == ["existing", COMPONENT_LIMITATION]

    card = """# Card

## Held-out test results

- Official result stays here.
- Without the 4 test images that have a near-duplicate in another split: mAP 0.050, AP50 0.180.

## Limitations

- Existing.

Full report: `report.json`.
"""
    card = model_card_with_component_rescore(card, result, "docs/validation/models/model.component_rescore.json")
    assert "After excluding all 10 test images" in card
    assert "(290 retained): mAP 0.055, AP50 0.190" in card
    assert card.count(COMPONENT_LIMITATION) == 1
    assert "Conservative rescore evidence: `docs/validation/models/model.component_rescore.json`." in card
    assert "\n\n\nFull report:" not in card


def test_segmentation_component_rescore_preserves_official_test_and_marks_sparse_classes():
    official = {
        "n_images": 300,
        "mean_foreground_dice_per_image": 0.30,
        "vessel_dice": 0.68,
        "per_segment": [
            {"segment": "10", "images": 14, "mean_dice": 0.0},
            {"segment": "10a", "images": 0, "mean_dice": None},
        ],
    }
    report = {
        "test": official,
        "leakage_check": {"test_images_with_cross_split_duplicate": 1},
        "test_without_cross_split_duplicates": {"n_images": 299, "mean_foreground_dice_per_image": 0.301},
        "limitations": ["existing"],
    }
    result = {
        "source": {"held_out_predictions": "artifacts/run/test_masks"},
        "selection": {
            "near_duplicate_components_crossing_splits": 2,
            "images_in_crossing_components": 6,
            "test_images_in_crossing_components": 2,
            "exclusion_rule": "exclude every test image in a transitive near-duplicate component that spans publisher splits",
            "excluded_test_images": 2,
        },
        "conservative_component_subset": {
            "n_images": 298,
            "mean_foreground_dice_per_image": 0.308,
            "vessel_dice": 0.683,
            "vessel_iou": 0.536,
            "per_segment": [],
        },
    }

    updated = segmentation_report_with_component_rescore(
        report, result, "docs/validation/models/segmenter.component_rescore.json"
    )

    assert report["test"] == official
    assert updated["test"] == official
    assert updated["test_without_cross_split_duplicates"]["n_images"] == 298
    assert updated["legacy_test_without_direct_cross_split_duplicate_endpoints"]["n_images"] == 299
    assert updated["leakage_check"]["test_images_in_crossing_components"] == 2
    assert any("10a" in item and "undefined" in item for item in updated["limitations"])
    assert any("10" in item and "unstable" in item for item in updated["limitations"])

    card = """# Card

## Held-out test results

- Without test images that have a near-duplicate in another split (n = 299): mean Dice 0.301.

## Limitations

- Existing.

Full report: `report.json`.
"""
    card = segmentation_card_with_component_rescore(
        card, result, "docs/validation/models/segmenter.component_rescore.json"
    )
    assert "After excluding all 2 test images" in card
    assert "(298 retained): mean foreground Dice per image 0.308; whole-vessel Dice 0.683" in card
    assert card.count(COMPONENT_LIMITATION) == 1
