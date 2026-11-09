"""Served masks vs the masks the held-out evaluation saved, for a registered multi-channel volumetric model.

Each test case of the model's manifest goes through the serving path exactly as an upload would: the input
envelope (read_volume), the SHA-256-checked checkpoint load (model_inference.load_model) and
volume_inference.predict. The served label volume is compared voxel by voxel with the saved held-out
prediction. Float16/cuDNN can introduce differences; the comparison records them
and does not itself establish accuracy or clinical equivalence.

    python scripts/verify_volumetric_serving_parity.py --model-id brain_mri_stroke_lesion_segresnet
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

from app.services import model_inference, volume_inference  # noqa: E402
from app.services.model_registry import _resolve_artifact_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--offline-evaluation-only", action="store_true", help="Verify a rejected research checkpoint offline without authorizing upload serving")
    args = parser.parse_args()
    if args.offline_evaluation_only:
        model = next((m for m in model_inference._load_registry()["models"] if m["model_id"] == args.model_id), None)
        if model is None:
            raise SystemExit("Model is not registered")
    else:
        model = model_inference.get_model(args.model_id)
    bundle = model["artifact_bundle"]
    manifest = json.loads(_resolve_artifact_path(bundle["split_manifest_path"]).read_text(encoding="utf-8"))
    envelope = volume_inference.load_envelope(_resolve_artifact_path(bundle["input_envelope_path"]), bundle["dataset_version"])
    predictions = _resolve_artifact_path(bundle["held_out_predictions_path"])
    root = Path(manifest["dataset_root"])
    network, payload, device = model_inference.load_model(model)
    rows, refused = [], {}
    for case in (item for item in manifest["cases"] if item["split"] == "test"):
        try:
            volume = volume_inference.read_volume(root / case["image_path"], envelope)
        except volume_inference.VolumeInputError as exc:
            refused[case["case_id"]] = exc.codes
            continue
        with model_inference._inference_lock:
            served = volume_inference.predict(network, payload, device, volume)
        saved = np.asarray(nib.load(str(predictions / f"{case['case_id']}.nii.gz")).dataobj).astype(np.uint8)
        differing = int((served != saved).sum())
        foreground = int(((served > 0) | (saved > 0)).sum())
        rows.append({"case_id": case["case_id"], "voxels": int(saved.size), "differing_voxels": differing,
                     "foreground_voxels_either": foreground, "identical": differing == 0})
    summary = {
        "scope": "OFFLINE_CHECKPOINT_PARITY_NOT_UPLOAD_AUTHORIZATION" if args.offline_evaluation_only else "UPLOAD_GATE_PARITY_NOT_CLINICAL_VALIDATION",
        "model_id": args.model_id, "checkpoint_sha256": bundle["checkpoint_sha256"], "test_cases": len(rows) + len(refused),
        "accepted_by_gate": len(rows), "refused_by_gate": refused,
        "identical_cases": sum(row["identical"] for row in rows), "differing_voxels_total": sum(row["differing_voxels"] for row in rows),
        "max_differing_voxels_in_a_case": max((row["differing_voxels"] for row in rows), default=0),
        "differing_share_of_foreground": (sum(row["differing_voxels"] for row in rows) / max(1, sum(row["foreground_voxels_either"] for row in rows))),
        "device": device.type, "cases": rows,
        "comparison_status": "EXACT" if all(row["identical"] for row in rows) else "DIFFERENCES_RECORDED_NOT_EXACT",
    }
    output = ROOT / "docs" / "validation" / "models" / f"{args.model_id}_serving_parity.json"
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("test_cases", "accepted_by_gate", "identical_cases", "differing_voxels_total",
                                                    "max_differing_voxels_in_a_case", "differing_share_of_foreground")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
