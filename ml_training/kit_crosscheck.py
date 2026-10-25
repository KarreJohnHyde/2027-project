"""Independent re-scoring of saved held-out predictions with MedTwin_2_Validation_Kit.

detection     Re-scores a detector's predictions_test.json against either the publisher's
              COCO test annotations or a strict COCO conversion of held-out YOLO labels,
              so the trainer's target loading is checked as well as its evaluator.
segmentation  Binarises the saved class-index test masks and the references to
              whole-vessel masks at the model resolution and lets the kit compute Dice/IoU.

Writes <run>/kit_crosscheck/ (inputs and the kit's JSON) and prints both numbers.
  python -m ml_training.kit_crosscheck detection --model-id angiography_stenosis_detector --category stenosis

For a post-hoc detection or segmentation sensitivity analysis that excludes every
test member of any transitive near-duplicate component spanning publisher splits, use
``--component-rescore``.  It writes a separate directory and committed sidecar;
``--update-artifacts`` additionally updates the conservative report/card fields.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ml_training.common import ROOT, cross_split_component_summary, read_samples

KIT = ROOT / "MedTwin_2_Validation_Kit" / "evaluate_medtw.py"
# The kit needs pandas and scikit-learn, kept out of the training environment:
# uv venv .venv-kit --python 3.12; uv pip install --python .venv-kit/Scripts/python.exe
#   numpy==2.5.2 pillow==12.3.0 pycocotools==2.0.11 pandas==2.3.3 scikit-learn==1.7.2
KIT_PYTHON = Path(os.getenv("MEDTWIN_KIT_PYTHON", str(ROOT / ".venv-kit" / "Scripts" / "python.exe")))
COMPONENT_LIMITATION = (
    "The conservative duplicate sensitivity analysis excludes every test image in a transitive "
    "near-duplicate component spanning publisher splits; it is a post-hoc subset analysis, while "
    "the official publisher test result remains unchanged."
)


def report_for(model_id: str) -> dict:
    return json.loads((ROOT / "docs" / "validation" / "models" / f"{model_id}.json").read_text(encoding="utf-8"))


def run_kit(arguments: list[str], output: Path) -> dict:
    command = [str(KIT_PYTHON if KIT_PYTHON.exists() else sys.executable), "-I", str(KIT), *arguments, "--output", str(output)]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise SystemExit(f"validation kit failed ({completed.returncode}): {completed.stderr.strip()[-400:]}")
    return json.loads(output.read_text(encoding="utf-8"))


def _manifest_kind(rows: list[dict]) -> str:
    """Return the manifest's annotation kind without treating missing data as another kind."""
    if not rows:
        raise ValueError("the held-out test manifest has no rows")
    columns = set(rows[0])
    if not all(set(row) == columns for row in rows):
        raise ValueError("the held-out test manifest has inconsistent columns")
    has_coco = "annotation_file" in columns and any(row.get("annotation_file", "").strip() for row in rows)
    has_yolo = "label_file" in columns and "annotation_file" not in columns
    if has_coco and "label_file" in columns and any(row.get("label_file", "").strip() for row in rows):
        raise ValueError("the held-out test manifest mixes COCO and YOLO annotations")
    if has_coco:
        return "COCO"
    if has_yolo:
        return "YOLO"
    raise ValueError("the held-out test manifest has neither COCO annotation_file nor YOLO label_file columns")


def _row_entries(rows: list[dict]) -> list[str]:
    entries = []
    for index, row in enumerate(rows, start=1):
        entry = row.get("entry", "").strip()
        if not entry:
            raise ValueError(f"manifest row {index} has no entry")
        entries.append(entry)
    if len(set(entries)) != len(entries):
        raise ValueError("the held-out test manifest contains duplicate entries")
    return entries


