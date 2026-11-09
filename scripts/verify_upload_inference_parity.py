"""Check that upload inference reproduces the held-out predictions saved at training time.

Runs the server code path (app.services.ecg_inference / volume_inference, the registered
checkpoint behind the SHA-256 gate) on the public held-out test sets and compares with the
predictions each trainer wrote:
- PTB-XL fold 10: every record through the WFDB reader and contract checks, then the
  Platt-scaled probabilities against predictions_test.csv.
- ACDC publisher test frames: every frame through the NIfTI envelope gate, then the
  predicted mask against held_out_predictions/<case>.nii.gz.
- The seven 2D image models: every test-split image through the served functions
  (segment / detect / classify, plus the feature-space applicability gate), against the
  saved test predictions and the dataset's own reference masks or boxes, including the
  segmentation masks mapped back to source pixels (the coordinates the viewer draws).
Writes counts and differences only (no case identifiers) to
docs/validation/UPLOAD_INFERENCE_PARITY.json.

  .venv\\Scripts\\python.exe scripts/verify_upload_inference_parity.py [--only ecg|volume|images]
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.services import ecg_inference, image_ood, model_inference, volume_inference  # noqa: E402
from app.services.model_registry import _resolve_artifact_path  # noqa: E402

OUTPUT = ROOT / "docs" / "validation" / "UPLOAD_INFERENCE_PARITY.json"


def ecg_parity() -> dict:
    from ml_training.ptbxl import DATASET_DIR, SUPERCLASSES, load_metadata

    model = model_inference.get_model("ptbxl_ecg_baseline")
    bundle = model["artifact_bundle"]
    contract = ecg_inference.CONTRACTS[bundle["preprocessing_version"]]
    files = {record["ecg_id"]: record["file"] for record in load_metadata()[0]}
    with _resolve_artifact_path(bundle["held_out_predictions_path"]).open(encoding="utf-8", newline="") as handle:
        saved = list(csv.DictReader(handle))
    refused, differences, flips, started = Counter(), [], 0, time.perf_counter()
    thresholds = np.array([bundle["decision_thresholds"]["values"][name] for name in SUPERCLASSES])
    for row in saved:
        base = DATASET_DIR / files[int(row["ecg_id"])]
        try:
            record = ecg_inference.check_record(
                ecg_inference.read_wfdb(base.with_suffix(".hea").read_bytes(), base.with_suffix(".dat").read_bytes()), contract)
        except ecg_inference.EcgInputError as exc:
            refused[exc.code] += 1
            continue
        output = model_inference.run_prepared(model, record)
        served = np.array([item["probability"] for item in output["classes"]])
        reference = np.array([float(row[f"p_{name}"]) for name in SUPERCLASSES])
        differences.append(np.abs(served - reference))
        flips += int(np.sum((served >= thresholds) != (reference >= thresholds)))
    differences = np.array(differences)
    return {
        "model_id": "ptbxl_ecg_baseline", "checkpoint_sha256": bundle["checkpoint_sha256"], "held_out_split": "PTB-XL strat_fold 10 (publisher test fold)",
        "records": len(saved), "refused_by_contract_gate": dict(refused), "compared": int(len(differences)),
        "probability_abs_difference": {"max": float(differences.max()), "mean": float(differences.mean()), "p99": float(np.quantile(differences, 0.99))},
        "threshold_decisions_compared": int(differences.size), "threshold_decision_disagreements": flips,
        "reference_precision": "saved probabilities are rounded to 6 decimals; training scored batches of 256 under bfloat16 autocast on CUDA",
        "served_precision": output["numeric_precision"], "seconds": round(time.perf_counter() - started, 1),
    }


def volume_parity() -> dict:
    model = model_inference.get_model("acdc_cardiac_mri_3d_unet")
    bundle = model["artifact_bundle"]
    envelope = volume_inference.load_envelope(_resolve_artifact_path(bundle["input_envelope_path"]), bundle["dataset_version"])
    manifest = json.loads((ROOT / bundle["split_manifest_path"]).read_text(encoding="utf-8"))
    root = Path(manifest["dataset_root"])
    root = root if root.is_absolute() else ROOT / root
    predictions = _resolve_artifact_path(bundle["held_out_predictions_path"])
    network, payload, device = model_inference.load_model(model)
    import nibabel as nib

    refused, agreement, dice, identical, started = Counter(), [], [], 0, time.perf_counter()
    cases = [case for case in manifest["cases"] if case["split"] == "test"]
    for case in cases:
        try:
            volume = volume_inference.read_volume(root / case["image_path"], envelope)
        except volume_inference.VolumeInputError as exc:
            refused.update(exc.codes)
            continue
        with model_inference._inference_lock:
            served = volume_inference.predict(network, payload, device, volume)
        saved = np.asarray(nib.load(str(predictions / f"{case['case_id']}.nii.gz")).dataobj).astype(np.uint8)
        agreement.append(float((served == saved).mean()))
        identical += int(np.array_equal(served, saved))
        for label in (1, 2, 3):
            a, b = served == label, saved == label
            total = int(a.sum() + b.sum())
            if total:
                dice.append(2 * int((a & b).sum()) / total)
    return {
        "model_id": "acdc_cardiac_mri_3d_unet", "checkpoint_sha256": bundle["checkpoint_sha256"], "held_out_split": "ACDC publisher test set (frames)",
        "frames": len(cases), "refused_by_envelope_gate": dict(refused), "compared": len(agreement), "identical_masks": identical,
        "voxel_agreement": {"min": min(agreement), "mean": float(np.mean(agreement))},
        "served_vs_saved_structure_dice": {"min": float(min(dice)), "mean": float(np.mean(dice))},
        "reference_precision": "saved masks came from float16 autocast on CUDA; CUDA kernels in this path are not deterministic",
        "served_precision": "float16 autocast on CUDA" if device.type == "cuda" else "float32 on CPU", "seconds": round(time.perf_counter() - started, 1),
    }


def _manifest_rows(bundle: dict) -> list[dict]:
    with (ROOT / bundle["split_manifest_path"]).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _open(path: str) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        return image.copy()


class _Applicability:
    """The feature-space gate check_distribution applies, with the reference loaded once."""

    def __init__(self, model: dict, network, payload: dict, device):
        self.reference = model_inference.ood_reference(model)
        self.network, self.payload, self.device = network, payload, device
        self.accepted = self.checked = 0

    def __call__(self, image: Image.Image) -> None:
        features = model_inference.image_features(self.network, self.payload, self.device, image)
        value = float(image_ood.score(self.reference, [values[None] for values in features])[0])
        self.checked += 1
        self.accepted += int(value <= self.reference["threshold"])

    def summary(self) -> dict:
        return {"test_images_checked": self.checked, "accepted": self.accepted, "refused_as_out_of_distribution": self.checked - self.accepted,
                "acceptance_rate": round(self.accepted / self.checked, 4) if self.checked else None}


def _segmentation_summary(scores: list[dict]) -> dict:
    """The trainer's per-image definitions (ml_training.segment.summarise), without the bootstrap."""
    image_means = [float(np.mean(list(score["dice"].values()))) if score["dice"] else 1.0 for score in scores]
    return {"images": len(scores), "mean_foreground_dice_per_image": round(float(np.mean(image_means)), 4),
            "foreground_dice": round(float(np.mean([score["vessel_dice"] for score in scores])), 4),
            "foreground_iou": round(float(np.mean([score["vessel_iou"] for score in scores])), 4)}


