"""Isolated experiment-method tests; no downloaded corpus or OCR run required."""
import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest
from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("word_preprocessing_experiment", SCRIPTS / "experiment_ocr_word_preprocessing.py")
experiment = importlib.util.module_from_spec(spec); spec.loader.exec_module(experiment)


def test_development_holdout_partition_is_disjoint_and_does_not_use_labels():
    records = [{"id": str(i), "image_sha256": hashlib.sha256(str(i).encode()).hexdigest(), "gold": "unseen label"} for i in range(100)]
    dev, hold = experiment.partition(records, 16, 32)
    before = [r["id"] for r in dev + hold]
    assert not ({r["image_sha256"] for r in dev} & {r["image_sha256"] for r in hold})
    for row in records: row["gold"] = "changed label"
    repeated = experiment.partition(list(reversed(records)), 16, 32)
    assert [r["id"] for group in repeated for r in group] == before


def test_duplicate_sources_cannot_cross_partitions():
    records = [{"id": str(i), "image_sha256": "same"} for i in range(60)]
    with pytest.raises(ValueError, match="Duplicate"):
        experiment.partition(records, 16, 32)


@pytest.mark.parametrize("colour", ["white", "black", "gray"])
def test_recognizer_only_candidate_refuses_uniform_blank_crops(colour):
    image, details = experiment.prepared_image(Image.new("RGB", (128, 128), colour), "word_recognizer_tight_scale2_border8")
    assert image is None and details["refusal"] == "UNIFORM_IMAGE"


def test_fixed_source_transform_preserves_foreground_and_records_inverse_mapping():
    original = Image.new("RGB", (128, 128), "white")
    ImageDraw.Draw(original).rectangle((24, 40, 96, 63), fill="black")
    transformed, details = experiment.prepared_image(original, "word_recognizer_tight_scale2_border8")
    x0, y0, x1, y1 = details["source_crop_bbox"]
    assert 0 <= x0 < 24 < 96 < x1 <= 128 and 0 <= y0 < 40 < 63 < y1 <= 128
    assert transformed.width == (x1 - x0) * details["scale"] + 2 * details["border"]
    assert transformed.height == (y1 - y0) * details["scale"] + 2 * details["border"]
    assert transformed.getextrema()[0][0] == 0


def test_paired_comparison_keeps_source_identity_and_reference_denominator():
    base = [{"id": str(i), "reference_characters": 10, "character_edits": 8} for i in range(32)]
    candidate = [{"id": str(i), "reference_characters": 10, "character_edits": 6} for i in range(32)]
    result = experiment.paired_delta(base, candidate)
    assert result["candidate_minus_baseline_cer"] == pytest.approx(-.2)
    assert result["word_resampling_95_percentile_interval"] == pytest.approx([-.2, -.2])
    candidate[0]["id"] = "different-source"
    with pytest.raises(ValueError, match="source IDs"): experiment.paired_delta(base, candidate)