def component_conservative_subset(rows: list[dict], predictions: Any) -> tuple[list[dict], list[dict], dict]:
    """Select a component-clean test subset and its saved predictions.

    The manifest's ``cross_split_duplicate`` flag marks confirmed pair endpoints,
    but near-duplicate groups are transitive.  Coverage is therefore validated
    against the complete publisher test split before every member of a component
    that spans splits is excluded.
    """
    if not isinstance(predictions, list):
        raise ValueError("held-out predictions must be a list")
    test_rows = [row for row in rows if row.get("split") == "test"]
    expected_entries = set(_row_entries(test_rows))
    predicted_entries = []
    for item_index, item in enumerate(predictions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"prediction item {item_index} must be an object")
        entry = item.get("entry")
        if not isinstance(entry, str) or not entry:
            raise ValueError(f"prediction item {item_index} has no entry")
        predicted_entries.append(entry)
    if len(predicted_entries) != len(set(predicted_entries)):
        raise ValueError("held-out predictions contain duplicate entries")
    actual_entries = set(predicted_entries)
    if actual_entries != expected_entries:
        missing = sorted(expected_entries - actual_entries)
        extra = sorted(actual_entries - expected_entries)
        raise ValueError(f"held-out predictions do not match the test manifest (missing={missing[:3]}, extra={extra[:3]})")

    summary = cross_split_component_summary(rows)
    crossing_groups = summary.pop("group_ids")
    selected_rows = [
        row for row in test_rows
        if str(row.get("group_id", "")).strip() not in crossing_groups
    ]
    selected_entries = set(_row_entries(selected_rows))
    selected_predictions = [item for item in predictions if item["entry"] in selected_entries]
    summary.update({
        "official_test_images": len(test_rows),
        "excluded_test_images": len(test_rows) - len(selected_rows),
        "retained_test_images": len(selected_rows),
    })
    return selected_rows, selected_predictions, summary


def component_conservative_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    """Select test rows outside every duplicate component that spans splits."""
    test_rows = [row for row in rows if row.get("split") == "test"]
    _row_entries(test_rows)
    summary = cross_split_component_summary(rows)
    crossing_groups = summary.pop("group_ids")
    selected_rows = [
        row for row in test_rows
        if str(row.get("group_id", "")).strip() not in crossing_groups
    ]
    summary.update({
        "official_test_images": len(test_rows),
        "excluded_test_images": len(test_rows) - len(selected_rows),
        "retained_test_images": len(selected_rows),
    })
    return selected_rows, summary


def _category(categories: Any, requested: str | None) -> dict:
    if not isinstance(categories, list) or not categories:
        raise ValueError("COCO reference has no categories")
    if requested:
        matches = [item for item in categories if item.get("name") == requested]
        if len(matches) != 1:
            names = sorted(str(item.get("name")) for item in categories)
            raise ValueError(f"COCO category {requested!r} was not found exactly once; available: {names}")
        return matches[0]
    if len(categories) != 1:
        names = sorted(str(item.get("name")) for item in categories)
        raise ValueError(f"--category is required for a multi-category COCO reference; available: {names}")
    return categories[0]