def segmenter_parity(model_id: str) -> dict:
    import torch
    from pycocotools import mask as coco_mask
    from ml_training.segment import build_binary_masks, build_masks, per_image_scores

    model = model_inference.get_model(model_id)
    bundle = model["artifact_bundle"]
    network, payload, device = model_inference.load_model(model)
    gate = _Applicability(model, network, payload, device)
    saved_dir = _resolve_artifact_path(bundle["held_out_predictions_path"])
    rows = _manifest_rows(bundle)
    cache = Path(tempfile.mkdtemp(prefix="medtwin-parity-masks-"))
    started = time.perf_counter()
    try:
        if rows and rows[0].get("mask_file"):
            _names, items = build_binary_masks([row for row in rows if row["split"] == "test"], cache, payload["classes"][0])
        else:  # class indices depend on the categories of every split, as at training time
            _names, items = build_masks(rows, cache)
            items = [item for item in items if item["split"] == "test"]
        classes, size = len(payload["classes"]), payload["input_size"]
        precision_note = model_inference.evaluated_precision(device)[1]
        grid_identical, grid_agreement, source_matches_grid = 0, [], 0
        saved_scores, served_grid_scores, served_source_scores = [], [], []
        for item in items:
            image = _open(item["path"])
            precision, _ = model_inference.evaluated_precision(device)
            with torch.no_grad(), precision:
                grid = network(model_inference.segmenter_tensor(payload, image).to(device)).float().argmax(1).cpu().numpy()[0].astype(np.uint8)
            served = model_inference.segment(network, payload, device, image)
            gate(image)
            decoded = np.zeros((image.size[1], image.size[0]), dtype=np.uint8)
            for segment in served["segments"]:
                rle = {"size": segment["rle"]["size"], "counts": segment["rle"]["counts"].encode("ascii")}
                decoded[coco_mask.decode(rle) > 0] = segment["class_index"]
            source_matches_grid += int(np.array_equal(decoded, model_inference.mask_to_source(grid, image.size)))
            saved = np.asarray(Image.open(saved_dir / f"{item['image_id']}.png"), dtype=np.uint8)
            grid_identical += int(np.array_equal(grid, saved))
            grid_agreement.append(float((grid == saved).mean()))
            with Image.open(item["mask_path"]) as reference_image:
                native_reference = np.asarray(reference_image, dtype=np.uint8)
                grid_reference = np.asarray(reference_image.resize((size, size), Image.Resampling.NEAREST), dtype=np.uint8)
            if served["image_size"] != [native_reference.shape[1], native_reference.shape[0]]:
                raise RuntimeError("served mask size differs from the reference mask size")
            saved_scores.append(per_image_scores(saved, grid_reference, classes))
            served_grid_scores.append(per_image_scores(grid, grid_reference, classes))
            served_source_scores.append(per_image_scores(decoded, native_reference, classes))
    finally:
        shutil.rmtree(cache, ignore_errors=True)
    return {
        "model_id": model_id, "checkpoint_sha256": bundle["checkpoint_sha256"], "held_out_split": "internal test split (split manifest)",
        "test_images": len(items), "model_grid": f"{size}x{size}",
        "served_grid_identical_to_saved": grid_identical, "served_grid_pixel_agreement": {"min": round(min(grid_agreement), 5), "mean": round(float(np.mean(grid_agreement)), 5)},
        "served_rle_decodes_to_resized_grid": source_matches_grid,
        "reference_comparison": {
            "saved_predictions_at_model_grid": _segmentation_summary(saved_scores),
            "served_predictions_at_model_grid": _segmentation_summary(served_grid_scores),
            "served_masks_in_source_pixels": _segmentation_summary(served_source_scores),
            "note": "Source-pixel scores compare the mask the viewer draws (nearest-neighbour mapped back to each image's own size) with the publisher's mask at that size.",
        },
        "applicability_gate": gate.summary(),
        "served_precision": precision_note, "seconds": round(time.perf_counter() - started, 1),
    }


