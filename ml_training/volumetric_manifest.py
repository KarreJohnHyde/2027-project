"""Build and validate patient-grouped NIfTI segmentation manifests.

The manifest is deliberately separate from training.  Dataset inspection is
permitted even when training rights are unresolved; the trainer independently
re-checks the registry's explicit ``license.authorization_status`` gate before
loading any patient volume.

Examples
--------
Build the locally present ACDC inventory (this does not train a model)::

    python -m ml_training.volumetric_manifest acdc \
      --dataset-root database --output artifacts/audits/acdc-volumes.json

Build a reusable manifest from a CSV with ``patient_id``, ``case_id``,
``image_path`` and ``mask_path`` columns::

    python -m ml_training.volumetric_manifest pairs \
      --dataset-id kits19 --dataset-root /data/kits \
      --pairs-csv pairs.csv --labels labels.json --output kits.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import nibabel as nib
import numpy as np

from ml_training.common import ROOT, sha256_file


SCHEMA_VERSION = "1.0.0"
BUILDER_VERSION = "volumetric-manifest-v1"
DEFAULT_REGISTRY = ROOT / "dataset_registry" / "tasks.json"
ACDC_LABELS = {
    0: "background",
    1: "right_ventricular_cavity",
    2: "myocardium",
    3: "left_ventricular_cavity",
}
SPLITS = ("train", "val", "test")


class ManifestValidationError(ValueError):
    """Raised when a manifest cannot safely describe paired volumes."""


class LicenseAuthorizationError(PermissionError):
    """Raised when real-data training has not been explicitly authorized."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _inside_root(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ManifestValidationError(f"Path escapes dataset root: {path}") from exc
    if not resolved.is_file():
        raise ManifestValidationError(f"Required NIfTI file is missing: {path}")
    return resolved


def _relative_volume_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _load_registry_dataset(registry_path: Path, dataset_id: str) -> dict[str, Any] | None:
    if not registry_path.is_file():
        return None
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    return next((item for item in payload.get("datasets", []) if item.get("id") == dataset_id), None)


def registry_license_evidence(registry_path: Path, dataset_id: str) -> dict[str, Any]:
    """Return the explicit training-authorization state, never inferred from publicity.

    ``license.status`` may describe source or citation verification.  It is not
    sufficient permission to train.  Only the separate exact value
    ``license.authorization_status == VERIFIED`` opens the real-data gate.
    """

    dataset = _load_registry_dataset(registry_path, dataset_id)
    if dataset is None:
        return {
            "dataset_registered": False,
            "authorization_status": "NOT_REGISTERED",
            "source_status": None,
            "license_name": None,
            "license_source": None,
            "reason": "Dataset is absent from the task registry.",
        }
    license_block = dataset.get("license") or {}
    authorization = str(license_block.get("authorization_status") or "UNVERIFIED").upper()
    return {
        "dataset_registered": True,
        "authorization_status": authorization,
        "source_status": license_block.get("status"),
        "license_name": license_block.get("name"),
        "license_source": license_block.get("source"),
        "reason": license_block.get("authorization_reason")
        or ("Explicit registry authorization is recorded." if authorization == "VERIFIED" else "Explicit training authorization is not recorded."),
    }


def enforce_training_license(
    manifest: dict[str, Any],
    registry_path: Path = DEFAULT_REGISTRY,
    *,
    allow_synthetic_test_fixture: bool = False,
) -> dict[str, Any]:
    """Fail closed for real data unless the live registry says ``VERIFIED``."""

    if manifest.get("synthetic_test_fixture") is True:
        if not allow_synthetic_test_fixture:
            raise LicenseAuthorizationError(
                "Synthetic fixtures require the explicit --allow-synthetic-test-fixture test flag."
            )
        return {
            "authorized": True,
            "authorization_status": "SYNTHETIC_TEST_ONLY",
            "registry_path": None,
            "reason": "Isolated generated fixture; not patient data and never registry evidence.",
        }

    dataset_id = str(manifest.get("dataset_id") or "")
    evidence = registry_license_evidence(registry_path, dataset_id)
    if evidence["authorization_status"] != "VERIFIED":
        raise LicenseAuthorizationError(
            f"Training blocked for {dataset_id or 'unknown dataset'}: registry "
            f"license.authorization_status is {evidence['authorization_status']}, not VERIFIED. "
            "Source availability, a citation request, or an inferred public-use status is not authorization."
        )
    return {
        "authorized": True,
        **evidence,
        "registry_path": str(registry_path.resolve()),
        "registry_sha256": sha256_file(registry_path),
    }