def _coco_detection_reference(rows: list[dict], category_name: str | None) -> tuple[dict, dict[str, int], int]:
    annotation_files = {row.get("annotation_file", "").strip() for row in rows}
    if "" in annotation_files:
        raise ValueError("every COCO manifest row must specify annotation_file")
    if len(annotation_files) != 1:
        raise ValueError("a COCO held-out manifest must reference exactly one annotation file")
    annotation_path = Path(annotation_files.pop())
    reference = json.loads(annotation_path.read_text(encoding="utf-8"))
    category = _category(reference.get("categories"), category_name)
    category_id = int(category["id"])
    images = reference.get("images")
    annotations = reference.get("annotations")
    if not isinstance(images, list) or not isinstance(annotations, list):
        raise ValueError("COCO reference must contain images and annotations lists")
    images_by_id = {int(image["id"]): image for image in images}
    if len(images_by_id) != len(images):
        raise ValueError("COCO reference contains duplicate image ids")
    entry_to_image_id: dict[str, int] = {}
    selected_ids: set[int] = set()
    selected_images = []
    for index, (row, entry) in enumerate(zip(rows, _row_entries(rows)), start=1):
        try:
            image_id = int(row["image_id"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"COCO manifest row {index} has an invalid image_id") from error
        if image_id in selected_ids:
            raise ValueError("the held-out COCO manifest contains duplicate image ids")
        image = images_by_id.get(image_id)
        if image is None:
            raise ValueError(f"COCO image id {image_id} from the manifest is absent from the reference")
        if Path(str(image.get("file_name", ""))).name != Path(entry).name:
            raise ValueError(f"COCO image id {image_id} does not match manifest entry {entry!r}")
        entry_to_image_id[entry] = image_id
        selected_ids.add(image_id)
        selected_images.append(image)
    selected_annotations = []
    annotation_ids: set[int] = set()
    for annotation in annotations:
        if int(annotation.get("category_id", -1)) != category_id or int(annotation.get("image_id", -1)) not in selected_ids:
            continue
        annotation_id = int(annotation["id"])
        if annotation_id in annotation_ids:
            raise ValueError("COCO reference contains duplicate annotation ids")
        bbox = annotation.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4 or not all(math.isfinite(float(value)) for value in bbox):
            raise ValueError(f"COCO annotation {annotation_id} has an invalid bbox")
        if float(bbox[2]) <= 0 or float(bbox[3]) <= 0:
            raise ValueError(f"COCO annotation {annotation_id} has a non-positive bbox")
        annotation_ids.add(annotation_id)
        selected_annotations.append(annotation)
    return {**reference, "images": selected_images, "categories": [category], "annotations": selected_annotations}, entry_to_image_id, category_id


def _yolo_detection_reference(rows: list[dict], category_name: str | None) -> tuple[dict, dict[str, int], int]:
    images, annotations = [], []
    entry_to_image_id: dict[str, int] = {}
    for image_id, (row, entry) in enumerate(zip(rows, _row_entries(rows)), start=1):
        image_path_text = row.get("path", "").strip()
        if not image_path_text:
            raise ValueError(f"YOLO manifest entry {entry!r} has no image path")
        with Image.open(image_path_text) as image:
            width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError(f"YOLO manifest entry {entry!r} has invalid image dimensions")
        images.append({"id": image_id, "width": width, "height": height, "file_name": entry})
        entry_to_image_id[entry] = image_id
        label_path_text = row.get("label_file", "").strip()
        lines = Path(label_path_text).read_text(encoding="utf-8").splitlines() if label_path_text else []
        parsed_count = 0
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) != 5:
                raise ValueError(f"YOLO label {label_path_text}:{line_number} must contain five values")
            try:
                class_value = float(parts[0])
                cx, cy, box_width, box_height = map(float, parts[1:])
            except ValueError as error:
                raise ValueError(f"YOLO label {label_path_text}:{line_number} contains a non-numeric value") from error
            values = (class_value, cx, cy, box_width, box_height)
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"YOLO label {label_path_text}:{line_number} contains a non-finite value")
            if class_value < 0 or not class_value.is_integer():
                raise ValueError(f"YOLO label {label_path_text}:{line_number} has an invalid class id")
            if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < box_width <= 1 and 0 < box_height <= 1):
                raise ValueError(f"YOLO label {label_path_text}:{line_number} is not a valid normalised box")
            x1 = max(0.0, (cx - box_width / 2) * width)
            y1 = max(0.0, (cy - box_height / 2) * height)
            x2 = min(float(width), (cx + box_width / 2) * width)
            y2 = min(float(height), (cy + box_height / 2) * height)
            if x2 - x1 < 1 or y2 - y1 < 1:
                raise ValueError(f"YOLO label {label_path_text}:{line_number} becomes sub-pixel after conversion")
            annotations.append({
                "id": len(annotations) + 1,
                "image_id": image_id,
                "category_id": 1,
                "iscrowd": 0,
                "bbox": [x1, y1, x2 - x1, y2 - y1],
                "area": (x2 - x1) * (y2 - y1),
            })
            parsed_count += 1
        declared_count = row.get("boxes", "").strip()
        if declared_count:
            try:
                if int(declared_count) != parsed_count:
                    raise ValueError(f"YOLO manifest entry {entry!r} declares {declared_count} boxes but has {parsed_count}")
            except ValueError as error:
                if str(error).startswith("YOLO manifest entry"):
                    raise
                raise ValueError(f"YOLO manifest entry {entry!r} has an invalid boxes count") from error
    return {
        "images": images,
        "annotations": annotations,
        "categories": [{"id": 1, "name": category_name or "target"}],
    }, entry_to_image_id, 1


