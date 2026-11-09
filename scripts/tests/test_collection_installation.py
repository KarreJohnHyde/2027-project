"""Integrity and evidence-boundary checks for the new installation tools."""
import csv
import importlib.util
import json
from pathlib import Path
import sys
import zipfile
import subprocess

import numpy as np
import pytest

SCRIPTS = Path(__file__).parents[1]
sys.path.insert(0, str(SCRIPTS))
import install_medmnist_collection as collection
import resume_dataset_cohorts as recovery

spec = importlib.util.spec_from_file_location("coverage_export", SCRIPTS / "export_capability_coverage.py")
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)


def test_verified_complete_partial_promotes_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "DATA", tmp_path)
    target = tmp_path / "case.zip"
    part = tmp_path / "case.zip.part"
    with zipfile.ZipFile(part, "w") as archive:
        archive.writestr("synthetic.dcm", b"synthetic-not-clinical")
    size = part.stat().st_size
    def forbidden(*args, **kwargs):
        pytest.fail("A verified complete archive must not be downloaded again")
    monkeypatch.setattr(recovery.subprocess, "run", forbidden)
    result = recovery.acquire("https://example.invalid/fixture", target, size, 1)
    assert result["status"] == "VERIFIED_RECOVERED_PARTIAL"
    assert target.exists() and not part.exists()
    assert result["local_sha256"] == recovery.sha256(target)


def test_corrupt_complete_partial_is_preserved_before_fresh_transfer(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "DATA", tmp_path)
    monkeypatch.setattr(recovery, "RESERVE", 0)
    source = tmp_path / "fixture.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("synthetic.dcm", b"synthetic-not-clinical")
    valid = source.read_bytes()
    target = tmp_path / "case.zip"
    part = tmp_path / "case.zip.part"
    part.write_bytes(b"x" * len(valid))
    def transfer(command, **kwargs):
        assert not part.exists()
        assert len(list(tmp_path.glob("case.zip.part.invalid-*"))) == 1
        part.write_bytes(valid)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(recovery.subprocess, "run", transfer)
    result = recovery.acquire("https://example.invalid/fixture", target, len(valid), 1)
    assert result["status"] == "DOWNLOADED_ARCHIVE_VERIFIED"
    assert target.read_bytes() == valid
    assert next(tmp_path.glob("case.zip.part.invalid-*")).read_bytes() == b"x" * len(valid)


def test_benchmark_indexes_preserve_split_labels_and_3d_arrays(tmp_path):
    source = tmp_path / "benchmark.npz"
    data = {}
    for split in ("train", "val", "test"):
        data[f"{split}_images"] = np.zeros((2, 28, 28, 28), dtype=np.uint8)
        data[f"{split}_labels"] = np.array([[0], [1]], dtype=np.uint8)
    np.savez_compressed(source, **data)
    item = {"dataset": "synthetic", "split_counts": dict.fromkeys(("train", "val", "test"), 2),
            "dimensions": 3, "task": "binary-class", "labels": {"0": "a", "1": "b"},
            "hash": "test-source-checksum", "license": "test-only"}
    result = collection.prepare(item, source, tmp_path / "index")
    with (tmp_path / "index/samples.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6
    assert [row["split"] for row in rows] == ["train", "train", "val", "val", "test", "test"]
    assert json.loads(rows[1]["labels_json"]) == [1]
    assert result["clinical_validated"] is False
    assert result["patient_independence"] == "NOT_ESTABLISHED"
    assert (tmp_path / "index/test_preview.png").is_file()
    assert collection.digest(source) == result["local_sha256"]


def test_invalid_benchmark_categories_never_publish_index(tmp_path):
    source = tmp_path / "bad.npz"
    np.savez_compressed(source, train_images=np.zeros((1, 28, 28), dtype=np.uint8), train_labels=np.array([[9]]))
    item = {"dataset": "bad", "split_counts": {"train": 1}, "dimensions": 2,
            "task": "multi-class", "labels": {"0": "normal"}}
    with pytest.raises(ValueError, match="outside declared categories"):
        collection.prepare(item, source, tmp_path / "index")
    assert not (tmp_path / "index/samples.csv").exists()


def test_lidc_archive_requires_the_declared_slice_count(tmp_path):
    path = tmp_path / "scan.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("one.dcm", b"synthetic DICOM placeholder")
    with pytest.raises(ValueError, match="Expected 2 DICOM"):
        recovery.check_archive(path, expected_images=2)
    result = recovery.check_archive(path, expected_images=1)
    assert result["dicom_images"] == 1
    # This only verifies a transport archive, not a parsed or usable scan.
    assert "clinical" not in result


def test_download_path_cannot_escape_the_dataset_root(tmp_path, monkeypatch):
    monkeypatch.setattr(recovery, "DATA", tmp_path / "allowed")
    with pytest.raises(ValueError):
        recovery.acquire("https://example.invalid/never-requested", tmp_path / "outside.zip")


def test_segmentation_coverage_preserves_anatomy_and_never_implies_validation():
    model = {"model_id": "anatomy-only", "task": "volumetric_semantic_segmentation", "anatomy": "multi_system",
             "supported_classes": ["background", "liver"], "supported_modalities": ["CT"],
             "artifact_bundle": {"checkpoint_path": "test.pt", "checkpoint_sha256": "a" * 64},
             "activation": {"eligible": False}, "validated": False, "limitations": ["Not a disease detector"]}
    rows = coverage.build_rows([model])
    assert len(rows) == 1
    assert rows[0]["organ_or_system"] == "liver"
    assert rows[0]["target_kind"] == "ANATOMICAL_OR_LESION_MASK"
    assert rows[0]["registry_activation_gate_passed"] is False
    assert rows[0]["registry_validated_flag"] is False
    assert coverage.build_rows([{**model, "processor_only": True}]) == []
