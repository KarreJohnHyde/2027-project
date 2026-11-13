"""LIDC-IDRI subset -> NIfTI CT volumes and consensus nodule masks for ml_training.volumetric_multichannel.

Input: the per-series zips downloaded from the TCIA NBIA API (one CT series per patient, chosen among the series the
LIDC XML annotates) and LIDC-XML-only.zip (TCIA, CC BY 3.0). Each patient's series is extracted into its own folder,
ordered by GDCM along the slice normal and written as NIfTI in Hounsfield units with its patient-space affine.

Masks: every reader's outlined nodules (unblindedReadNodule with roi edge maps; nodules of 3 mm or more) are filled
slice by slice (edge pixels included) on the series' own grid; a voxel is nodule when at least two of the readers
outlined it (the common 50 % consensus). Nodules under 3 mm (centroid only) and non-nodules carry no outline and are
not drawn. Archives are kept; extracted folders and derived files stay under the Git-ignored dataset folders.

    python -I scripts/prepare_lidc_dataset.py --series-dir C:/MedTwin_Datasets/LIDC/series \
        --xml-zip C:/MedTwin_Datasets/LIDC/annotations/LIDC-XML-only.zip --output C:/MedTwin_Datasets/LIDC/derived
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SERIES_UID = re.compile(rb"<SeriesInstanceUid>\s*([0-9.]+)\s*</SeriesInstanceUid>", re.I)
CONSENSUS_READERS = 2


def xml_by_series(xml_zip: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    with zipfile.ZipFile(xml_zip) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".xml"):
                data = archive.read(name)
                match = SERIES_UID.search(data[:65536])
                if match:
                    found.setdefault(match.group(1).decode("ascii"), data)
    return found


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def reader_outlines(xml: bytes) -> list[list[tuple[str, list[tuple[int, int]], bool]]]:
    """Per reading session: (SOP instance UID, edge points, inclusion) for every outlined ROI of its nodules."""
    root = ET.fromstring(xml)
    sessions = []
    for session in root.iter():
        if _local(session.tag) != "readingSession":
            continue
        rois = []
        for nodule in session:
            if _local(nodule.tag) != "unblindedReadNodule":
                continue
            for roi in nodule:
                if _local(roi.tag) != "roi":
                    continue
                sop, inclusion, points = None, True, []
                for child in roi:
                    name = _local(child.tag)
                    if name == "imageSOP_UID":
                        sop = (child.text or "").strip()
                    elif name == "inclusion":
                        inclusion = (child.text or "TRUE").strip().upper() == "TRUE"
                    elif name == "edgeMap":
                        coords = {_local(item.tag): int(float(item.text)) for item in child}
                        points.append((coords["xCoord"], coords["yCoord"]))
                if sop and len(points) >= 1:
                    rois.append((sop, points, inclusion))
        sessions.append(rois)
    return sessions


def fill(points: list[tuple[int, int]], rows: int, columns: int) -> np.ndarray:
    canvas = Image.new("1", (columns, rows), 0)
    draw = ImageDraw.Draw(canvas)
    if len(points) >= 3:
        draw.polygon(points, outline=1, fill=1)
    else:
        draw.point(points, fill=1)
    return np.asarray(canvas, dtype=bool)


class ConversionRefused(ValueError):
    """The series or its annotations cannot give a trustworthy volume and mask."""


def extract(zip_path: Path, folder: Path) -> None:
    """Extract the series' DICOM files flat into ``folder`` (member paths are never used as paths); atomic: a
    partial extraction is never mistaken for a complete one."""
    if folder.exists():
        return
    partial = folder.with_name(folder.name + ".part")
    if partial.exists():
        for stale in partial.iterdir():
            stale.unlink()
    partial.mkdir(parents=True, exist_ok=True)
    expected = 0
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            name = Path(member.filename).name
            if name.lower().endswith(".dcm") and not member.is_dir():
                expected += 1
                (partial / name).write_bytes(archive.read(member))
    written = sum(1 for _ in partial.glob("*.dcm"))
    if written != expected or expected == 0:
        raise ConversionRefused(f"extraction wrote {written} of {expected} DICOM files")
    partial.rename(folder)


def convert(zip_path: Path, xml: bytes, extract_root: Path, images: Path, masks: Path) -> dict:
    import pydicom
    import SimpleITK as sitk

    patient, uid = zip_path.stem.split("__", 1)
    folder = extract_root / f"{patient}__{uid}"
    extract(zip_path, folder)
    reader = sitk.ImageSeriesReader()
    files = reader.GetGDCMSeriesFileNames(str(folder))
    if len(files) != sum(1 for _ in folder.glob("*.dcm")):
        raise ConversionRefused(f"GDCM ordered {len(files)} of {sum(1 for _ in folder.glob('*.dcm'))} files (more than one series or unreadable files)")
    reader.SetFileNames(files)
    image = reader.Execute()
    hounsfield = sitk.Cast(image, sitk.sitkInt16)
    sop_index = {str(pydicom.dcmread(path, stop_before_pixels=True).SOPInstanceUID): index for index, path in enumerate(files)}
    size = image.GetSize()  # (columns, rows, slices)
    votes = np.zeros((size[2], size[1], size[0]), dtype=np.uint8)
    sessions = reader_outlines(xml)
    missing = 0
    for rois in sessions:
        drawn = np.zeros_like(votes, dtype=bool)
        excluded = np.zeros_like(votes, dtype=bool)
        for sop, points, inclusion in rois:
            index = sop_index.get(sop)
            if index is None:
                missing += 1
                continue
            plane = fill(points, size[1], size[0])
            (drawn if inclusion else excluded)[index] |= plane
        votes += (drawn & ~excluded).astype(np.uint8)
    if missing:
        # An outline on a slice the series does not hold would leave the mask incomplete; such a case is not exported.
        raise ConversionRefused(f"{missing} reader outline(s) name slices that are not in the series")
    mask = (votes >= CONSENSUS_READERS).astype(np.uint8)
    mask_image = sitk.GetImageFromArray(mask)
    mask_image.CopyInformation(image)
    sitk.WriteImage(hounsfield, str(images / f"{patient}.nii.gz"), useCompression=True)
    sitk.WriteImage(mask_image, str(masks / f"{patient}.nii.gz"), useCompression=True)
    return {"patient": patient, "series_uid": uid, "slices": int(size[2]), "readers": len(sessions), "nodule_voxels": int(mask.sum()),
            "rois_on_missing_slices": 0, "spacing_mm": [round(float(value), 4) for value in image.GetSpacing()]}


def register(output: Path, cases: int, series_dir: Path) -> None:
    """Add (or replace) the LIDC subset and its segmentation task in dataset_registry/tasks.json."""
    root = Path(__file__).resolve().parents[1]
    record = {
        "id": "lidc-idri-subset", "archive": "TCIA NBIA API series zips", "title": f"LIDC-IDRI thoracic CT with reader nodule outlines ({cases}-patient subset)",
        "modality": "CT", "system": "lungs",
        "identity": f"{cases} patients (first by patient ID among series annotated by LIDC-XML-only.zip), one CT series each; 50 % reader-consensus nodule masks",
        "labels": "READER_XML_CONSENSUS_MASKS", "official_splits": False, "patient_ids": "TCIA_PATIENT_IDS",
        "source_archive": f"{str(series_dir).replace(chr(92), '/')} (selected_series.json lists every series UID)",
        "files": cases, "location": str(output).replace("\\", "/"),
        "license": {
            "status": "VERIFIED", "authorization_status": "VERIFIED",
            "authorization_reason": "TCIA collection page lists the LIDC-IDRI licence as CC BY 3.0 (checked 2026-11-06); the 300-patient download was "
                                    "approved by the repository owner on 2026-11-06.",
            "authorized_by": "published licence (CC BY 3.0); download approved by the repository owner on 2026-11-06", "authorized_on": "2026-11-06",
            "authorization_scope": "local research training and evaluation; images and masks are not committed or redistributed",
            "name": "CC BY 3.0 (TCIA Data Usage Policy; citation required)", "source": "https://www.cancerimagingarchive.net/collection/lidc-idri/",
            "verified_on": "2026-11-06",
            "citation": ("Armato SG III, McLennan G, Bidaut L, et al. Med Phys 38(2):915-931 (2011); Armato SG III et al. Data From LIDC-IDRI. TCIA (2015), "
                         "doi:10.7937/K9/TCIA.2015.LO9QL9SX; Clark K et al. The Cancer Imaging Archive (TCIA). J Digit Imaging 26(6):1045-1057 (2013)."),
        },
        "privacy": "PUBLISHER_DE_IDENTIFIED (TCIA)", "exact_duplicate_overlap": {}, "notes": [],
        "tasks": [{"task_id": "lidc-nodule-segmentation", "type": "SEGMENTATION_VOLUMES", "target": "lung nodules of 3 mm or more (reader consensus)",
                   "flags": ["TASK_SUPPORTED_BY_LABELS"], "training_eligible": True, "validation_ready": True, "readiness": "READY_FOR_TRAINING",
                   "trainer": "python -m ml_training.volumetric_multichannel train --intensity ct",
                   "manifest_builder": "python -I scripts/prepare_lidc_dataset.py; python -m ml_training.volumetric_manifest pairs"}],
    }
    path = root / "dataset_registry" / "tasks.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["datasets"] = [item for item in registry["datasets"] if item["id"] != record["id"]] + [record]
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--series-dir", type=Path, required=True)
    parser.add_argument("--xml-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--extract-dir", type=Path, default=None)
    parser.add_argument("--register", action="store_true", help="also record the dataset and task in dataset_registry/tasks.json")
    args = parser.parse_args()
    images, masks = args.output / "images", args.output / "masks"
    images.mkdir(parents=True, exist_ok=True)
    masks.mkdir(parents=True, exist_ok=True)
    extract_root = args.extract_dir or (args.output.parent / "extracted_series")
    records = args.output / "conversions"
    records.mkdir(parents=True, exist_ok=True)
    by_series = xml_by_series(args.xml_zip)
    rows, summary, refused = [], [], {}
    for zip_path in sorted(args.series_dir.glob("*.zip")):
        patient, uid = zip_path.stem.split("__", 1)
        if uid not in by_series:
            refused[patient] = "no reader XML for the series"
            continue
        record_path = records / f"{patient}.json"
        record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else None
        # Outputs count only with this script's record of a complete conversion of this very series.
        if not (record and record.get("series_uid") == uid and (images / f"{patient}.nii.gz").exists() and (masks / f"{patient}.nii.gz").exists()):
            # Extraction is a working copy of the kept zip: one made by this run is removed after the conversion, so
            # 300 series do not leave a second ~30 GB copy on the disk.
            folder = extract_root / f"{patient}__{uid}"
            made_here = not folder.exists()
            try:
                record = convert(zip_path, by_series[uid], extract_root, images, masks)
            except ConversionRefused as exc:
                refused[patient] = str(exc)
                print(json.dumps({"patient": patient, "refused": str(exc)}), flush=True)
                continue
            finally:
                if made_here:
                    for working in (folder, folder.with_name(folder.name + ".part")):
                        shutil.rmtree(working, ignore_errors=True)
            record_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            summary.append(record)
            print(json.dumps(record), flush=True)
        rows.append({"patient_id": patient, "case_id": patient, "image_path": f"images/{patient}.nii.gz", "mask_path": f"masks/{patient}.nii.gz"})
    with (args.output / "pairs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["patient_id", "case_id", "image_path", "mask_path"])
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "labels.json").write_text(json.dumps({"0": "background", "1": "lung_nodule"}, indent=2) + "\n", encoding="utf-8")
    (args.output / "preparation.json").write_text(json.dumps({
        "dataset": "LIDC-IDRI (subset)", "licence": "CC BY 3.0 (TCIA Data Usage Policy; citation required)", "cases": len(rows),
        "mask_rule": f"voxels outlined by at least {CONSENSUS_READERS} readers (nodules >= 3 mm; edge pixels included)",
        "refused": refused, "converted_this_run": summary}, indent=2) + "\n", encoding="utf-8")
    if args.register:
        register(args.output.resolve(), len(rows), args.series_dir.resolve())
    print(json.dumps({"cases": len(rows), "converted": len(summary)}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
