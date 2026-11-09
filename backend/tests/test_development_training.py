"""Real synthetic development run: verify rare-class gradients and no test evaluation."""
from dataclasses import replace
import torch
import pytest

from ml_training import volumetric_multichannel as trainer


def test_weighted_loss_emphasises_the_rare_positive_voxel(tmp_path):
    config = trainer.Config(tmp_path / "manifest", tmp_path / "run", "synthetic", ("CT",), class_weights=(0.1, 1.0, 4.0))
    logits = torch.zeros((1, 3, 2, 2, 2), requires_grad=True)
    masks = torch.zeros((1, 1, 2, 2, 2), dtype=torch.long)
    masks[0, 0, 0, 0, 0] = 2
    loss = trainer.training_loss(config, 3, torch.device("cpu"))(logits, masks)
    loss.backward()
    assert torch.isfinite(loss)
    assert logits.grad[0, :, 0, 0, 0].abs().sum() > logits.grad[0, :, 1, 1, 1].abs().sum()
    with pytest.raises(ValueError):
        trainer.training_loss(replace(config, class_weights=(1, float("nan"), 4)), 3, "cpu")


def test_development_run_never_evaluates_test_patients(tmp_path, monkeypatch):
    manifest = trainer.create_synthetic_fixture(tmp_path / "fixture")
    original = trainer.evaluate
    evaluated_splits = []
    def validation_only(network, payload, cases, *args, **kwargs):
        evaluated_splits.extend(c["split"] for c in cases)
        assert all(c["split"] == "val" for c in cases), "The development run evaluated frozen test patients"
        return original(network, payload, cases, *args, **kwargs)
    monkeypatch.setattr(trainer, "evaluate", validation_only)
    config = trainer.Config(manifest, tmp_path / "run", "synthetic_dev", ("A", "B"), device="cpu", epochs=1,
                            iterations_per_epoch=1, batch_size=2, patch_size=(16, 16, 8), init_filters=8,
                            blocks_down=(1, 1), blocks_up=(1,), validate_every=1, workers=0, amp=False,
                            target_spacing=(2, 2, 2), sw_batch_size=1, class_weights=(0.1, 4),
                            development_only=True, allow_synthetic_test_fixture=True)
    result = trainer.run_training(config)
    assert result["execution_status"] == "DEVELOPMENT_COMPLETE_TEST_NOT_EVALUATED"
    assert result["held_out_test"]["status"] == "NOT_EVALUATED" and evaluated_splits
    assert "validation_per_structure_dice" in result["epochs"][0]
    assert not (tmp_path / "run/held_out_predictions").exists()
