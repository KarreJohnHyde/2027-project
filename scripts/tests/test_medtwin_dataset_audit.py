"""Pure stdlib tests: no application conftest, patient storage or ML imports."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("review_audit", ROOT / "scripts/medtwin_dataset_audit.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DatasetAuditTests(unittest.TestCase):
    def test_zero_group_and_patient_overlap_are_not_silently_ignored(self):
        result = module.grouping_summary([{"group_id": 0, "split": "train"}, {"group_id": "0", "split": "test"}])
        self.assertEqual(result["groups_crossing_splits"], 1)
        self.assertEqual(result["rows_without_group"], 0)
        self.assertNotIn("0", result["crossing_group_tokens"])
        self.assertIn("NOT_ESTABLISHED", result["patient_independence"])

    def test_sha_and_path_overlap_do_not_require_matching_patient_ids(self):
        rows = [{"patient_id": "a", "path": "A\\file.png", "image_sha256": "abc", "split": "train"},
                {"patient_id": "b", "path": "a/file.png", "image_sha256": "abc", "split": "test"}]
        result = module.grouping_summary(rows)
        self.assertEqual(result["groups_crossing_splits"], 0)
        self.assertEqual(result["paths_crossing_splits"], 1)
        self.assertEqual(result["recorded_image_sha256_crossing_splits"], 1)

    def test_sampled_checks_report_corruption_missing_and_budget_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "small").write_bytes(b"new")
            (root / "large").write_bytes(b"x" * 8)
            rows = [{"path": "small", "split": "train", "sha256": hashlib.sha256(b"old").hexdigest()},
                    {"path": "large", "split": "test"}, {"path": "missing", "split": "val"}]
            result = module.check_bytes(rows, {}, root=root, sample_per_split=1, byte_budget=5, max_file_bytes=5)
            self.assertEqual(result["hash_mismatches"], 1)
            self.assertEqual(result["missing_selected"], 1)
            self.assertEqual(result["deferred_by_budget"], 1)
            self.assertEqual(result["checked"], 1)

    def test_read_limit_is_explicit_and_validation_alias_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps({"cases": [{"split": "validation"}, {"split": "train"}]}))
            rows, _, truncated = module.read_rows(path, 1)
            self.assertTrue(truncated)
            self.assertEqual(module.grouping_summary(rows)["split_counts"], {"val": 1})

    def test_near_duplicate_results_are_candidates_not_confirmed(self):
        result = module.dhash_candidates([{"path": "a", "split": "train", "dhash": "0000"},
                                         {"path": "b", "split": "test", "dhash": "0001"}], limit=2)
        self.assertEqual(result["candidate_pairs"], 1)
        self.assertFalse(result["pixel_confirmed"])

    def test_ptbxl_publisher_fold_and_checksums_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "ptbxl_database.csv"
            path.write_text("patient_id,strat_fold,filename_lr\np1,1,records/a\np2,9,records/b\np3,10,records/c\n")
            (root / "SHA256SUMS.txt").write_text("abc  records/a.dat\ndef  records/b.dat\nghi  records/c.dat\n")
            rows, metadata, truncated = module.read_rows(path, 100)
            self.assertFalse(truncated)
            self.assertEqual([row["split"] for row in rows], ["train", "val", "test"])
            self.assertEqual(rows[0]["sha256"], "abc")
            self.assertEqual(metadata["dataset_root"], str(root))

    def test_experiment_preparation_is_nonexecuting_and_no_test_command(self):
        experiment_spec = importlib.util.spec_from_file_location("review_experiments", ROOT / "scripts/prepare_review_experiments.py")
        experiments = importlib.util.module_from_spec(experiment_spec)
        experiment_spec.loader.exec_module(experiments)
        result = experiments.prepare(ROOT)
        self.assertFalse(result["training_launched"])
        self.assertEqual(len(result["experiments"]), 6)
        for item in result["experiments"]:
            self.assertFalse(item["execution_allowed"])
            for command in item.get("development_commands", []):
                self.assertIn("--development-only", command["argv"])
                self.assertNotIn("publish", " ".join(command["argv"]))


class DevelopmentTrainerTests(unittest.TestCase):
    """Synthetic control-flow checks; no real-data training or accuracy claims."""

    @classmethod
    def setUpClass(cls):
        import torch
        from ml_training import classify, detect
        cls.torch, cls.classify, cls.detect = torch, classify, detect

    def test_both_trainers_drop_test_and_reject_development_group_leakage(self):
        rows = [{"entry": "a", "split": "train", "group_id": "a"},
                {"entry": "b", "split": "val", "group_id": "b"},
                {"entry": "DO_NOT_OPEN", "split": "test", "group_id": "test"}]
        for trainer in (self.classify, self.detect):
            selected = trainer.development_rows(rows, enabled=True, seed=1)
            self.assertEqual({row["split"] for row in selected}, {"train", "val"})
            with self.assertRaisesRegex(ValueError, "caps"):
                trainer.development_rows(rows, enabled=False, seed=1, max_train=1)
            with self.assertRaisesRegex(ValueError, "leakage"):
                trainer.development_rows([rows[0], dict(rows[1], group_id="a")], enabled=True, seed=1)

    def fixture(self, root):
        (root / "dataset_registry").mkdir()
        registry = {"datasets": [{"id": "synthetic", "title": "Synthetic control flow fixture", "labels": "YOLO",
                     "license": {"name": "SYNTHETIC_TEST_ONLY"}, "tasks": [{"task_id": "fixture", "training_eligible": True,
                     "preparation": {"sample_manifest": "NOT_OPENED.csv", "dataset_version": "fixture-v1"}}]}]}
        (root / "dataset_registry/tasks.json").write_text(json.dumps(registry))
        rows = [{"entry": f"train{i}", "path": f"train{i}.png", "split": "train", "group_id": f"train{i}", "label": str(i % 2)} for i in range(4)]
        rows.extend([{"entry": f"val{i}", "path": f"val{i}.png", "split": "val", "group_id": f"val{i}", "label": str(i)} for i in range(2)])
        rows.append({"entry": "TEST_MUST_NOT_BE_OPENED", "path": "MISSING_TEST.png", "split": "test", "group_id": "test", "label": "TEST_ONLY_LABEL"})
        return rows

    def fake_run(self, root):
        class FakeRun:
            def __init__(self, *args):
                self.directory, self.run_id = root / "run", "synthetic-control-flow"
                self.directory.mkdir()
            def log(self, **values):
                pass
            def save_checkpoint(self, payload):
                assert payload["development_only"] is True
                path = self.directory / "model.pt"
                path.write_bytes(b"SYNTHETIC_CONTROL_FLOW_NOT_A_MODEL")
                return path, "synthetic-not-real-sha"
            def write_json(self, name, payload):
                path = self.directory / name
                path.write_text(json.dumps(payload))
                return path
        return FakeRun

    def test_classifier_development_main_never_evaluates_or_publishes_test(self):
        trainer, torch = self.classify, self.torch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = self.fixture(root)
            model = torch.nn.Linear(1, 2)
            def candidate(*args):
                return model.state_dict(), 0.5, 1
            def logits(model, loader, dev):
                self.assertTrue(all(row["split"] == "val" for row in loader.dataset.rows))
                return trainer.np.array([[1., 0.], [0., 1.]], dtype="float32"), trainer.np.array([0, 1])
            with patch.multiple(trainer, ROOT=root, Run=self.fake_run(root), read_samples=lambda _: rows,
                                enforce_training_license=lambda *args: {"scope": "SYNTHETIC_TEST_ONLY"},
                                device=lambda: torch.device("cpu"), set_seed=lambda _: None,
                                build=lambda *args: model, train_candidate=candidate, logits_for=logits,
                                fit_temperature=lambda *args: 1.0,
                                checkpoint_ref=str, register_model=lambda *args: self.fail("Registry publication occurred"),
                                write_model_card=lambda *args: self.fail("Model card publication occurred")):
                status = trainer.main(["--task-id", "fixture", "--model-id", "synthetic", "--display-name", "Synthetic",
                                       "--modality", "SYNTHETIC", "--anatomy", "fixture", "--development-only", "--epochs", "1",
                                       "--archs", "resnet18", "--batch-size", "2", "--workers", "0"])
            self.assertEqual(status, 0)
            result = json.loads((root / "run/development.json").read_text())
            self.assertNotIn("TEST_ONLY_LABEL", result["classes"])
            self.assertEqual(result["held_out_test"]["status"], "NOT_EVALUATED")
            self.assertFalse(result["model_registry_mutation"])
            self.assertFalse((root / "run/predictions_test.csv").exists())

    def test_detector_development_main_never_loads_or_publishes_test(self):
        from types import SimpleNamespace
        trainer, torch = self.detect, self.torch
        class TinyDetector(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.tensor(1.0))
                self.roi_heads = SimpleNamespace(box_predictor=SimpleNamespace(cls_score=SimpleNamespace(in_features=1)))
            def forward(self, images, targets):
                return {"loss": self.weight.square()}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = self.fixture(root)
            def targets(members, *args):
                self.assertTrue(all(row["split"] in {"train", "val"} for row in members))
                return [dict(row, width=10, height=10, boxes=[[1, 1, 4, 4]]) for row in members]
            def predict(model, items, dev):
                self.assertTrue(all(row["split"] == "val" for row in items))
                return [[] for _ in items]
            class TinySet:
                def __init__(self, items, **kwargs):
                    self.items = items
                def __len__(self):
                    return len(self.items)
                def __getitem__(self, index):
                    return torch.zeros((3, 10, 10)), {"boxes": torch.zeros((0, 4)), "labels": torch.zeros(0, dtype=torch.long)}
            with patch.multiple(trainer, ROOT=root, Run=self.fake_run(root), read_samples=lambda _: rows,
                                enforce_training_license=lambda *args: {"scope": "SYNTHETIC_TEST_ONLY"},
                                device=lambda: torch.device("cpu"), set_seed=lambda _: None,
                                load_targets=targets, fasterrcnn_resnet50_fpn_v2=lambda **kwargs: TinyDetector(),
                                FastRCNNPredictor=lambda *args: torch.nn.Linear(1, 2), DetectionSet=TinySet,
                                predict=predict, score=lambda *args: {"metrics": {"ap_50": 0., "map_50_95": 0.}},
                                checkpoint_ref=str, register_model=lambda *args: self.fail("Registry publication occurred")):
                status = trainer.main(["--task-id", "fixture", "--model-id", "synthetic", "--display-name", "Synthetic",
                                       "--modality", "SYNTHETIC", "--anatomy", "fixture", "--development-only", "--epochs", "1",
                                       "--batch-size", "2", "--workers", "0"])
            self.assertEqual(status, 0)
            result = json.loads((root / "run/development.json").read_text())
            self.assertEqual(result["held_out_test"]["status"], "NOT_EVALUATED")
            self.assertFalse((root / "run/predictions_test.json").exists())

    def test_real_permission_denial_precedes_manifest_and_images(self):
        for trainer in (self.classify, self.detect):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root)
                def refused(*args):
                    raise PermissionError("Synthetic denial fixture")
                with patch.multiple(trainer, ROOT=root, enforce_training_license=refused,
                                    read_samples=lambda *args: self.fail("Data loaded before permission gate")):
                    with self.assertRaisesRegex(PermissionError, "denial"):
                        trainer.main(["--task-id", "fixture", "--model-id", "synthetic", "--display-name", "Synthetic",
                                      "--modality", "SYNTHETIC", "--anatomy", "fixture", "--development-only"])


if __name__ == "__main__":
    unittest.main()
