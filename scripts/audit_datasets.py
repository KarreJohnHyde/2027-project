"""Create a conservative, read-only inventory of MedTwin dataset paths.

The scanner never follows symlinks and never opens files for writing. It reports
file-level evidence separately from clinical/model-readiness claims. Directory
names are observations, not ground-truth class definitions.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import re
import struct
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATASET_PATHS = [
    "2d segmentation dataset",
    "BEHSOF",
    "benchmarks",
    "Brain_Stroke_CT_Dataset",
    "cerebrovascular lesions",
    "data",
    "DATASET",
    "dyed-lifted-polyps",
    "dyed-resection-margins",
    "esophagitis",
    "External_test",
    "Gastrovision",
    "kvasir-dataset-v2",
    "LungcancerDataSet",
    "mri-tumor-detection-dataset(training and testing)",
    "normal-cecum",
    "normal-pylorus",
    "normal-z-line",
    "polyps",
    "segmentations",
    "split_data",
    "ST000001",
    "test",
    "Testing",
    "train",
    "Training",
    "ulcerative-colitis",
    "valid",
    "volume_pt1",
    "volume_pt2",
    "volume_pt3",
    "volume_pt4",
    "volume_pt5",
]

IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
MEDICAL_EXTENSIONS = IMAGE_EXTENSIONS | {".dcm", ".dicom", ".nii", ".nii.gz"}
METADATA_NAMES = {
    "readme",
    "readme.md",
    "readme.txt",
    "readme.dataset.txt",
    "readme.roboflow.txt",
    "license",
    "license.md",
    "license.txt",
    "copying",
    "data.yaml",
    "data.yml",
    "dataset.yaml",
    "dataset.yml",
}

REGISTRY_KIND = {
    "benchmarks": "engineering_artifact_not_medical_dataset",
    "dyed-lifted-polyps": "possible_dataset_fragment",
    "dyed-resection-margins": "possible_dataset_fragment",
    "esophagitis": "possible_dataset_fragment",
    "External_test": "possible_split_fragment",
    "normal-cecum": "possible_dataset_fragment",
    "normal-pylorus": "possible_dataset_fragment",
    "normal-z-line": "possible_dataset_fragment",
    "polyps": "possible_dataset_fragment",
    "segmentations": "possible_dataset_component",
    "test": "mixed_collection_or_split",
    "Testing": "possible_split_fragment",
    "train": "mixed_collection_or_split",
    "Training": "possible_split_fragment",
    "ulcerative-colitis": "possible_dataset_fragment",
    "valid": "mixed_collection_or_split",
    "volume_pt1": "possible_dataset_component",
    "volume_pt2": "possible_dataset_component",
    "volume_pt3": "possible_dataset_component",
    "volume_pt4": "possible_dataset_component",
    "volume_pt5": "possible_dataset_component",
}


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def extension_for(path: Path) -> str:
    lower = path.name.lower()
    if lower.endswith(".nii.gz"):
        return ".nii.gz"
    return path.suffix.lower() or "[no-extension]"


def bounded_walk(root: Path, max_files: int, max_dirs: int) -> tuple[list[Path], int, bool, list[str]]:
    files: list[Path] = []
    directories = 0
    truncated = False
    errors: list[str] = []
    stack = [root]

    while stack:
        directory = stack.pop()
        directories += 1
        if directories > max_dirs:
            truncated = True
            break
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            errors.append(f"{directory.relative_to(root)}: {exc.__class__.__name__}")
            continue
        child_dirs: list[Path] = []
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    child_dirs.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    files.append(Path(entry.path))
                    if len(files) >= max_files:
                        truncated = True
                        break
            except OSError as exc:
                errors.append(f"{entry.name}: {exc.__class__.__name__}")
        if truncated:
            break
        stack.extend(reversed(child_dirs))
    return files, directories, truncated, errors


def relative(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("/", "\\")


def safe_text(path: Path, limit: int = 1_000_000) -> str | None:
    try:
        if path.stat().st_size > limit:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def inspect_image(path: Path) -> str:
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
        return "readable"
    except ImportError:
        try:
            header = path.read_bytes()[:16]
        except OSError:
            return "unreadable"
        suffix = extension_for(path)
        if suffix == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "signature_only"
        if suffix in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8"):
            return "signature_only"
        return "not_checked_no_pillow"
    except Exception:
        return "unreadable"


def inspect_nifti(path: Path) -> str:
    if path.name.lower().endswith(".nii.gz"):
        return "not_checked_compressed"
    try:
        with path.open("rb") as handle:
            header = handle.read(348)
    except OSError:
        return "unreadable"
    if len(header) < 348:
        return "invalid_short_header"
    little = struct.unpack("<I", header[:4])[0]
    big = struct.unpack(">I", header[:4])[0]
    if 348 not in {little, big}:
        return "invalid_header_size"
    return "header_valid"


def inspect_dicom(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            header = handle.read(132)
    except OSError:
        return "unreadable"
    if len(header) >= 132 and header[128:132] == b"DICM":
        return "preamble_valid"
    return "no_preamble_signature_not_conclusive"


def inspect_coco(path: Path, root: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > 50_000_000:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or not {"images", "annotations", "categories"}.issubset(value):
        return None
    images = value.get("images") if isinstance(value.get("images"), list) else []
    annotations = value.get("annotations") if isinstance(value.get("annotations"), list) else []
    categories = value.get("categories") if isinstance(value.get("categories"), list) else []
    image_ids = [item.get("id") for item in images if isinstance(item, dict) and "id" in item]
    image_id_set = set(image_ids)
    category_ids = {
        item.get("id") for item in categories if isinstance(item, dict) and "id" in item
    }
    orphan_annotations = sum(
        1
        for item in annotations
        if isinstance(item, dict) and item.get("image_id") not in image_id_set
    )
    category_names = [
        str(item.get("name"))
        for item in categories
        if isinstance(item, dict) and item.get("name") is not None
    ]
    annotation_ids = [
        item.get("id") for item in annotations if isinstance(item, dict) and "id" in item
    ]
    orphan_category_references = sum(
        1
        for item in annotations
        if isinstance(item, dict) and item.get("category_id") not in category_ids
    )
    invalid_bboxes = 0
    for item in annotations:
        if not isinstance(item, dict) or "bbox" not in item:
            continue
        bbox = item.get("bbox")
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or not all(isinstance(value, (int, float)) for value in bbox)
            or bbox[2] <= 0
            or bbox[3] <= 0
        ):
            invalid_bboxes += 1
    image_directory = path.parent.parent / "images"
    missing_image_files = sum(
        1
        for item in images
        if isinstance(item, dict)
        and isinstance(item.get("file_name"), str)
        and not (image_directory / item["file_name"]).is_file()
    )
    return {
        "path": relative(path, root),
        "format": "COCO_JSON",
        "images": len(images),
        "annotations": len(annotations),
        "categories": category_names,
        "duplicate_image_ids": len(image_ids) - len(image_id_set),
        "duplicate_annotation_ids": len(annotation_ids) - len(set(annotation_ids)),
        "orphan_annotations": orphan_annotations,
        "orphan_category_references": orphan_category_references,
        "invalid_bboxes": invalid_bboxes,
        "missing_referenced_image_files": missing_image_files,
    }


def inspect_csv(path: Path, root: Path) -> dict[str, Any] | None:
    try:
        if path.stat().st_size > 20_000_000:
            return None
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            row_count = sum(1 for _ in reader)
    except OSError:
        return None
    return {
        "path": relative(path, root),
        "format": "CSV",
        "columns": header,
        "data_rows": row_count,
        "semantics": "unverified",
    }


def inspect_yolo(label_files: list[Path], root: Path, limit: int) -> dict[str, Any] | None:
    relevant = [
        path
        for path in label_files
        if any(part.casefold() in {"label", "labels", "annotation", "annotations"} for part in path.parts)
    ][:limit]
    if not relevant:
        return None
    nonempty_lines = 0
    invalid_lines = 0
    observed_class_ids: set[int] = set()
    for path in relevant:
        text = safe_text(path, 2_000_000)
        if text is None:
            invalid_lines += 1
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            nonempty_lines += 1
            tokens = line.split()
            try:
                class_value = float(tokens[0])
                coordinates = [float(item) for item in tokens[1:5]]
                valid = (
                    len(tokens) == 5
                    and class_value.is_integer()
                    and class_value >= 0
                    and all(0.0 <= value <= 1.0 for value in coordinates)
                )
                if valid:
                    observed_class_ids.add(int(class_value))
                else:
                    invalid_lines += 1
            except (IndexError, ValueError):
                invalid_lines += 1
    return {
        "format": "YOLO_NORMALIZED_TEXT_CANDIDATE",
        "files_checked": len(relevant),
        "nonempty_lines_checked": nonempty_lines,
        "invalid_lines": invalid_lines,
        "observed_class_ids": sorted(observed_class_ids),
        "scope": "bounded sample; directory context only",
    }


def yolo_image_label_pairing(files: list[Path]) -> list[dict[str, Any]]:
    groups: dict[Path, dict[str, set[str]]] = defaultdict(lambda: {"images": set(), "labels": set()})
    for path in files:
        extension = extension_for(path)
        if path.parent.name.casefold() == "labels" and extension == ".txt":
            groups[path.parent.parent]["labels"].add(path.stem.casefold())
        elif path.parent.name.casefold() == "images" and extension in IMAGE_EXTENSIONS:
            groups[path.parent.parent]["images"].add(path.stem.casefold())
    results: list[dict[str, Any]] = []
    for split_root, observed in sorted(groups.items(), key=lambda item: str(item[0]).casefold()):
        if not observed["labels"]:
            continue
        results.append(
            {
                "relative_group": split_root.name,
                "image_files": len(observed["images"]),
                "label_files": len(observed["labels"]),
                "matching_stems": len(observed["images"] & observed["labels"]),
                "images_without_label_file": len(observed["images"] - observed["labels"]),
                "labels_without_image": len(observed["labels"] - observed["images"]),
                "semantics": "filename pairing only; empty label files may represent negative images",
            }
        )
    return results


def parse_root_roboflow_metadata(workspace: Path) -> dict[str, Any] | None:
    yaml_path = workspace / "data.yaml"
    dataset_readme = workspace / "README.dataset.txt"
    roboflow_readme = workspace / "README.roboflow.txt"
    if not yaml_path.is_file():
        return None
    text = safe_text(yaml_path) or ""
    names: list[str] = []
    match = re.search(r"(?m)^names:\s*(.+)$", text)
    if match:
        try:
            parsed = ast.literal_eval(match.group(1).strip())
            if isinstance(parsed, list):
                names = [str(item) for item in parsed]
        except (SyntaxError, ValueError):
            pass
    license_match = re.search(r"(?m)^\s*license:\s*(.+)$", text)
    return {
        "configuration": "data.yaml",
        "documentation": [
            path.name for path in (dataset_readme, roboflow_readme) if path.is_file()
        ],
        "declared_classes": names,
        "declared_license": license_match.group(1).strip() if license_match else None,
        "declared_task": "object_detection",
        "declared_subject": "Kidney-stones",
        "scope": "Only the train/images, train/labels, valid/images, valid/labels, test/images, and test/labels paths referenced by data.yaml.",
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def top_directories(root: Path) -> list[str]:
    try:
        return sorted(
            entry.name
            for entry in os.scandir(root)
            if not entry.is_symlink() and entry.is_dir(follow_symlinks=False)
        )[:100]
    except OSError:
        return []


def paired_image_mask_check(root: Path, files: list[Path], probe_limit: int) -> dict[str, Any] | None:
    image_files = [path for path in files if "images" in {part.casefold() for part in path.parts}]
    mask_files = [path for path in files if "masks" in {part.casefold() for part in path.parts}]
    if not image_files or not mask_files:
        return None
    image_by_stem = {path.stem.casefold(): path for path in image_files}
    mask_by_stem = {path.stem.casefold(): path for path in mask_files}
    image_stems = set(image_by_stem)
    mask_stems = set(mask_by_stem)
    checked = 0
    matching_dimensions = 0
    unreadable_pairs = 0
    mask_color_cardinalities: list[int | str] = []
    try:
        from PIL import Image

        for stem in sorted(image_stems & mask_stems)[:probe_limit]:
            checked += 1
            try:
                with Image.open(image_by_stem[stem]) as image, Image.open(mask_by_stem[stem]) as mask:
                    if image.size == mask.size:
                        matching_dimensions += 1
                    colors = mask.convert("L").getcolors(maxcolors=257)
                    mask_color_cardinalities.append(len(colors) if colors is not None else ">256")
            except Exception:
                unreadable_pairs += 1
    except ImportError:
        pass
    return {
        "image_files": len(image_files),
        "mask_files": len(mask_files),
        "matching_stems": len(image_stems & mask_stems),
        "image_stems_without_mask": len(image_stems - mask_stems),
        "mask_stems_without_image": len(mask_stems - image_stems),
        "bounded_content_probe": {
            "pairs_checked": checked,
            "pairs_with_matching_dimensions": matching_dimensions,
            "unreadable_pairs": unreadable_pairs,
            "mask_grayscale_color_cardinalities": mask_color_cardinalities,
        },
        "semantics": "filename pairing only; mask content and subject identity not validated",
    }


def paired_dicom_jpeg_check(files: list[Path]) -> dict[str, Any] | None:
    dicom_stems = {
        str(path.with_suffix("")).casefold()
        for path in files
        if extension_for(path) in {".dcm", ".dicom"}
    }
    jpeg_stems = {
        str(path.with_suffix("")).casefold()
        for path in files
        if extension_for(path) in {".jpg", ".jpeg"}
    }
    if not dicom_stems or not jpeg_stems:
        return None
    return {
        "dicom_files": len(dicom_stems),
        "jpeg_files": len(jpeg_stems),
        "matching_relative_stems": len(dicom_stems & jpeg_stems),
        "dicom_stems_without_jpeg": len(dicom_stems - jpeg_stems),
        "jpeg_stems_without_dicom": len(jpeg_stems - dicom_stems),
        "semantics": "filename pairing only; pixel equivalence and derivation history not validated",
    }


def scan_dataset(
    workspace: Path,
    name: str,
    max_files: int,
    max_dirs: int,
    probe_limit: int,
) -> tuple[dict[str, Any], list[tuple[str, int, Path]]]:
    root = workspace / name
    base: dict[str, Any] = {
        "dataset_id": slug(name),
        "source_path": str(root),
        "path_exists": root.is_dir(),
        "registry_kind": REGISTRY_KIND.get(name, "dataset_candidate"),
        "medical_domain": "unknown",
        "modality": "unknown",
        "task": "unknown",
        "annotation_format": "unknown",
        "classes": [],
        "sample_count": None,
        "sample_count_semantics": "unknown",
        "split_status": "unverified",
        "license_status": "unknown",
        "supported_models": [],
        "integration_status": "DISCOVERED_CATALOG_ONLY",
        "training_eligible": False,
        "validation_eligible": False,
        "limitations": [],
    }
    if not root.is_dir():
        base["integration_status"] = "MISSING"
        base["limitations"].append("Named path was not found at scan time.")
        return base, []

    files, dir_count, truncated, scan_errors = bounded_walk(root, max_files, max_dirs)
    extension_counts = Counter(extension_for(path) for path in files)
    total_bytes = 0
    stat_errors = 0
    fingerprint_candidates: list[tuple[str, int, Path]] = []
    for path in files:
        try:
            size = path.stat().st_size
            total_bytes += size
            if extension_for(path) in MEDICAL_EXTENSIONS and size <= 32 * 1024 * 1024:
                fingerprint_candidates.append((path.name.casefold(), size, path))
        except OSError:
            stat_errors += 1

    media_files = [path for path in files if extension_for(path) in MEDICAL_EXTENSIONS]
    base["sample_count"] = len(media_files) if not truncated else None
    base["sample_count_semantics"] = (
        "exact media-file count; not a patient, study, independent-sample, or deduplicated count"
        if not truncated
        else "unknown because bounded scan was truncated"
    )
    base["observed_top_level_directories"] = top_directories(root)
    base["file_inventory"] = {
        "files_scanned": len(files),
        "directories_scanned": dir_count,
        "total_bytes": total_bytes if not truncated else None,
        "extension_counts": dict(sorted(extension_counts.items(), key=lambda item: (-item[1], item[0]))),
        "scan_truncated": truncated,
        "scan_errors": scan_errors[:20],
        "stat_errors": stat_errors,
    }

    evidence_files: list[str] = []
    for path in files:
        lowered = path.name.casefold()
        if (
            lowered in METADATA_NAMES
            or lowered.startswith("readme")
            or lowered.startswith("license")
            or "source" in lowered
            or "citation" in lowered
            or extension_for(path) in {".csv", ".json", ".yaml", ".yml"}
        ):
            evidence_files.append(relative(path, root))
    base["metadata_evidence_files"] = evidence_files[:200]

    coco = [value for path in files if extension_for(path) == ".json" if (value := inspect_coco(path, root))]
    csv_evidence = [
        value for path in files if extension_for(path) == ".csv" if (value := inspect_csv(path, root))
    ]
    text_labels = [path for path in files if extension_for(path) == ".txt"]
    yolo = inspect_yolo(text_labels, root, min(100, probe_limit * 5))
    image_mask_pairing = paired_image_mask_check(root, files, probe_limit)
    formats: list[str] = []
    if coco:
        formats.append("COCO_JSON")
    if yolo:
        formats.append("YOLO_NORMALIZED_TEXT_CANDIDATE")
    if csv_evidence:
        formats.append("CSV_UNVERIFIED_SCHEMA")
    if any(extension_for(path) in IMAGE_EXTENSIONS for path in files) and image_mask_pairing:
        formats.append("IMAGE_MASK_FILENAME_PAIRS")
    if formats:
        base["annotation_format"] = "+".join(formats)
    base["annotation_evidence"] = {
        "coco": coco,
        "csv": csv_evidence,
        "yolo": yolo,
        "yolo_image_label_pairing": yolo_image_label_pairing(files),
        "image_mask_pairing": image_mask_pairing,
    }
    base["file_relationship_evidence"] = {
        "dicom_jpeg_filename_pairing": paired_dicom_jpeg_check(files),
    }
    declared_classes = sorted({category for item in coco for category in item["categories"]})
    if declared_classes:
        base["classes"] = declared_classes
        base["class_semantics"] = "declared COCO category names; clinical meaning not independently verified"

    child_names = {item.casefold() for item in base["observed_top_level_directories"]}
    expected_splits = {"train", "training", "val", "valid", "validation", "test", "testing"}
    observed_splits = sorted(child_names & expected_splits)
    if observed_splits:
        base["split_status"] = "directory_splits_observed_not_patient_verified"
        base["observed_split_directory_names"] = observed_splits
    elif name.casefold() in expected_splits or name == "External_test":
        base["split_status"] = "split_fragment_name_observed_not_verified"

    probes: dict[str, Any] = {}
    image_probe = [path for path in media_files if extension_for(path) in IMAGE_EXTENSIONS][:probe_limit]
    if image_probe:
        probes["images"] = dict(Counter(inspect_image(path) for path in image_probe))
        probes["images"]["checked"] = len(image_probe)
    nifti_probe = [path for path in media_files if extension_for(path) in {".nii", ".nii.gz"}][:probe_limit]
    if nifti_probe:
        probes["nifti"] = dict(Counter(inspect_nifti(path) for path in nifti_probe))
        probes["nifti"]["checked"] = len(nifti_probe)
    dicom_probe = [path for path in media_files if extension_for(path) in {".dcm", ".dicom"}][:probe_limit]
    if dicom_probe:
        probes["dicom"] = dict(Counter(inspect_dicom(path) for path in dicom_probe))
        probes["dicom"]["checked"] = len(dicom_probe)
        base["limitations"].append("DICOM tags were not read or emitted; PHI/de-identification status is unverified.")
    base["bounded_readability_probes"] = probes

    if name in {"train", "test", "valid"}:
        roboflow = parse_root_roboflow_metadata(workspace)
        if roboflow:
            base["scoped_declared_subset"] = roboflow
            base["classes"] = roboflow["declared_classes"]
            base["class_semantics"] = "declared by root data.yaml for the images/labels subset only"
            base["license_status"] = "DECLARED_CC_BY_4_0_FOR_SCOPED_ROBOFLOW_SUBSET"
            base["task"] = "mixed_root; object_detection declared only for images/labels subset"
            base["medical_domain"] = "mixed_or_unknown; kidney-stone declared only for images/labels subset"

    if name == "benchmarks":
        base["sample_count"] = 0
        base["sample_count_semantics"] = "no medical media files detected"
        base["integration_status"] = "NOT_A_MEDICAL_DATASET"
        base["limitations"].append("Contains software benchmark code/results, not source medical data.")

    if not evidence_files and name not in {"train", "test", "valid"}:
        base["limitations"].append("No local README, license, or dataset configuration was found in this path.")
    if base["license_status"] == "unknown":
        base["limitations"].append("License is unknown; do not redistribute or use for training until verified.")
    if base["split_status"] != "unverified":
        base["limitations"].append("Directory split names do not prove patient/study-disjoint partitioning.")
    if base["registry_kind"] in {"mixed_collection_or_split", "possible_split_fragment", "possible_dataset_fragment"}:
        base["limitations"].append("This path may overlap another registered root; deduplicate before counting or splitting.")
    base["limitations"].append("Folder names were not promoted to ground-truth class labels.")
    return base, fingerprint_candidates


def find_duplicate_indicators(
    workspace: Path,
    candidates_by_dataset: dict[str, list[tuple[str, int, Path]]],
    max_hash_files: int,
    max_hash_bytes: int,
) -> dict[str, Any]:
    groups: dict[tuple[str, int], list[tuple[str, Path]]] = defaultdict(list)
    for dataset_id, candidates in candidates_by_dataset.items():
        for filename, size, path in candidates:
            groups[(filename, size)].append((dataset_id, path))

    potential = [
        (key, values)
        for key, values in groups.items()
        if len({dataset_id for dataset_id, _ in values}) > 1
    ]
    potential.sort(key=lambda item: (item[0][0], item[0][1]))
    hash_cache: dict[Path, str] = {}
    hashed_files = 0
    hashed_bytes = 0
    exact_groups: list[dict[str, Any]] = []
    budget_exhausted = False
    for (_, size), values in potential:
        if hashed_files + len(values) > max_hash_files or hashed_bytes + size * len(values) > max_hash_bytes:
            budget_exhausted = True
            break
        digest_groups: dict[str, list[tuple[str, Path]]] = defaultdict(list)
        for dataset_id, path in values:
            if path not in hash_cache:
                try:
                    hash_cache[path] = sha256(path)
                    hashed_files += 1
                    hashed_bytes += size
                except OSError:
                    continue
            digest_groups[hash_cache[path]].append((dataset_id, path))
        for digest, matches in digest_groups.items():
            if len({dataset_id for dataset_id, _ in matches}) <= 1:
                continue
            exact_groups.append(
                {
                    "sha256": digest,
                    "size_bytes": size,
                    "occurrences": [
                        {
                            "dataset_id": dataset_id,
                            "path": str(path.relative_to(workspace)).replace("/", "\\"),
                        }
                        for dataset_id, path in matches
                    ],
                }
            )
            if len(exact_groups) >= 50:
                budget_exhausted = True
                break
        if len(exact_groups) >= 50:
            break
    return {
        "method": "Candidate files were matched by case-normalized filename and byte size, then full SHA-256 hashed within fixed budgets.",
        "candidate_name_size_groups": len(potential),
        "files_hashed": hashed_files,
        "bytes_hashed": hashed_bytes,
        "hash_file_budget": max_hash_files,
        "hash_byte_budget": max_hash_bytes,
        "budget_exhausted": budget_exhausted,
        "reported_group_limit": 50,
        "exact_cross_root_duplicate_groups": exact_groups,
        "interpretation": "Indicators only. Nested/split roots may intentionally contain the same files; no files were changed.",
    }


def nifti_component_check(workspace: Path) -> dict[str, Any]:
    volume_paths = [
        path
        for part in range(1, 6)
        for path in sorted((workspace / f"volume_pt{part}").glob("volume-*.nii"))
    ]
    segmentation_paths = sorted((workspace / "segmentations").glob("segmentation-*.nii"))

    def indices(paths: list[Path], prefix: str) -> set[int]:
        found: set[int] = set()
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)\.nii$", re.IGNORECASE)
        for path in paths:
            match = pattern.match(path.name)
            if match:
                found.add(int(match.group(1)))
        return found

    volume_indices = indices(volume_paths, "volume")
    segmentation_indices = indices(segmentation_paths, "segmentation")
    volume_by_index = {
        int(re.search(r"(\d+)", path.stem).group(1)): path
        for path in volume_paths
        if re.search(r"(\d+)", path.stem)
    }
    segmentation_by_index = {
        int(re.search(r"(\d+)", path.stem).group(1)): path
        for path in segmentation_paths
        if re.search(r"(\d+)", path.stem)
    }

    def geometry(path: Path) -> dict[str, Any] | None:
        try:
            with path.open("rb") as handle:
                header = handle.read(348)
        except OSError:
            return None
        if len(header) < 348:
            return None
        little = struct.unpack("<I", header[:4])[0]
        big = struct.unpack(">I", header[:4])[0]
        endian = "<" if little == 348 else ">" if big == 348 else None
        if endian is None:
            return None
        dimensions = struct.unpack(f"{endian}8h", header[40:56])
        pixdim = struct.unpack(f"{endian}8f", header[76:108])
        qform_code, sform_code = struct.unpack(f"{endian}2h", header[252:256])
        quaternion_and_offsets = struct.unpack(f"{endian}6f", header[256:280])
        srow = struct.unpack(f"{endian}12f", header[280:328])
        dimension_count = max(0, min(7, dimensions[0]))
        return {
            "dimensions": list(dimensions[1 : dimension_count + 1]),
            "pixel_spacing": [round(value, 8) for value in pixdim[1 : dimension_count + 1]],
            "qform_code": qform_code,
            "sform_code": sform_code,
            "quaternion_and_offsets": [round(value, 8) for value in quaternion_and_offsets],
            "srow": [round(value, 8) for value in srow],
        }

    def geometry_values_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
        if left["dimensions"] != right["dimensions"]:
            return False
        for key in ("pixel_spacing", "quaternion_and_offsets", "srow"):
            if len(left[key]) != len(right[key]):
                return False
            if any(abs(a - b) > 1e-5 for a, b in zip(left[key], right[key])):
                return False
        return True

    geometry_pairs_checked = 0
    geometry_pairs_matching = 0
    form_code_pairs_matching = 0
    geometry_probe_failures = 0
    for index in sorted(volume_indices & segmentation_indices)[:12]:
        volume_geometry = geometry(volume_by_index[index])
        segmentation_geometry = geometry(segmentation_by_index[index])
        if volume_geometry is None or segmentation_geometry is None:
            geometry_probe_failures += 1
            continue
        geometry_pairs_checked += 1
        if geometry_values_equal(volume_geometry, segmentation_geometry):
            geometry_pairs_matching += 1
        if (
            volume_geometry["qform_code"] == segmentation_geometry["qform_code"]
            and volume_geometry["sform_code"] == segmentation_geometry["sform_code"]
        ):
            form_code_pairs_matching += 1
    return {
        "check": "NIfTI filename-index pairing across volume_pt1..volume_pt5 and segmentations",
        "volume_files": len(volume_paths),
        "unique_volume_indices": len(volume_indices),
        "segmentation_files": len(segmentation_paths),
        "unique_segmentation_indices": len(segmentation_indices),
        "paired_indices": len(volume_indices & segmentation_indices),
        "volume_indices_without_segmentation": sorted(volume_indices - segmentation_indices),
        "segmentation_indices_without_volume": sorted(segmentation_indices - volume_indices),
        "bounded_geometry_probe": {
            "pair_limit": 12,
            "pairs_checked": geometry_pairs_checked,
            "pairs_with_matching_dimensions_pixel_spacing_and_transforms": geometry_pairs_matching,
            "pairs_with_matching_qform_sform_codes": form_code_pairs_matching,
            "probe_failures": geometry_probe_failures,
            "interpretation": "Different qform/sform codes can change which transform a loader selects even when sampled numeric transforms match; normalize only after source-specific review.",
        },
        "semantics": "Filename-index evidence only; volume/mask geometry, anatomy, provenance, and label meaning were not validated.",
    }


def build_registry(args: argparse.Namespace) -> dict[str, Any]:
    workspace = args.workspace.resolve()
    datasets: list[dict[str, Any]] = []
    candidates_by_dataset: dict[str, list[tuple[str, int, Path]]] = {}
    for name in DATASET_PATHS:
        dataset, candidates = scan_dataset(
            workspace,
            name,
            args.max_files_per_path,
            args.max_dirs_per_path,
            args.probe_limit,
        )
        datasets.append(dataset)
        candidates_by_dataset[dataset["dataset_id"]] = candidates

    root_directory_names = {
        entry.name.casefold()
        for entry in os.scandir(workspace)
        if not entry.is_symlink() and entry.is_dir(follow_symlinks=False)
    }
    return {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "safety": {
            "read_only_source_scan": True,
            "symlinks_followed": False,
            "dicom_tags_emitted": False,
            "folder_names_treated_as_verified_labels": False,
        },
        "scan_policy": {
            "max_files_per_path": args.max_files_per_path,
            "max_directories_per_path": args.max_dirs_per_path,
            "format_probe_limit_per_path": args.probe_limit,
            "duplicate_hash_file_budget": args.max_hash_files,
            "duplicate_hash_byte_budget": args.max_hash_bytes,
        },
        "root_metadata_evidence": [
            name
            for name in ("README.dataset.txt", "README.roboflow.txt", "data.yaml", "Brain_MRI_conditions.csv")
            if (workspace / name).is_file()
        ],
        "datasets": datasets,
        "cross_root_duplicate_indicators": find_duplicate_indicators(
            workspace,
            candidates_by_dataset,
            args.max_hash_files,
            args.max_hash_bytes,
        ),
        "cross_component_checks": {
            "nifti_volume_segmentation_pairing": nifti_component_check(workspace),
        },
        "named_core_evaluation_dataset_presence": {
            "MURA": any("mura" in name for name in root_directory_names),
            "PTB-XL": any(name in {"ptb-xl", "ptb_xl", "ptbxl"} for name in root_directory_names),
            "interpretation": "Name-based root presence check only; false does not prove the data is absent from every archive or nested path.",
        },
        "global_readiness": "CATALOG_ONLY_NOT_TRAINING_READY",
        "global_blockers": [
            "Most paths lack a locally verifiable license.",
            "No patient/study identity manifest was found to prove leakage-safe splits.",
            "Several roots appear to be fragments or mixed collections and may overlap.",
            "Folder names alone were not accepted as label definitions.",
            "No dataset-to-checkpoint validation bundle was established by this scan.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dataset_registry" / "datasets.json",
    )
    parser.add_argument("--max-files-per-path", type=int, default=200_000)
    parser.add_argument("--max-dirs-per-path", type=int, default=50_000)
    parser.add_argument("--probe-limit", type=int, default=12)
    parser.add_argument("--max-hash-files", type=int, default=256)
    parser.add_argument("--max-hash-bytes", type=int, default=1_073_741_824)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = build_registry(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "entries": len(registry["datasets"]),
                "existing_paths": sum(item["path_exists"] for item in registry["datasets"]),
                "truncated_paths": sum(
                    bool(item.get("file_inventory", {}).get("scan_truncated"))
                    for item in registry["datasets"]
                ),
                "duplicate_groups_reported": len(
                    registry["cross_root_duplicate_indicators"]["exact_cross_root_duplicate_groups"]
                ),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