def detection_reference(rows: list[dict], category_name: str | None) -> tuple[dict, dict[str, int], int]:
    kind = _manifest_kind(rows)
    if kind == "COCO":
        return _coco_detection_reference(rows, category_name)
    return _yolo_detection_reference(rows, category_name)


def detection_results(predictions: Any, entry_to_image_id: dict[str, int], category_id: int) -> list[dict]:
    if not isinstance(predictions, list):
        raise ValueError("held-out predictions must be a list")
    predicted_entries: list[str] = []
    results = []
    for item_index, item in enumerate(predictions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"prediction item {item_index} must be an object")
        entry = item.get("entry")
        if not isinstance(entry, str) or not entry:
            raise ValueError(f"prediction item {item_index} has no entry")
        predicted_entries.append(entry)
        boxes = item.get("boxes")
        if not isinstance(boxes, list):
            raise ValueError(f"prediction entry {entry!r} has no boxes list")
        for box_index, box in enumerate(boxes, start=1):
            if not isinstance(box, dict) or not isinstance(box.get("bbox"), list) or len(box["bbox"]) != 4:
                raise ValueError(f"prediction entry {entry!r} box {box_index} has an invalid bbox")
            try:
                x1, y1, x2, y2 = map(float, box["bbox"])
                score = float(box["score"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"prediction entry {entry!r} box {box_index} has invalid numeric data") from error
            if not all(math.isfinite(value) for value in (x1, y1, x2, y2, score)):
                raise ValueError(f"prediction entry {entry!r} box {box_index} has non-finite numeric data")
            if x2 <= x1 or y2 <= y1 or not 0 <= score <= 1:
                raise ValueError(f"prediction entry {entry!r} box {box_index} has invalid geometry or score")
            results.append({"image_id": entry_to_image_id.get(entry), "category_id": category_id,
                            "bbox": [x1, y1, x2 - x1, y2 - y1], "score": score})
    if len(predicted_entries) != len(set(predicted_entries)):
        raise ValueError("held-out predictions contain duplicate entries")
    expected, actual = set(entry_to_image_id), set(predicted_entries)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"held-out predictions do not match the test manifest (missing={missing[:3]}, extra={extra[:3]})")
    return results


def _trainer_detection_metrics(rows: list[dict], predictions: list[dict], category_name: str | None) -> dict:
    """Re-run the trainer's exact scoring protocol without loading a model.

    The publisher COCO file's ``area`` values can differ from bbox area.  The
    trainer intentionally reconstructs targets and derives area from each bbox,
    so its small/medium/large metrics must use that same reference construction.
    The independent validation kit still checks the three primary COCO metrics
    against the publisher reference below.
    """
    from ml_training.detect import load_targets, score

    items = load_targets(rows, _manifest_kind(rows), category_name)
    prediction_by_entry = {item["entry"]: item["boxes"] for item in predictions}
    evaluated = score(items, [prediction_by_entry[item["entry"]] for item in items])
    if evaluated.get("status") == "DEPENDENCY_MISSING":
        raise RuntimeError(evaluated["reason"])
    return evaluated


