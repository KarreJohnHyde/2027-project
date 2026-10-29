"""Uploads survive the loss of an instance's files when an object store keeps durable copies,
as on Vercel with a private Blob store. An in-memory fake stands in for Vercel Blob."""

import secrets
import types
from pathlib import Path

import pytest

from app.config import normalise_database_url
from app.services import object_store, upload_store
from app.services.storage_crypto import generate_key, is_encrypted
from tests.conftest import get_auth_headers


class FakeBlobStore:
    """The parts of vercel.blob.sync that object_store uses, held in memory."""

    class BlobNotFoundError(Exception):
        pass

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_blob(self, pathname, body, *, access, content_length=None, content_type=None, allow_overwrite=False, **_):
        assert access == "private"
        if pathname in self.objects and not allow_overwrite:
            raise RuntimeError("pathname exists")
        self.objects[pathname] = body.read() if hasattr(body, "read") else bytes(body)

    def get_blob(self, pathname, *, access):
        assert access == "private"
        if pathname not in self.objects:
            raise self.BlobNotFoundError(pathname)
        return types.SimpleNamespace(body=self.objects[pathname])

    def delete_blob(self, pathname, **_):
        self.objects.pop(pathname, None)


@pytest.fixture
def blob_store(monkeypatch):
    store = FakeBlobStore()
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "test-only-token")
    monkeypatch.setattr(object_store, "_client", lambda: store)
    yield store


@pytest.fixture
def storage_key(monkeypatch):
    monkeypatch.setenv("MEDTWIN_STORAGE_KEYS", generate_key())
    monkeypatch.setenv("MEDTWIN_STORAGE_ENCRYPTION", "required")
    upload_store.reset()
    yield
    upload_store.reset()


def _case(client, headers, pseudonym):
    return client.post("/api/v1/cases", json={"pseudonymous_id": pseudonym}, headers=headers).json()["id"]


def test_an_upload_is_read_back_after_the_instance_lost_its_files(client, test_users, db_session, blob_store, storage_key):
    from app.models.entities import UploadedFile

    headers = get_auth_headers(test_users["clinician_a"])
    case_id = _case(client, headers, "CASE-DURABLE")
    report = f"Synthetic test report {secrets.token_hex(6)}. Creatinine 1.1 mg/dL.".encode()
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("durable.txt", report, "text/plain")},
                         data={"deidentified": "true"}, headers=headers).json()
    stored = Path(db_session.get(UploadedFile, upload["id"]).file_path)
    assert is_encrypted(stored) and blob_store.objects[object_store.PREFIX + stored.name] == stored.read_bytes()
    stored.unlink()  # a new serverless instance has none of the previous instance's files
    assert client.get(f"/api/v1/uploads/{upload['id']}/content", headers=headers).content == report
    assert stored.exists()
    stored.unlink()
    job = client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=headers)
    assert job.status_code == 201, job.text
    assert [m["name"] for m in client.get(f"/api/v1/cases/{case_id}/measurements", headers=headers).json()] == ["creatinine"]
    checks = client.get("/api/v1/system/readiness").json()["checks"]["upload_storage"]
    assert checks["durable_copies"] == "OBJECT_STORE" and checks["temporary"] is False


def test_durable_storage_refuses_unencrypted_uploads(client, test_users, blob_store, monkeypatch):
    monkeypatch.delenv("MEDTWIN_STORAGE_KEYS", raising=False)
    upload_store.reset()
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = _case(client, headers, "CASE-DURABLE-PLAIN")
    response = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("plain.txt", b"Synthetic note.", "text/plain")},
                           data={"deidentified": "true"}, headers=headers)
    assert response.status_code == 503 and "encrypted uploads only" in response.json()["detail"]
    assert blob_store.objects == {}


def test_erasing_an_object_removes_its_durable_copy(tmp_path, monkeypatch, blob_store, storage_key):
    from app import config

    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path)
    target, incoming = tmp_path / "abc.txt", tmp_path / ".incoming.part"
    incoming.write_bytes(b"synthetic")
    upload_store.store(incoming, target)
    target.unlink()  # erased by an instance that never held the local copy
    assert upload_store.delete_managed_file(target, "abc.txt") is True
    assert blob_store.objects == {} and not target.exists()


def test_hosted_postgres_urls_name_the_installed_driver():
    assert normalise_database_url("postgres://u:p@host/db?sslmode=require") == "postgresql+psycopg://u:p@host/db?sslmode=require"
    assert normalise_database_url("postgresql://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    assert normalise_database_url("postgresql+psycopg://u@h/d") == "postgresql+psycopg://u@h/d"
    assert normalise_database_url("sqlite:///x.db") == "sqlite:///x.db"
