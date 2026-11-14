"""Pairs list for a Medical Segmentation Decathlon CT task (Task03 Liver, Task07 Pancreas) for
ml_training.volumetric_multichannel.

Labels and the licence are read from the task's own dataset.json (MSD: CC BY-SA 4.0); the images are single-channel
CT in Hounsfield units. Only labelled training cases (imagesTr/labelsTr) are listed; macOS "._" files are skipped.
Nothing leaves this computer, and the data stay under the Git-ignored dataset folders.

    python scripts/prepare_msd_ct_datasets.py --source <...>/Task07_Pancreas --output _derived/datasets/msd-pancreas
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

NAMES = {  # display names for MSD label strings (dataset.json "labels")
    "background": "background", "liver": "liver", "cancer": "tumour", "pancreas": "pancreas", "tumour": "tumour", "tumor": "tumour",
}


def prepare(source: Path, output: Path, any_modality: bool = False) -> dict:
    meta = json.loads((source / "dataset.json").read_text(encoding="utf-8"))
    modality = {str(key): value for key, value in (meta.get("modality") or {}).items()}
    if not modality or (not any_modality and list(modality.values()) != ["CT"]):
        raise SystemExit(f"{source.name}: dataset.json modality is {modality}, not single-channel CT (use --any-modality for MRI tasks)")
    channels = [modality[key] for key in sorted(modality, key=int)]
    labels = {int(key): NAMES.get(str(value).strip().lower(), re.sub(r"\W+", "_", str(value).strip().lower())) for key, value in meta["labels"].items()}
    expected = meta.get("training")
    if not isinstance(expected, list) or len(expected) != meta.get("numTraining"):
        raise ValueError("Publisher training inventory is absent or inconsistent")
    expected_images, expected_masks = set(), set()
    for pair in expected:
        for field, folder, names in (("image", "imagesTr", expected_images), ("label", "labelsTr", expected_masks)):
            value = str(pair[field]).removeprefix("./")
            parts = value.split("/")
            if len(parts) != 2 or parts[0] != folder or not parts[1].endswith(".nii.gz") or "\\" in value or ":" in value:
                raise ValueError("Invalid publisher pair path")
            if parts[1] in names:
                raise ValueError("Duplicate publisher pair path")
            names.add(parts[1])
        if Path(str(pair["image"])).name != Path(str(pair["label"])).name:
            raise ValueError("Image and mask case identities differ")
    actual_images = {p.name for p in (source / "imagesTr").glob("*.nii.gz") if not p.name.startswith("._")}
    actual_masks = {p.name for p in (source / "labelsTr").glob("*.nii.gz") if not p.name.startswith("._")}
    if actual_images != expected_images or actual_masks != expected_masks:
        raise ValueError("Extracted image/mask files differ from the publisher training inventory")
    rows = []
    for image in sorted((source / "imagesTr").glob("*.nii.gz")):
        if image.name.startswith("._"):
            continue
        mask = source / "labelsTr" / image.name
        if not mask.is_file():
            raise SystemExit(f"{image.name}: label missing")
        case = image.name[: -len(".nii.gz")]
        rows.append({"patient_id": case, "case_id": case, "image_path": f"imagesTr/{image.name}", "mask_path": f"labelsTr/{mask.name}"})
    output.mkdir(parents=True, exist_ok=True)
    with (output / "pairs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["patient_id", "case_id", "image_path", "mask_path"])
        writer.writeheader()
        writer.writerows(rows)
    (output / "labels.json").write_text(json.dumps({str(key): value for key, value in sorted(labels.items())}, indent=2) + "\n", encoding="utf-8")
    summary = {"dataset": f"Medical Segmentation Decathlon {meta.get('name', source.name)}", "licence": meta.get("licence") or meta.get("license"),
               "reference": meta.get("reference"), "release": meta.get("release"), "source": str(source), "channels": channels,
               "labels": labels, "cases": len(rows)}
    (output / "preparation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "labels": labels, "licence": summary["licence"], "output": str(output)}))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--any-modality", action="store_true", help="Accept MRI tasks (channels as dataset.json lists them)")
    args = parser.parse_args(argv)
    prepare(args.source.resolve(), args.output.resolve(), args.any_modality)
    return 0


if __name__ == "__main__":
    sys.exit(main())