def _read_acdc_info(path: Path) -> dict[str, int | str]:
    values: dict[str, int | str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        values[key] = int(value) if value.isdigit() else value
    if not isinstance(values.get("ED"), int) or not isinstance(values.get("ES"), int):
        raise ManifestValidationError(f"ACDC phase metadata lacks integer ED/ES values: {path}")
    return values


def discover_acdc_pairs(dataset_root: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Discover labelled ACDC ED/ES phases and retain the publisher test cohort."""

    root = dataset_root.resolve()
    pairs: list[dict[str, str]] = []
    patients_per_publisher_split: dict[str, int] = {}
    for directory_name, publisher_split in (("training", "train"), ("testing", "test")):
        cohort = root / directory_name
        if not cohort.is_dir():
            raise ManifestValidationError(f"ACDC {directory_name} directory is missing: {cohort}")
        patient_dirs = sorted(path for path in cohort.glob("patient[0-9][0-9][0-9]") if path.is_dir())
        patients_per_publisher_split[publisher_split] = len(patient_dirs)
        for patient_dir in patient_dirs:
            patient_id = patient_dir.name
            info = _read_acdc_info(patient_dir / "Info.cfg")
            for phase_name in ("ED", "ES"):
                frame = int(info[phase_name])
                stem = f"{patient_id}_frame{frame:02d}"
                pairs.append(
                    {
                        "patient_id": patient_id,
                        "case_id": f"{patient_id}_{phase_name.lower()}",
                        "phase": phase_name,
                        "publisher_split": publisher_split,
                        "image_path": _relative_volume_path(_inside_root(patient_dir / f"{stem}.nii", root), root),
                        "mask_path": _relative_volume_path(_inside_root(patient_dir / f"{stem}_gt.nii", root), root),
                    }
                )

    discovered_masks = sorted(root.glob("*/patient[0-9][0-9][0-9]/*_gt.nii*"))
    if len(discovered_masks) != len(pairs):
        raise ManifestValidationError(
            f"ACDC pairing is incomplete: discovered {len(discovered_masks)} masks but paired {len(pairs)} phases."
        )
    return pairs, {
        "layout": "ACDC_ED_ES",
        "label_definition_source": "ACDC challenge integer-mask convention",
        "labelled_patients": sum(patients_per_publisher_split.values()),
        "labelled_phase_cases": len(pairs),
        "patients_per_publisher_split": patients_per_publisher_split,
        "publisher_test_ground_truth_present": True,
        "excluded_4d_cine_volumes": sum(patients_per_publisher_split.values()),
    }


def read_pairs_csv(path: Path, dataset_root: Path) -> list[dict[str, str]]:
    """Read generic pairs while resolving every file below the declared root."""

    root = dataset_root.resolve()
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"patient_id", "case_id", "image_path", "mask_path"}
    missing = required - set(rows[0] if rows else {})
    if missing:
        raise ManifestValidationError(f"Pairs CSV is empty or missing columns: {sorted(missing)}")
    pairs: list[dict[str, str]] = []
    for row in rows:
        image = Path(row["image_path"])
        mask = Path(row["mask_path"])
        image = image if image.is_absolute() else root / image
        mask = mask if mask.is_absolute() else root / mask
        publisher_split = str(row.get("split") or row.get("publisher_split") or "").strip().lower()
        if publisher_split == "training":
            publisher_split = "train"
        elif publisher_split == "validation":
            publisher_split = "val"
        elif publisher_split == "testing":
            publisher_split = "test"
        pairs.append(
            {
                **{
                    key: value
                    for key, value in row.items()
                    if value is not None and key not in {"image_path", "mask_path", "split", "publisher_split"}
                },
                **({"publisher_split": publisher_split} if publisher_split else {}),
                "image_path": _relative_volume_path(_inside_root(image, root), root),
                "mask_path": _relative_volume_path(_inside_root(mask, root), root),
            }
        )
    return pairs


def deterministic_patient_splits(
    patient_ids: Iterable[str],
    *,
    seed: int,
    val_fraction: float,
    test_fraction: float,
) -> dict[str, str]:
    """Assign complete patients using a stable hash order and non-empty splits."""

    patients = sorted(set(str(item).strip() for item in patient_ids if str(item).strip()))
    if len(patients) < 3:
        raise ManifestValidationError("At least three distinct patients are required for train/val/test splits.")
    if val_fraction <= 0 or test_fraction <= 0 or val_fraction + test_fraction >= 1:
        raise ManifestValidationError("val_fraction and test_fraction must be positive and sum to less than one.")
    ordered = sorted(
        patients,
        key=lambda patient: hashlib.sha256(f"{seed}:{patient}".encode("utf-8")).hexdigest(),
    )
    n_val = max(1, int(round(len(ordered) * val_fraction)))
    n_test = max(1, int(round(len(ordered) * test_fraction)))
    while n_val + n_test >= len(ordered):
        if n_test >= n_val and n_test > 1:
            n_test -= 1
        elif n_val > 1:
            n_val -= 1
        else:
            raise ManifestValidationError("Split fractions leave no training patient.")
    assignments = {patient: "test" for patient in ordered[:n_test]}
    assignments.update({patient: "val" for patient in ordered[n_test : n_test + n_val]})
    assignments.update({patient: "train" for patient in ordered[n_test + n_val :]})
    return assignments


def patient_split_assignments(
    pairs: list[dict[str, str]],
    *,
    seed: int,
    val_fraction: float,
    test_fraction: float,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Preserve a declared publisher test cohort; otherwise split all patients."""

    publisher_by_patient: dict[str, set[str]] = defaultdict(set)
    for pair in pairs:
        patient = str(pair.get("patient_id") or "").strip()
        publisher = str(pair.get("publisher_split") or "").strip().lower()
        if publisher:
            if publisher not in SPLITS:
                raise ManifestValidationError(f"{pair.get('case_id')}: invalid publisher_split {publisher!r}.")
            publisher_by_patient[patient].add(publisher)
    if not publisher_by_patient:
        assignments = deterministic_patient_splits(
            (pair["patient_id"] for pair in pairs),
            seed=seed,
            val_fraction=val_fraction,
            test_fraction=test_fraction,
        )
        return assignments, {
            "unit": "patient_id",
            "method": "sha256(seed:patient_id) stable ordering",
            "seed": seed,
            "val_fraction": val_fraction,
            "test_fraction": test_fraction,
            "publisher_test_preserved": False,
        }

    all_patients = {str(pair["patient_id"]).strip() for pair in pairs}
    if set(publisher_by_patient) != all_patients:
        raise ManifestValidationError("publisher_split must be declared for every patient or for none.")
    crossing = {patient: values for patient, values in publisher_by_patient.items() if len(values) != 1}
    if crossing:
        raise ManifestValidationError(f"Patients cross publisher splits: {sorted(crossing)}")
    publisher = {patient: next(iter(values)) for patient, values in publisher_by_patient.items()}
    test_patients = {patient for patient, split in publisher.items() if split == "test"}
    declared_val = {patient for patient, split in publisher.items() if split == "val"}
    development = {patient for patient, split in publisher.items() if split == "train"}
    if not test_patients:
        raise ManifestValidationError("A declared publisher split must contain a non-empty test cohort.")
    if declared_val:
        assignments = {patient: split for patient, split in publisher.items()}
        method = "publisher train/validation/test patient cohorts preserved"
    else:
        if len(development) < 2:
            raise ManifestValidationError("Publisher training cohort needs at least two patients for train/validation.")
        ordered = sorted(
            development,
            key=lambda patient: hashlib.sha256(f"{seed}:{patient}".encode("utf-8")).hexdigest(),
        )
        n_val = max(1, int(round(len(ordered) * val_fraction)))
        n_val = min(n_val, len(ordered) - 1)
        assignments = {patient: "val" for patient in ordered[:n_val]}
        assignments.update({patient: "train" for patient in ordered[n_val:]})
        assignments.update({patient: "test" for patient in test_patients})
        method = "publisher test patients frozen; publisher training patients split by sha256(seed:patient_id)"
    return assignments, {
        "unit": "patient_id",
        "method": method,
        "seed": seed,
        "val_fraction_of_publisher_training": None if declared_val else val_fraction,
        "publisher_test_preserved": True,
        "publisher_patient_counts": dict(Counter(publisher.values())),
    }


def _labels_payload(labels: dict[int, str]) -> list[dict[str, Any]]:
    ids = sorted(labels)
    if ids != list(range(len(ids))) or ids[0] != 0:
        raise ManifestValidationError("Label ids must be contiguous integers beginning with background id 0.")
    if len(set(labels.values())) != len(labels):
        raise ManifestValidationError("Label names must be unique.")
    return [{"id": item, "name": str(labels[item])} for item in ids]


def _inspect_case(case: dict[str, Any], dataset_root: Path, label_ids: set[int]) -> dict[str, Any]:
    image_path = _inside_root(dataset_root / case["image_path"], dataset_root)
    mask_path = _inside_root(dataset_root / case["mask_path"], dataset_root)
    image = nib.load(str(image_path))
    mask = nib.load(str(mask_path))
    if len(image.shape) != 3 or len(mask.shape) != 3:
        raise ManifestValidationError(f"{case['case_id']}: image and mask must both be 3-D.")
    if tuple(image.shape) != tuple(mask.shape):
        raise ManifestValidationError(
            f"{case['case_id']}: image shape {image.shape} differs from mask shape {mask.shape}."
        )
    if not np.allclose(image.affine, mask.affine, rtol=1e-5, atol=1e-4):
        raise ManifestValidationError(f"{case['case_id']}: image and mask affines differ.")

    image_data = np.asanyarray(image.dataobj)
    mask_data = np.asanyarray(mask.dataobj)
    if not np.isfinite(image_data).all():
        raise ManifestValidationError(f"{case['case_id']}: image contains non-finite voxels.")
    if not np.isfinite(mask_data).all() or not np.allclose(mask_data, np.rint(mask_data), atol=1e-6):
        raise ManifestValidationError(f"{case['case_id']}: mask labels must be finite integers.")
    values, counts = np.unique(np.rint(mask_data).astype(np.int64), return_counts=True)
    observed = {int(value) for value in values}
    unexpected = observed - label_ids
    if unexpected:
        raise ManifestValidationError(f"{case['case_id']}: mask has undeclared labels {sorted(unexpected)}.")
    voxel_sizes = nib.affines.voxel_sizes(image.affine)
    if not np.isfinite(voxel_sizes).all() or np.any(voxel_sizes <= 0):
        raise ManifestValidationError(f"{case['case_id']}: affine has invalid voxel sizes.")
    return {
        **case,
        "shape": [int(item) for item in image.shape],
        "affine": np.asarray(image.affine, dtype=float).round(8).tolist(),
        "orientation": list(nib.aff2axcodes(image.affine)),
        "voxel_spacing": [float(item) for item in voxel_sizes],
        "image_sha256": sha256_file(image_path),
        "mask_sha256": sha256_file(mask_path),
        "label_voxels": {str(int(value)): int(count) for value, count in zip(values, counts)},
    }


def _summarize_cases(cases: list[dict[str, Any]], declared_labels: set[int]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    case_ids = [str(case["case_id"]) for case in cases]
    if len(case_ids) != len(set(case_ids)):
        errors.append("case_id values are not unique")

    patient_splits: dict[str, set[str]] = defaultdict(set)
    split_patients: dict[str, set[str]] = defaultdict(set)
    split_cases = Counter()
    label_counts: Counter[int] = Counter()
    split_label_counts: dict[str, Counter[int]] = defaultdict(Counter)
    hash_splits: dict[tuple[str, str], set[str]] = defaultdict(set)
    for case in cases:
        split = str(case.get("split") or "")
        patient = str(case.get("patient_id") or "")
        if split not in SPLITS:
            errors.append(f"{case.get('case_id')}: invalid split {split!r}")
        if not patient:
            errors.append(f"{case.get('case_id')}: patient_id is empty")
        patient_splits[patient].add(split)
        split_patients[split].add(patient)
        split_cases[split] += 1
        for label, count in case.get("label_voxels", {}).items():
            label_counts[int(label)] += int(count)
            split_label_counts[split][int(label)] += int(count)
        for kind in ("image", "mask"):
            value = str(case.get(f"{kind}_sha256") or "")
            if value:
                hash_splits[(kind, value)].add(split)

    overlaps = {patient: sorted(splits) for patient, splits in patient_splits.items() if len(splits) > 1}
    if overlaps:
        errors.append(f"patients cross splits: {sorted(overlaps)}")
    duplicate_hashes = [
        {"kind": kind, "sha256": digest, "splits": sorted(splits)}
        for (kind, digest), splits in sorted(hash_splits.items())
        if len(splits) > 1
    ]
    if duplicate_hashes:
        errors.append("identical image or mask content crosses splits")
    for split in SPLITS:
        if not split_patients[split]:
            errors.append(f"split {split} has no patients")
    absent = sorted(declared_labels - set(label_counts))
    if absent:
        warnings.append(f"declared labels absent from all masks: {absent}")

    return {
        "status": "PASSED" if not errors else "FAILED",
        "errors": errors,
        "warnings": warnings,
        "geometry_checks": {
            "dimensions": "3-D_IMAGE_AND_MASK_REQUIRED",
            "shape": "EXACT_MATCH_REQUIRED",
            "affine": {"rtol": 1e-5, "atol": 1e-4},
            "finite_image_voxels": "REQUIRED",
            "integral_declared_mask_labels": "REQUIRED",
        },
        "case_count": len(cases),
        "patient_count": len(patient_splits),
        "cases_per_split": {split: split_cases[split] for split in SPLITS},
        "patients_per_split": {split: len(split_patients[split]) for split in SPLITS},
        "patient_split_overlap": overlaps,
        "cross_split_identical_content": duplicate_hashes,
        "observed_label_ids": sorted(label_counts),
        "label_voxels": {str(label): label_counts[label] for label in sorted(label_counts)},
        "label_voxels_per_split": {
            split: {str(label): split_label_counts[split][label] for label in sorted(split_label_counts[split])}
            for split in SPLITS
        },
    }


def _exclude_development_duplicates_of_publisher_test(
    cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep the frozen publisher test cohort and remove linked development patients.

    The exclusion unit is the complete development patient, not only the matching
    phase.  Different masks on identical images are retained in the audit record as
    an annotation conflict, but the frozen publisher-test copy remains untouched.
    """

    by_image: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        by_image[str(case["image_sha256"])].append(case)
    conflicting_groups = []
    excluded_patients: set[str] = set()
    for digest, members in sorted(by_image.items()):
        splits = {str(member["split"]) for member in members}
        if "test" not in splits or not (splits - {"test"}):
            continue
        development = [member for member in members if member["split"] != "test"]
        excluded_patients.update(str(member["patient_id"]) for member in development)
        conflicting_groups.append(
            {
                "image_sha256": digest,
                "mask_annotations_identical": len({str(member["mask_sha256"]) for member in members}) == 1,
                "members": [
                    {
                        "patient_id": member["patient_id"],
                        "case_id": member["case_id"],
                        "split_before_exclusion": member["split"],
                        "mask_sha256": member["mask_sha256"],
                    }
                    for member in members
                ],
            }
        )
    kept = [case for case in cases if str(case["patient_id"]) not in excluded_patients]
    return kept, {
        "rule": "preserve publisher test; exclude the complete development patient linked by identical image SHA-256",
        "excluded_development_patients": sorted(excluded_patients),
        "excluded_development_cases": len(cases) - len(kept),
        "cross_cohort_identical_image_groups": conflicting_groups,
    }


def build_manifest(
    *,
    dataset_id: str,
    dataset_root: Path,
    pairs: list[dict[str, str]],
    labels: dict[int, str],
    seed: int = 20261024,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    registry_path: Path = DEFAULT_REGISTRY,
    discovery: dict[str, Any] | None = None,
    synthetic_test_fixture: bool = False,
) -> dict[str, Any]:
    """Build a fully inspected manifest and refuse invalid geometry or leakage."""

    dataset_root = dataset_root.resolve()
    if not dataset_root.is_dir():
        raise ManifestValidationError(f"Dataset root is missing: {dataset_root}")
    labels_payload = _labels_payload(labels)
    label_ids = {int(item["id"]) for item in labels_payload}
    patient_ids = [str(pair.get("patient_id") or "") for pair in pairs]
    if not pairs or any(not item for item in patient_ids):
        raise ManifestValidationError("Every non-empty pair must have a patient_id.")
    assignments, split_policy = patient_split_assignments(
        pairs, seed=seed, val_fraction=val_fraction, test_fraction=test_fraction
    )

    inspected = []
    for pair in sorted(pairs, key=lambda item: (item["patient_id"], item["case_id"])):
        inspected.append(
            _inspect_case(
                {**pair, "split": assignments[pair["patient_id"]]},
                dataset_root,
                label_ids,
            )
        )
    if split_policy.get("publisher_test_preserved"):
        original_counts = dict(split_policy.get("publisher_patient_counts") or {})
        inspected, exclusions = _exclude_development_duplicates_of_publisher_test(inspected)
        if exclusions["excluded_development_patients"]:
            kept_patients = {str(case["patient_id"]) for case in inspected}
            kept_pairs = [pair for pair in pairs if str(pair["patient_id"]) in kept_patients]
            assignments, split_policy = patient_split_assignments(
                kept_pairs, seed=seed, val_fraction=val_fraction, test_fraction=test_fraction
            )
            for case in inspected:
                case["split"] = assignments[str(case["patient_id"])]
        split_policy["publisher_patient_counts_before_leakage_exclusion"] = original_counts
        split_policy["leakage_exclusions"] = exclusions
    validation = _summarize_cases(inspected, label_ids)
    validation["pre_split_leakage_exclusions"] = split_policy.get("leakage_exclusions")
    if validation["status"] != "PASSED":
        raise ManifestValidationError("; ".join(validation["errors"]))

    version_material = {
        "dataset_id": dataset_id,
        "labels": labels_payload,
        "cases": [
            {
                key: case[key]
                for key in ("patient_id", "case_id", "split", "image_sha256", "mask_sha256", "shape", "affine")
            }
            for case in inspected
        ],
    }
    dataset_version = hashlib.sha256(_canonical_json(version_material)).hexdigest()
    license_evidence = (
        {
            "dataset_registered": False,
            "authorization_status": "SYNTHETIC_TEST_ONLY",
            "source_status": "GENERATED",
            "license_name": "Generated test data",
            "license_source": None,
            "reason": "Isolated generated fixture; not patient data.",
        }
        if synthetic_test_fixture
        else registry_license_evidence(registry_path, dataset_id)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "volumetric_segmentation_manifest",
        "builder_version": BUILDER_VERSION,
        "generated_at": _utc_now(),
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "dataset_root": str(dataset_root),
        "synthetic_test_fixture": synthetic_test_fixture,
        "labels": labels_payload,
        "split_policy": split_policy,
        "provenance": {
            "registry_path": None if synthetic_test_fixture else str(registry_path.resolve()),
            "registry_sha256": None if synthetic_test_fixture or not registry_path.is_file() else sha256_file(registry_path),
            "license_gate": license_evidence,
            "discovery": discovery or {"layout": "GENERIC_PAIRS_CSV"},
        },
        "cases": inspected,
        "validation": validation,
        "training_eligible": license_evidence["authorization_status"] == "VERIFIED" or synthetic_test_fixture,
        "training_eligibility_scope": "SYNTHETIC_TEST_ONLY" if synthetic_test_fixture else "REAL_DATA",
    }


def validate_manifest(manifest: dict[str, Any], *, verify_hashes: bool = True) -> dict[str, Any]:
    """Re-check a saved manifest and its current files before a run starts."""

    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("kind") != "volumetric_segmentation_manifest":
        raise ManifestValidationError("Unsupported volumetric manifest schema or kind.")
    root = Path(str(manifest.get("dataset_root") or ""))
    if not root.is_dir():
        raise ManifestValidationError("Manifest dataset_root is missing.")
    labels = manifest.get("labels") or []
    label_ids = {int(item["id"]) for item in labels}
    if sorted(label_ids) != list(range(len(label_ids))):
        raise ManifestValidationError("Manifest labels must be contiguous from zero.")
    cases = manifest.get("cases") or []
    inspected = []
    for expected in cases:
        current = _inspect_case(
            {
                key: value
                for key, value in expected.items()
                if key not in {"shape", "affine", "orientation", "voxel_spacing", "image_sha256", "mask_sha256", "label_voxels"}
            },
            root,
            label_ids,
        )
        if verify_hashes:
            for key in ("image_sha256", "mask_sha256"):
                if current[key] != expected.get(key):
                    raise ManifestValidationError(f"{expected.get('case_id')}: {key} changed after manifest creation.")
        inspected.append(current)
    validation = _summarize_cases(inspected, label_ids)
    if validation["status"] != "PASSED":
        raise ManifestValidationError("; ".join(validation["errors"]))
    return validation


def write_manifest(manifest: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def _parse_labels(value: str) -> dict[int, str]:
    source = Path(value)
    payload = json.loads(source.read_text(encoding="utf-8")) if source.is_file() else json.loads(value)
    if isinstance(payload, list):
        return {int(item["id"]): str(item["name"]) for item in payload}
    if not isinstance(payload, dict):
        raise ManifestValidationError("Labels must be a JSON object or list of id/name objects.")
    return {int(key): str(name) for key, name in payload.items()}


def _add_common_build_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--test-fraction", type=float, default=0.15)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    acdc = subparsers.add_parser("acdc", help="Discover the local ACDC ED/ES image-mask pairs.")
    _add_common_build_arguments(acdc)
    acdc.add_argument("--dataset-id", default="acdc-cardiac-mri")

    generic = subparsers.add_parser("pairs", help="Build from a generic image/mask pairs CSV.")
    _add_common_build_arguments(generic)
    generic.add_argument("--dataset-id", required=True)
    generic.add_argument("--pairs-csv", type=Path, required=True)
    generic.add_argument("--labels", required=True, help="JSON object/list or path to a JSON file.")

    validate = subparsers.add_parser("validate", help="Revalidate all manifest paths, hashes, geometry and labels.")
    validate.add_argument("--manifest", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "validate":
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
        print(json.dumps(validate_manifest(payload), indent=2))
        return 0

    if args.command == "acdc":
        pairs, discovery = discover_acdc_pairs(args.dataset_root)
        labels = ACDC_LABELS
    else:
        pairs = read_pairs_csv(args.pairs_csv, args.dataset_root)
        discovery = {"layout": "GENERIC_PAIRS_CSV", "pairs_csv": str(args.pairs_csv.resolve())}
        labels = _parse_labels(args.labels)
    manifest = build_manifest(
        dataset_id=args.dataset_id,
        dataset_root=args.dataset_root,
        pairs=pairs,
        labels=labels,
        seed=args.seed,
        val_fraction=args.val_fraction,
        test_fraction=args.test_fraction,
        registry_path=args.registry,
        discovery=discovery,
    )
    write_manifest(manifest, args.output)
    summary = {
        "manifest": str(args.output.resolve()),
        "dataset_id": manifest["dataset_id"],
        "dataset_version": manifest["dataset_version"],
        "cases": manifest["validation"]["case_count"],
        "patients": manifest["validation"]["patient_count"],
        "patients_per_split": manifest["validation"]["patients_per_split"],
        "license_authorization": manifest["provenance"]["license_gate"]["authorization_status"],
        "training_eligible": manifest["training_eligible"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
