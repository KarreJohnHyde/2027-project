"""
Pytest configuration and test fixtures for MedTwin Backend.
Uses an isolated in-memory SQLite database for deterministic testing.
"""

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import Base, get_db
from app.main import app
from app.models.entities import User, UserRole, Case, Examination, UploadedFile, ModalityType
from app.services.auth import get_password_hash, create_access_token

# Test database engine
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


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
        is_active=True
    )
    clinician_a = User(
        username="clinician_a",
        email="clinician_a@test.medtwin",
        hashed_password=get_password_hash("ClinicianPass1!"),
        full_name="Dr. Alice Smith",
        role=UserRole.CLINICIAN,
        is_active=True
    )
    clinician_b = User(
        username="clinician_b",
        email="clinician_b@test.medtwin",
        hashed_password=get_password_hash("ClinicianPass2!"),
        full_name="Dr. Bob Jones",
        role=UserRole.CLINICIAN,
        is_active=True
    )
    db_session.add_all([admin, clinician_a, clinician_b])
    db_session.commit()
    return {"admin": admin, "clinician_a": clinician_a, "clinician_b": clinician_b}


def get_auth_headers(user: User) -> dict:
    token = create_access_token({"sub": user.username, "role": user.role.value, "user_id": user.id})
    return {"Authorization": f"Bearer {token}"}
