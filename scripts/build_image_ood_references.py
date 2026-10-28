"""Fit and evaluate the feature-space applicability reference of every 2-D research image model.

For each registry model with research inference on 2-D images:
  * features of a seeded sample of its training images fit the reference (app/services/image_ood.py);
  * the refusal limit is the 0.99 quantile of the scores of its validation images (stage scores
    averaged; MEDTWIN_OOD_COMBINE=max takes the largest instead);
  * its test images, never used for fitting or calibration, measure the in-distribution refusal
    rate, and test images of the other image families (GI endoscopy, coronary angiography, CT,
    blood-cell microscopy) the cross-domain refusal rate.
Calibrating on validation images pooled with half of each test split was also tried: it lowered
false refusals where a publisher's test split differs from its validation split, but it let the
polyp segmenter's heavy-tailed test images widen its limit until CT and angiography passed, so the
validation split alone is used (docs/validation/IMAGE_APPLICABILITY_GATE.md).
Features are computed by app.services.model_inference.image_features, the same code path the
upload gate uses. Writes ood_reference.npz next to each checkpoint, docs/validation/models/
<model_id>.ood.json, and the registry bundle fields ood_reference_path / ood_reference_sha256.

  python scripts/build_image_ood_references.py [model_id ...]
"""

from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import image_ood, model_inference  # noqa: E402
from app.services.model_registry import _load_registry, _resolve_artifact_path  # noqa: E402

REGISTRY = ROOT / "model_registry" / "models.json"
# Features of public research images, cached outside the repository so evaluations can be repeated.
FEATURE_CACHE = Path(os.environ.get("MEDTWIN_OOD_FEATURE_CACHE") or Path(tempfile.gettempdir()) / "medtwin-ood-features")
COMBINE = os.environ.get("MEDTWIN_OOD_COMBINE", "mean")
SEED = 20261028
FIT_N, CALIBRATION_N, TEST_N, CROSS_DOMAIN_N = 3000, 1500, 1500, 300
FAMILIES = {
    "gi_kvasir_v2_classifier": "GI endoscopy", "gi_gastrovision_27class_classifier": "GI endoscopy",
    "gi_kvasir_seg_polyp_segmenter": "GI endoscopy", "angiography_stenosis_detector": "Coronary angiography",
    "angiography_syntax_segmenter": "Coronary angiography", "kidney_stone_detector": "CT",
    "hematology_cnmc_all_classifier": "Blood-cell microscopy",
}
# One test split per family supplies its cross-domain images.
FAMILY_SOURCE = {"GI endoscopy": "gi_kvasir_v2_classifier", "Coronary angiography": "angiography_stenosis_detector",
                 "CT": "kidney_stone_detector", "Blood-cell microscopy": "hematology_cnmc_all_classifier"}


def split_paths(model: dict, split: str) -> list[Path]:
    manifest = _resolve_artifact_path(model["artifact_bundle"]["split_manifest_path"])
    with manifest.open(encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("split") == split]
    paths = []
    for row in rows:
        path = Path(row["path"])
        paths.append(path if path.is_absolute() else ROOT / path)
    return sorted(set(paths))


def sample(paths: list[Path], n: int, salt: str) -> list[Path]:
    paths = list(paths)
    random.Random(f"{SEED}:{salt}").shuffle(paths)
    return paths[:n]


def features(model: dict, paths: list[Path], label: str) -> list[np.ndarray]:
    """One (images, dimensions) array per network stage (cached per model, image set and feature version)."""
    cache = FEATURE_CACHE / f"{model['model_id']}.{label}.{model_inference.FEATURE_VERSION}.npz"
    if cache.exists():
        with np.load(cache) as stored:
            if list(stored["paths"]) == [str(path) for path in paths]:
                return [stored[f"stage{index}"] for index in range(len(stored.files) - 1)]
    network, payload, device = model_inference.load_model(model)
    rows = []
    for path in paths:
        with Image.open(path) as image:
            image.load()
            rows.append(model_inference.image_features(network, payload, device, image))
    stages = [np.vstack([row[stage] for row in rows]) for stage in range(len(rows[0]))]
    FEATURE_CACHE.mkdir(parents=True, exist_ok=True)
    np.savez(cache, paths=np.array([str(path) for path in paths]), **{f"stage{index}": values for index, values in enumerate(stages)})
    return stages


