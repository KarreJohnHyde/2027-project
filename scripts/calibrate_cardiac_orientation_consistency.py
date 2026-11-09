"""Calibrate and evaluate how the cardiac MRI segmenter chooses a scanner series' axis convention.

The ACDC development frames carry no patient orientation (their affines are placeholders), so a scanner DICOM series
cannot be put into their voxel convention from tags. app.services.volume_inference.choose_convention runs the model
under all 16 conventions (row/column transpose x flips) and keeps the one whose predicted right ventricle lies in the
development direction from the left ventricle, among those where the left-ventricle area shrinks along the slices.

This script
1. takes that direction and its spread from the ground truth of the training frames only;
2. runs the rule on every held-out test frame, which is stored in the publisher's convention, and reports the Dice
   of the chosen convention against the ground truth next to the publisher's convention and each fixed convention.
   Every convention of a series is a relabelling of the same 16 candidates, so this measures the rule for any
   unknown convention;
3. with --write, records the prior and the held-out result in the model's input envelope.

    python scripts/calibrate_cardiac_orientation_consistency.py [--write] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import model_inference, volume_inference as vi  # noqa: E402
from app.services.model_registry import _resolve_artifact_path  # noqa: E402

MODEL_ID = "acdc_cardiac_mri_3d_unet"
RV, MYO, LV = 1, 2, 3
LIMIT_QUANTILE = 0.99


def macro_dice(prediction: np.ndarray, truth: np.ndarray) -> float:
    return float(np.mean([vi._dice(prediction == label, truth == label) for label in (RV, MYO, LV)]))


def simulated_geometry(truth: np.ndarray, spacing, rng: np.random.Generator) -> np.ndarray:
    """A scanner-like LPS affine for a frame on its own grid: a random double-oblique slice normal, and in-plane axes
    that put the ground-truth RV anterior-right of the LV (normal anatomy) at a random angle within 60 degrees.
    ACDC records no patient orientation; this stands in for the DICOM geometry a scanner series carries."""
    offset = (np.argwhere(truth == RV).mean(0) - np.argwhere(truth == LV).mean(0))[:2] * np.asarray(spacing[:2])
    theta = np.arctan2(offset[1], offset[0])
    while True:
        normal = rng.normal(size=3)
        normal /= np.linalg.norm(normal)
        if np.degrees(np.arccos(np.max(np.abs(normal)))) >= 25:
            break
    target = np.array([-1.0, -1.0, 0.0]) / np.sqrt(2.0)
    in_plane = target - normal * np.dot(target, normal)
    in_plane /= np.linalg.norm(in_plane)
    other = np.cross(normal, in_plane)
    turn = np.radians(rng.uniform(-60, 60))
    in_plane, other = np.cos(turn) * in_plane + np.sin(turn) * other, -np.sin(turn) * in_plane + np.cos(turn) * other
    row_dir = np.cos(theta) * in_plane - np.sin(theta) * other
    col_dir = np.cross(normal, row_dir)
    affine = np.eye(4)
    affine[:3, 0], affine[:3, 1], affine[:3, 2] = row_dir * spacing[0], col_dir * spacing[1], np.cross(row_dir, col_dir) * spacing[2]
    return affine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    model = model_inference.get_model(MODEL_ID)
    envelope_path = _resolve_artifact_path(model["artifact_bundle"]["input_envelope_path"])
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "_derived" / "datasets" / "acdc-cardiac-segmentation" / "manifest.json").read_text(encoding="utf-8"))
    root = Path(manifest["dataset_root"])

    # 1. Prior from the training ground truth only.
    directions, trends = [], []
    for case in [item for item in manifest["cases"] if item["split"] == "train"]:
        truth = np.asarray(nib.load(str(root / case["mask_path"])).dataobj).astype(np.uint8)
        zooms = tuple(float(value) for value in nib.load(str(root / case["image_path"])).header.get_zooms()[:3])
        direction = vi.ventricle_direction_deg(truth, zooms, RV, LV)
        if direction is not None:
            directions.append(direction)
        trends.append(vi.area_trend(truth, LV))
    radians = np.radians(directions)
    mean_direction = float(np.degrees(np.arctan2(np.sin(radians).mean(), np.cos(radians).mean())))
    offsets = np.abs([vi.angle_offset(value, mean_direction) for value in directions])
    limit = float(np.ceil(np.quantile(offsets, LIMIT_QUANTILE)))
    prior = {"rv_label": RV, "lv_label": LV, "rv_direction_deg": round(mean_direction, 1), "rv_direction_limit_deg": limit}
    training = {"frames": len(directions), "direction_resultant_length": round(float(np.hypot(np.sin(radians).mean(), np.cos(radians).mean())), 3),
                "abs_offset_quantiles_deg": {q: round(float(np.quantile(offsets, q)), 1) for q in (0.5, 0.95, 0.99)},
                "lv_area_shrinks_along_k_fraction": round(float(np.mean(np.array(trends) < 0)), 3)}
    print(json.dumps({"prior": prior, "training": training}), flush=True)

    # 2. The rule on every held-out frame.
    network, payload, device = model_inference.load_model(model)
    real_predict = vi.predict
    recorded: list[np.ndarray] = []

    def recording_predict(*call):
        mask = real_predict(*call)
        recorded.append(mask)
        return mask

    vi.predict = recording_predict
    cases = [item for item in manifest["cases"] if item["split"] == "test"]
    if args.limit:
        cases = cases[: args.limit]
    rows, refusals = [], {"with_geometry": {}, "without_geometry": {}}
    rng = np.random.default_rng(20261106)
    try:
        for index, case in enumerate(cases, 1):
            try:
                volume = vi.read_volume(root / case["image_path"], envelope)
            except vi.VolumeInputError as exc:  # outside the input envelope: never reaches the model at serving time either
                for key in refusals:
                    refusals[key][f"ENVELOPE:{exc.codes[0]}"] = refusals[key].get(f"ENVELOPE:{exc.codes[0]}", 0) + 1
                continue
            truth = np.asarray(nib.load(str(root / case["mask_path"])).dataobj).astype(np.uint8)
            affine = simulated_geometry(truth, volume.spacing_mm, rng)
            row = {}
            for key, geometry in (("with_geometry", affine), ("without_geometry", None)):
                recorded.clear()
                try:
                    chosen_mask, report = vi.choose_convention(network, payload, device, volume, prior, geometry)
                    row[key] = macro_dice(chosen_mask, truth)
                    row[f"{key}_untransposed"] = not report["chosen"]["variant"]["transpose_rows_columns"]
                except vi.VolumeInputError as exc:
                    refusals[key][exc.codes[0]] = refusals[key].get(exc.codes[0], 0) + 1
                    row[key] = None
                if key == "with_geometry":
                    row["per_variant"] = [macro_dice(vi._unorient(mask, variant), truth) for mask, variant in zip(recorded, vi.ORIENTATION_VARIANTS)]
            rows.append(row)
            if index % 20 == 0:
                print(f"{index}/{len(cases)}", flush=True)
    finally:
        vi.predict = real_predict
    per_variant_mean = np.mean([row["per_variant"] for row in rows], axis=0)

    def summary(key: str) -> dict:
        accepted = [row for row in rows if row[key] is not None]
        return {"accepted": len(accepted), "refused": refusals[key],
                "mean_macro_dice_chosen_convention": round(float(np.mean([row[key] for row in accepted])), 4) if accepted else None,
                "mean_macro_dice_publisher_convention_on_accepted": round(float(np.mean([row["per_variant"][0] for row in accepted])), 4) if accepted else None,
                "chosen_is_untransposed_fraction": round(float(np.mean([row[f"{key}_untransposed"] for row in accepted])), 3) if accepted else None}

    held_out = {
        "frames": len(rows),
        "with_simulated_scanner_geometry": summary("with_geometry"),
        "content_only_without_geometry": summary("without_geometry"),
        "mean_macro_dice_publisher_convention": round(float(per_variant_mean[0]), 4),
        "mean_macro_dice_worst_fixed_convention": round(float(per_variant_mean.min()), 4),
        "mean_macro_dice_by_fixed_convention": [round(float(value), 4) for value in per_variant_mean],
        "metric": "mean over frames of the macro Dice of RV, myocardium and LV cavity against the publisher's ground truth",
        "geometry_note": ("ACDC records no patient orientation. Each held-out frame was given a random double-oblique geometry in which its "
                          "ground-truth RV lies anterior-right of the LV within 60 degrees, standing in for a scanner series' DICOM geometry."),
    }
    print(json.dumps(held_out, indent=1))
    if args.write:
        envelope.pop("orientation_consistency", None)
        envelope["axis_convention"] = {**prior, "rule": vi.CONVENTION_RULE, "training_ground_truth": training, "held_out": held_out,
                                       "limit_basis": f"{LIMIT_QUANTILE:.0%} quantile of the absolute direction offset over the training frames",
                                       "script": "scripts/calibrate_cardiac_orientation_consistency.py"}
        envelope_path.write_bytes((json.dumps(envelope, indent=2) + "\n").encode("utf-8"))
        print(f"written to {envelope_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
