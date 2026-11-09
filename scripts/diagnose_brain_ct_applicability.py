"""Measure the existing RSNA applicability reference without changing its gate.

Feature extraction only: no diagnostic predictions are returned or persisted.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import image_ood, model_inference


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--photograph", type=Path)
    args = parser.parse_args()
    model = model_inference.get_model("brain_ct_rsna_ich_classifier")
    reference = model_inference.ood_reference(model)
    network, payload, device = model_inference.load_model(model)
    with (ROOT / model["artifact_bundle"]["ood_sample_manifest_path"]).open() as handle:
        held_out = [row for row in csv.DictReader(handle) if row["split"] == "test"][:5]
    checks = []

    def check(label, image, source):
        tensor = model_inference.multilabel_tensor(payload, image)
        stages = model_inference.image_features(network, payload, device, image)
        scores = image_ood.stage_scores(reference, [stage[None] for stage in stages])[0]
        value = float(scores.mean())
        checks.append({"control": label, "source": source, "score": value, "stage_scores": scores.tolist(),
                       "exceeds_threshold": value > reference["threshold"], "input_tensor_range": [float(tensor.min()), float(tensor.max())],
                       "input_tensor_finite": bool(np.isfinite(tensor.cpu().numpy()).all())})

    for row in held_out:
        with Image.open(ROOT / row["path"]) as image:
            check("OWN_HELD_OUT_TEST_IMAGE", image.convert("RGB"), row["path"])
    check("NEGATIVE_CONTROL_NOISE", Image.fromarray(np.random.default_rng(42).integers(0, 256, (256, 256, 3), dtype=np.uint8)), "synthetic seed 42")
    endoscopy = next((ROOT / "kvasir-dataset-v2").glob("*/*.jpg"), None)
    if endoscopy:
        with Image.open(endoscopy) as image:
            check("INAPPROPRIATE_MODALITY_ENDOSCOPY", image.convert("RGB"), str(endoscopy.relative_to(ROOT)))
    if args.photograph:
        with Image.open(args.photograph) as image:
            check("PHOTOGRAPH_FOR_APPLICABILITY_DIAGNOSTICS_ONLY", image.convert("RGB"), "private source photograph; no disease inference")
    result = {"model_id": model["model_id"], "preprocessing_version": model["artifact_bundle"]["preprocessing_version"],
              "reference_version": reference["metadata"]["score_version"], "threshold_unchanged": reference["threshold"],
              "controls": checks, "clinical_validation": "NOT_PERFORMED", "diagnostic_predictions_produced": False,
              "limitation": "Five-image smoke check, not a threshold recalibration or independent validation study."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"threshold_unchanged": reference["threshold"], "scores": [(c["control"], round(c["score"], 3)) for c in checks]}, indent=2))


if __name__ == "__main__":
    main()