def detection(args, report: dict, run_dir: Path, out: Path, component_rescore: bool = False) -> dict:
    manifest_rows = read_samples(ROOT / "_derived" / "datasets" / report["task_id"] / "samples.csv")
    category_name = args.category or report.get("config", {}).get("category")
    predictions = json.loads((run_dir / "predictions_test.json").read_text(encoding="utf-8"))
    selection = None
    if component_rescore:
        rows, predictions, selection = component_conservative_subset(manifest_rows, predictions)
    else:
        rows = [row for row in manifest_rows if row["split"] == "test"]
    reference, image_ids, category_id = detection_reference(rows, category_name)
    results = detection_results(predictions, image_ids, category_id)
    (out / "reference_publisher_test.json").write_text(json.dumps(reference), encoding="utf-8")
    (out / "predictions_coco.json").write_text(json.dumps(results), encoding="utf-8")
    kit = run_kit(["detection", "--csv", str(out / "predictions_coco.json"), "--annotations", str(out / "reference_publisher_test.json"),
                   "--dataset", report["dataset"], "--dataset-version", report["dataset_version"], "--checkpoint", f"sha256:{report['checkpoint']['sha256']}",
                   "--split", "test"], out / "kit_detection.json")
    if component_rescore:
        evaluated = _trainer_detection_metrics(rows, predictions, category_name)
        differences = {
            "map_50_95_abs_difference": abs(evaluated["metrics"]["map_50_95"] - kit["coco_mAP_50_95"]),
            "ap_50_abs_difference": abs(evaluated["metrics"]["ap_50"] - kit["coco_AP_50"]),
            "ap_75_abs_difference": abs(evaluated["metrics"]["ap_75"] - kit["coco_AP_75"]),
        }
        return {
            "source": {
                "method": "post-hoc re-score of the frozen saved publisher-test predictions",
                "held_out_predictions": report["held_out_predictions"],
                "checkpoint": f"sha256:{report['checkpoint']['sha256']}",
            },
            "official_full_test": {
                **report["test"],
                "status": "PRESERVED_UNCHANGED",
                "independent_crosscheck": f"docs/validation/models/{report['model_id']}.kit_crosscheck.json",
            },
            "selection": selection,
            "conservative_component_subset": {
                "n_images": evaluated["n"],
                "reference_boxes": evaluated["reference_boxes"],
                "detections": evaluated["detections"],
                "metrics": evaluated["metrics"],
                "metric_implementation": "trainer score() protocol with bbox-derived reference area",
                "evaluation_protocol": evaluated["evaluation_protocol"],
            },
            "independent_kit": kit,
            "evaluator_agreement": differences,
        }
    return {"trainer": report["test"]["metrics"], "kit": kit}


def report_with_component_rescore(report: dict, result: dict, sidecar_path: str) -> dict:
    """Return a report updated with the post-hoc sensitivity subset only."""
    updated = json.loads(json.dumps(report))
    official_test = json.dumps(updated["test"], sort_keys=True)
    selection = result["selection"]
    subset = result["conservative_component_subset"]
    updated.setdefault("leakage_check", {}).update({
        key: selection[key] for key in (
            "near_duplicate_components_crossing_splits",
            "images_in_crossing_components",
            "test_images_in_crossing_components",
            "exclusion_rule",
        )
    })
    prior = updated.get("test_without_cross_split_duplicates")
    if prior and prior.get("n_images") != subset["n_images"] and "legacy_test_without_direct_cross_split_duplicate_endpoints" not in updated:
        updated["legacy_test_without_direct_cross_split_duplicate_endpoints"] = {
            **prior,
            "status": "SUPERSEDED_AS_CONSERVATIVE_SENSITIVITY_ANALYSIS",
            "reason": "Direct endpoint filtering omitted other test members of transitive components spanning splits.",
        }
    updated["test_without_cross_split_duplicates"] = {
        "n_images": subset["n_images"],
        "reference_boxes": subset["reference_boxes"],
        "metrics": subset["metrics"],
        "metric_implementation": subset.get("metric_implementation", "trainer score() protocol with bbox-derived reference area"),
        "selection_rule": selection["exclusion_rule"],
        "post_hoc_rescore": True,
        "source_predictions": result["source"]["held_out_predictions"],
        "independent_crosscheck": sidecar_path,
    }
    limitations = updated.setdefault("limitations", [])
    if COMPONENT_LIMITATION not in limitations:
        limitations.append(COMPONENT_LIMITATION)
    if json.dumps(updated["test"], sort_keys=True) != official_test:
        raise RuntimeError("component rescore attempted to alter the official full-test result")
    return updated


