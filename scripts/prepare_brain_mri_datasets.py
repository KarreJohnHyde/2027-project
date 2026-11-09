"""Prepare the two licensed brain-MRI segmentation datasets for ml_training.volumetric_multichannel.

isles   ISLES 2022 (CC BY 4.0): each subject's DWI (b=1000) and ADC share one grid; they are stacked into one 4-D
        NIfTI (channel order DWI, ADC), the format an upload to the stroke-lesion model must also have, and the
        lesion mask is copied beside it. FLAIR is not used: it lies on a different grid and is not co-registered.
msd     Medical Segmentation Decathlon Task01 BrainTumour (CC BY-SA 4.0, BraTS 2016/2017): images are already 4-D
        (FLAIR, T1w, T1gd, T2w) on the SRI24 1 mm grid; only the pairs list is written (macOS "._" files skipped).

Each command writes pairs.csv and labels.json for ``python -m ml_training.volumetric_manifest pairs``.
Nothing leaves this computer, and the data stay under the Git-ignored /_derived/ and /MedTwin_Datasets/ folders.

    python scripts/prepare_brain_mri_datasets.py isles --source MedTwin_Datasets/_extracted/isles22/ISLES-2022 \
        --output _derived/datasets/isles22-dwi-adc
    python scripts/prepare_brain_mri_datasets.py msd --source MedTwin_Datasets/_extracted/msd_task01/Task01_BrainTumour \
        --output _derived/datasets/msd-brain-tumour
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np

ISLES_LABELS = {0: "background", 1: "ischaemic_stroke_lesion"}
# MSD Task01 dataset.json: 1 edema, 2 non-enhancing tumor, 3 enhancing tumour. Label 2 is the BraTS necrotic and
# non-enhancing tumour core.
MSD_LABELS = {0: "background", 1: "peritumoural_oedema", 2: "necrotic_or_non_enhancing_tumour_core", 3: "enhancing_tumour"}


def _write(output: Path, rows: list[dict[str, str]], labels: dict[int, str], source: dict) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "pairs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["patient_id", "case_id", "image_path", "mask_path"])
        writer.writeheader()
        writer.writerows(rows)
    (output / "labels.json").write_text(json.dumps({str(key): value for key, value in labels.items()}, indent=2) + "\n", encoding="utf-8")
    (output / "preparation.json").write_text(json.dumps({**source, "cases": len(rows)}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "output": str(output)}))


def prepare_isles(source: Path, output: Path) -> None:
    rows = []
    (output / "images").mkdir(parents=True, exist_ok=True)
    (output / "masks").mkdir(parents=True, exist_ok=True)
    for subject in sorted(path for path in source.glob("sub-strokecase*") if path.is_dir()):
        dwi_path = next(subject.glob("**/*_dwi.nii.gz"))
        adc_path = next(subject.glob("**/*_adc.nii.gz"))
        mask_path = next((source / "derivatives" / subject.name).glob("**/*_msk.nii.gz"))
        dwi, adc, mask = nib.load(str(dwi_path)), nib.load(str(adc_path)), nib.load(str(mask_path))
        if dwi.shape != adc.shape or dwi.shape != mask.shape:
            raise SystemExit(f"{subject.name}: DWI, ADC and mask grids differ")
        if not (np.allclose(dwi.affine, adc.affine, atol=1e-3) and np.allclose(dwi.affine, mask.affine, atol=1e-3)):
            raise SystemExit(f"{subject.name}: DWI, ADC and mask affines differ")
        stacked = np.stack([np.asarray(dwi.dataobj, dtype=np.float32), np.asarray(adc.dataobj, dtype=np.float32)], axis=-1)
        header = dwi.header.copy()
        header.set_data_dtype(np.float32)
        header.set_data_shape(stacked.shape)
        zooms = tuple(float(value) for value in dwi.header.get_zooms()[:3]) + (1.0,)
        header.set_zooms(zooms)
        image_name = f"images/{subject.name}_dwi_adc.nii.gz"
        mask_name = f"masks/{subject.name}_msk.nii.gz"
        out_image = nib.Nifti1Image(stacked, dwi.affine, header)
        out_image.set_qform(dwi.get_qform(), code=int(dwi.header["qform_code"]))
        out_image.set_sform(dwi.get_sform(), code=int(dwi.header["sform_code"]))
        nib.save(out_image, str(output / image_name))
        mask_header = mask.header.copy()
        mask_header.set_data_dtype(np.uint8)
        nib.save(nib.Nifti1Image((np.asarray(mask.dataobj) > 0).astype(np.uint8), mask.affine, mask_header), str(output / mask_name))
        rows.append({"patient_id": subject.name, "case_id": subject.name, "image_path": image_name, "mask_path": mask_name})
    _write(output, rows, ISLES_LABELS, {"dataset": "ISLES 2022", "licence": "CC BY 4.0", "source": str(source),
                                        "channels": ["DWI", "ADC"], "mask": "binary ischaemic lesion (publisher's label)"})


def prepare_msd(source: Path, output: Path) -> None:
    rows = []
    for image in sorted((source / "imagesTr").glob("BRATS_*.nii.gz")):
        mask = source / "labelsTr" / image.name
        if not mask.is_file():
            raise SystemExit(f"{image.name}: label missing")
        case = image.name[: -len(".nii.gz")]
        rows.append({"patient_id": case, "case_id": case, "image_path": f"imagesTr/{image.name}", "mask_path": f"labelsTr/{mask.name}"})
    _write(output, rows, MSD_LABELS, {"dataset": "Medical Segmentation Decathlon Task01 BrainTumour", "licence": "CC BY-SA 4.0",
                                      "source": str(source), "channels": ["FLAIR", "T1w", "T1gd", "T2w"]})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dataset", choices=("isles", "msd"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    (prepare_isles if args.dataset == "isles" else prepare_msd)(args.source.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
