"""Behaviour on serverless hosts (Vercel): read-only code, a proxy in front, no ML stack."""

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

from starlette.requests import Request

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_read_only_code_directory_keeps_state_in_the_temp_directory(monkeypatch, tmp_path):
    from app import config

    monkeypatch.setattr(config.os, "access", lambda path, mode: False)
    assert config.default_state_dir(tmp_path) == Path(tempfile.gettempdir()) / "medtwin"
    monkeypatch.setattr(config.os, "access", lambda path, mode: True)
    assert config.default_state_dir(tmp_path) == tmp_path


def test_rate_limit_key_trusts_the_forwarded_client_only_on_vercel(monkeypatch):
    from app.security import client_address

    scope = {"type": "http", "headers": [(b"x-forwarded-for", b"203.0.113.7, 10.0.0.1")], "client": ("10.0.0.1", 4321)}
    monkeypatch.delenv("VERCEL", raising=False)
    assert client_address(Request(scope)) == "10.0.0.1"
    monkeypatch.setenv("VERCEL", "1")
    assert client_address(Request(scope)) == "203.0.113.7"


def test_vercel_git_commit_is_recorded_when_none_is_configured(monkeypatch):
    from app.services.build_info import code_revision

    monkeypatch.delenv("MEDTWIN_CODE_COMMIT", raising=False)
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "0123abc")
    assert code_revision() == {"commit": "0123abc", "source": "VERCEL_GIT_COMMIT_SHA", "working_tree_clean": None}


def test_generated_evidence_is_read_below_the_project_root():
    from app.config import PROJECT_ROOT
    from app.services import dataset_registry

    assert dataset_registry.DEFAULT_DATASET_REGISTRY_PATH == PROJECT_ROOT / "dataset_registry" / "datasets.json"
    assert dataset_registry.DEFAULT_DATASET_TASK_AUDIT_PATH == PROJECT_ROOT / "dataset_registry" / "tasks.json"


def test_api_starts_and_answers_without_the_ml_stack(tmp_path):
    """requirements.txt alone (no PyTorch, torchvision or MONAI) must serve the API; research
    models then report the missing dependency instead of the process failing to import."""
    script = textwrap.dedent(
        """
        import importlib.abc
        import sys
        from pathlib import Path


        class Absent(importlib.abc.MetaPathFinder):
            # Behaves as if the ML stack were not installed, as on a slim install.
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in {"torch", "torchvision", "monai"}:
                    raise ModuleNotFoundError(f"No module named {name!r}", name=name)
                return None


        sys.meta_path.insert(0, Absent())
        from fastapi.testclient import TestClient
        from PIL import Image
        from app.main import app
        from app.services.image_processor import analyze_medical_image

        with TestClient(app) as client:
            health = client.get("/api/v1/system/health").json()
            ready = client.get("/api/v1/system/readiness").json()
        image = Path(sys.argv[1])
        Image.new("RGB", (64, 48), "gray").save(image)
        shape = analyze_medical_image(image, "fixture-hash")["provenance"]["preprocessed_shape"]
        print(health["cuda_available"], health["temporary_storage"], ready["checks"]["database"]["ready"], shape)
        """
    )
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'slim.db').as_posix()}",
        "UPLOAD_DIR": str(tmp_path / "uploads"),
    }
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "fixture.png")],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=300,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    assert completed.stdout.strip().splitlines()[-1] == "False False True [1, 3, 224, 224]"