def model_card_with_component_rescore(text: str, result: dict, sidecar_path: str) -> str:
    """Update only the conservative result and its limitation in a model card."""
    selection = result["selection"]
    subset = result["conservative_component_subset"]
    metrics = subset["metrics"]
    replacement = (
        f"- After excluding all {selection['excluded_test_images']} test images belonging to any transitive "
        f"near-duplicate component spanning publisher splits ({subset['n_images']} retained): "
        f"mAP {metrics['map_50_95']:.3f}, AP50 {metrics['ap_50']:.3f}."
    )
    lines = text.splitlines()
    candidates = [
        index for index, line in enumerate(lines)
        if line.startswith("- Without the ") or line.startswith("- After excluding all ")
    ]
    if len(candidates) != 1:
        raise ValueError("model card must contain exactly one conservative duplicate-sensitivity result line")
    lines[candidates[0]] = replacement
    limitation_line = f"- {COMPONENT_LIMITATION}"
    if limitation_line not in lines:
        report_index = next((index for index, line in enumerate(lines) if line.startswith("Full report:")), None)
        if report_index is None:
            raise ValueError("model card has no Full report line")
        insert_at = report_index
        while insert_at > 0 and not lines[insert_at - 1]:
            insert_at -= 1
        lines[insert_at:insert_at] = [limitation_line, ""]
    evidence_line = f"Conservative rescore evidence: `{sidecar_path}`."
    if evidence_line not in lines:
        report_index = next(index for index, line in enumerate(lines) if line.startswith("Full report:"))
        lines.insert(report_index + 1, evidence_line)
    report_index = next(index for index, line in enumerate(lines) if line.startswith("Full report:"))
    while report_index >= 2 and not lines[report_index - 1] and not lines[report_index - 2]:
        del lines[report_index - 1]
        report_index -= 1
    return "\n".join(lines) + "\n"


def registry_with_component_limitation(registry: dict, model_id: str) -> dict:
    """Add the sensitivity-analysis limitation without changing the artifact bundle."""
    updated = json.loads(json.dumps(registry))
    models = [model for model in updated.get("models", []) if model.get("model_id") == model_id]
    if len(models) != 1:
        raise ValueError(f"model registry must contain exactly one {model_id!r} entry")
    limitations = models[0].setdefault("limitations", [])
    if COMPONENT_LIMITATION not in limitations:
        limitations.append(COMPONENT_LIMITATION)
    return updated


def update_component_artifacts(model_id: str, report: dict, result: dict, sidecar_path: str) -> None:
    """Persist the mechanically updated report, card, and registry limitation."""
    report_path = ROOT / "docs" / "validation" / "models" / f"{model_id}.json"
    report_path.write_text(json.dumps(report_with_component_rescore(report, result, sidecar_path), indent=2) + "\n", encoding="utf-8")
    card_path = ROOT / "docs" / "models" / f"{model_id}.md"
    card_path.write_text(model_card_with_component_rescore(card_path.read_text(encoding="utf-8"), result, sidecar_path), encoding="utf-8")
    registry_path = ROOT / "model_registry" / "models.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_path.write_text(json.dumps(registry_with_component_limitation(registry, model_id), indent=2) + "\n", encoding="utf-8")


def segmentation_report_with_component_rescore(report: dict, result: dict, sidecar_path: str) -> dict:
    """Update only the segmentation sensitivity subset and preserve full-test evidence."""
    updated = json.loads(json.dumps(report))
    official_test = json.dumps(updated["test"], sort_keys=True)
    selection = result["selection"]
    subset = result["conservative_component_subset"]
    updated.setdefault("leakage_check", {}).update({
        key: selection[key] for key in (
            "near_duplicate_components_crossing_splits",
            "images_in_crossing_components",
            "test_images_in_crossing_components",
            "exclusion_rule",
        )
    })
    prior = updated.get("test_without_cross_split_duplicates")
    if prior and prior.get("n_images") != subset["n_images"] and "legacy_test_without_direct_cross_split_duplicate_endpoints" not in updated:
        updated["legacy_test_without_direct_cross_split_duplicate_endpoints"] = {
            **prior,
            "status": "SUPERSEDED_AS_CONSERVATIVE_SENSITIVITY_ANALYSIS",
            "reason": "Direct endpoint filtering omitted other test members of transitive components spanning splits.",
        }
    updated["test_without_cross_split_duplicates"] = {
        **subset,
        "selection_rule": selection["exclusion_rule"],
        "post_hoc_rescore": True,
        "source_predictions": result["source"]["held_out_predictions"],
        "independent_crosscheck": sidecar_path,
    }
    limitations = updated.setdefault("limitations", [])
    if COMPONENT_LIMITATION not in limitations:
        limitations.append(COMPONENT_LIMITATION)
    per_segment = updated.get("test", {}).get("per_segment", [])
    absent = [str(item["segment"]) for item in per_segment if item.get("images") == 0]
    rare = [str(item["segment"]) for item in per_segment if 0 < int(item.get("images") or 0) < 20]
    if absent:
        message = f"No held-out reference mask exists for segment(s) {', '.join(absent)}; their per-segment Dice is undefined."
        if message not in limitations:
            limitations.append(message)
    if rare:
        message = f"Held-out support is below 20 images for segment(s) {', '.join(rare)}; their per-segment estimates are unstable."
        if message not in limitations:
            limitations.append(message)
    if json.dumps(updated["test"], sort_keys=True) != official_test:
        raise RuntimeError("component rescore attempted to alter the official full-test result")
    return updated


