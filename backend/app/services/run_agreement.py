"""Agreement between two research runs on the same upload (model versus model; neither is ground truth)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from app.services.evaluation_metrics import _overlap
from app.services.reference_annotations import _iou, decode

SEMANTICS = ("Agreement between two model outputs on the same upload. Neither output is ground truth: agreement can be shared error, "
             "and disagreement does not say which model is right. Each model's held-out evaluation is its performance evidence.")


class NotComparable(ValueError):
    """The two outputs are of kinds that cannot be compared."""


def _masks(output: dict) -> dict[str, np.ndarray]:
    width, height = output["image_size"]
    masks: dict[str, np.ndarray] = {}
    for segment in output["segments"]:
        mask = decode(segment["rle"])
        masks[segment["segment"]] = masks.get(segment["segment"], np.zeros((height, width), dtype=bool)) | mask
    return masks


def _segmentation(a: dict, b: dict) -> dict[str, Any]:
    if list(a["image_size"]) != list(b["image_size"]):
        raise NotComparable("IMAGE_SIZE_MISMATCH: the runs were made on different pixel grids.")
    masks_a, masks_b = _masks(a), _masks(b)
    width, height = a["image_size"]
    empty = np.zeros((height, width), dtype=bool)
    union_a = np.logical_or.reduce(list(masks_a.values())) if masks_a else empty
    union_b = np.logical_or.reduce(list(masks_b.values())) if masks_b else empty
    dice, iou = _overlap(union_a, union_b)
    per_class = {}
    for name in sorted(set(masks_a) & set(masks_b)):
        class_dice, class_iou = _overlap(masks_a[name], masks_b[name])
        per_class[name] = {"dice": round(class_dice, 4), "iou": round(class_iou, 4)}
    return {"kind": "segmentation", "foreground_dice": round(dice, 4), "foreground_iou": round(iou, 4),
            "area_px": [int(union_a.sum()), int(union_b.sum())], "shared_classes": per_class,
            "classes_only_in_first": sorted(set(masks_a) - set(masks_b)), "classes_only_in_second": sorted(set(masks_b) - set(masks_a))}


def _detection(a: dict, b: dict) -> dict[str, Any]:
    if list(a["image_size"]) != list(b["image_size"]):
        raise NotComparable("IMAGE_SIZE_MISMATCH: the runs were made on different pixel grids.")
    first = sorted((box for box in a["boxes"] if box["above_display_threshold"]), key=lambda box: -box["score"])
    second = [box for box in b["boxes"] if box["above_display_threshold"]]
    unmatched = list(range(len(second)))
    pairs, only_first = [], []
    for box in first:
        best = max(unmatched, key=lambda index: _iou(box["bbox_xyxy"], second[index]["bbox_xyxy"]), default=None)
        overlap = _iou(box["bbox_xyxy"], second[best]["bbox_xyxy"]) if best is not None else 0.0
        if best is not None and overlap >= 0.5:
            pairs.append({"first_box": box["bbox_xyxy"], "second_box": second[best]["bbox_xyxy"], "iou": round(overlap, 4)})
            unmatched.remove(best)
        else:
            only_first.append(box["bbox_xyxy"])
    return {"kind": "detection", "matched": len(pairs), "only_first": len(only_first), "only_second": len(unmatched),
            "mean_matched_iou": round(float(np.mean([pair["iou"] for pair in pairs])), 4) if pairs else None,
            "pairs": pairs, "only_first_boxes": only_first, "only_second_boxes": [second[index]["bbox_xyxy"] for index in unmatched],
            "classes": [a.get("class"), b.get("class")]}


def _classification(a: dict, b: dict) -> dict[str, Any]:
    probabilities = [{item["class"]: item["probability"] for item in output["classes"]} for output in (a, b)]
    shared = sorted(set(probabilities[0]) & set(probabilities[1]))
    return {"kind": "classification", "top_classes": [a["top_class"], b["top_class"]], "same_top_class": a["top_class"] == b["top_class"],
            "shared_classes": {name: [round(probabilities[0][name], 4), round(probabilities[1][name], 4)] for name in shared},
            "note": "Probabilities of different models are not calibrated against each other and are not averaged."}


def _multilabel(a: dict, b: dict) -> dict[str, Any]:
    labels = [{item["label"]: item for item in output["labels"]} for output in (a, b)]
    shared = sorted(set(labels[0]) & set(labels[1]))
    return {"kind": "multilabel_classification", "positive_labels": [a["positive_labels"], b["positive_labels"]],
            "shared_labels": {name: {"probabilities": [round(labels[0][name]["probability"], 4), round(labels[1][name]["probability"], 4)],
                                     "at_or_above_threshold": [bool(labels[0][name].get("at_or_above_threshold")), bool(labels[1][name].get("at_or_above_threshold"))]}
                              for name in shared},
            "note": "Each model's threshold was chosen on its own validation data; probabilities are not averaged."}


def _volume(a: dict, b: dict) -> dict[str, Any]:
    volumes = [{item["structure"]: item["volume_ml"] for item in output["structures"]} for output in (a, b)]
    shared = sorted(set(volumes[0]) & set(volumes[1]))
    return {"kind": "volume_segmentation", "shared_structures": {name: {"volume_ml": [volumes[0][name], volumes[1][name]],
                                                                        "difference_ml": round(volumes[1][name] - volumes[0][name], 3)} for name in shared},
            "same_grid": list(a.get("volume_shape_ijk", [])) == list(b.get("volume_shape_ijk", []))}


HANDLERS = {"segmentation": _segmentation, "detection": _detection, "classification": _classification,
            "multilabel_classification": _multilabel, "volume_segmentation": _volume}


def agreement(first: Optional[dict], second: Optional[dict]) -> dict[str, Any]:
    if not first or not second:
        raise NotComparable("NO_MODEL_OUTPUT: both runs must have produced an output (abstentions cannot be compared).")
    if first["type"] != second["type"] or first["type"] not in HANDLERS:
        raise NotComparable(f"NOT_COMPARABLE: a {first['type']} output and a {second['type']} output are not the same kind of result.")
    return {"comparison": "MODEL_VS_MODEL_AGREEMENT", "semantics": SEMANTICS, **HANDLERS[first["type"]](first, second)}
