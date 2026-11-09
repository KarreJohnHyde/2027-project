import io
import json
from pathlib import Path
import sys
import tarfile

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from prepare_liver_pipeline import selected_members, extract_labelled, checksum
from prepare_msd_ct_datasets import prepare


def fixture_tar(path, extra=None):
    with tarfile.open(path, "w") as archive:
        for name, payload in [("Task03_Liver/dataset.json", b"{}"), ("Task03_Liver/imagesTr/a.nii.gz", b"synthetic-image"),
                              ("Task03_Liver/labelsTr/a.nii.gz", b"synthetic-mask"), ("Task03_Liver/imagesTs/b.nii.gz", b"unlabelled")]:
            info = tarfile.TarInfo(name); info.size = len(payload); archive.addfile(info, io.BytesIO(payload))
        if extra:
            archive.addfile(extra)


@pytest.mark.parametrize("kind", ["traversal", "link", "duplicate"])
def test_bad_members_are_refused_before_any_extraction(tmp_path, kind):
    path = tmp_path / "bad.tar"
    name = {"traversal": "../escape", "link": "Task03_Liver/link", "duplicate": "Task03_Liver/dataset.json"}[kind]
    info = tarfile.TarInfo(name)
    if kind == "link": info.type = tarfile.SYMTYPE; info.linkname = "../escape"
    fixture_tar(path, info)
    with tarfile.open(path) as archive, pytest.raises(ValueError):
        selected_members(archive)


def test_extraction_preserves_source_and_omits_unlabelled_test_images(tmp_path):
    source = tmp_path / "source.tar"; fixture_tar(source)
    expected = checksum(source)
    target = tmp_path / "Task03_Liver"
    result = extract_labelled(source, target, expected, reserve=0)
    assert checksum(source) == expected
    assert set(result["files"]) == {"dataset.json", "imagesTr/a.nii.gz", "labelsTr/a.nii.gz"}
    assert not (target / "imagesTs").exists()
    (target / "imagesTr/a.nii.gz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        extract_labelled(source, target, expected, reserve=0)


def test_pairing_requires_exact_publisher_inventory(tmp_path):
    for folder in ("imagesTr", "labelsTr"):
        (tmp_path / folder).mkdir(); (tmp_path / folder / "a.nii.gz").write_bytes(b"synthetic")
    meta = {"modality": {"0": "CT"}, "labels": {"0": "background", "1": "liver"}, "numTraining": 1,
            "training": [{"image": "./imagesTr/a.nii.gz", "label": "./labelsTr/a.nii.gz"}], "licence": "CC-BY-SA 4.0"}
    (tmp_path / "dataset.json").write_text(json.dumps(meta))
    assert prepare(tmp_path, tmp_path / "out")["cases"] == 1
    (tmp_path / "labelsTr/orphan.nii.gz").write_bytes(b"orphan")
    with pytest.raises(ValueError, match="inventory"):
        prepare(tmp_path, tmp_path / "out")


def test_registration_does_not_convert_preparation_into_commercial_permission(tmp_path, monkeypatch):
    import register_msd_ct_dataset as register
    from ml_training import volumetric_manifest as vm
    monkeypatch.setattr(register, "ROOT", tmp_path)
    context = tmp_path / "context.json"
    context.write_text(json.dumps({"training_purpose": "commercial_development"}))
    monkeypatch.setattr(vm, "RELEASE_CONTEXT", context)
    registry = tmp_path / "dataset_registry/tasks.json"
    registry.parent.mkdir(); registry.write_text(json.dumps({"datasets": []}))
    source = tmp_path / "Task03_Liver"
    (source / "imagesTr").mkdir(parents=True); (source / "imagesTr/a.nii.gz").write_bytes(b"synthetic")
    (source / "dataset.json").write_text(json.dumps({"licence": "CC-BY-SA 4.0", "labels": {"0": "background", "1": "liver"}}))
    archive = tmp_path / "synthetic.tar"; archive.write_bytes(b"synthetic-source")
    monkeypatch.setattr(sys, "argv", ["register", "--archive", str(archive), "--task-dir", str(source),
                                    "--dataset-id", "synthetic-liver", "--task-id", "synthetic-seg", "--system", "liver",
                                    "--target", "synthetic test only", "--title", "Synthetic test only"])
    assert register.main() == 0
    row = json.loads(registry.read_text())["datasets"][0]
    assert row["license"]["authorization_status"] == "VERIFIED"
    assert row["tasks"][0]["training_eligible"] is False
    assert row["tasks"][0]["readiness"] == "RIGHTS_REVIEW_REQUIRED_FOR_DECLARED_PURPOSE"
