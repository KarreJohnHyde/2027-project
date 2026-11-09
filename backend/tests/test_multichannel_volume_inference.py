"""Multi-channel brain-MRI volume inference (volumetric-monai-multichannel-v2): input contract, preprocessing,
the research-inference route and the trainer's execution path.

Every volume, checkpoint and report here is a synthetic fixture created inside the test (randomly initialised
networks); none of it is patient evidence or a model result."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

torch = pytest.importorskip("torch")
nib = pytest.importorskip("nibabel")
pytest.importorskip("monai")

from app.services import model_inference, model_registry, volume_inference  # noqa: E402
from app.services.volume_inference import VolumeInputError  # noqa: E402
from tests.conftest import get_auth_headers  # noqa: E402

ENVELOPE = {"dataset_version": "fixture", "channels": ["DWI", "ADC"], "in_plane_spacing_mm": {"min": 1.0, "max": 2.0},
            "in_plane_square_pixels": True, "slice_spacing_mm": {"min": 2.0, "max": 5.0}, "slice_axis_last": False,
            "matrix": {"i": {"min": 8, "max": 64}, "j": {"min": 8, "max": 64}, "k": {"min": 4, "max": 40}},
            "nonzero_fraction": {"min": 0.2, "max": 0.5, "margin": 0.05}}
SPEC = {"version": "nifti-foreground-crop-channel-zscore-resample-v2", "foreground_crop": True, "target_spacing_mm": [2.0, 2.0, 2.0],
        "normalisation": "per-channel z-score", "sliding_window_overlap": 0.5, "sliding_window_mode": "gaussian", "sw_batch_size": 1}
ARCHITECTURE = {"name": "monai.networks.nets.SegResNet", "spatial_dims": 3, "in_channels": 2, "out_channels": 2, "init_filters": 8,
                "blocks_down": [1, 1], "blocks_up": [1], "dropout_prob": 0.2}


def _brain(shape=(24, 24, 12), channels=2, seed=0, stripped=True):
    """A synthetic ellipsoid 'brain' with a zero background (as skull-stripped data have)."""
    rng = np.random.default_rng(seed)
    grid = np.indices(shape)
    centre = [(size - 1) / 2 for size in shape]
    inside = sum(((grid[axis] - centre[axis]) / (shape[axis] * 0.42)) ** 2 for axis in range(3)) <= 1
    data = np.stack([np.where(inside | (not stripped), 100.0 + rng.normal(0, 5, shape), 0.0) for _ in range(channels)], axis=-1)
    return data.astype(np.float32)


def _nifti(path, data, zooms=(1.5, 1.5, 3.0)):
    image = nib.Nifti1Image(data, np.diag([1.0, 1.0, 1.0, 1.0]))
    image.header.set_zooms(tuple(zooms) + ((1.0,) if data.ndim == 4 else ()))
    image.header.set_xyzt_units(xyz="mm")
    nib.save(image, str(path))
    return path


def test_stacked_sequences_are_read_channel_first(tmp_path):
    volume = volume_inference.read_volume(_nifti(tmp_path / "v.nii.gz", _brain()), ENVELOPE)
    assert volume.image.shape == (2, 24, 24, 12) and volume.spatial_shape == (24, 24, 12)
    assert volume.spacing_mm == pytest.approx((1.5, 1.5, 3.0))


@pytest.mark.parametrize("data, zooms, code", [
    (_brain(channels=3), (1.5, 1.5, 3.0), "CHANNEL_COUNT_MISMATCH"),
    (_brain(channels=1)[..., 0], (1.5, 1.5, 3.0), "CHANNEL_COUNT_MISMATCH"),
    (_brain(), (2.5, 2.5, 3.0), "IN_PLANE_SPACING_OUTSIDE_DEVELOPMENT_RANGE"),
    (_brain(), (1.5, 1.5, 6.0), "SLICE_SPACING_OUTSIDE_DEVELOPMENT_RANGE"),
    (_brain(stripped=False), (1.5, 1.5, 3.0), "NONZERO_FRACTION_OUTSIDE_DEVELOPMENT_RANGE"),
])
def test_uploads_outside_the_multichannel_contract_are_refused(tmp_path, data, zooms, code):
    with pytest.raises(VolumeInputError) as error:
        volume_inference.read_volume(_nifti(tmp_path / "v.nii.gz", data, zooms), ENVELOPE)
    assert code in error.value.codes


def test_both_in_plane_spacings_and_the_axis_layout_are_checked(tmp_path):
    loose = {**ENVELOPE, "in_plane_square_pixels": False}
    with pytest.raises(VolumeInputError) as error:
        volume_inference.read_volume(_nifti(tmp_path / "dy.nii.gz", _brain(), (1.5, 40.0, 3.0)), loose)
    assert "IN_PLANE_SPACING_OUTSIDE_DEVELOPMENT_RANGE" in error.value.codes, "dy is checked even when square pixels are not required"
    image = nib.Nifti1Image(_brain(), np.diag([-1.0, 1.0, 1.0, 1.0]))  # stored L-A-S instead of R-A-S
    image.header.set_zooms((1.5, 1.5, 3.0, 1.0))
    image.header.set_xyzt_units(xyz="mm")
    nib.save(image, str(tmp_path / "flipped.nii.gz"))
    with pytest.raises(VolumeInputError) as error:
        volume_inference.read_volume(tmp_path / "flipped.nii.gz", {**ENVELOPE, "orientations": ["RAS"]})
    assert "ORIENTATION_OUTSIDE_DEVELOPMENT_SET" in error.value.codes
    assert volume_inference.read_volume(_nifti(tmp_path / "ras.nii.gz", _brain()), {**ENVELOPE, "orientations": ["RAS"]}).image.shape[0] == 2


def test_resampling_that_would_allocate_a_huge_grid_is_refused():
    image = np.zeros((1, 8, 8, 8), dtype=np.float32)
    image[0, 2:6, 2:6, 2:6] = 1.0
    with pytest.raises(VolumeInputError) as error:
        volume_inference.preprocess_multichannel(image, (1.0, 1.0, 1.0), {**SPEC, "target_spacing_mm": [0.001, 0.001, 0.001]})
    assert "RESAMPLED_VOLUME_TOO_LARGE" in error.value.codes


def test_lesion_f1_is_zero_when_nothing_is_detected():
    from ml_training import volumetric_multichannel as trainer

    labels = [{"id": 0, "name": "background"}, {"id": 1, "name": "lesion"}]
    reference = np.zeros((10, 10, 10), np.uint8)
    reference[2:4, 2:4, 2:4] = 1
    cases = [{"case_id": f"c{index}", "patient_id": f"p{index}",
              **trainer.case_metrics(np.zeros_like(reference), reference, labels, {}, (1.0, 1.0, 1.0), True)} for index in range(3)]
    detection = trainer.summarise(cases, labels, {}, 1)["metrics"]["lesion_detection"]
    assert detection["lesion_sensitivity"] == 0.0 and detection["lesion_f1"] == 0.0


def test_isotropic_volumes_are_accepted_when_the_slice_axis_rule_is_off(tmp_path):
    volume = volume_inference.read_volume(_nifti(tmp_path / "iso.nii.gz", _brain(), (2.0, 2.0, 2.0)), ENVELOPE)
    assert volume.spacing_mm == (2.0, 2.0, 2.0)
    with pytest.raises(VolumeInputError) as error:
        volume_inference.read_volume(_nifti(tmp_path / "iso.nii.gz", _brain()[..., :1], (2.0, 2.0, 2.0)),
                                     {**{key: value for key, value in ENVELOPE.items() if key not in {"channels", "nonzero_fraction"}},
                                      "slice_axis_last": True, "slice_spacing_mm": {"min": 2.0, "max": 5.0}})
    assert "SLICE_AXIS_NOT_LAST" in error.value.codes, "single-channel (cardiac) envelopes keep the slice-axis rule"


def test_a_dicom_series_cannot_feed_a_multi_sequence_model():
    with pytest.raises(VolumeInputError) as error:
        volume_inference.from_series(np.zeros((12, 24, 24), np.float32), {"column": 1.5, "row": 1.5, "slice": 3.0}, ENVELOPE)
    assert "CHANNEL_COUNT_MISMATCH" in error.value.codes


def test_preprocessing_crops_normalises_per_channel_and_resamples():
    image = np.moveaxis(_brain(), 3, 0)
    image[1] *= 1000.0  # ADC-like scale: per-channel z-scoring removes it
    array, box, cropped = volume_inference.preprocess_multichannel(image, (1.5, 1.5, 3.0), SPEC)
    occupied = np.any(image != 0, axis=0)
    assert all(occupied[box].any(axis=tuple(other for other in range(3) if other != axis)).all() for axis in range(3))
    assert cropped == tuple(item.stop - item.start for item in box)
    assert array.shape == (2, *volume_inference.resampled_shape(cropped, (1.5, 1.5, 3.0), (2.0, 2.0, 2.0)))
    assert abs(float(array[0].std()) - float(array[1].std())) < 0.1


def test_predictions_return_to_the_upload_grid_with_nothing_outside_the_crop():
    from monai.networks.nets import SegResNet

    torch.manual_seed(0)
    network = SegResNet(spatial_dims=3, init_filters=8, in_channels=2, out_channels=2, blocks_down=(1, 1), blocks_up=(1,)).eval()
    image = np.moveaxis(_brain(), 3, 0)
    payload = {"preprocessing": SPEC, "patch_size": [16, 16, 8]}
    labels = volume_inference.predict_multichannel(network, payload, torch.device("cpu"), image, (1.5, 1.5, 3.0))
    assert labels.shape == (24, 24, 12) and labels.dtype == np.uint8
    box = volume_inference.foreground_box(image)
    outside = np.ones(labels.shape, bool)
    outside[box] = False
    assert not labels[outside].any()


def test_unknown_architectures_are_refused():
    with pytest.raises(VolumeInputError) as error:
        volume_inference.build_network({"trainer_version": volume_inference.MULTICHANNEL_TRAINER, "architecture": {**ARCHITECTURE, "name": "other"}})
    assert "UNSUPPORTED_ARCHITECTURE" in error.value.codes


@pytest.fixture
def brain_registry(tmp_path, monkeypatch):
    torch.manual_seed(0)
    payload = {"trainer_version": volume_inference.MULTICHANNEL_TRAINER, "architecture": ARCHITECTURE}
    network = volume_inference.build_network(payload)
    checkpoint = tmp_path / "brain.pt"
    labels = [{"id": 0, "name": "background"}, {"id": 1, "name": "ischaemic_stroke_lesion"}]
    torch.save({"kind": "volumetric_semantic_segmenter", **payload, "state_dict": network.state_dict(), "labels": labels,
                "channels": ["DWI", "ADC"], "preprocessing": SPEC, "patch_size": [16, 16, 8],
                "volume_semantics": "Fixture lesion volume semantics."}, checkpoint)
    envelope = tmp_path / "envelope.json"
    envelope.write_text(json.dumps(ENVELOPE), encoding="utf-8")
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"test_n": 4, "test_patients": 4, "metrics": {
        "mean_case_macro_dice": 0.7, "per_structure": {"ischaemic_stroke_lesion": {"mean_dice": 0.7}},
        "lesion_detection": {"lesion_sensitivity": 0.8, "lesion_f1": 0.6, "false_positive_components_per_case": 1.5}},
        "clinical_indices": {"ischaemic_stroke_lesion_volume_ml": {"n_patients": 4, "bias": 1.0, "limits_of_agreement": [-2.0, 4.0]}}}), encoding="utf-8")
    card = tmp_path / "card.md"
    card.write_text("# Synthetic test fixture\n", encoding="utf-8")
    model = {"model_id": "fixture_brain", "display_name": "fixture_brain", "task": "volumetric_semantic_segmentation", "status": "READY_UNVALIDATED",
             "validated": False, "research_inference": True, "inference_input": "volume_nifti", "anatomy": "brain",
             "supported_modalities": ["BRAIN_MRI_DIFFUSION"], "supported_classes": [], "limitations": [],
             "artifact_bundle": {"dataset_version": "fixture", "dataset_license": "CC0 (synthetic test fixture)", "split_manifest_path": str(report),
                                 "task_definition": "fixture", "label_definition": {}, "preprocessing_version": SPEC["version"],
                                 "checkpoint_path": str(checkpoint), "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                                 "calibration": None, "decision_thresholds": None, "abstention_thresholds": None, "held_out_predictions_path": str(report),
                                 "evaluation_report_path": str(report), "model_card_path": str(card), "input_envelope_path": str(envelope)}}
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"schema_version": "1.0.0", "models": [model]}), encoding="utf-8")
    monkeypatch.setattr(model_registry, "REGISTRY_PATH", path)
    model_registry._load_registry.cache_clear()
    model_inference._load.cache_clear()
    yield model
    model_registry._load_registry.cache_clear()
    model_inference._load.cache_clear()


def test_brain_research_inference_marks_slices_on_the_upload_grid(client, test_users, brain_registry, tmp_path):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-BRAIN-FIXTURE"}, headers=headers).json()["id"]

    def upload(name, data, zooms=(1.5, 1.5, 3.0)):
        body = _nifti(tmp_path / name, data, zooms).read_bytes()
        response = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (name, body, "application/gzip")},
                               data={"deidentified": "true"}, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    upload_id = upload("brain.nii.gz", _brain())
    run = client.post(f"/api/v1/uploads/{upload_id}/research-inference", json={"model_id": "fixture_brain", "declared_input_type": "BRAIN_MRI_DIFFUSION"}, headers=headers)
    assert run.status_code == 201, run.text
    output = run.json()["research_output"]
    assert output["type"] == "volume_segmentation" and output["volume_shape_ijk"] == [24, 24, 12] and len(output["slices"]) == 12
    assert output["volume_semantics"] == "Fixture lesion volume semantics."
    assert output["held_out_volume_agreement"]["ischaemic_stroke_lesion_volume_ml"]["bias_ml"] == 1.0
    assert run.json()["research_provenance"]["anatomy_system_of_model"] == "brain"

    single = upload("dwi_only.nii.gz", _brain()[..., 0])
    refused = client.post(f"/api/v1/uploads/{single}/research-inference", json={"model_id": "fixture_brain", "declared_input_type": "BRAIN_MRI_DIFFUSION"}, headers=headers)
    assert refused.status_code == 400 and "CHANNEL_COUNT_MISMATCH" in refused.json()["detail"]
    skull = upload("with_skull.nii.gz", _brain(stripped=False))
    refused = client.post(f"/api/v1/uploads/{skull}/research-inference", json={"model_id": "fixture_brain", "declared_input_type": "BRAIN_MRI_DIFFUSION"}, headers=headers)
    assert refused.status_code == 400 and "NONZERO_FRACTION_OUTSIDE_DEVELOPMENT_RANGE" in refused.json()["detail"]

    listed = {item["model_id"]: item for item in client.get("/api/v1/research-models", headers=headers).json()["models"]}
    evaluation = listed["fixture_brain"]["held_out_evaluation"]
    assert evaluation["ischaemic_stroke_lesion_dice"] == 0.7 and evaluation["lesion_f1"] == 0.6


def test_the_trainer_evaluates_through_the_serving_path(tmp_path):
    from ml_training import volumetric_multichannel as trainer

    manifest = trainer.create_synthetic_fixture(tmp_path / "work")
    config = trainer.Config(manifest_path=manifest, output_dir=tmp_path / "work" / "run", model_id="synthetic_smoke", channel_names=("A", "B"),
                            device="cpu", epochs=1, iterations_per_epoch=2, batch_size=2, patch_size=(16, 16, 8), init_filters=8,
                            blocks_down=(1, 1), blocks_up=(1,), validate_every=1, amp=False, workers=0, target_spacing=(2.0, 2.0, 2.0),
                            lesion_detection=True, sw_batch_size=1, allow_synthetic_test_fixture=True)
    result = trainer.run_training(config)
    assert result["execution_status"] == "COMPLETE" and result["held_out_test"]["case_count"] == 2
    assert result["config"]["preprocessing"]["target_spacing_mm"] == [2.0, 2.0, 2.0]
    saved = torch.load(result["checkpoint"]["path"], map_location="cpu", weights_only=True)
    assert saved["trainer_version"] == volume_inference.MULTICHANNEL_TRAINER and saved["channels"] == ["A", "B"]
    detection = result["held_out_test"]["metrics"]["lesion_detection"]
    assert detection["reference_lesions"] >= detection["detected_lesions"] >= 0
    with pytest.raises(PermissionError):
        trainer.run_training(trainer.Config(**{**config.__dict__, "output_dir": tmp_path / "work" / "blocked", "allow_synthetic_test_fixture": False}))


def test_the_trainer_resumes_from_its_last_epoch_after_an_interruption(tmp_path):
    from ml_training import volumetric_multichannel as trainer

    manifest = trainer.create_synthetic_fixture(tmp_path / "work")
    config = trainer.Config(manifest_path=manifest, output_dir=tmp_path / "work" / "run", model_id="synthetic_resume", channel_names=("A", "B"),
                            device="cpu", epochs=2, iterations_per_epoch=2, batch_size=2, patch_size=(16, 16, 8), init_filters=8,
                            blocks_down=(1, 1), blocks_up=(1,), validate_every=1, amp=False, workers=0, sw_batch_size=1,
                            allow_synthetic_test_fixture=True)
    first = trainer.run_training(config)
    resume = torch.load(config.output_dir / "resume.pt", map_location="cpu", weights_only=False)
    assert resume["epoch"] == 2 and len(resume["epoch_records"]) == 2 and "resumed_from_epoch" not in first
    # A restart after the last epoch (e.g. a shutdown during the held-out evaluation) continues from the saved state.
    again = trainer.run_training(config)
    assert again["resumed_from_epoch"] == 2 and [item["epoch"] for item in again["epochs"]] == [1, 2]
    assert again["selection"]["best_epoch"] == first["selection"]["best_epoch"]
    with pytest.raises(SystemExit, match="different settings"):
        trainer.run_training(trainer.Config(**{**config.__dict__, "learning_rate": 1e-3}))
    # A manifest regenerated at the same path does not resume the old state (its content hash differs).
    regenerated = json.loads(manifest.read_text(encoding="utf-8"))
    regenerated["generated_at"] = "2026-11-07T00:00:00+00:00"
    manifest.write_text(json.dumps(regenerated, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="manifest_sha256"):
        trainer.run_training(config)


def test_ct_normalisation_clips_to_the_training_window_and_z_scores():
    spec = {"intensity": volume_inference.CT_INTENSITY, "ct_clip_hu": [-100.0, 300.0], "ct_mean": 100.0, "ct_std": 50.0}
    out = volume_inference.normalise_ct(np.array([[[-1000.0, 100.0, 2000.0]]]), spec)
    assert out.dtype == np.float32 and out.ravel().tolist() == [-4.0, 0.0, 4.0]


def _ct(shape=(24, 24, 12), seed=0):
    """Synthetic CT in Hounsfield units: air outside an ellipsoid 'body' (about 40 HU) with a denser 'organ' (about 120 HU)."""
    rng = np.random.default_rng(seed)
    grid = np.indices(shape)
    centre = [(size - 1) / 2 for size in shape]
    body = sum(((grid[axis] - centre[axis]) / (shape[axis] * 0.45)) ** 2 for axis in range(3)) <= 1
    shift = [seed % 3, (seed // 3) % 3, 0]  # each case its own organ position (identical masks would cross splits)
    organ = sum(((grid[axis] - centre[axis] - shift[axis]) / (shape[axis] * 0.2)) ** 2 for axis in range(3)) <= 1
    data = np.where(body, 40.0, -1000.0) + np.where(organ, 80.0, 0.0) + rng.normal(0, 5, shape)
    return data.astype(np.float32), organ.astype(np.uint8)


CT_ENVELOPE = {**{key: value for key, value in ENVELOPE.items() if key != "nonzero_fraction"}, "channels": ["CT"],
               "hu_percentiles": {"p01": {"min": -1020.0, "max": -980.0}, "p99": {"min": 100.0, "max": 140.0}, "margin_hu": 100.0}}


def test_the_hounsfield_gate_accepts_ct_and_refuses_an_mri_like_volume(tmp_path):
    ct, _ = _ct()
    assert volume_inference.read_volume(_nifti(tmp_path / "ct.nii.gz", ct, zooms=(1.5, 1.5, 3.0)), CT_ENVELOPE).image.shape[-3:] == (24, 24, 12)
    mri = _brain(channels=1)[..., 0]
    with pytest.raises(VolumeInputError) as refused:
        volume_inference.read_volume(_nifti(tmp_path / "mri.nii.gz", mri, zooms=(1.5, 1.5, 3.0)), CT_ENVELOPE)
    assert "INTENSITY_OUTSIDE_CT_DEVELOPMENT_RANGE" in refused.value.codes


def test_the_ct_trainer_takes_its_window_from_the_training_foreground(tmp_path):
    from ml_training import volumetric_multichannel as trainer

    root = tmp_path / "work" / "fixture"
    root.mkdir(parents=True)
    pairs = []
    for index in range(8):
        image, mask = _ct(seed=index)
        _nifti(root / f"ct_{index:02d}_image.nii.gz", image, zooms=(1.5, 1.5, 3.0))
        _nifti(root / f"ct_{index:02d}_mask.nii.gz", mask, zooms=(1.5, 1.5, 3.0))
        pairs.append({"patient_id": f"ct_{index:02d}", "case_id": f"ct_{index:02d}", "image_path": f"ct_{index:02d}_image.nii.gz", "mask_path": f"ct_{index:02d}_mask.nii.gz"})
    manifest = trainer.write_manifest(trainer.build_manifest(
        dataset_id="synthetic-ct-fixture", dataset_root=root, pairs=pairs, labels={0: "background", 1: "fixture_organ"}, seed=7, val_fraction=0.25,
        test_fraction=0.25, discovery={"layout": "GENERATED_SYNTHETIC_TEST_FIXTURE", "generator": trainer.TRAINER_VERSION}, synthetic_test_fixture=True),
        tmp_path / "work" / "manifest.json")
    run_dir = tmp_path / "work" / "run"
    config = trainer.Config(manifest_path=manifest, output_dir=run_dir, model_id="synthetic_ct_smoke", channel_names=("CT",), device="cpu",
                            epochs=1, iterations_per_epoch=2, batch_size=2, patch_size=(16, 16, 8), init_filters=8, blocks_down=(1, 1),
                            blocks_up=(1,), validate_every=1, amp=False, workers=0, sw_batch_size=1, allow_synthetic_test_fixture=True, intensity="ct")
    result = trainer.run_training(config)
    spec = result["config"]["preprocessing"]
    assert result["execution_status"] == "COMPLETE" and spec["intensity"] == volume_inference.CT_INTENSITY and spec["foreground_crop"] is False
    low, high = spec["ct_clip_hu"]
    assert 80 < low < 120 < high < 160 and 100 < spec["ct_mean"] < 140, "window and statistics come from the organ (foreground) voxels"
    envelope = trainer.build_envelope(run_dir, tmp_path / "envelope.json")
    assert "hu_percentiles" in envelope and "nonzero_fraction" not in envelope
    assert envelope["held_out_test_cases"]["accepted_by_gate"] == envelope["held_out_test_cases"]["total"]
