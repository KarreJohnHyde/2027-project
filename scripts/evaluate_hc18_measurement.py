"""Head-circumference evaluation of the HC18 head segmenter through the serving path (test subjects only, run once).

For each held-out test image: the registered model segments the head with the app's own serving functions
(model_inference.segmenter_tensor, the evaluated precision, mask_to_source), an ellipse is fitted to the predicted
boundary (ml_training.hc18_measure, border pixels excluded) and the circumference is measured in mm with the image's
own pixel size. Compared with the publisher's reference circumference: MAE, bias, SD, share within 2 and 3 mm.
A failed fit is counted as a failure, never dropped silently. The method floor (fit applied to the sonographer's
outline) is reported alongside.

  python scripts/evaluate_hc18_measurement.py [--model-id ultrasound_fetal_head_segmenter]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.services import model_inference as mi  # noqa: E402
from ml_training import hc18_measure  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-id", default="ultrasound_fetal_head_segmenter")
    args = parser.parse_args()
    import torch

    model = mi.get_model(args.model_id)
    network, payload, device = mi.load_model(model)
    precision, note = mi.evaluated_precision(device, payload)
    tasks = json.loads((ROOT / "dataset_registry" / "tasks.json").read_text(encoding="utf-8"))
    prep = next(t for d in tasks["datasets"] for t in d["tasks"] if t["task_id"] == "hc18-fetal-head-segmentation")["preparation"]
    rows = [row for row in csv.DictReader(open(prep["sample_manifest"], encoding="utf-8")) if row["split"] == "test"]
    errors, failures, records = [], 0, []
    for row in rows:
        image = Image.open(row["path"])
        with torch.no_grad(), precision:
            logits = network(mi.segmenter_tensor(payload, image).to(device))
        mask = mi.mask_to_source(logits.float().argmax(1).cpu().numpy()[0].astype(np.uint8), image.size) == 1
        try:
            ellipse = hc18_measure.fit_ellipse(hc18_measure.boundary_points(mask))
            measured = hc18_measure.circumference_mm(ellipse, float(row["pixel_size_mm"]))
        except (ValueError, np.linalg.LinAlgError):
            failures += 1
            records.append({"image": row["image_id"], "status": "FIT_FAILED"})
            continue
        error = measured - float(row["head_circumference_mm"])
        errors.append(error)
        records.append({"image": row["image_id"], "measured_mm": round(measured, 3), "reference_mm": float(row["head_circumference_mm"]), "error_mm": round(error, 3)})
    e = np.asarray(errors)
    result = {"model_id": args.model_id, "checkpoint_sha256": model["artifact_bundle"]["checkpoint_sha256"], "test_images": len(rows),
              "measured": len(e), "fit_failures": failures, "numeric_precision": note,
              "mean_absolute_error_mm": float(np.abs(e).mean()), "bias_mm": float(e.mean()), "sd_mm": float(e.std(ddof=1)),
              "within_2mm": float((np.abs(e) <= 2).mean()), "within_3mm": float((np.abs(e) <= 3).mean()),
              "method_floor_mm": prep.get("measurement_method_floor_mm"), "reference": "publisher head circumference (HC18 training labels)",
              "scope": "held-out test subjects of the 70/15/15 subject split; HC18 challenge test labels are not public", "records": records}
    out = ROOT / "docs" / "validation" / "models" / f"{args.model_id}.hc_measurement.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("test_images", "measured", "fit_failures", "mean_absolute_error_mm", "bias_mm", "within_3mm")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
