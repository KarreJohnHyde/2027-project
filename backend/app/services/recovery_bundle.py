"""Encrypted, offline SQLite/SQLCipher + managed-upload backup and staged recovery.

Writers must be stopped by the operator. Restore never overwrites a destination.
Keys, models and training datasets are deliberately not bundled with patient data.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tarfile
import tempfile

from app.services.storage_crypto import KeyRing, encrypt_file, file_key_id, iter_plaintext

MAX_RECOVERY_BYTES = 100 * 1024**3


class RecoveryError(ValueError):
    pass


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024**2), b""):
            result.update(chunk)
    return result.hexdigest()


def stream_digest(handle):
    result = hashlib.sha256()
    for block in iter(lambda: handle.read(1024**2), b""):
        result.update(block)
    return result.hexdigest()


def connect_database(path, key=None, *, readonly=False):
    module = sqlite3
    if key:
        from sqlcipher3 import dbapi2
        module = dbapi2
    path = Path(path).resolve()
    connection = module.connect(path.as_uri() + "?mode=ro", uri=True) if readonly else module.connect(str(path))
    if key:
        if not re.fullmatch(r"[a-fA-F0-9]{64}", key):
            connection.close()
            raise RecoveryError("Recovery tooling requires the external 256-bit raw SQLCipher key in hex")
        connection.execute(f"PRAGMA key = \"x'{key}'\"")
    return connection


def check_database(path, key=None):
    try:
        with closing(connect_database(path, key, readonly=True)) as database:
            integrity = database.execute("PRAGMA integrity_check").fetchall()
            if integrity != [("ok",)] or database.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RecoveryError("Restored database integrity or foreign-key check failed")
            return {"integrity_check": "ok", "tables": database.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]}
    except RecoveryError:
        raise
    except Exception as exc:
        raise RecoveryError("Database could not be verified with the supplied external key") from exc


def create_bundle(database_path, upload_root, output, backup_keys: KeyRing, *, database_key=None,
                  writers_stopped=False, allow_plaintext_source=False):
    database_path, upload_root, output = (Path(path).resolve() for path in (database_path, upload_root, output))
    if not writers_stopped:
        raise RecoveryError("Stop API, worker and maintenance writers before taking an offline recovery bundle")
    if output.exists():
        raise RecoveryError("Backup output already exists; existing backups are never overwritten")
    if not database_key and not allow_plaintext_source:
        raise RecoveryError("A SQLCipher source and external database key are required")
    if not backup_keys.enabled or not database_path.is_file() or not upload_root.is_dir():
        raise RecoveryError("Missing backup key, database or upload directory")
    if output.is_relative_to(upload_root) or output == database_path:
        raise RecoveryError("Backup output must be outside its input store")
    files = []
    for path in sorted(upload_root.rglob("*")):
        if path.is_symlink():
            raise RecoveryError("Upload-store links are refused during backup")
        if path.is_file() and ".work" not in path.relative_to(upload_root).parts and not path.name.endswith(".enc-part"):
            if not allow_plaintext_source and file_key_id(path) is None:
                raise RecoveryError("A plaintext upload needs encryption before production backup")
            files.append(path)
    total = database_path.stat().st_size + sum(path.stat().st_size for path in files)
    if total > MAX_RECOVERY_BYTES:
        raise RecoveryError("Recovery bundle exceeds the configured byte budget")
    output.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(output.parent).free < 4 * total + 1024**3:
        raise RecoveryError("Insufficient space for staged, encrypted recovery verification")
    with tempfile.TemporaryDirectory(prefix="medtwin-backup-", dir=output.parent) as temporary:
        work = Path(temporary)
        snapshot = work / "database.db"
        # The destination is keyed before copying: SQLCipher sources do not
        # become plaintext files in a temporary directory.
        with closing(connect_database(database_path, database_key, readonly=True)) as source:
            with closing(connect_database(snapshot, database_key)) as target:
                source.backup(target)
                target.commit()
        db_check = check_database(snapshot, database_key)
        with closing(connect_database(snapshot, database_key, readonly=True)) as database:
            has_upload_table = database.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='uploaded_files'").fetchone()
            if has_upload_table:
                for stored, recorded in database.execute("SELECT stored_filename, file_path FROM uploaded_files"):
                    local = (upload_root / stored).resolve()
                    if Path(stored).name != stored or local.parent != upload_root or Path(recorded).resolve() != local or not local.is_file():
                        raise RecoveryError("Database references an upload that is not present in the local managed store")
        members = {"database.db": snapshot, **{f"uploads/{path.relative_to(upload_root).as_posix()}": path for path in files}}
        manifest = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
                    "database_encryption": "SQLCIPHER" if database_key else "PLAINTEXT_TEST_ONLY",
                    "original_upload_root": str(upload_root), "writers_stopped_attestation": True,
                    "scope": "Database and local managed uploads; keys, model artifacts, training data and remote-only objects excluded.",
                    "files": {name: {"bytes": path.stat().st_size, "sha256": digest(path)} for name, path in members.items()}}
        package = work / "bundle.tar"
        manifest_path = work / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        with tarfile.open(package, "w") as archive:
            archive.add(manifest_path, arcname="manifest.json", recursive=False)
            for name, path in members.items():
                if digest(path) != manifest["files"][name]["sha256"]:
                    raise RecoveryError("A source upload changed while preparing backup")
                archive.add(path, arcname=name, recursive=False)
        with tarfile.open(package, "r:") as archive:
            for name, record in manifest["files"].items():
                with archive.extractfile(name) as source:
                    if stream_digest(source) != record["sha256"]:
                        raise RecoveryError("Packed bytes differ from the checked recovery inventory")
        pending = work / "verified-recovery.enc"
        encrypt_file(package, pending, backup_keys)
        # Authentication is verified before publishing the completed backup.
        for _block in iter_plaintext(pending, backup_keys):
            pass
        pending.replace(output)
    return {"status": "ENCRYPTED_BACKUP_VERIFIED", "files": len(members), "sha256": digest(output),
            "database_check": db_check, "keys_included": False, "requires_original_key_custody": True}


def _safe_member(name):
    value = PurePosixPath(name)
    if value.is_absolute() or ".." in value.parts or "\\" in name or ":" in name:
        raise RecoveryError("Unsafe path in recovery package")
    if name not in {"manifest.json", "database.db"} and not (len(value.parts) > 1 and value.parts[0] == "uploads"):
        raise RecoveryError("Unexpected file in recovery package")
    return value


def restore_bundle(bundle, destination, backup_keys: KeyRing, *, database_key=None):
    destination = Path(destination).resolve()
    if file_key_id(Path(bundle)) is None:
        raise RecoveryError("Recovery requires an authenticated encrypted bundle")
    if destination.exists():
        raise RecoveryError("Restore destination exists; restore always stages into a new directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="medtwin-restore-", dir=destination.parent) as temporary:
        work = Path(temporary)
        package = work / "authenticated.tar"
        count = 0
        with package.open("xb") as handle:
            for block in iter_plaintext(Path(bundle), backup_keys):
                count += len(block)
                if count > MAX_RECOVERY_BYTES:
                    raise RecoveryError("Decrypted recovery package exceeds byte budget")
                if shutil.disk_usage(work).free < len(block) + 1024**3:
                    raise RecoveryError("Storage reserve reached during authenticated recovery")
                handle.write(block)
        staged = work / "staged"
        staged.mkdir()
        with tarfile.open(package, "r:") as archive:
            members = archive.getmembers()
            names = [member.name for member in members]
            if len(names) != len(set(names)) or sum(member.size for member in members) > MAX_RECOVERY_BYTES:
                raise RecoveryError("Duplicate members or excessive expanded recovery size")
            for member in members:
                name = _safe_member(member.name)
                if not member.isfile():
                    raise RecoveryError("Links and special files are refused during recovery")
                target = staged.joinpath(*name.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("xb") as sink:
                    shutil.copyfileobj(source, sink, length=1024**2)
        manifest = json.loads((staged / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1 or set(names) != {"manifest.json", *manifest["files"]}:
            raise RecoveryError("Recovery package inventory differs from its manifest")
        for name, record in manifest["files"].items():
            target = staged.joinpath(*_safe_member(name).parts)
            if target.stat().st_size != record["bytes"] or digest(target) != record["sha256"]:
                raise RecoveryError("Restored file size or checksum mismatch")
        if manifest["database_encryption"] == "SQLCIPHER" and not database_key:
            raise RecoveryError("The external SQLCipher key is needed to verify restored database")
        db_check = check_database(staged / "database.db", database_key)
        staged.rename(destination)
    return {"status": "RESTORED_TO_NEW_STAGING_DIRECTORY", "files": len(manifest["files"]),
            "database_check": db_check, "original_upload_root": manifest["original_upload_root"],
            "activation_required": "Restore the original managed-store mount or separately review database path rebasing before startup."}
