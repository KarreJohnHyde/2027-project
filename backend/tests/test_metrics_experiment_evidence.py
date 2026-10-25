"""Focused contracts for registered research-experiment evidence in Eq. 1-5."""

import json

from app.services import model_registry
from tests.conftest import get_auth_headers


CHECKPOINT_SHA = "a" * 64


def _model(model_id: str, task: str, report: str, dataset_version: str) -> dict:
    return {
        "model_id": model_id,
        "display_name": f"Synthetic {task} experiment",
        "task": task,
        "status": "READY_UNVALIDATED",
        "validated": False,
        "research_inference": True,
        "artifact_bundle": {
            "dataset_version": dataset_version,
            "dataset_license": "CC0 synthetic fixture",
            "evaluation_report_path": report,
            "checkpoint_sha256": CHECKPOINT_SHA,
        },
    }


def _base_report(model_id: str, dataset_version: str) -> dict:
    return {
        "model_id": model_id,
        "dataset": f"Synthetic public dataset for {model_id}",
        "dataset_version": dataset_version,
        "split_method": "fixture held-out split",
        "checkpoint": {"sha256": CHECKPOINT_SHA},
        "limitations": ["Synthetic fixture; internal held-out evaluation only."],
    }


def _write(root, relative: str, payload: dict) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


def _equations(response) -> dict[str, dict]:
    assert response.status_code == 200, response.text
    return {item["equation_id"]: item for item in response.json()["equations"]}


def test_ieee_metrics_load_registered_classification_segmentation_and_detection_reports(
    client, test_users, tmp_path, monkeypatch
):
    root = tmp_path / "project"
    root.mkdir()
    classification = _base_report("fixture-classifier", "class-v1")
    classification.update({
        "test_n": 17,
        "metrics": {"accuracy": 0.75, "macro_f1": 0.7, "ignored_metric": 999},
        "confidence_intervals_95": {"accuracy": {"status": "COMPUTED", "low": 0.5, "high": 0.9}},
    })
    segmentation = _base_report("fixture-segmenter", "segment-v1")
    segmentation.update({
        "test": {
            "n_images": 11,
            "mean_foreground_dice_per_image": 0.61,
            "vessel_dice": 0.72,
            "vessel_iou": 0.58,
            "confidence_intervals_95": {
                "vessel_dice": {"status": "COMPUTED", "low": 0.6, "high": 0.8}
            },
        }
    })
    detection = _base_report("fixture-detector", "detect-v1")
    detection.update({
        "test": {"n_images": 13, "metrics": {"map_50_95": 0.2, "ap_50": 0.44, "ar_100": 0.5}},
        "evaluation_protocol": "Synthetic COCO-style held-out evaluation.",
    })
    for relative, report in (
        ("reports/classification.json", classification),
        ("reports/segmentation.json", segmentation),
        ("reports/detection.json", detection),
    ):
        _write(root, relative, report)
    models = [
        _model("fixture-classifier", "image_classification", "reports/classification.json", "class-v1"),
        _model("fixture-segmenter", "semantic_segmentation", "reports/segmentation.json", "segment-v1"),
        _model("fixture-detector", "object_detection", "reports/detection.json", "detect-v1"),
    ]
    monkeypatch.setattr(model_registry, "PROJECT_ROOT", root)
    monkeypatch.setattr(model_registry, "_load_registry", lambda: {"models": models})

    headers = get_auth_headers(test_users["clinician_a"])
    response = client.get("/api/v1/metrics/ieee-validation", headers=headers)
    equations = _equations(response)
    assert list(equations) == [
        "Eq. 1-2", "Eq. 3-4", "Eq. 5", "Eq. 6", "Eq. 7", "Eq. 8-10",
        "Eq. 11-12", "Eq. 13-14", "Eq. 15", "Eq. 16",
    ]

    expected = {
        "Eq. 1-2": ("fixture-classifier", 17, "accuracy", 0.75),
        "Eq. 3-4": ("fixture-segmenter", 11, "vessel_dice", 0.72),
        "Eq. 5": ("fixture-detector", 13, "map_50_95", 0.2),
    }
    for equation_id, (model_id, sample_count, metric, value) in expected.items():
        measured = equations[equation_id]["measured_metric"]
        assert measured["status"] == "COMPLETED"
        assert measured["value"]["evidence_scope"] == "INTERNAL_HELD_OUT_RESEARCH_ONLY"
        assert measured["value"]["clinical_validation"] is False
        assert measured["value"]["external_validation"] is False
        experiment = measured["value"]["experiments"][0]
        assert experiment["model_id"] == model_id
        assert experiment["held_out_sample_count"] == sample_count
        assert experiment["metrics"][metric] == value
        assert "ignored_metric" not in experiment["metrics"]
        assert experiment["clinical_validation"] is False
        assert experiment["external_validation"] is False
        assert len(experiment["evaluation_report_sha256"]) == 64
        assert experiment["limitations"][-1].endswith("not external or clinical validation.")

    payload = response.json()
    assert payload["status"] == "PENDING_VALIDATION"
    assert "not external or clinical validation" in payload["research_notice"]


def test_ieee_metrics_reject_unsafe_or_malformed_reports_without_hiding_valid_evidence(
    client, test_users, tmp_path, monkeypatch
):
    root = tmp_path / "project"
    root.mkdir()
    valid = _base_report("valid-detector", "valid-v1")
    valid["test"] = {"n_images": 5, "metrics": {"map_50_95": 0.1}}
    _write(root, "reports/valid.json", valid)
    invalid = root / "reports" / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(valid), encoding="utf-8")
    mismatch = _base_report("different-model", "mismatch-v1")
    mismatch["test"] = {"n_images": 5, "metrics": {"map_50_95": 0.9}}
    _write(root, "reports/mismatch.json", mismatch)
    models = [
        _model("valid-detector", "object_detection", "reports/valid.json", "valid-v1"),
        _model("invalid-detector", "object_detection", "reports/invalid.json", "invalid-v1"),
        _model("outside-detector", "object_detection", str(outside), "outside-v1"),
        _model("mismatch-detector", "object_detection", "reports/mismatch.json", "mismatch-v1"),
    ]
    monkeypatch.setattr(model_registry, "PROJECT_ROOT", root)
    monkeypatch.setattr(model_registry, "_load_registry", lambda: {"models": models})

    response = client.get(
        "/api/v1/metrics/ieee-validation",
        headers=get_auth_headers(test_users["clinician_a"]),
    )
    measured = _equations(response)["Eq. 5"]["measured_metric"]
    assert measured["status"] == "COMPLETED"
    assert [item["model_id"] for item in measured["value"]["experiments"]] == ["valid-detector"]
    assert measured["registered_models_considered"] == 4
    assert {item["code"] for item in measured["unavailable_reports"]} == {
        "EVALUATION_REPORT_INVALID_JSON",
        "EVALUATION_REPORT_OUTSIDE_PROJECT_ROOT",
        "EVALUATION_REPORT_MODEL_MISMATCH",
    }
    assert "{not-json" not in response.text
    assert str(tmp_path) not in response.text
