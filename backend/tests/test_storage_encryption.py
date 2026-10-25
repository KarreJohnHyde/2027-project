"""Encryption at rest: round trips, tamper detection, key handling and API integration.

All payloads are synthetic test fixtures."""

import io
import os
import secrets
from pathlib import Path

import pytest

from app.services import upload_store
from app.services.storage_crypto import (
    HEADER,
    KeyRing,
    StorageCryptoError,
    StorageKeyError,
    encrypt_file,
    encrypt_stream,
    generate_key,
    is_encrypted,
    key_id_for,
    load_keyring,
    plaintext_path,
    read_plaintext,
)
from tests.conftest import get_auth_headers

CHUNK = 64


def ring(*encoded: str) -> KeyRing:
    return load_keyring({"MEDTWIN_STORAGE_KEYS": ",".join(encoded)})


def sealed(tmp_path: Path, data: bytes, keys: KeyRing, name: str = "blob.bin") -> Path:
    plain = tmp_path / f"{name}.plain"
    plain.write_bytes(data)
    target = tmp_path / name
    encrypt_file(plain, target, keys, chunk_size=CHUNK)
    return target


@pytest.mark.parametrize("size", [0, 1, CHUNK - 1, CHUNK, CHUNK + 1, 3 * CHUNK + 5])
def test_round_trip_preserves_every_byte(tmp_path, size):
    keys = ring(generate_key())
    data = os.urandom(size)
    target = sealed(tmp_path, data, keys)
    assert is_encrypted(target)
    assert read_plaintext(target, keys) == data
    assert target.stat().st_size == HEADER.size + size + 16 * max(1, -(-size // CHUNK))


def corrupt(path: Path, offset: int) -> None:
    data = bytearray(path.read_bytes())
    data[offset] ^= 0x01
    path.write_bytes(bytes(data))


def test_any_modification_truncation_or_reordering_is_rejected(tmp_path):
    keys = ring(generate_key())
    data = os.urandom(3 * CHUNK + 5)
    for name, damage in {
        "body": lambda p: corrupt(p, HEADER.size + 10),
        "header-size": lambda p: corrupt(p, HEADER.size - 1),
        "header-nonce": lambda p: corrupt(p, 15),
        "tag": lambda p: corrupt(p, p.stat().st_size - 1),
        "truncated": lambda p: p.write_bytes(p.read_bytes()[:-20]),
        "appended": lambda p: p.write_bytes(p.read_bytes() + b"x"),
    }.items():
        target = sealed(tmp_path, data, keys, name=name)
        damage(target)
        with pytest.raises(StorageCryptoError):
            read_plaintext(target, keys)
    # Swapping two equal-length chunks breaks the position binding.
    target = sealed(tmp_path, data, keys, name="swapped")
    raw = bytearray(target.read_bytes())
    first = slice(HEADER.size, HEADER.size + CHUNK + 16)
    second = slice(HEADER.size + CHUNK + 16, HEADER.size + 2 * (CHUNK + 16))
    raw[first], raw[second] = raw[second], raw[first]
    target.write_bytes(bytes(raw))
    with pytest.raises(StorageCryptoError):
        read_plaintext(target, keys)


def test_unknown_key_and_missing_configuration_are_typed(tmp_path):
    target = sealed(tmp_path, b"fixture", ring(generate_key()))
    with pytest.raises(StorageKeyError):
        read_plaintext(target, ring(generate_key()))
    with pytest.raises(StorageKeyError):
        encrypt_stream(io.BytesIO(b"x"), io.BytesIO(), 1, KeyRing(keys={}, active_id=None))


def test_rotation_keeps_old_files_readable_and_writes_with_the_new_key(tmp_path):
    old, new = generate_key(), generate_key()
    before = sealed(tmp_path, b"written before rotation", ring(old), "before")
    rotated = ring(new, old)
    assert read_plaintext(before, rotated) == b"written before rotation"
    after = sealed(tmp_path, b"written after rotation", rotated, "after")
    assert after.read_bytes()[6:14] == key_id_for(__import__("base64").b64decode(new))


def test_reencrypt_in_place_handles_legacy_and_rotated_files(tmp_path):
    from app.services.storage_crypto import file_key_id, reencrypt_in_place

    old, new = generate_key(), generate_key()
    legacy = tmp_path / "legacy.bin"
    legacy.write_bytes(os.urandom(3 * CHUNK + 7))
    legacy_bytes = legacy.read_bytes()
    rotated = sealed(tmp_path, os.urandom(2 * CHUNK), ring(old), "rotated.bin")
    rotated_bytes = read_plaintext(rotated, ring(old))
    keys = ring(new, old)
    reencrypt_in_place(legacy, keys, chunk_size=CHUNK)
    reencrypt_in_place(rotated, keys, chunk_size=CHUNK)
    assert file_key_id(legacy) == file_key_id(rotated) == keys.active_id
    assert read_plaintext(legacy, ring(new)) == legacy_bytes and read_plaintext(rotated, ring(new)) == rotated_bytes
    assert not list(tmp_path.glob("*.enc-part"))
    with pytest.raises(StorageKeyError):
        reencrypt_in_place(legacy, KeyRing(keys={}, active_id=None))


def test_storage_keys_cli_is_a_dry_run_unless_applied(tmp_path, monkeypatch, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location("storage_keys", Path(__file__).resolve().parents[2] / "scripts" / "storage_keys.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    old, new = generate_key(), generate_key()
    (tmp_path / "a.png").write_bytes(b"legacy upload fixture")
    sealed(tmp_path, b"older key fixture", ring(old), "b.dcm")
    (tmp_path / "b.dcm.plain").unlink()  # the helper's plaintext source is not a stored upload
    (tmp_path / ".work").mkdir()
    (tmp_path / ".work" / "scratch.bin").write_bytes(b"never touched")
    monkeypatch.setenv("MEDTWIN_STORAGE_KEYS", f"{new},{old}")
    monkeypatch.delenv("MEDTWIN_STORAGE_KEY_FILE", raising=False)
    def snapshot():
        return {path.name: path.read_bytes() for path in tmp_path.iterdir() if path.is_file()}

    before = snapshot()
    assert cli.main(["rotate", "--upload-dir", str(tmp_path)]) == 0
    assert snapshot() == before, "dry run changes nothing"
    assert cli.main(["rotate", "--upload-dir", str(tmp_path), "--apply"]) == 0
    groups = cli.classify(cli.stored_files(tmp_path), ring(new, old))
    assert len(groups["active_key"]) == 2 and not groups["plaintext"] and not groups["other_known_key"]
    assert (tmp_path / ".work" / "scratch.bin").read_bytes() == b"never touched"
    assert "rewritten" in capsys.readouterr().out


def test_plaintext_copies_exist_only_inside_the_block(tmp_path):
    keys = ring(generate_key())
    target = sealed(tmp_path, b"volume fixture", keys, "scan.nii.gz")
    work = tmp_path / "work"
    with plaintext_path(target, keys, work) as plain:
        assert plain.name == "scan.nii.gz" and plain.read_bytes() == b"volume fixture"
    assert not any(work.iterdir())
    legacy = tmp_path / "legacy.txt"
    legacy.write_bytes(b"plaintext legacy upload")
    with plaintext_path(legacy, keys, work) as plain:
        assert plain == legacy


@pytest.fixture
def encrypted_storage(monkeypatch):
    monkeypatch.setenv("MEDTWIN_STORAGE_KEYS", generate_key())
    monkeypatch.setenv("MEDTWIN_STORAGE_ENCRYPTION", "required")
    upload_store.reset()
    yield
    upload_store.reset()


def test_uploads_are_encrypted_on_disk_and_every_reader_still_works(client, test_users, db_session, encrypted_storage):
    from app.models.entities import UploadedFile

    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-ENCRYPTED"}, headers=headers).json()["id"]
    marker = f"FIXTURE-{secrets.token_hex(6)}"
    report = f"Synthetic test report {marker}. Creatinine 1.1 mg/dL. No evidence of pneumothorax.".encode()
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("enc.txt", report, "text/plain")},
                         data={"deidentified": "true"}, headers=headers).json()
    assert upload["is_associated"] is True, upload
    stored = Path(db_session.get(UploadedFile, upload["id"]).file_path)
    assert is_encrypted(stored)
    assert marker.encode() not in stored.read_bytes()
    job = client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=headers)
    assert job.status_code == 201, job.text
    measurements = client.get(f"/api/v1/cases/{case_id}/measurements", headers=headers).json()
    assert [m["name"] for m in measurements] == ["creatinine"]
    assert marker in client.get(f"/api/v1/uploads/{upload['id']}/text", headers=headers).json()["text"]
    assert client.get(f"/api/v1/uploads/{upload['id']}/content", headers=headers).content == report
    assert not any(upload_store.work_dir().glob("*/*")), "decrypted copies must not outlive the request"
    readiness = client.get("/api/v1/system/readiness").json()["checks"]["storage_encryption"]
    assert readiness["ready"] and readiness["encryption_active"] and readiness["mode"] == "required"


def test_encrypted_dicom_still_renders(client, test_users, encrypted_storage):
    from tests.test_medtwin2_capabilities import _dicom_bytes

    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-ENC-DICOM"}, headers=headers).json()["id"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (f"{secrets.token_hex(4)}.dcm", _dicom_bytes(), "application/dicom")},
                         data={"deidentified": "true"}, headers=headers)
    assert upload.status_code == 201, upload.text
    rendered = client.get(f"/api/v1/uploads/{upload.json()['id']}/imaging/render", headers=headers)
    assert rendered.status_code == 200 and rendered.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_required_mode_without_a_key_refuses_to_store(client, test_users, monkeypatch):
    monkeypatch.delenv("MEDTWIN_STORAGE_KEYS", raising=False)
    monkeypatch.delenv("MEDTWIN_STORAGE_KEY_FILE", raising=False)
    monkeypatch.setenv("MEDTWIN_STORAGE_ENCRYPTION", "required")
    upload_store.reset()
    try:
        headers = get_auth_headers(test_users["clinician_a"])
        case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-NO-KEY"}, headers=headers).json()["id"]
        response = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (f"{secrets.token_hex(4)}.txt", b"fixture text", "text/plain")},
                               data={"deidentified": "true"}, headers=headers)
        assert response.status_code == 503
        readiness = client.get("/api/v1/system/readiness").json()
        assert readiness["ready"] is False and readiness["checks"]["storage_encryption"]["ready"] is False
    finally:
        upload_store.reset()
