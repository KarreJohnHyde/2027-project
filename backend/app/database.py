"""
Database initialization and session management for MedTwin.
Supports SQLite (with WAL & foreign key enforcement), SQLCipher-encrypted SQLite and PostgreSQL.

Encryption at rest of the database (MEDTWIN_DB_ENCRYPTION):
  off        plain SQLite or PostgreSQL (PostgreSQL relies on encrypted storage underneath)
  sqlcipher  the whole SQLite file, including its write-ahead log, is AES-256 encrypted by
             SQLCipher. The key comes from MEDTWIN_DB_KEY_FILE (preferred) or MEDTWIN_DB_KEY:
             64 hex characters are used as a raw 256-bit key; anything else is a passphrase
             (PBKDF2 key derivation, slower per connection). Keys never live in the repository.
A plaintext database is converted with scripts/encrypt_database.py, which writes an encrypted
copy and never deletes the original.
"""

import os
import re
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.pool import QueuePool
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import DATABASE_URL

DATABASE_ENCRYPTION_MODES = {"off", "sqlcipher"}
_RAW_KEY = re.compile(r"[0-9a-fA-F]{64}")


class DatabaseKeyError(RuntimeError):
    """Encrypted-database configuration is missing or invalid."""


def database_key(environ=os.environ) -> str:
    """The SQLCipher key from MEDTWIN_DB_KEY_FILE or MEDTWIN_DB_KEY, as the PRAGMA key argument."""
    key_file = environ.get("MEDTWIN_DB_KEY_FILE", "").strip()
    secret = Path(key_file).read_text(encoding="utf-8").strip() if key_file else environ.get("MEDTWIN_DB_KEY", "").strip()
    if not secret:
        raise DatabaseKeyError("MEDTWIN_DB_ENCRYPTION=sqlcipher needs MEDTWIN_DB_KEY_FILE or MEDTWIN_DB_KEY.")
    if _RAW_KEY.fullmatch(secret):
        return f"x'{secret.upper()}'"
    if len(secret) < 16:
        raise DatabaseKeyError("A database passphrase must be at least 16 characters (or use a 64-hex-character raw key).")
    return secret


def build_engine(url: str, encryption: str = "off", key: Optional[str] = None) -> Engine:
    if encryption not in DATABASE_ENCRYPTION_MODES:
        raise DatabaseKeyError(f"MEDTWIN_DB_ENCRYPTION must be one of {sorted(DATABASE_ENCRYPTION_MODES)}.")
    connect_args = {}
    options: dict = {}
    target: "str | URL" = url
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    if encryption == "sqlcipher":
        if not url.startswith("sqlite:///") or url.endswith(":memory:"):
            raise DatabaseKeyError("SQLCipher encryption needs a file-backed SQLite DATABASE_URL (sqlite:///path).")
        # The dialect issues PRAGMA key with this password before any other statement.
        target = URL.create("sqlite+pysqlcipher", password=key, database=url[len("sqlite:///"):])
        # The dialect defaults to SingletonThreadPool, which closes other threads' connections once more
        # threads than pool_size are active (the API serves requests from a thread pool). A queue pool,
        # as for plain file SQLite, keeps each connection with one request; every new connection is keyed.
        options["poolclass"] = QueuePool
    engine = create_engine(target, connect_args=connect_args, echo=False, pool_pre_ping=True, **options)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    return engine


DATABASE_ENCRYPTION = os.getenv("MEDTWIN_DB_ENCRYPTION", "off").strip().lower()
engine = build_engine(DATABASE_URL, DATABASE_ENCRYPTION, database_key() if DATABASE_ENCRYPTION == "sqlcipher" else None)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def encryption_status() -> dict:
    """What protects the database at rest, for the readiness report (no key material)."""
    if DATABASE_ENCRYPTION == "sqlcipher":
        return {"ready": True, "mode": "SQLCIPHER_AES_256", "scope": "whole SQLite file and write-ahead log"}
    if DATABASE_URL.startswith("postgresql"):
        return {"ready": True, "mode": "DELEGATED_TO_STORAGE", "scope": "PostgreSQL relies on encrypted storage underneath", "optional": True}
    return {"ready": True, "mode": "NONE", "scope": "plain SQLite file; set MEDTWIN_DB_ENCRYPTION=sqlcipher", "optional": True}

def get_db():
    """Dependency that yields a database session and closes it cleanly."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
