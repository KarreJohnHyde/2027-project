"""Applicability reference for the EchoNet ejection-fraction model (the image gate's method on video features).

Fit on centre-clip features of training videos, set per-stage normalisers and the threshold (0.99 quantile)
on validation videos, then measure refusal on the test videos (false refusals) and on still images from
other modalities shown as static 112 x 112 clips (cross-domain catch rate). Writes the reference next to the
checkpoint and its evidence to docs/validation/models/<model>.ood.json, and records both in the registry.

    python scripts/build_echo_ood_reference.py [--fit 2000]
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from app.services import echo_inference as echo, image_ood, model_inference  # noqa: E402
from build_image_ood_references import FAMILY_SOURCE, split_paths, wilson  # noqa: E402

MODEL_ID = "echonet_ef_r2plus1d"
SEED = 20261106


def video_features(network, mean, std, device, paths: list[Path]) -> list[np.ndarray]:
    rows = []
    for path in paths:
        rows.append(echo.clip_features(network, echo.read_video(path), mean, std, device))
    return [np.vstack([row[stage] for row in rows]) for stage in range(len(rows[0]))]


def still_clip(path: Path) -> echo.EchoVideo:
    """A still image as a static clip in the development format (resized to 112 x 112, repeated)."""
    from PIL import Image

    with Image.open(path) as image:
        frame = np.asarray(image.convert("RGB").resize((echo.SIZE, echo.SIZE)), dtype=np.uint8)
    frames = np.repeat(frame[None], echo.needed_frames() + 8, axis=0)
    return echo.EchoVideo(frames, 50.0, len(frames))


def refusal(reference: dict, values: list[np.ndarray]) -> dict:
    distances = image_ood.score(reference, values)
    refused = int((distances > reference["threshold"]).sum())
    return {"n": int(len(distances)), "refused": refused, "refusal_rate": round(refused / len(distances), 4),
            "refusal_rate_95ci_wilson": wilson(refused, len(distances)),
            "distance_quantiles": {q: round(float(np.quantile(distances, float(q))), 2) for q in ("0.05", "0.5", "0.95")}}


def serving_gate_metrics(passed: set[str], bundle: dict) -> dict:
    """Held-out metrics on the test videos the whole serving pipeline accepts (format gate and applicability reference),
    written into the evaluation report and card; the registry summary then reports this population."""
    sys.path.insert(0, str(ROOT))
    from ml_training.common import bootstrap_ci
    from ml_training.echo_ef import auroc, regression_metrics

    predictions = json.loads((ROOT / bundle["held_out_predictions_path"]).read_text(encoding="utf-8"))
    kept = [item for item in predictions if item["video"] in passed]
    truth = np.array([item["reference_ef"] for item in kept])
    estimate = np.array([item["estimated_ef"] for item in kept])
    groups = np.array([item["video"] for item in kept])
    metrics = regression_metrics(truth, estimate)
    reduced = (truth < 50).astype(int)
    result = {"videos_scored": len(predictions), "accepted_by_both_gates": len(kept), "refused_by_applicability_reference": len(predictions) - len(kept),
              "metrics": metrics,
              "metrics_95ci": {key: bootstrap_ci(lambda index, key=key: regression_metrics(truth[index], estimate[index])[key], len(kept), groups, unit="patient (one video)")
                               for key in ("mae", "rmse", "r2")},
              "reduced_ef_auroc": auroc(reduced, -estimate),
              "note": "The format gate and the applicability reference together, as served; the reference was fitted after training on training and validation videos only."}
    report_path = ROOT / bundle["evaluation_report_path"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["test_serving_gate"] = result
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    card_path = ROOT / bundle["model_card_path"]
    ci = result["metrics_95ci"]["mae"]
    line = (f"- Through the full serving gate (format and applicability reference): {len(kept)} of {len(predictions)} format-accepted test videos; "
            f"MAE {metrics['mae']:.2f} EF points (95% CI {ci.get('low', float('nan')):.2f}-{ci.get('high', float('nan')):.2f}), R² {metrics['r2']:.3f}.")
    card = card_path.read_text(encoding="utf-8").splitlines()
    card = [existing for existing in card if not existing.startswith("- Through the full serving gate")]
    at = next((index for index, existing in enumerate(card) if existing.startswith("## Limitations")), len(card))
    card[at:at] = [line, ""]
    card_path.write_text("\n".join(card) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fit", type=int, default=2000)
    parser.add_argument("--cross", type=int, default=200)
    parser.add_argument("--limit", type=int, default=0, help="Smoke test: at most this many validation and test videos.")
    args = parser.parse_args()
    started = time.perf_counter()
    registry_path = ROOT / "model_registry" / "models.json"
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    entry = next(model for model in raw["models"] if model["model_id"] == MODEL_ID)
    bundle = entry["artifact_bundle"]
    network, payload, device = model_inference.load_model(entry)
    mean, std = echo.statistics(payload)
    with (ROOT / bundle["split_manifest_path"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    envelope = bundle["input_envelope"]

    def usable(split: str) -> list[Path]:
        paths = []
        for row in rows:
            if row["split"] == split and int(row["frames"]) >= echo.needed_frames():
                paths.append(Path(row["path"]))
        return paths[:args.limit] if args.limit and split != "train" else paths

    rng = random.Random(SEED)
    fit_paths = usable("train")
    rng.shuffle(fit_paths)
    fit = video_features(network, mean, std, device, fit_paths[:args.fit])
    calibration = video_features(network, mean, std, device, usable("val"))
    reference = image_ood.fit_reference(fit, calibration, metadata={
        "model_id": MODEL_ID, "checkpoint_sha256": bundle["checkpoint_sha256"], "feature_version": echo.FEATURE_VERSION,
        "feature_source": "centre clip: input statistics, then each R(2+1)-D stage's spatio-temporal mean",
        "fit_split": "train", "calibration_split": "val", "evaluation_split": "test", "seed": SEED, "dataset_version": bundle["dataset_version"]})
    test_rows = [row for row in rows if row["split"] == "test" and int(row["frames"]) >= echo.needed_frames()]
    test_rows = test_rows[:args.limit] if args.limit else test_rows
    test_features = video_features(network, mean, std, device, [Path(row["path"]) for row in test_rows])
    evaluation = {"in_distribution_test": refusal(reference, test_features), "cross_domain_still_images": {}}
    test_scores = image_ood.score(reference, test_features)
    passed = {row["group_id"] for row, value in zip(test_rows, test_scores) if value <= reference["threshold"]}
    models = {model["model_id"]: model for model in raw["models"]}
    for family, source in FAMILY_SOURCE.items():
        if source not in models:
            continue
        paths = split_paths(models[source], "test")
        random.Random(f"{SEED}:{family}").shuffle(paths)
        clips = [echo.clip_features(network, still_clip(path), mean, std, device) for path in paths[:args.cross]]
        if clips:
            evaluation["cross_domain_still_images"][family] = refusal(reference, [np.vstack([c[s] for c in clips]) for s in range(len(clips[0]))])
    checkpoint = ROOT / bundle["checkpoint_path"]
    target = checkpoint.with_name("ood_reference.npz")
    digest = image_ood.save_reference(target, reference)
    relative = target.relative_to(ROOT).as_posix()
    evidence = {"model_id": MODEL_ID, "reference_path": relative, "reference_sha256": digest, "threshold": round(reference["threshold"], 3),
                "metadata": reference["metadata"], "evaluation": evaluation, "runtime_seconds": round(time.perf_counter() - started, 1),
                "interpretation": "Refusal of test videos is the gate's false-refusal rate; refusal of other modalities' still images shown as "
                                  "static clips is a cross-domain catch rate. Neither is a clinical performance measure."}
    (ROOT / "docs" / "validation" / "models" / f"{MODEL_ID}.ood.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8", newline="\n")
    bundle["ood_reference_path"], bundle["ood_reference_sha256"] = relative, digest
    registry_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    serving = serving_gate_metrics(passed, bundle)
    print(json.dumps({"serving_gate_test": {key: serving[key] for key in ("videos_scored", "accepted_by_both_gates")}, "mae": serving["metrics"]["mae"]}))
    print(json.dumps({"threshold": evidence["threshold"], "test_refusal": evaluation["in_distribution_test"]["refusal_rate"],
                      "cross_domain": {k: v["refusal_rate"] for k, v in evaluation["cross_domain_still_images"].items()}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
