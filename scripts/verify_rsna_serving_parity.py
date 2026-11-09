"""Served RSNA ICH model vs its held-out evaluation: the upload code path on test slices against predictions_test.csv.

A seeded sample of test slices is read from the archive and scored with app.services.model_inference.classify_multilabel
(one image at a time, as an upload is); probabilities and threshold decisions are compared with the evaluation's.
    python scripts/verify_rsna_serving_parity.py --sample 300
"""

import argparse
import csv
import io
import json
import random
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from PIL import Image  # noqa: E402

from app.services import model_inference  # noqa: E402

MODEL_ID = "brain_ct_rsna_ich_classifier"
LABELS = ("edh", "sdh", "iph", "ivh", "sah", "any")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sample", type=int, default=300)
    args = parser.parse_args()
    model = model_inference.get_model(MODEL_ID)
    network, payload, device = model_inference.load_model(model)
    predictions = model_inference._resolve_artifact_path(model["artifact_bundle"]["held_out_predictions_path"])
    with predictions.open(encoding="utf-8") as handle:
        rows = random.Random(20261104).sample(list(csv.DictReader(handle)), args.sample)
    worst, disagreements = 0.0, 0
    with zipfile.ZipFile(ROOT / "RSNA_PNG" / "rsna-ich-png.zip") as archive:
        for row in rows:
            output = model_inference.classify_multilabel(network, payload, device, Image.open(io.BytesIO(archive.read(row["entry"]))))
            for key, served in zip(LABELS, output["labels"]):
                evaluated = float(row[f"p_{key}"])
                worst = max(worst, abs(served["probability"] - evaluated))
                disagreements += served["at_or_above_threshold"] != (evaluated >= float(payload["thresholds"][key]))
    print(json.dumps({"slices": len(rows), "max_abs_probability_difference": round(worst, 6),
                      "threshold_decision_disagreements": disagreements, "decisions_compared": len(rows) * len(LABELS)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
