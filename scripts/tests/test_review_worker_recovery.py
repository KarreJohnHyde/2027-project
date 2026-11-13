"""Real isolated process recovery and pre-import isolation refusal tests."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("review_worker_recovery", ROOT / "scripts/review_worker_recovery.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WorkerRecoveryTests(unittest.TestCase):
    def test_actual_child_crash_reclaims_same_job_and_persists_one_result(self):
        result = module.exercise()
        self.assertEqual(result["status"], "VERIFIED", result)
        self.assertEqual([step["exit_code"] for step in result["steps"]], [0, 73, 0, 0])
        self.assertTrue(all(result["checks"].values()))
        self.assertFalse(result["application_or_qa_database_accessed"])

    def test_existing_workspace_is_refused_before_application_import(self):
        with self.assertRaisesRegex(ValueError, "temporary workspace"):
            module.validate_workspace(ROOT, "not-a-marker")

    def test_marker_and_inherited_database_settings_cannot_redirect_test(self):
        with tempfile.TemporaryDirectory(prefix="medtwin-worker-review-") as directory:
            root = Path(directory)
            (root / module.MARKER).write_text("fixture", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "marker"):
                module.isolated_environment(root, "wrong-marker")
            with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///D:/project/backend/medtwin.db", "MEDTWIN_DB_ENCRYPTION": "sqlcipher",
                                         "MEDTWIN_DB_KEY_FILE": "real-key-must-not-be-read"}):
                env = module.isolated_environment(root, "fixture")
            self.assertEqual(env["DATABASE_URL"], f"sqlite:///{(root / 'recovery.db').as_posix()}")
            self.assertEqual(env["MEDTWIN_DB_ENCRYPTION"], "off")
            self.assertNotIn("MEDTWIN_DB_KEY_FILE", env)


if __name__ == "__main__":
    unittest.main()
