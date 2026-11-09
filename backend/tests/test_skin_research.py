import csv
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from app.routers.research_models import ResearchInferenceRequest
from app.services import model_inference as inference, skin_metadata


def schema():
    return skin_metadata.fit_encoder([{"age": 20, "gender": "FEMALE", "region": "ARM"},
                                      {"age": 80, "gender": "MALE", "region": "FACE"}])


def test_metadata_is_train_only_and_rejects_label_leakage():
    contract = schema()
    assert contract["age_mean"] == 50
    assert np.isfinite(skin_metadata.encode({"age": None, "region": "unseen"}, contract)).all()
    with pytest.raises(ValueError, match="Only age"):
        skin_metadata.encode({"age": 40, "diagnostic": "melanoma"}, contract)
    with pytest.raises(ValueError, match="required"):
        skin_metadata.check_serving_features({}, contract)
    with pytest.raises(ValueError, match="training age range"):
        skin_metadata.check_serving_features({"age": 90, "region": "ARM"}, contract)
    with pytest.raises(ValueError, match="lesion region"):
        skin_metadata.check_serving_features({"age": 40, "region": "NOT_DOCUMENTED"}, contract)


@pytest.mark.parametrize("age", [True, float("nan"), float("inf"), -1, 121, "not an age"])
def test_bad_ages_are_never_imputed_into_valid_values(age):
    with pytest.raises(ValueError):
        skin_metadata.age_value(age)


def test_request_carries_only_explicit_validated_clinical_features():
    request = ResearchInferenceRequest(model_id="skin", declared_input_type="DERMATOLOGY",
                                        clinical_features={"age": 40.0, "region": "ARM"})
    assert request.options()["clinical_features"] == {"age": 40.0, "region": "ARM"}
    with pytest.raises(ValueError):
        ResearchInferenceRequest(model_id="skin", declared_input_type="DERMATOLOGY",
                                   clinical_features={"age": 40.0, "region": "ARM", "biopsied": True})


def test_blank_and_achromatic_images_refuse_before_model_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(inference, "ood_reference", lambda model: {})
    model = {"input_quality": {"min_dimension": 64, "min_intensity_std": 2.0, "min_chroma": 5.0}}
    path = tmp_path / "blank.png"
    Image.new("RGB", (128, 128), "white").save(path)
    with pytest.raises(inference.InferenceNotPermitted, match="INSUFFICIENT_CONTRAST"):
        inference.check_distribution(model, path)
    pixels = np.tile(np.arange(128, dtype=np.uint8)[None, :] * 2, (128, 1))
    Image.fromarray(pixels).save(path)
    with pytest.raises(inference.InferenceNotPermitted, match="ACHROMATIC"):
        inference.check_distribution(model, path)


def test_real_registered_skin_checkpoints_reproduce_saved_predictions():
    root = Path(__file__).resolve().parents[2]
    source = root / "_derived/datasets/multimodal/pad-ufes-20/samples.jsonl"
    if not source.exists():
        pytest.skip("Local PAD cohort is not present in CI")
    rows = {Path(row["image_path"]).name: row for row in map(json.loads, source.read_text().splitlines())}
    for model_id in ("skin_padufes_image_classifier", "skin_padufes_image_tabular_classifier"):
        model = next((item for item in inference._load_registry()["models"] if item["model_id"] == model_id), None)
        if model is None or not (root / model["artifact_bundle"]["checkpoint_path"]).exists():
            pytest.skip("Local research checkpoint is not present in CI")
        with (root / model["artifact_bundle"]["held_out_predictions_path"]).open(newline="") as handle:
            saved = list(csv.DictReader(handle))
        checked = 0
        for prediction in saved:
            row = rows[prediction["entry"]]
            attributes = {field: row["features"].get(field) for field in skin_metadata.FIELDS}
            options = {}
            if model.get("requires_clinical_features"):
                try:
                    skin_metadata.check_serving_features(attributes, model["clinical_metadata_contract"])
                except ValueError:
                    continue
                options["clinical_features"] = attributes
            output = inference.run_model(model, Path(row["image_path"]), options)
            for item in output["classes"]:
                assert abs(item["probability"] - float(prediction["p_" + item["class"]])) < 0.005
            assert model["validated"] is False
            checked += 1
            if checked == 6:
                break
        assert checked == 6
