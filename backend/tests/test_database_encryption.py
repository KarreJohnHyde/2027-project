"""SQLCipher encryption of the SQLite database at rest, and the plaintext-to-encrypted copy."""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from app.database import DatabaseKeyError, build_engine, database_key

pytest.importorskip("sqlcipher3")
RAW_KEY = "ab" * 32
MARKER = "SYNTHETIC-DATABASE-MARKER"
ROOT = Path(__file__).resolve().parents[2]


def test_encrypted_engine_writes_no_plaintext_and_needs_the_key(tmp_path):
    path = tmp_path / "medtwin.db"
    engine = build_engine(f"sqlite:///{path.as_posix()}", "sqlcipher", database_key({"MEDTWIN_DB_KEY": RAW_KEY}))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE notes (body TEXT)"))
        connection.execute(text("INSERT INTO notes VALUES (:body)"), {"body": MARKER})
    with engine.connect() as connection:
        assert connection.execute(text("SELECT body FROM notes")).scalar() == MARKER
    engine.dispose()
    stored = b"".join(file.read_bytes() for file in tmp_path.iterdir())
    assert MARKER.encode() not in stored and not path.read_bytes().startswith(b"SQLite format 3")
    wrong = build_engine(f"sqlite:///{path.as_posix()}", "sqlcipher", database_key({"MEDTWIN_DB_KEY": "cd" * 32}))
    with pytest.raises(Exception), wrong.connect() as connection:
        connection.execute(text("SELECT body FROM notes")).scalar()
    wrong.dispose()


def test_key_configuration_is_validated(tmp_path):
    with pytest.raises(DatabaseKeyError):
        database_key({})
    with pytest.raises(DatabaseKeyError):
        database_key({"MEDTWIN_DB_KEY": "short"})
    key_file = tmp_path / "db.key"
    key_file.write_text(RAW_KEY + "\n", encoding="utf-8")
    assert database_key({"MEDTWIN_DB_KEY_FILE": str(key_file)}) == f"x'{RAW_KEY.upper()}'"
    with pytest.raises(DatabaseKeyError):
        build_engine("sqlite:///:memory:", "sqlcipher", "x")
    with pytest.raises(DatabaseKeyError):
        build_engine("sqlite:///x.db", "rot13")


def test_plaintext_database_is_copied_encrypted_and_left_untouched(tmp_path):
    source, target, key_file = tmp_path / "plain.db", tmp_path / "encrypted.db", tmp_path / "keys" / "db.key"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE notes (body TEXT)")
        connection.executemany("INSERT INTO notes VALUES (?)", [(MARKER,), ("second",)])
    before = source.read_bytes()
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "encrypt_database.py"), "--source", str(source), "--target", str(target),
                             "--key-file", str(key_file), "--new-key"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 rows" in result.stdout and source.read_bytes() == before
    assert MARKER.encode() not in target.read_bytes()
    engine = build_engine(f"sqlite:///{target.as_posix()}", "sqlcipher", database_key({"MEDTWIN_DB_KEY_FILE": str(key_file)}))
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM notes")).scalar() == 2
    engine.dispose()
    again = subprocess.run([sys.executable, str(ROOT / "scripts" / "encrypt_database.py"), "--source", str(source), "--target", str(target),
                            "--key-file", str(key_file)], capture_output=True, text=True)
    assert again.returncode != 0 and "already exists" in again.stderr


def test_encrypted_engine_serves_many_threads_at_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    engine = build_engine(f"sqlite:///{(tmp_path / 'medtwin.db').as_posix()}", "sqlcipher", database_key({"MEDTWIN_DB_KEY": RAW_KEY}))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE notes (body TEXT)"))
        connection.execute(text("INSERT INTO notes VALUES ('x')"))

    def read(_):
        with engine.connect() as connection:
            return connection.execute(text("SELECT COUNT(*) FROM notes")).scalar()

    with ThreadPoolExecutor(max_workers=24) as pool:
        assert list(pool.map(read, range(200))) == [1] * 200
    engine.dispose()
