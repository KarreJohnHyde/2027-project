import json
from pathlib import Path
import sys
import zipfile
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from prepare_rcc_aid import metadata_pairs, index_archive, extract_pairs


def rows():
    return [{"SeriesInstanceUID": f"1.2.{i}", "PatientID": "SYNTHETIC-SHARED", "Collection": "TCGA-KIRC",
             "Modality": "CT", "LicenseURI": "http://creativecommons.org/licenses/by/3.0/"} for i in (1, 2)]


def test_exact_series_matching_retains_patient_groups_and_excludes_other_metadata():
    records = rows(); records[0]["PatientName"] = "SYNTHETIC TEST ONLY"
    pairs = metadata_pairs(records)
    assert pairs[0]["image_path"] == "images/KIRC_1_2_1.nii.gz"
    assert pairs[0]["patient_id"] == pairs[1]["patient_id"]
    assert "PatientName" not in json.dumps(pairs)
    with pytest.raises(ValueError): metadata_pairs(records + records[:1])


def test_wrong_or_traversing_archive_member_is_rejected(tmp_path):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as archive: archive.writestr("../escape.nii.gz", b"synthetic")
    with zipfile.ZipFile(path) as archive, pytest.raises(ValueError): index_archive(archive, {"images/expected.nii.gz"})


def test_safe_extraction_preserves_zip_and_matches_all_pairs(tmp_path):
    pairs = metadata_pairs(rows())
    for name, field in [("images.zip", "image_path"), ("annotations.zip", "mask_path")]:
        with zipfile.ZipFile(tmp_path / name, "w") as archive:
            for pair in pairs: archive.writestr(pair[field], b"synthetic-nifti-placeholder")
    destination = tmp_path / "paired"
    extract_pairs(tmp_path, destination, pairs, {"synthetic": "fixture"}, reserve=0)
    assert (tmp_path / "images.zip").is_file()
    assert len(json.loads((destination / "extraction.json").read_text())) == 4
    assert (destination / pairs[0]["mask_path"]).read_bytes() == b"synthetic-nifti-placeholder"
