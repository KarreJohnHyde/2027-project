import json
import stat
import sys
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1]
sys.path.insert(0, str(SCRIPTS))
import acquire_public_datasets as acquisition
import prepare_multimodal_resources as prepare


def test_castagnoli_checksum_matches_standard_vector(tmp_path):
    pytest.importorskip("google_crc32c")
    file = tmp_path / "payload"
    file.write_bytes(b"123456789")
    assert acquisition.digest(file, "crc32c") == "e3069283"


@pytest.mark.parametrize("name", ["../outside.txt", "/outside.txt", "C:/outside.txt", "inside/../../outside.txt"])
def test_extraction_rejects_paths_outside_dataset(tmp_path, monkeypatch, name):
    monkeypatch.setattr(prepare, "RESERVE", 0)
    source = tmp_path / "input.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(name, b"payload")
    with pytest.raises(ValueError, match="Unsafe archive member"):
        prepare.extract_safe(source, tmp_path / "extracted")
    assert not (tmp_path / "outside.txt").exists()


def test_extraction_rejects_zip_links(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare, "RESERVE", 0)
    source = tmp_path / "input.zip"
    member = zipfile.ZipInfo("link")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(member, "../outside")
    with pytest.raises(ValueError, match="links"):
        prepare.extract_safe(source, tmp_path / "extracted")


def test_extraction_checks_crc_and_does_not_overwrite_modified_data(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare, "RESERVE", 0)
    source = tmp_path / "input.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("image.bin", b"expected")
    root = tmp_path / "extracted"
    prepare.extract_safe(source, root)
    prepare.extract_safe(source, root)
    (root / "image.bin").write_bytes(b"modified")
    with pytest.raises(ValueError, match="Existing extraction differs"):
        prepare.extract_safe(source, root)
    assert (root / "image.bin").read_bytes() == b"modified"


def test_oversized_expansion_is_refused(tmp_path):
    source = tmp_path / "input.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("image", b"x" * 1000)
    with pytest.raises(ValueError, match="size budget"):
        prepare.extract_safe(source, tmp_path / "extracted", max_bytes=100)


def test_identical_vqa_images_stay_together_across_questions(tmp_path):
    root = tmp_path / "vqa"
    images = root / "images"
    images.mkdir(parents=True)
    (images / "a.jpg").write_bytes(b"same image content")
    (images / "b.jpg").write_bytes(b"same image content")
    data = [{"image_name": name, "question": q, "answer": "yes"} for name, q in [("a.jpg", "Q1"), ("a.jpg", "Q2"), ("b.jpg", "Q3")]]
    (root / "VQA_RAD Dataset Public.json").write_text(json.dumps(data))
    output = tmp_path / "derived"
    prepare.prepare_vqa(root, output)
    rows = [json.loads(line) for line in (output / "samples.jsonl").read_text().splitlines()]
    assert len(rows) == 3
    assert len({row["split"] for row in rows}) == 1
    assert len({row["image_sha256"] for row in rows}) == 1


def test_cbis_publisher_overlap_cannot_put_a_test_patient_in_training():
    rows = [{"patient_id": "patient-a", "publisher_split": "train"},
            {"patient_id": "patient-a", "publisher_split": "test"},
            {"patient_id": "patient-b", "publisher_split": "train"},
            {"patient_id": "patient-b", "publisher_split": "train"}]
    result = prepare.cbis_patient_split(rows)
    assert [row["split"] for row in result[:2]] == ["test", "test"]
    assert result[2]["split"] == result[3]["split"]
    assert result[2]["split"] in ("train", "val")
    assert "split" not in rows[0]
