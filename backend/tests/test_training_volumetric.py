"""Execution tests for the license-gated volumetric segmentation path."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml_training.volumetric import TrainConfig, create_synthetic_fixture, run_training  # noqa: E402
from ml_training.volumetric_manifest import (  # noqa: E402
    DEFAULT_REGISTRY,
    LicenseAuthorizationError,
    ManifestValidationError,
    build_manifest,
    enforce_training_license,
    validate_manifest,
)


def _registry(tmp_path: Path, license_block: dict) -> Path:
    path = tmp_path / "tasks.json"
    path.write_text(json.dumps({"datasets": [{"id": "acdc-cardiac-mri", "license": license_block}]}), encoding="utf-8")
    return path


def test_real_acdc_training_fails_closed_without_explicit_authorization(tmp_path: Path) -> None:
    manifest = {
        "dataset_id": "acdc-cardiac-mri",
        "synthetic_test_fixture": False,
    }
    output = tmp_path / "must-not-exist"
    # Source and citation verification alone is not authorization.
    unauthorized = _registry(tmp_path, {"status": "SOURCE_AND_CITATION_VERIFIED_TERMS_NOT_FOUND", "authorization_status": "UNVERIFIED"})

    with pytest.raises(LicenseAuthorizationError, match="not VERIFIED"):
        enforce_training_license(manifest, unauthorized)
    with pytest.raises(LicenseAuthorizationError, match="NOT_REGISTERED"):
        enforce_training_license({**manifest, "dataset_id": "not-registered"}, unauthorized)

    assert not output.exists()


def test_recorded_owner_authorization_opens_the_real_data_gate(tmp_path: Path) -> None:
    authorized = _registry(tmp_path, {"status": "SOURCE_AND_CITATION_VERIFIED_TERMS_NOT_FOUND", "authorization_status": "VERIFIED"})
    evidence = enforce_training_license({"dataset_id": "acdc-cardiac-mri", "synthetic_test_fixture": False}, authorized)
    assert evidence["authorized"] is True and evidence["authorization_status"] == "VERIFIED"
    # The live registry records the owner's 2026-10-25 authorization for ACDC.
    live = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    acdc = next(item for item in live["datasets"] if item["id"] == "acdc-cardiac-mri")
    assert acdc["license"]["authorization_status"] == "VERIFIED" and acdc["license"]["authorized_on"] == "2026-10-25"


def test_manifest_rejects_image_mask_affine_mismatch(tmp_path: Path) -> None:
    pairs = []
    for index in range(3):
        patient = f"patient{index}"
        image_path = tmp_path / f"{patient}_image.nii.gz"
        mask_path = tmp_path / f"{patient}_mask.nii.gz"
        image_affine = np.eye(4)
        mask_affine = np.eye(4)
        if index == 1:
            mask_affine[0, 3] = 3.0
        nib.save(nib.Nifti1Image(np.ones((8, 8, 8), dtype=np.float32), image_affine), image_path)
        nib.save(nib.Nifti1Image(np.ones((8, 8, 8), dtype=np.uint8), mask_affine), mask_path)
        pairs.append(
            {
                "patient_id": patient,
                "case_id": f"{patient}_case",
                "image_path": image_path.name,
                "mask_path": mask_path.name,
            }
        )

    with pytest.raises(ManifestValidationError, match="affines differ"):
        build_manifest(
            dataset_id="geometry-test",
            dataset_root=tmp_path,
            pairs=pairs,
            labels={0: "background", 1: "target"},
            synthetic_test_fixture=True,
        )


def test_manifest_preserves_publisher_test_and_excludes_linked_development_patient(tmp_path: Path) -> None:
    pairs = []
    shared_image = np.arange(8**3, dtype=np.float32).reshape(8, 8, 8)
    for index in range(6):
        patient = f"patient{index}"
        image_path = tmp_path / f"{patient}_image.nii.gz"
        mask_path = tmp_path / f"{patient}_mask.nii.gz"
        # patient0 (development) and patient4 (publisher test) are exact image
        # duplicates but carry different annotations. The frozen test copy wins.
        image = shared_image if index in {0, 4} else shared_image + index * 1_000
        mask = np.zeros((8, 8, 8), dtype=np.uint8)
        mask[index, index, index] = 1
        nib.save(nib.Nifti1Image(image, np.eye(4)), image_path)
        nib.save(nib.Nifti1Image(mask, np.eye(4)), mask_path)
        pairs.append(
            {
                "patient_id": patient,
                "case_id": f"{patient}_case",
                "publisher_split": "train" if index < 4 else "test",
                "image_path": image_path.name,
                "mask_path": mask_path.name,
            }
        )

    manifest = build_manifest(
        dataset_id="publisher-split-test",
        dataset_root=tmp_path,
        pairs=pairs,
        labels={0: "background", 1: "target"},
        val_fraction=1 / 3,
        synthetic_test_fixture=True,
    )

    assert manifest["validation"]["status"] == "PASSED"
    assert manifest["validation"]["patients_per_split"] == {"train": 2, "val": 1, "test": 2}
    assert {case["patient_id"] for case in manifest["cases"] if case["split"] == "test"} == {
        "patient4",
        "patient5",
    }
    exclusions = manifest["split_policy"]["leakage_exclusions"]
    assert exclusions["excluded_development_patients"] == ["patient0"]
    assert exclusions["excluded_development_cases"] == 1
    assert exclusions["cross_cohort_identical_image_groups"][0]["mask_annotations_identical"] is False


def test_synthetic_smoke_executes_validation_training_evaluation_and_resume(tmp_path: Path) -> None:
    smoke_root = tmp_path / "smoke"
    manifest_path = create_synthetic_fixture(smoke_root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    validation = validate_manifest(manifest)
    assert validation["status"] == "PASSED"
    assert validation["patient_split_overlap"] == {}
    assert validation["cross_split_identical_content"] == []
    assert validation["patients_per_split"] == {"train": 4, "val": 1, "test": 1}
    assert validation["observed_label_ids"] == [0, 1, 2]

    first = run_training(
        TrainConfig(
            manifest_path=manifest_path,
            output_dir=smoke_root / "run-1",
            device="cpu",
            epochs=1,
            batch_size=2,
            patch_size=(12, 12, 12),
            channels=(4, 8),
            patches_per_case=1,
            workers=0,
            seed=20261024,
            save_predictions=True,
            torch_threads=1,
            allow_synthetic_test_fixture=True,
        )
    )

    assert first["execution_status"] == "COMPLETE"
    assert first["model_registry_mutation"] == "NONE"
    assert first["held_out_test"]["case_count"] == 1
    assert len(first["held_out_test"]["per_class"]) == 2
    assert Path(first["checkpoint"]["path"]).is_file()
    assert len(list((smoke_root / "run-1" / "held_out_predictions").glob("*.nii.gz"))) == 1

    resumed = run_training(
        TrainConfig(
            manifest_path=manifest_path,
            output_dir=smoke_root / "run-2",
            device="cpu",
            epochs=2,
            batch_size=2,
            patch_size=(12, 12, 12),
            channels=(4, 8),
            patches_per_case=1,
            workers=0,
            seed=20261024,
            resume=smoke_root / "run-1" / "last.pt",
            torch_threads=1,
            allow_synthetic_test_fixture=True,
        )
    )

    assert resumed["execution_status"] == "COMPLETE"
    assert resumed["resume"]["from_epoch"] == 1
    assert [item["epoch"] for item in resumed["epochs"]] == [2]
    assert Path(resumed["checkpoint"]["path"]).is_file()
