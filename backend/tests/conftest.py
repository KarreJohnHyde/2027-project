"""
Pytest configuration and test fixtures for MedTwin Backend.
Uses an isolated in-memory SQLite database for deterministic testing.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Configure all process-global application state before importing ``app``.
# A request dependency override alone is insufficient: TestClient runs the app
# lifespan, and some tests/workers import SessionLocal directly.  Both must be
# bound to disposable test storage rather than backend/medtwin.db.
_test_runtime = tempfile.TemporaryDirectory(prefix="medtwin-pytest-")
TEST_RUNTIME_DIR = Path(_test_runtime.name).resolve()
TEST_DATABASE_PATH = TEST_RUNTIME_DIR / "medtwin-test.db"
TEST_UPLOAD_DIR = TEST_RUNTIME_DIR / "uploads"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEV_SEED_ENABLED"] = "false"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
os.environ["UPLOAD_DIR"] = str(TEST_UPLOAD_DIR)
os.environ["MEDTWIN_STORAGE_ENCRYPTION"] = "off"
os.environ.pop("MEDTWIN_STORAGE_KEY_FILE", None)
os.environ.pop("MEDTWIN_STORAGE_KEYS", None)

from app.database import Base, SessionLocal as TestingSessionLocal, engine as test_engine, get_db
from app.main import app
from app.models.entities import (
    Case,
    Examination,
    ModalityType,
    UploadedFile,
    User,
    UserRole,
    VerificationStatus,
)
from app.services.auth import get_password_hash, create_access_token


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    configured_database = Path(test_engine.url.database or "").resolve()
    development_database = (backend_dir / "medtwin.db").resolve()
    if configured_database != TEST_DATABASE_PATH or configured_database == development_database:
        raise RuntimeError(
            "Pytest database isolation failed: refusing to run against a non-temporary database."
        )

    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    _test_runtime.cleanup()


@pytest.fixture
def db_session():
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_users(db_session):
    """Creates a set of test users with different roles."""
    admin = User(
        username="test_admin",
        email="admin@test.medtwin",
        hashed_password=get_password_hash("AdminSecret123!"),
        full_name="Dr. Admin",
        role=UserRole.ADMIN,
        verification_status=VerificationStatus.VERIFIED,
        is_active=True
    )
    clinician_a = User(
        username="clinician_a",
        email="clinician_a@test.medtwin",
        hashed_password=get_password_hash("ClinicianPass1!"),
        full_name="Dr. Alice Smith",
        role=UserRole.CLINICIAN,
        verification_status=VerificationStatus.VERIFIED,
        is_active=True
    )
    clinician_b = User(
        username="clinician_b",
        email="clinician_b@test.medtwin",
        hashed_password=get_password_hash("ClinicianPass2!"),
        full_name="Dr. Bob Jones",
        role=UserRole.CLINICIAN,
        verification_status=VerificationStatus.VERIFIED,
        is_active=True
    )
    db_session.add_all([admin, clinician_a, clinician_b])
    db_session.commit()
    return {"admin": admin, "clinician_a": clinician_a, "clinician_b": clinician_b}


def get_auth_headers(user: User) -> dict:
    token = create_access_token({"sub": user.username, "role": user.role.value, "user_id": user.id})
    return {"Authorization": f"Bearer {token}"}