def detector_parity(model_id: str) -> dict:
    from ml_training.detect import iou, load_targets, operating_point

    model = model_inference.get_model(model_id)
    bundle = model["artifact_bundle"]
    network, payload, device = model_inference.load_model(model)
    gate = _Applicability(model, network, payload, device)
    rows = [row for row in _manifest_rows(bundle) if row["split"] == "test"]
    label_format = "COCO" if rows and rows[0].get("annotation_file") else "YOLO"
    category = payload["classes"][0] if label_format == "COCO" and payload["classes"][0] != "target" else None
    items = load_targets(rows, label_format, category)
    saved = {entry["entry"]: entry["boxes"] for entry in json.loads(_resolve_artifact_path(bundle["held_out_predictions_path"]).read_text(encoding="utf-8"))}
    threshold = float(payload["score_threshold"])
    started = time.perf_counter()
    served_all, coordinate_differences, score_differences, count_mismatches = [], [], [], 0
    for item in items:
        image = _open(item["path"])
        output = model_inference.detect(network, payload, device, image)
        gate(image)
        served = [{"bbox": box["bbox_xyxy"], "score": box["score"]} for box in output["boxes"]]
        served_all.append(served)
        kept_served = [box for box in served if box["score"] >= threshold]
        kept_saved = [box for box in saved[item["entry"]] if box["score"] >= threshold]
        count_mismatches += int(len(kept_served) != len(kept_saved))
        for box in kept_served:
            match = max(kept_saved, key=lambda other: iou(box["bbox"], other["bbox"]), default=None)
            if match is not None:
                coordinate_differences.append(max(abs(a - b) for a, b in zip(box["bbox"], match["bbox"])))
                score_differences.append(abs(box["score"] - match["score"]))
    return {
        "model_id": model_id, "checkpoint_sha256": bundle["checkpoint_sha256"], "held_out_split": "internal test split (split manifest)",
        "test_images": len(items), "reference_boxes": sum(len(item["boxes"]) for item in items), "display_score_threshold": threshold,
        "images_with_different_box_count_at_threshold": count_mismatches,
        "matched_box_max_coordinate_difference_px": {"max": round(max(coordinate_differences), 3), "mean": round(float(np.mean(coordinate_differences)), 4)} if coordinate_differences else None,
        "matched_box_score_difference": {"max": round(max(score_differences), 5)} if score_differences else None,
        "operating_point_served": operating_point(items, served_all, threshold),
        "operating_point_saved": operating_point(items, [saved[item["entry"]] for item in items], threshold),
        "applicability_gate": gate.summary(),
        "note": "Boxes are in source image pixels; served boxes are clipped to the image as the API returns them.",
        "seconds": round(time.perf_counter() - started, 1),
    }


