"""Fit a colour-input floor on PAD training images; evaluate frozen splits/domains.

This quality gate catches achromatic images. It is not proof of organ identity,
image authenticity, image adequacy for diagnosis, or clinical validation.
"""
from collections import defaultdict
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_image_ood_references import FAMILY_SOURCE, sample, split_paths
from app.services.skin_metadata import check_serving_features, FIELDS


def metadata_eligibility(rows, contract):
    counts = defaultdict(lambda: {"n": 0, "eligible": 0, "refused_reasons": {}})
    for row in rows:
        result = counts[row["split"]]
        result["n"] += 1
        try:
            check_serving_features({field: row["features"].get(field) for field in FIELDS}, contract)
            result["eligible"] += 1
        except ValueError as exc:
            reason = str(exc)
            result["refused_reasons"][reason] = result["refused_reasons"].get(reason, 0) + 1
    return dict(counts)


def chroma(path):
    with Image.open(path) as image:
        pixels = np.asarray(image.convert("RGB").resize((128, 128)), dtype=np.float32)
    return float((np.abs(pixels[..., 0] - pixels[..., 1]) + np.abs(pixels[..., 1] - pixels[..., 2])).mean() / 2)


def main():
    rows = [json.loads(line) for line in (ROOT / "_derived/datasets/multimodal/pad-ufes-20/samples.jsonl").read_text().splitlines()]
    values = defaultdict(list)
    for row in rows:
        values[row["split"]].append(chroma(row["image_path"]))
    threshold = float(np.quantile(values["train"], 0.005))
    registry_path = ROOT / "model_registry/models.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    models = {model["model_id"]: model for model in registry["models"]}
    cross = {}
    for family, source in FAMILY_SOURCE.items():
        paths = sample(split_paths(models[source], "test"), 100, "skin-quality:" + family)
        measured = np.array([chroma(path) for path in paths])
        cross[family] = {"images": len(paths), "colour_gate_refusal_rate": float(np.mean(measured < threshold))}
    result = {"fitted_on": "PAD train only", "quantile": 0.005, "minimum_chroma_255": threshold,
              "metadata_serving_eligibility": metadata_eligibility(rows, models["skin_padufes_image_tabular_classifier"]["clinical_metadata_contract"]),
              "definition": "mean(abs(R-G)+abs(G-B))/2 on an RGB 128-pixel thumbnail",
              "frozen_split_false_refusal": {name: {"n": len(items), "rate": float(np.mean(np.array(items) < threshold))}
                                             for name, items in values.items()},
              "cross_domain": cross,
              "scope": "Colour gate alone. Separate feature-space gate also runs; no clinical adequacy or universal modality guarantee."}
    for model in registry["models"]:
        if model["model_id"].startswith("skin_padufes_"):
            model["input_quality"].update(min_chroma=threshold, colour_gate_version="pad-training-chroma-quantile-v1")
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    target = ROOT / "docs/validation/models/skin_padufes_input_quality.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
