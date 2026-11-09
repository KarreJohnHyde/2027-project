"""Local external check of TotalSegmentator's lungs on LUNA16 CT (CC BY 4.0), against LUNA16's published masks.

Design, fixed before running: the population is every LUNA16 CT present locally (subset*/subset*/*.mhd) that
has a mask in seg-lungs-LUNA16; a random sample of --sample scans is drawn with --seed. For each scan the
TotalSegmentator 'total' model (--mode fast = 3 mm, or full = 1.5 mm) segments the five lung lobes; their
union is compared with LUNA16's lungs (mask values 3 and 4; 5 is the trachea) by Dice on the CT's own grid.
TotalSegmentator was trained on University Hospital Basel CT, not LUNA16, so this is external to its training.
The LUNA16 record does not document how its masks were made, so the result is agreement with them, not
accuracy against manual ground truth. Writes docs/validation/models/ct_totalsegmentator_v2.luna16_lungs.json.

nnU-Net starts worker processes, which on Windows re-import this file: all work sits under __main__.
    python scripts/evaluate_totalseg_luna16.py --sample 60 --seed 20261031 --mode fast
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASKS = ROOT / "seg-lungs-LUNA16" / "seg-lungs-LUNA16"
OUTPUT = ROOT / "docs" / "validation" / "models" / "ct_totalsegmentator_v2.luna16_lungs.json"
LOBES = ["lung_upper_lobe_left", "lung_lower_lobe_left", "lung_upper_lobe_right", "lung_middle_lobe_right", "lung_lower_lobe_right"]


def population() -> list[tuple[str, Path]]:
    scans = sorted((path.stem, path) for path in ROOT.glob("subset*/subset*/*.mhd"))
    return [(uid, path) for uid, path in scans if (MASKS / f"{uid}.mhd").exists()]


def bootstrap_mean_ci(values: list[float], seed: int, rounds: int = 2000) -> list[float]:
    import numpy as np

    rng = np.random.default_rng(seed)
    data = np.array(values)
    means = [float(data[rng.integers(0, len(data), len(data))].mean()) for _ in range(rounds)]
    return [round(float(np.percentile(means, 2.5)), 4), round(float(np.percentile(means, 97.5)), 4)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20261031)
    parser.add_argument("--mode", choices=("fast", "full"), default="fast")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "backend"))
    import nibabel as nib
    import numpy as np
    import SimpleITK as sitk

    from app.services import ct_organ_research

    ct_organ_research._configure()  # project-local weights; TotalSegmentator usage statistics off
    from totalsegmentator.python_api import totalsegmentator

    candidates = population()
    chosen = sorted(random.Random(args.seed).sample(candidates, min(args.sample, len(candidates))))
    rows = []
    for number, (uid, path) in enumerate(chosen, start=1):
        with tempfile.TemporaryDirectory() as tmp:
            nifti = Path(tmp) / "ct.nii.gz"
            sitk.WriteImage(sitk.ReadImage(str(path)), str(nifti))
            image = nib.load(str(nifti))
            start = time.time()
            result = totalsegmentator(image, None, fast=args.mode == "fast", roi_subset=LOBES, quiet=True, device="gpu",
                                      nr_thr_resamp=1, nr_thr_saving=1)
            seconds = time.time() - start
            spacing = [float(value) for value in image.header.get_zooms()[:3]]
        predicted = np.asanyarray(result.dataobj) > 0
        # ITK arrays are z, y, x; the NIfTI written from the same image is x, y, z on the same voxel order.
        reference = np.isin(sitk.GetArrayFromImage(sitk.ReadImage(str(MASKS / f"{uid}.mhd"))), (3, 4)).transpose(2, 1, 0)
        if reference.shape != predicted.shape:
            raise SystemExit(f"{uid}: grid {predicted.shape} differs from the reference {reference.shape}")
        both = int((predicted & reference).sum())
        dice = 2 * both / (int(predicted.sum()) + int(reference.sum()))
        voxel_ml = spacing[0] * spacing[1] * spacing[2] / 1000
        rows.append({"series_uid": uid, "dice_lungs": round(float(dice), 4), "volume_ml_model": round(float(predicted.sum() * voxel_ml), 1),
                     "volume_ml_reference": round(float(reference.sum() * voxel_ml), 1), "voxel_spacing_mm": [round(value, 4) for value in spacing],
                     "seconds": round(seconds, 1)})
        print(f"{number}/{len(chosen)} {uid[-12:]} dice {dice:.4f} ({seconds:.0f} s)", flush=True)

    dice = [row["dice_lungs"] for row in rows]
    differences = [row["volume_ml_model"] - row["volume_ml_reference"] for row in rows]
    report = {
        "model_id": "ct_totalsegmentator_v2", "generated_on": date.today().isoformat(), "tool": "scripts/evaluate_totalseg_luna16.py",
        "reference": "LUNA16", "reference_detail": "seg-lungs-LUNA16 lung masks (values 3 and 4), LUNA16 release on Zenodo (record 3723295), CC BY 4.0",
        "design": {"population": f"{len(candidates)} local LUNA16 CTs with a published lung mask", "sample": len(rows), "seed": args.seed,
                   "sampling": "simple random sample without replacement, drawn before any scan was segmented"},
        "mode": f"{args.mode} ({'3 mm' if args.mode == 'fast' else '1.5 mm'} TotalSegmentator 'total' model, five lung lobes merged)",
        "scans": len(rows),
        "dice_lungs": {"mean": round(float(np.mean(dice)), 4), "ci95": bootstrap_mean_ci(dice, args.seed), "median": round(float(np.median(dice)), 4),
                       "min": round(float(np.min(dice)), 4), "max": round(float(np.max(dice)), 4)},
        "volume_difference_ml": {"mean": round(float(np.mean(differences)), 1), "sd": round(float(np.std(differences, ddof=1)), 1) if len(differences) > 1 else None},
        "note": ("Agreement with LUNA16's published lung masks, whose method the release does not document; not accuracy against manual "
                 "ground truth. TotalSegmentator was not trained on LUNA16. Lungs only: LUNA16 has no masks for other organs or lobes."),
        "per_scan": rows,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes((json.dumps(report, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({key: report[key] for key in ("scans", "mode", "dice_lungs", "volume_difference_ml")}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