def wilson(k: int, n: int) -> list[float]:
    if n == 0:
        return [None, None]
    z, p = 1.959964, k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def refusal(reference: dict, values: list[np.ndarray]) -> dict:
    distances = image_ood.score(reference, values)
    refused = int((distances > reference["threshold"]).sum())
    return {"n": int(len(distances)), "refused": refused, "refusal_rate": round(refused / len(distances), 4),
            "refusal_rate_95ci_wilson": wilson(refused, len(distances)),
            "distance_quantiles": {q: round(float(np.quantile(distances, float(q))), 2) for q in ("0.05", "0.5", "0.95")}}


def main(selected: list[str]) -> None:
    models = {m["model_id"]: m for m in _load_registry()["models"]
              if m.get("research_inference") and m.get("inference_input", "image_2d") == "image_2d"}
    targets = [model_id for model_id in models if not selected or model_id in selected]
    raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for model_id in targets:
        model = models[model_id]
        bundle = model["artifact_bundle"]
        started = time.perf_counter()
        fit_paths = sample(split_paths(model, "train"), FIT_N, f"{model_id}:fit")
        test_paths = sample(split_paths(model, "test"), TEST_N, f"{model_id}:test")
        calibration_paths = sample(split_paths(model, "val"), CALIBRATION_N, f"{model_id}:cal")
        reference = image_ood.fit_reference(
            features(model, fit_paths, "fit"), features(model, calibration_paths, "calibration"), combine=COMBINE,
            metadata={"model_id": model_id, "checkpoint_sha256": bundle["checkpoint_sha256"],
                      "feature_version": model_inference.FEATURE_VERSION,
                      "feature_source": {"image_classifier": "every backbone stage, spatial mean",
                                         "object_detector": "ResNet stages 1-4 of the detector backbone, spatial mean",
                                         "semantic_segmenter": "every U-Net encoder level and the bottleneck, spatial mean"}[model_inference.load_model(model)[1]["kind"]],
                      "fit_split": "train", "calibration_split": "val", "evaluation_split": "test", "seed": SEED,
                      "dataset_version": bundle.get("dataset_version")},
        )
        evaluation = {"in_distribution_test": refusal(reference, features(model, test_paths, "test-all")), "cross_domain": {}}
        own_family = FAMILIES[model_id]
        for family, source in FAMILY_SOURCE.items():
            if family == own_family:
                continue
            paths = sample(split_paths(models[source], "test"), CROSS_DOMAIN_N, f"{model_id}:{family}")
            evaluation["cross_domain"][family] = refusal(reference, features(model, paths, f"cross-{family.split()[0].lower()}"))
        checkpoint = _resolve_artifact_path(bundle["checkpoint_path"])
        target = checkpoint.with_name("ood_reference.npz")
        digest = image_ood.save_reference(target, reference)
        relative = target.relative_to(ROOT).as_posix()
        evidence = {
            "model_id": model_id, "family": own_family, "reference_path": relative, "reference_sha256": digest,
            "threshold": round(reference["threshold"], 3), "metadata": reference["metadata"], "evaluation": evaluation,
            "runtime_seconds": round(time.perf_counter() - started, 1),
            "interpretation": "Refusal of in-distribution test images is the gate's false-refusal rate; refusal of other "
                              "families' images is its cross-domain catch rate. Neither is a clinical performance measure.",
        }
        (ROOT / "docs" / "validation" / "models" / f"{model_id}.ood.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8", newline="\n")
        for entry in raw["models"]:
            if entry["model_id"] == model_id:
                entry["artifact_bundle"]["ood_reference_path"] = relative
                entry["artifact_bundle"]["ood_reference_sha256"] = digest
        REGISTRY.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(model_id, "threshold", evidence["threshold"], "test refusal", evaluation["in_distribution_test"]["refusal_rate"],
              {family: result["refusal_rate"] for family, result in evaluation["cross_domain"].items()},
              f"{evidence['runtime_seconds']}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