def segmentation_card_with_component_rescore(text: str, result: dict, sidecar_path: str) -> str:
    selection = result["selection"]
    subset = result["conservative_component_subset"]
    replacement = (
        f"- After excluding all {selection['excluded_test_images']} test images belonging to any transitive "
        f"near-duplicate component spanning publisher splits ({subset['n_images']} retained): "
        f"mean foreground Dice per image {subset['mean_foreground_dice_per_image']:.3f}; "
        f"whole-vessel Dice {subset['vessel_dice']:.3f}."
    )
    lines = text.splitlines()
    candidates = [
        index for index, line in enumerate(lines)
        if line.startswith("- Without test images") or line.startswith("- After excluding all ")
    ]
    if len(candidates) != 1:
        raise ValueError("segmentation model card must contain exactly one conservative duplicate-sensitivity result line")
    lines[candidates[0]] = replacement
    limitation_line = f"- {COMPONENT_LIMITATION}"
    if limitation_line not in lines:
        report_index = next(index for index, line in enumerate(lines) if line.startswith("Full report:"))
        lines[report_index:report_index] = [limitation_line, ""]
    evidence_line = f"Conservative rescore evidence: `{sidecar_path}`."
    if evidence_line not in lines:
        report_index = next(index for index, line in enumerate(lines) if line.startswith("Full report:"))
        lines.insert(report_index + 1, evidence_line)
    return "\n".join(lines) + "\n"


def update_segmentation_component_artifacts(model_id: str, report: dict, result: dict, sidecar_path: str) -> None:
    report_path = ROOT / "docs" / "validation" / "models" / f"{model_id}.json"
    report_path.write_text(json.dumps(segmentation_report_with_component_rescore(report, result, sidecar_path), indent=2) + "\n", encoding="utf-8")
    card_path = ROOT / "docs" / "models" / f"{model_id}.md"
    card_path.write_text(segmentation_card_with_component_rescore(card_path.read_text(encoding="utf-8"), result, sidecar_path), encoding="utf-8")
    registry_path = ROOT / "model_registry" / "models.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_path.write_text(json.dumps(registry_with_component_limitation(registry, model_id), indent=2) + "\n", encoding="utf-8")


