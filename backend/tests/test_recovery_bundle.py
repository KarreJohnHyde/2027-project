"""Real encrypted database/upload round trips; synthetic records only."""
from pathlib import Path
import secrets
import sqlite3

import pytest

from app.services import recovery_bundle as recovery
from app.services.storage_crypto import KeyRing, StorageCryptoError, encrypt_file, key_id_for, read_plaintext


def ring():
    key = secrets.token_bytes(32)
    identity = key_id_for(key)
    return KeyRing({identity: key}, identity)


def fixture_store(tmp_path):
    key = secrets.token_hex(32)
    database = tmp_path / "source.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    upload_keys, backup_keys = ring(), ring()
    original = tmp_path / "synthetic-source.txt"
    original.write_bytes(b"Synthetic recovery fixture, no patient data.")
    encrypt_file(original, uploads / "opaque-object.txt", upload_keys)
    with recovery.connect_database(database, key) as connection:
        connection.execute("CREATE TABLE uploaded_files (stored_filename TEXT, file_path TEXT)")
        connection.execute("INSERT INTO uploaded_files VALUES (?, ?)", ("opaque-object.txt", str(uploads / "opaque-object.txt")))
        connection.commit()
    return database, uploads, key, upload_keys, backup_keys


def test_real_encrypted_database_and_upload_restore_into_new_directory(tmp_path):
    database, uploads, key, upload_keys, backup_keys = fixture_store(tmp_path)
    before = recovery.digest(database)
    bundle = tmp_path / "recovery.enc"
    result = recovery.create_bundle(database, uploads, bundle, backup_keys, database_key=key, writers_stopped=True)
    assert result["keys_included"] is False
    restored = tmp_path / "restored"
    result = recovery.restore_bundle(bundle, restored, backup_keys, database_key=key)
    assert result["database_check"]["integrity_check"] == "ok"
    assert recovery.digest(database) == before
    assert read_plaintext(restored / "uploads/opaque-object.txt", upload_keys) == b"Synthetic recovery fixture, no patient data."
    assert (restored / "database.db").read_bytes()[:16] != b"SQLite format 3\0"
    with pytest.raises(sqlite3.DatabaseError):
        with sqlite3.connect(restored / "database.db") as plain:
            plain.execute("SELECT * FROM uploaded_files").fetchall()
    with pytest.raises(recovery.RecoveryError, match="destination exists"):
        recovery.restore_bundle(bundle, restored, backup_keys, database_key=key)


def test_backup_requires_stopped_writers_and_preserves_existing_bundle(tmp_path):
    database, uploads, key, _, backup_keys = fixture_store(tmp_path)
    output = tmp_path / "existing.enc"
    with pytest.raises(recovery.RecoveryError, match="Stop API"):
        recovery.create_bundle(database, uploads, output, backup_keys, database_key=key)
    output.write_bytes(b"previous backup")
    with pytest.raises(recovery.RecoveryError, match="already exists"):
        recovery.create_bundle(database, uploads, output, backup_keys, database_key=key, writers_stopped=True)
    assert output.read_bytes() == b"previous backup"


def test_wrong_key_or_tampered_archive_never_publishes_restore(tmp_path):
    database, uploads, key, _, backup_keys = fixture_store(tmp_path)
    output = tmp_path / "backup.enc"
    recovery.create_bundle(database, uploads, output, backup_keys, database_key=key, writers_stopped=True)
    destination = tmp_path / "must-not-exist"
    with pytest.raises((StorageCryptoError, recovery.RecoveryError)):
        recovery.restore_bundle(output, destination, ring(), database_key=key)
    assert not destination.exists()
    damaged = bytearray(output.read_bytes())
    damaged[-4] ^= 0x10
    output.write_bytes(damaged)
    with pytest.raises(StorageCryptoError):
        recovery.restore_bundle(output, destination, backup_keys, database_key=key)
    assert not destination.exists()


def test_missing_referenced_object_blocks_backup(tmp_path):
    database, uploads, key, _, backup_keys = fixture_store(tmp_path)
    with recovery.connect_database(database, key) as connection:
        connection.execute("INSERT INTO uploaded_files VALUES (?,?)", ("not-here.txt", str(uploads / "not-here.txt")))
        connection.commit()
    with pytest.raises(recovery.RecoveryError, match="not present"):
        recovery.create_bundle(database, uploads, tmp_path / "no.enc", backup_keys, database_key=key, writers_stopped=True)


@pytest.mark.parametrize("path", ["../outside", "/absolute", "uploads/../../outside", "C:/outside", "uploads\\outside", "secrets/key.json"])
def test_recovery_rejects_unsafe_members(path):
    with pytest.raises(recovery.RecoveryError):
        recovery._safe_member(path)