def test_vercel_manifest_keeps_the_requirements_pins_and_its_lock_is_current():
    import re
    import tomllib

    def name(requirement):
        return re.split(r"[\[=<>]", requirement, maxsplit=1)[0].strip().lower().replace("_", "-")

    requirements = [line.strip() for line in (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
                    if re.match(r"^[A-Za-z0-9_.\[\]-]+==", line.strip())]
    declared = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    assert set(declared) - set(requirements) == {"opencv-python-headless==5.0.0.93", "vercel-blob==0.5.0"}
    assert set(requirements) <= set(declared)
    lock = tomllib.loads((BACKEND_DIR / "uv.lock").read_text(encoding="utf-8"))
    root = next(package for package in lock["package"] if package["name"] == "medtwin-backend")
    assert {(item["name"], item["specifier"]) for item in root["metadata"]["requires-dist"]} == {
        (name(requirement), "==" + requirement.split("==")[1]) for requirement in declared
    }, "regenerate backend/uv.lock with `uv lock`"
    # RapidOCR's GUI OpenCV is never installed; the headless wheel provides cv2 without libGL.
    assert lock["manifest"]["overrides"] == [{"name": "opencv-python", "marker": "sys_platform == 'never'"}]


def test_vercel_build_stages_the_evidence_the_api_reads(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("vercel_build", BACKEND_DIR / "vercel_build.py")
    vercel_build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vercel_build)
    staged_root = tmp_path / "deployment_files"
    vercel_build.stage(staged_root)
    assert not list(staged_root.rglob("public"))  # Vercel drops any public/ directory from function bundles
    script = textwrap.dedent(
        """
        from fastapi.testclient import TestClient
        from app.config import ANATOMY_MANIFEST_PATH, PROJECT_ROOT
        from app.main import app

        with TestClient(app) as client:
            ready = client.get("/api/v1/system/readiness").json()["checks"]
        print(PROJECT_ROOT.name, ANATOMY_MANIFEST_PATH.parent.name, ready["model_registry"]["models"], ready["anatomy_manifest"]["ready"])
        """
    )
    env = {**os.environ, "ENVIRONMENT": "test", "MEDTWIN_PROJECT_ROOT": str(staged_root),
           "DATABASE_URL": f"sqlite:///{(tmp_path / 'staged.db').as_posix()}", "UPLOAD_DIR": str(tmp_path / "uploads")}
    for variable in ("MODEL_REGISTRY_PATH", "DATASET_REGISTRY_PATH", "DATASET_TASK_AUDIT_PATH", "ANATOMY_MANIFEST_PATH"):
        env.pop(variable, None)
    completed = subprocess.run([sys.executable, "-c", script], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=300)
    assert completed.returncode == 0, completed.stderr[-3000:]
    root, manifest_dir, models, manifest_ready = completed.stdout.strip().splitlines()[-1].split()
    assert (root, manifest_dir, manifest_ready) == ("deployment_files", "anatomy", "True") and int(models) > 0
    for path in ("dataset_registry/tasks.json", "docs/research/traceability.json", "docs/validation/models", "benchmarks/results"):
        assert (staged_root / path).exists(), path


def test_operator_provisions_and_verifies_professional_accounts():
    import secrets

    import pytest

    from app.database import SessionLocal
    from app.models.entities import User, UserRole, VerificationStatus
    from app.provision import provision
    from app.services.auth import get_password_hash, verify_password

    username, password = f"prov_{secrets.token_hex(4)}", secrets.token_urlsafe(16)
    with pytest.raises(SystemExit):
        provision(username, f"{username}@example.invalid", UserRole.CLINICIAN, password="short")
    assert provision(username, f"{username}@example.invalid", UserRole.CLINICIAN, password=password) == "PROFESSIONAL_ACCOUNT_PROVISIONED"

    public = f"pub_{secrets.token_hex(4)}"
    with SessionLocal() as db:  # a self-registered public account already in the deployment's database
        db.add(User(username=public, email=f"{public}@example.invalid", hashed_password=get_password_hash(password),
                    role=UserRole.PUBLIC, verification_status=VerificationStatus.UNVERIFIED, is_active=True))
        db.commit()
    assert provision(public, f"{public}@example.invalid", UserRole.RESEARCHER) == "PROFESSIONAL_ACCOUNT_VERIFIED"
    with pytest.raises(SystemExit):
        provision(public, "someone-else@example.invalid", UserRole.ADMIN)
    with SessionLocal() as db:
        created = db.query(User).filter(User.username == username).one()
        promoted = db.query(User).filter(User.username == public).one()
        assert (created.role, created.verification_status) == (UserRole.CLINICIAN, VerificationStatus.VERIFIED)
        assert verify_password(password, created.hashed_password) and verify_password(password, promoted.hashed_password)
        assert (promoted.role, promoted.verification_status) == (UserRole.RESEARCHER, VerificationStatus.VERIFIED)