def segmentation(args, report: dict, run_dir: Path, out: Path, component_rescore: bool = False) -> dict:
    size = int(report["evaluated_at_resolution"].split("x")[0])
    manifest_rows = read_samples(ROOT / "_derived" / "datasets" / report["task_id"] / "samples.csv")
    selection = None
    if component_rescore:
        rows, selection = component_conservative_rows(manifest_rows)
    else:
        rows = [row for row in manifest_rows if row["split"] == "test"]
    masks = ROOT / "_derived" / "datasets" / report["task_id"] / "masks"
    pairs = out / "pairs"
    pairs.mkdir(exist_ok=True)
    lines = []
    class_predictions, class_references = [], []
    for row in rows:
        with Image.open(masks / f"test_{row['image_id']}.png") as reference_image:
            reference_classes = np.asarray(reference_image.resize((size, size), Image.Resampling.NEAREST))
        with Image.open(run_dir / "test_masks" / f"{row['image_id']}.png") as predicted_image:
            predicted_classes = np.asarray(predicted_image)
        reference = reference_classes > 0
        predicted = predicted_classes > 0
        class_references.append(reference_classes)
        class_predictions.append(predicted_classes)
        reference_path, predicted_path = pairs / f"ref_{row['image_id']}.png", pairs / f"pred_{row['image_id']}.png"
        Image.fromarray(reference.astype(np.uint8) * 255).save(reference_path)
        Image.fromarray(predicted.astype(np.uint8) * 255).save(predicted_path)
        lines.append({"patient_id": row["group_id"], "reference_mask": str(reference_path), "predicted_mask": str(predicted_path)})
    with (out / "vessel_pairs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["patient_id", "reference_mask", "predicted_mask"])
        writer.writeheader()
        writer.writerows(lines)
    kit = run_kit(["segmentation", "--csv", str(out / "vessel_pairs.csv"), "--dataset", report["dataset"], "--dataset-version", report["dataset_version"],
                   "--checkpoint", f"sha256:{report['checkpoint']['sha256']}", "--split", "test"], out / "kit_segmentation.json")
    if component_rescore:
        from ml_training.segment import summarise

        evaluated = summarise(class_predictions, class_references, len(report["classes"]), report["classes"], None)
        differences = {
            "vessel_dice_abs_difference": abs(evaluated["vessel_dice"] - kit["mean_dice"]),
            "vessel_iou_abs_difference": abs(evaluated["vessel_iou"] - kit["mean_iou"]),
        }
        return {
            "source": {
                "method": "post-hoc re-score of the frozen saved publisher-test masks",
                "held_out_predictions": report["held_out_predictions"],
                "checkpoint": f"sha256:{report['checkpoint']['sha256']}",
            },
            "official_full_test": {
                **report["test"],
                "status": "PRESERVED_UNCHANGED",
                "independent_crosscheck": f"docs/validation/models/{report['model_id']}.kit_crosscheck.json",
            },
            "selection": selection,
            "conservative_component_subset": evaluated,
            "independent_kit": kit,
            "evaluator_agreement": differences,
        }
    return {"trainer": {"vessel_dice": report["test"]["vessel_dice"], "vessel_iou": report["test"]["vessel_iou"]}, "kit": kit}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=["detection", "segmentation"])
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--category", help="Detection category name (defaults to the training report's category).")
    parser.add_argument("--component-rescore", action="store_true",
                        help="Re-score saved predictions after excluding whole cross-split duplicate components.")
    parser.add_argument("--update-artifacts", action="store_true",
                        help="Update the model's conservative report/card/registry fields from the component rescore.")
    args = parser.parse_args()
    if args.update_artifacts and not args.component_rescore:
        parser.error("--update-artifacts requires --component-rescore")
    report = report_for(args.model_id)
    run_dir = ROOT / Path(report["checkpoint"]["path"]).parent
    out = run_dir / ("kit_crosscheck_components" if args.component_rescore else "kit_crosscheck")
    out.mkdir(parents=True, exist_ok=True)
    result = detection(args, report, run_dir, out, args.component_rescore) if args.task == "detection" else segmentation(args, report, run_dir, out, args.component_rescore)
    (out / "comparison.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    # A committed copy beside the evaluation report (run directories are not committed).
    committed = json.loads(json.dumps(result).replace(str(ROOT).replace("\\", "\\\\") + "\\\\", "").replace("\\\\", "/"))
    committed["generated_by"] = f"python -m ml_training.kit_crosscheck {args.task} --model-id {args.model_id}"
    if args.category:
        committed["generated_by"] += f" --category {args.category}"
    if args.component_rescore:
        committed["generated_by"] += " --component-rescore"
    if args.update_artifacts:
        committed["generated_by"] += " --update-artifacts"
    suffix = "component_rescore" if args.component_rescore else "kit_crosscheck"
    sidecar_path = f"docs/validation/models/{args.model_id}.{suffix}.json"
    (ROOT / sidecar_path).write_text(json.dumps(committed, indent=2) + "\n", encoding="utf-8")
    if args.update_artifacts:
        if args.task == "detection":
            update_component_artifacts(args.model_id, report, result, sidecar_path)
        else:
            update_segmentation_component_artifacts(args.model_id, report, result, sidecar_path)
    print(json.dumps(result, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
