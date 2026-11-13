"""One-input publisher-reference source-grid agreement for the saved native runs."""
from pathlib import Path
import hashlib
import json
import sys
import nibabel as nib
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.volume_inference import mask_from_output


def main():
    out = ROOT / "artifacts/universal-2026-11-13/native-workflows"
    comparisons = []
    for name, dataset in (("cardiac", "acdc-cardiac-segmentation"), ("brain", "isles22-dwi-adc")):
        manifest = json.loads((ROOT / f"_derived/datasets/{dataset}/manifest.json").read_text(encoding="utf-8"))
        sample = next(c for c in manifest["cases"] if c["split"] == "test")
        reference_path = Path(manifest["dataset_root"]) / sample["mask_path"]
        source_path = Path(manifest["dataset_root"]) / sample["image_path"]
        for path, key in ((reference_path, "mask_sha256"), (source_path, "image_sha256")):
            if hashlib.sha256(path.read_bytes()).hexdigest() != sample[key]:
                raise ValueError("Frozen publisher input/reference checksum mismatch")
        reference = np.asanyarray(nib.load(reference_path).dataobj)
        evidence = json.loads((out / f"{name}-native-evidence.json").read_text(encoding="utf-8"))
        prediction = mask_from_output(evidence["run"]["research_output"])
        if prediction.shape != reference.shape:
            raise ValueError("Reference/prediction source grids differ")
        metrics = []
        for label in sorted(set(np.unique(reference)) | set(np.unique(prediction))):
            if label == 0:
                continue
            a, b = prediction == label, reference == label
            intersection, union, denominator = int((a & b).sum()), int((a | b).sum()), int(a.sum() + b.sum())
            metrics.append({"class_index": int(label), "reference_voxels": int(b.sum()), "predicted_voxels": int(a.sum()),
                            "dice": 2 * intersection / denominator if denominator else None,
                            "iou": intersection / union if union else None})
        comparisons.append({"workflow": name, "scope": "ONE_PUBLIC_TEST_INPUT_NOT_POPULATION_ACCURACY",
                            "reference": "DATASET_PUBLISHER_ANNOTATION_NOT_INDEPENDENT_CLINICAL_REVIEW",
                            "reference_sha256": sample["mask_sha256"], "source_sha256": sample["image_sha256"],
                            "run_id": evidence["run"]["id"], "shape": list(prediction.shape), "metrics": metrics})
    (out / "publisher-reference-comparisons.json").write_text(json.dumps(comparisons, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"scope": "TWO_SINGLE_INPUT_SOURCE_GRID_COMPARISONS", "comparisons": len(comparisons)}))


if __name__ == "__main__":
    main()
