"""Bounded parity controls using one frozen Kvasir test frame and one PTB-XL test record.

Reuses the existing full-holdout verifier's manifest/image readers, but never
invokes its full-cohort loops or overwrites historical evaluation reports.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

# Frozen before executing these controls. This script does not tune model settings.
TOLERANCES = {"preprocessed_tensor_atol": 0.0, "current_path_logits_atol": 1e-5,
              "saved_ecg_probability_atol": 0.003, "saved_mask_differing_pixels": 0,
              "source_mapping_differing_pixels": 0, "threshold_decision_disagreements": 0}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def numeric_comparison(actual, reference, atol):
    actual, reference = np.asarray(actual), np.asarray(reference)
    if actual.shape != reference.shape or not actual.size:
        raise ValueError("comparison requires nonempty matching shapes")
    if not np.isfinite(actual).all() or not np.isfinite(reference).all():
        raise ValueError("comparison requires finite numeric values")
    difference = np.abs(actual.astype(np.float64) - reference.astype(np.float64))
    return {"shape": list(actual.shape), "elements": int(actual.size), "max_abs_difference": float(difference.max()),
            "mean_abs_difference": float(difference.mean()), "differing_elements": int(np.count_nonzero(actual != reference)),
            "atol": atol, "rtol": 0.0, "within_tolerance": bool(np.all(difference <= atol))}


def threshold_disagreements(actual, reference, thresholds):
    actual, reference, thresholds = map(np.asarray, (actual, reference, thresholds))
    if actual.shape != reference.shape or actual.shape != thresholds.shape:
        raise ValueError("probability and threshold shapes must match")
    if not all(np.isfinite(value).all() for value in (actual, reference, thresholds)):
        raise ValueError("decisions require finite values")
    return int(np.count_nonzero((actual >= thresholds) != (reference >= thresholds)))


def model_evidence(model, device, payload):
    from app.services.model_registry import _resolve_artifact_path
    bundle = model["artifact_bundle"]
    checkpoint = _resolve_artifact_path(bundle["checkpoint_path"])
    digest = sha256(checkpoint)
    if digest != bundle["checkpoint_sha256"]:
        raise ValueError("registered checkpoint hash mismatch")
    return {"model_id": model["model_id"], "checkpoint": bundle["checkpoint_path"], "checkpoint_sha256": digest,
            "dataset_version": bundle["dataset_version"], "dataset_permission_scope": bundle["dataset_license"],
            "preprocessing_version": bundle["preprocessing_version"], "device": str(device),
            "reference_evaluation": bundle["evaluation_report_path"],
            "preprocessing": {key: payload[key] for key in ("input_size", "color", "preprocessing", "samples", "sampling_rate_hz", "leads") if key in payload}}


def image_parity(image_id=None):
    import torch
    from PIL import Image
    from pycocotools import mask as coco_mask
    from app.services import model_inference
    from app.services.model_registry import _resolve_artifact_path
    from ml_training.segment import SegmentationSet, build_binary_masks, per_image_scores
    from verify_upload_inference_parity import _manifest_rows, _open

    model = model_inference.get_model("gi_kvasir_seg_polyp_segmenter")
    bundle = model["artifact_bundle"]
    rows = [row for row in _manifest_rows(bundle) if row["split"] == "test"]
    row = next((candidate for candidate in rows if candidate["image_id"] == image_id), None) if image_id else rows[0]
    if row is None:
        raise ValueError("requested image is not in the frozen test manifest")
    network, payload, device = model_inference.load_model(model)
    evidence = {**model_evidence(model, device, payload), "selection": "first frozen test manifest row unless explicit test image id supplied; no search for a passing case",
                "sample_count": 1, "image_id": row["image_id"], "input_sha256": sha256(row["path"]),
                "publisher_reference_sha256": sha256(row["mask_file"]), "input_split": "test"}
    try:
        model_inference.check_document_photograph(Path(row["path"]))
        evidence["applicability"] = model_inference.check_distribution(model, Path(row["path"]))
    except model_inference.InferenceNotPermitted as error:
        return {**evidence, "status": "REFUSED", "reason": str(error), "prediction_run": False}
    with tempfile.TemporaryDirectory(prefix="medtwin-review-parity-") as temporary:
        _, items = build_binary_masks([row], Path(temporary), payload["classes"][0])
        trainer_tensor, _ = SegmentationSet(items, payload["input_size"], train=False, rgb=payload.get("color") == "rgb")[0]
        image = _open(row["path"])
        served_tensor = model_inference.segmenter_tensor(payload, image)
        tensor_comparison = numeric_comparison(served_tensor.cpu().numpy()[0], trainer_tensor.cpu().numpy(), TOLERANCES["preprocessed_tensor_atol"])
        with torch.no_grad(), model_inference.evaluated_precision(device)[0]:
            trainer_logits = network(trainer_tensor[None].to(device)).float().cpu().numpy()
        captured = []
        hook = network.register_forward_hook(lambda _network, _inputs, output: captured.append(output.detach().float().cpu().numpy()))
        try:
            served = model_inference.run_model(model, Path(row["path"]))
        finally:
            hook.remove()
        if len(captured) != 1:
            raise RuntimeError("serving did not execute exactly one segmentation forward pass")
        logits_comparison = numeric_comparison(captured[0], trainer_logits, TOLERANCES["current_path_logits_atol"])
        grid = captured[0].argmax(1)[0].astype(np.uint8)
        saved_path = _resolve_artifact_path(bundle["held_out_predictions_path"]) / f"{row['image_id']}.png"
        with Image.open(saved_path) as saved_image:
            saved = np.asarray(saved_image, dtype=np.uint8)
        saved_comparison = numeric_comparison(grid, saved, TOLERANCES["saved_mask_differing_pixels"])
        decoded = np.zeros((image.height, image.width), dtype=np.uint8)
        for segment in served["segments"]:
            rle = {"size": segment["rle"]["size"], "counts": segment["rle"]["counts"].encode("ascii")}
            decoded[coco_mask.decode(rle) > 0] = segment["class_index"]
        source_comparison = numeric_comparison(decoded, model_inference.mask_to_source(grid, image.size), TOLERANCES["source_mapping_differing_pixels"])
        with Image.open(items[0]["mask_path"]) as reference_image:
            reference = np.asarray(reference_image, dtype=np.uint8)
        reference_score = per_image_scores(decoded, reference, len(payload["classes"]))
    checks = {"trainer_serving_preprocessed_tensor": tensor_comparison, "current_trainer_serving_logits": logits_comparison,
              "historical_saved_model_grid_mask": saved_comparison, "served_rle_source_mapping": source_comparison}
    return {**evidence, "status": "VERIFIED_BOUNDED_PARITY" if all(value["within_tolerance"] for value in checks.values()) else "DIFFERENCES_RECORDED",
            "numeric_precision": served["numeric_precision"], "checks": checks,
            "saved_prediction_sha256": sha256(saved_path), "saved_prediction_path": str(saved_path.relative_to(ROOT)),
            "source_image_size": list(image.size), "sample_publisher_mask_dice": reference_score["vessel_dice"],
            "sample_publisher_mask_iou": reference_score["vessel_iou"],
            "limitations": ["One predetermined public test frame; no aggregate accuracy estimate or new independent clinical evaluation.",
                            "Historical raw logits were not saved. Logit comparison executes current trainer preprocessing and serving on the same immutable checkpoint.",
                            "The historical saved mask is independent of today's forward passes; source-coordinate RLE agreement verifies serving geometry."]}


def ecg_parity():
    import torch
    from app.services import ecg_inference, model_inference
    from app.services.model_registry import _resolve_artifact_path
    from ml_training import ptbxl
    from ml_training.ecg import apply_platt, predict_logits

    model = model_inference.get_model("ptbxl_ecg_baseline")
    bundle = model["artifact_bundle"]
    predictions = _resolve_artifact_path(bundle["held_out_predictions_path"])
    with predictions.open(encoding="utf-8", newline="") as handle:
        saved = next(csv.DictReader(handle))
    metadata = next(record for record in ptbxl.load_metadata()[0] if record["ecg_id"] == int(saved["ecg_id"]))
    if metadata["split"] != "test":
        raise ValueError("saved ECG prediction does not resolve to a test-fold record")
    base = ptbxl.DATASET_DIR / metadata["file"]
    publisher_check = ptbxl.verify_files([f"{metadata['file']}.hea", f"{metadata['file']}.dat"], ptbxl.publisher_checksums())
    record = ecg_inference.check_record(ecg_inference.read_wfdb(base.with_suffix(".hea").read_bytes(), base.with_suffix(".dat").read_bytes()),
                                       ecg_inference.CONTRACTS[bundle["preprocessing_version"]])
    trainer_signal = ptbxl.read_record(base.with_suffix(".hea"))
    network, payload, device = model_inference.load_model(model)
    ecg_inference.verify_contract(payload, ecg_inference.CONTRACTS[bundle["preprocessing_version"]])
    evidence = {**model_evidence(model, device, payload), "sample_count": 1, "ecg_id": metadata["ecg_id"], "input_split": "PTB-XL strat_fold 10",
                "selection": "first saved test prediction row; no search for favorable parity", "publisher_checksum_check": publisher_check,
                "input_sha256": {suffix: sha256(base.with_suffix(suffix)) for suffix in (".hea", ".dat")},
                "saved_prediction_file_sha256": sha256(predictions)}
    physical = numeric_comparison(record.signal_mv, trainer_signal, 0.0)
    means = np.asarray(payload["lead_mean_mv"], dtype=np.float32)
    stds = np.asarray(payload["lead_std_mv"], dtype=np.float32)
    # The trainer normalizes (records, samples, leads), then permutes to N,C,T.
    trainer_tensor = torch.from_numpy(np.ascontiguousarray(((trainer_signal - means) / stds).T))[None]
    captured_inputs, captured_logits = [], []
    before = network.register_forward_pre_hook(lambda _network, inputs: captured_inputs.append(inputs[0].detach().float().cpu().numpy()))
    after = network.register_forward_hook(lambda _network, _inputs, output: captured_logits.append(output.detach().float().cpu().numpy()))
    try:
        served = model_inference.run_prepared(model, record)
    finally:
        before.remove()
        after.remove()
    if len(captured_inputs) != 1 or len(captured_logits) != 1:
        raise RuntimeError("serving did not execute exactly one ECG forward pass")
    tensor_comparison = numeric_comparison(captured_inputs[0], trainer_tensor.numpy(), TOLERANCES["preprocessed_tensor_atol"])
    trainer_logits = predict_logits(network, trainer_tensor, device, batch=1)
    logits_comparison = numeric_comparison(captured_logits[0], trainer_logits, TOLERANCES["current_path_logits_atol"])
    probabilities = np.asarray([item["probability"] for item in served["classes"]])
    historical = np.asarray([float(saved[f"p_{name}"]) for name in payload["classes"]])
    probability_comparison = numeric_comparison(probabilities, historical, TOLERANCES["saved_ecg_probability_atol"])
    trainer_probabilities = apply_platt(trainer_logits, payload["platt"])[0]
    current_probability_comparison = numeric_comparison(probabilities, trainer_probabilities, 1e-6)
    thresholds = np.asarray(payload["thresholds"])
    disagreements = threshold_disagreements(probabilities, historical, thresholds)
    checks = {"trainer_serving_physical_signal": physical, "trainer_serving_preprocessed_tensor": tensor_comparison,
              "current_trainer_serving_logits": logits_comparison, "current_trainer_serving_probabilities": current_probability_comparison,
              "historical_saved_probabilities": probability_comparison}
    passed = all(value["within_tolerance"] for value in checks.values()) and disagreements == TOLERANCES["threshold_decision_disagreements"]
    return {**evidence, "status": "VERIFIED_BOUNDED_PARITY" if passed else "DIFFERENCES_RECORDED", "checks": checks,
            "numeric_precision": served["numeric_precision"], "threshold_decisions_compared": len(probabilities), "threshold_decision_disagreements": disagreements,
            "classes": served["classes"], "input_contract": served["input"], "thresholds": thresholds.tolist(),
            "limitations": ["One predetermined public test record; no new cohort accuracy estimate.",
                            "Historical predictions were rounded to six decimals and evaluated in batches of 256 with CUDA bfloat16; serving uses one record.",
                            "Historical raw logits were not saved; current logit parity is a separate reproducibility control."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("all", "images", "ecg"), default="all")
    parser.add_argument("--kvasir-image-id")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/review-2026-11-13/parity-controls.json")
    args = parser.parse_args()
    started = time.perf_counter()
    results = []
    for name, action in (("images", lambda: image_parity(args.kvasir_image_id)), ("ecg", ecg_parity)):
        if args.only not in ("all", name):
            continue
        try:
            results.append(action())
        except Exception as error:
            results.append({"workflow": name, "status": "BLOCKED", "error_type": type(error).__name__, "reason": str(error)})
    import torch
    sources = [Path(__file__), ROOT / "scripts/verify_upload_inference_parity.py", ROOT / "ml_training/segment.py",
               ROOT / "ml_training/ecg.py", ROOT / "ml_training/ptbxl.py", ROOT / "backend/app/services/model_inference.py",
               ROOT / "backend/app/services/ecg_inference.py"]
    report = {"schema_version": "medtwin-bounded-parity-v1", "recorded_at": datetime.now(timezone.utc).isoformat(),
              "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip(),
              "source_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path) for path in sources},
              "environment": {"python": platform.python_version(), "executable": sys.executable, "torch": torch.__version__,
                              "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},
              "tolerances_declared_before_execution": TOLERANCES, "seconds": round(time.perf_counter() - started, 3),
              "scope": "Bounded technical parity on public frozen test inputs. No fitting, threshold tuning, aggregate reevaluation, clinical validation or checkpoint replacement.",
              "results": results}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "results": [{"model": row.get("model_id", row.get("workflow")), "status": row["status"]} for row in results]}))
    return 0 if all(row["status"] == "VERIFIED_BOUNDED_PARITY" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
