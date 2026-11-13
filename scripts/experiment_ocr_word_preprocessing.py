"""Isolated preregistered OCR word-crop experiment; no serving/model changes.

Uses commercially eligible RxHandBD publisher Train_Set only. The already exposed
official 1115-item test set and 48 ClinOCR pages are never rescored or used for
selection. A previously unscored internal holdout is reserved before execution.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import time
from zipfile import ZipFile
import csv

import numpy as np
from PIL import Image, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import ocr
from benchmark_external_ocr import aggregate, score, runtime_identity

ARCHIVE_SHA = "25d31c7bc1ceab4b3707d5e6d2205e518cadbd75d2f99efe1492a1aee5ef1951"
POLICIES = {
    "existing": {"mode": "existing_complete_ocr_images", "orientation": "existing_page_heuristic"},
    "upright": {"mode": "existing_detector_and_recognizer", "orientation": "preserve_publisher_crop_orientation"},
    "upright_scale2_border16": {"mode": "existing_detector_and_recognizer", "orientation": "preserve_publisher_crop_orientation", "scale": 2, "white_border": 16},
    "word_recognizer_tight_scale2_border8": {"mode": "existing_recognizer_only_on_explicit_single_word_crop", "orientation": "preserve_publisher_crop_orientation", "foreground_threshold": 230, "scale": 2, "white_border": 8, "uniform_image_stddev_refusal_below": 2},
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def partition(records: list[dict], dev_n: int, holdout_n: int) -> tuple[list[dict], list[dict]]:
    ordered = sorted(records, key=lambda row: digest(("medtwin-ocr-word-policy-v1:" + row["image_sha256"]).encode()))
    if len({r["image_sha256"] for r in ordered}) != len(ordered): raise ValueError("Duplicate source images require grouping before experiment")
    if len(ordered) < dev_n + holdout_n: raise ValueError("Insufficient distinct publisher-training crops")
    return ordered[:dev_n], ordered[dev_n:dev_n + holdout_n]


def prepared_image(image: Image.Image, policy: str) -> tuple[Image.Image | None, dict]:
    original = image.convert("RGB")
    details = {"original_size": list(original.size), "source_crop_bbox": None, "scale": 1, "border": 0}
    if policy == "upright_scale2_border16":
        transformed = original.resize((original.width * 2, original.height * 2), Image.Resampling.LANCZOS)
        details.update(scale=2, border=16)
        return ImageOps.expand(transformed, border=16, fill="white"), details
    if policy == "word_recognizer_tight_scale2_border8":
        gray = original.convert("L")
        if ImageStat.Stat(gray).stddev[0] < 2: return None, {**details, "refusal": "UNIFORM_IMAGE"}
        foreground = gray.point(lambda value: 255 if value < 230 else 0)
        bbox = foreground.getbbox()
        if bbox is None: return None, {**details, "refusal": "NO_VISIBLE_FOREGROUND"}
        # Fixed two-pixel margin is chosen before observing development errors.
        bbox = (max(0, bbox[0] - 2), max(0, bbox[1] - 2), min(original.width, bbox[2] + 2), min(original.height, bbox[3] + 2))
        transformed = original.crop(bbox)
        transformed = transformed.resize((transformed.width * 2, transformed.height * 2), Image.Resampling.LANCZOS)
        details.update(source_crop_bbox=list(bbox), scale=2, border=8)
        return ImageOps.expand(transformed, border=8, fill="white"), details
    return original, details


def predict(item):
    policy, image = item
    if policy == "existing":
        result = ocr._read_page(image)
        return {"text": result.text, "rotation": result.rotation_degrees, "confidence": result.mean_confidence,
                "lines": result.line_count, "transform": {"original_size": list(image.size)}}
    prepared, transform = prepared_image(image, policy)
    if prepared is None: return {"text": "", "rotation": 0, "confidence": None, "lines": 0, "transform": transform}
    engine = ocr._engine()
    if policy == "word_recognizer_tight_scale2_border8":
        readings, _ = engine.text_rec(np.asarray(prepared))
        text = " ".join(row[0] for row in readings)
        confidence = sum(float(row[1]) for row in readings) / len(readings) if readings else None
        return {"text": text, "rotation": 0, "confidence": confidence, "lines": len(readings), "transform": transform}
    found, _ = engine(np.asarray(prepared), use_cls=False, box_thresh=ocr.DETECTION_BOX_THRESHOLD)
    lines = ocr._reading_order(found or [])
    return {"text": ocr.page_text(lines), "rotation": 0,
            "confidence": sum(line["confidence"] for line in lines) / len(lines) if lines else None,
            "lines": len(lines), "transform": transform}


def run_policy(records: list[dict], policy: str) -> dict:
    predictions = list(ocr._executor().map(predict, [(policy, row["pil_image"]) for row in records]))
    scored = [{"id": row["id"], "image_sha256": row["image_sha256"],
               "reference_sha256": digest(row["gold"].encode()), "prediction_sha256": digest(prediction["text"].encode()),
               "rotation_degrees": prediction["rotation"], "mean_confidence": prediction["confidence"],
               "transform": prediction["transform"], **score(row["gold"], prediction["text"])}
              for row, prediction in zip(records, predictions, strict=True)]
    return {"policy": policy, "aggregate": aggregate(scored), "items": scored}


def paired_delta(baseline: list[dict], candidate: list[dict]) -> dict:
    if [r["id"] for r in baseline] != [r["id"] for r in candidate]: raise ValueError("Paired source IDs do not match")
    reference = np.asarray([r["reference_characters"] for r in baseline], dtype=float)
    differences = np.asarray([b["character_edits"] - a["character_edits"] for a, b in zip(baseline, candidate)], dtype=float)
    rng = np.random.default_rng(20261113)
    estimates = []
    for _ in range(2000):
        indices = rng.integers(0, len(baseline), len(baseline))
        estimates.append(float(differences[indices].sum() / reference[indices].sum()))
    delta = float(differences.sum() / reference.sum())
    interval = [float(v) for v in np.quantile(estimates, [.025, .975])]
    return {"candidate_minus_baseline_cer": delta, "word_resampling_95_percentile_interval": interval,
            "bootstrap_iterations": 2000, "seed": 20261113,
            "interpretation_scope": "Paired word-crop resampling only; writer/patient/source-prescription independence unknown; not a clinical-effect interval"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--development-n", type=int, default=128)
    parser.add_argument("--holdout-n", type=int, default=256)
    args = parser.parse_args()
    if not 16 <= args.development_n <= 256 or not 32 <= args.holdout_n <= 512: parser.error("Bounded development/holdout counts exceeded")
    if args.output_directory.exists(): parser.error("Choose a new output directory; existing experiment artifacts are never replaced")
    source = args.archive.read_bytes()
    if digest(source) != ARCHIVE_SHA: parser.error("Archive differs from the reviewed MIT RxHandBD v1 resource")
    records = []
    with ZipFile(io.BytesIO(source)) as archive:
        for row in csv.DictReader(io.StringIO(archive.read("Train_Label.csv").decode("utf-8-sig"))):
            if not row.get("Text", "").strip(): continue
            path = "Train_Set/" + row["Images"]
            content = archive.read(path)
            records.append({"id": Path(row["Images"]).stem, "image_sha256": digest(content), "gold": row["Text"], "content": content})
    development, holdout = partition(records, args.development_n, args.holdout_n)
    args.output_directory.mkdir(parents=True)
    plan = {"schema_version": "medtwin.ocr-word-experiment.v1", "planned_at": datetime.now(timezone.utc).isoformat(),
            "archive_sha256": ARCHIVE_SHA, "source": "RxHandBD Zenodo18478741 v1; MIT; publisher Train_Set only",
            "development": [{k: row[k] for k in ("id", "image_sha256")} for row in development],
            "reserved_holdout": [{k: row[k] for k in ("id", "image_sha256")} for row in holdout],
            "selection_rule": "Lowest development CER among fixed candidates, requiring >=0.01 absolute CER reduction and no reduction in exact fraction; otherwise retain existing. Evaluate selected policy and existing only on reserved holdout.",
            "policies": POLICIES, "model_artifacts": runtime_identity(),
            "no_exposed_official_test_reuse": True, "no_fitting_dictionary_or_label_repair": True,
            "limitations": ["The reserved set is publisher-training data, not the untouched official external test set.",
                            "Patient/writer/source-prescription grouping and prior generic-OCR pretraining exposure are unknown.",
                            "Policies are restricted to explicit single-word crops and cannot be applied to full clinical pages from this experiment."]}
    plan_bytes = json.dumps(plan, indent=2).encode()
    (args.output_directory / "plan.json").write_bytes(plan_bytes)
    start = time.monotonic()
    for row in development:
        image = Image.open(io.BytesIO(row["content"])); image.load(); row["pil_image"] = image
    dev_results = {policy: run_policy(development, policy) for policy in POLICIES}
    baseline = dev_results["existing"]["aggregate"]
    eligible = [policy for policy in POLICIES if policy != "existing"
                and dev_results[policy]["aggregate"]["cer_micro"] <= baseline["cer_micro"] - .01
                and dev_results[policy]["aggregate"]["exact_match_fraction"] >= baseline["exact_match_fraction"]]
    chosen = min(eligible, key=lambda p: dev_results[p]["aggregate"]["cer_micro"]) if eligible else "existing"
    frozen = {"frozen_at": datetime.now(timezone.utc).isoformat(), "plan_sha256": digest(plan_bytes),
              "selected_policy": chosen, "configuration": POLICIES[chosen],
              "development_results": {p: dev_results[p]["aggregate"] for p in POLICIES}}
    frozen_bytes = json.dumps(frozen, indent=2).encode()
    (args.output_directory / "development.json").write_text(json.dumps(dev_results, indent=2) + "\n", encoding="utf-8")
    (args.output_directory / "frozen-policy.json").write_bytes(frozen_bytes)
    # Reserved labels have not influenced candidate selection. Only now run the
    # existing pipeline and the single frozen candidate on those source images.
    for row in holdout:
        image = Image.open(io.BytesIO(row["content"])); image.load(); row["pil_image"] = image
    hold_base = run_policy(holdout, "existing")
    hold_chosen = run_policy(holdout, chosen) if chosen != "existing" else hold_base
    delta = paired_delta(hold_base["items"], hold_chosen["items"])
    proven = chosen != "existing" and delta["word_resampling_95_percentile_interval"][1] < 0
    result = {"schema_version": "medtwin.ocr-word-experiment-result.v1", "completed_at": datetime.now(timezone.utc).isoformat(),
              "plan_sha256": digest(plan_bytes), "frozen_policy_sha256": digest(frozen_bytes), "selected_policy": chosen,
              "development_results": frozen["development_results"], "holdout_baseline": hold_base,
              "holdout_candidate": hold_chosen, "paired_word_error_comparison": delta,
              "narrow_internal_word_cer_reduction_supported": proven, "serving_change_made": False,
              "full_real_report_or_clinical_validation": False, "elapsed_seconds": time.monotonic() - start,
              "limitations": plan["limitations"]}
    (args.output_directory / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output_directory), "selected": chosen, "development": frozen["development_results"],
                      "holdout_baseline": hold_base["aggregate"], "holdout_candidate": hold_chosen["aggregate"],
                      "paired_word_error_comparison": delta, "narrow_internal_word_cer_reduction_supported": proven,
                      "elapsed_seconds": result["elapsed_seconds"]}))


if __name__ == "__main__": main()
