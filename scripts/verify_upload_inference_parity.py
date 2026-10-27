"""Check that upload inference reproduces the held-out predictions saved at training time.

Runs the server code path (app.services.ecg_inference / volume_inference, the registered
checkpoint behind the SHA-256 gate) on the public held-out test sets and compares with the
predictions each trainer wrote:
- PTB-XL fold 10: every record through the WFDB reader and contract checks, then the
  Platt-scaled probabilities against predictions_test.csv.
- ACDC publisher test frames: every frame through the NIfTI envelope gate, then the
  predicted mask against held_out_predictions/<case>.nii.gz.
Writes counts and differences only (no case identifiers) to
docs/validation/UPLOAD_INFERENCE_PARITY.json.

  .venv\\Scripts\\python.exe scripts/verify_upload_inference_parity.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
from app.services import ecg_inference, model_inference, volume_inference  # noqa: E402
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


def main() -> int:
    result = {"generated_by": "scripts/verify_upload_inference_parity.py", "ecg": ecg_parity(), "volume": volume_parity()}
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