def classifier_parity(model_id: str) -> dict:
    model = model_inference.get_model(model_id)
    bundle = model["artifact_bundle"]
    network, payload, device = model_inference.load_model(model)
    gate = _Applicability(model, network, payload, device)
    rows = [row for row in _manifest_rows(bundle) if row["split"] == "test"]
    with _resolve_artifact_path(bundle["held_out_predictions_path"]).open(encoding="utf-8", newline="") as handle:
        saved = {row["entry"]: row for row in csv.DictReader(handle)}
    started = time.perf_counter()
    differences, top_agreement, served_correct, saved_correct = [], 0, 0, 0
    for row in rows:
        image = _open(row["path"])
        output = model_inference.classify(network, payload, device, image)
        gate(image)
        reference = saved[row["entry"]]
        served = {item["class"]: item["probability"] for item in output["classes"]}
        differences.append(max(abs(served[name] - float(reference[f"p_{name}"])) for name in payload["classes"]))
        top_agreement += int(output["top_class"] == reference["y_pred"])
        served_correct += int(output["top_class"] == reference["y_true"])
        saved_correct += int(reference["y_pred"] == reference["y_true"])
    return {
        "model_id": model_id, "checkpoint_sha256": bundle["checkpoint_sha256"], "held_out_split": "internal test split (split manifest)",
        "test_images": len(rows), "top_class_agreement_with_saved": top_agreement,
        "probability_abs_difference": {"max": round(max(differences), 6), "mean": round(float(np.mean(differences)), 7)},
        "accuracy_served": round(served_correct / len(rows), 4), "accuracy_saved": round(saved_correct / len(rows), 4),
        "applicability_gate": gate.summary(),
        "reference_precision": "saved probabilities are temperature-scaled and rounded to 6 decimals",
        "seconds": round(time.perf_counter() - started, 1),
    }


IMAGE_MODELS = {
    "gi_kvasir_seg_polyp_segmenter": segmenter_parity, "angiography_syntax_segmenter": segmenter_parity,
    "kidney_stone_detector": detector_parity, "angiography_stenosis_detector": detector_parity,
    "gi_kvasir_v2_classifier": classifier_parity, "gi_gastrovision_27class_classifier": classifier_parity,
    "hematology_cnmc_all_classifier": classifier_parity,
}


def image_parity() -> list[dict]:
    results = []
    for model_id, check in IMAGE_MODELS.items():
        print(f"checking {model_id}", flush=True)
        results.append(check(model_id))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=("ecg", "volume", "images"), help="Run one section and keep the others from the last run.")
    args = parser.parse_args()
    sections = {"ecg": ecg_parity, "volume": volume_parity, "images": image_parity}
    result = json.loads(OUTPUT.read_text(encoding="utf-8")) if args.only and OUTPUT.exists() else {}
    result["generated_by"] = "scripts/verify_upload_inference_parity.py"
    for name, run in sections.items():
        if args.only in (None, name):
            result[name] = run()
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
