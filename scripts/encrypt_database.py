"""Write a SQLCipher-encrypted copy of a plaintext MedTwin SQLite database.

The source is opened read-only and never modified or deleted. The copy is checked table by
table (row counts) and with PRAGMA integrity_check before this script reports success. Then
point the application at the copy:

    MEDTWIN_DB_ENCRYPTION=sqlcipher
    MEDTWIN_DB_KEY_FILE=<the key file>        (64 hex characters; keep it outside the repository)
    DATABASE_URL=sqlite:///<the encrypted copy>

and remove the plaintext original yourself once the application runs on the copy.

    python scripts/encrypt_database.py --source backend/medtwin.db --target backend/medtwin.encrypted.db \
        --key-file %APPDATA%\\medtwin\\db.key [--new-key]
"""

from __future__ import annotations

import argparse
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.database import database_key  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--new-key", action="store_true", help="Create the key file with a new random 256-bit key (refuses to overwrite).")
    args = parser.parse_args(argv)

    import sqlcipher3

    if not args.source.is_file():
        parser.error(f"source database not found: {args.source}")
    if args.target.exists():
        parser.error(f"target already exists: {args.target} (choose a new path; nothing is overwritten)")
    if args.new_key:
        if args.key_file.exists():
            parser.error(f"key file already exists: {args.key_file}")
        args.key_file.parent.mkdir(parents=True, exist_ok=True)
        args.key_file.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
        print(f"Created a new key file: {args.key_file} (back it up; without it the encrypted copy cannot be read).")
    key = database_key({"MEDTWIN_DB_KEY_FILE": str(args.key_file)})

    with sqlite3.connect(f"file:{args.source.as_posix()}?mode=ro", uri=True) as plain:
        tables = [row[0] for row in plain.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        expected = {table: plain.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}

    # The source is opened read-only; only the attached target is writable.
    connection = sqlcipher3.connect(f"file:{args.source.resolve().as_posix()}?mode=ro", uri=True)
    try:
        connection.execute(f"ATTACH DATABASE ? AS encrypted KEY \"{key}\"", (f"file:{args.target.resolve().as_posix()}?mode=rwc",))
        connection.execute("SELECT sqlcipher_export('encrypted')")
        connection.execute("DETACH DATABASE encrypted")
    finally:
        connection.close()

    check = sqlcipher3.connect(str(args.target))
    try:
        check.execute(f'PRAGMA key="{key}"')
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        copied = {table: check.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] for table in tables}
    finally:
        check.close()
    if integrity != "ok" or copied != expected:
        print(f"Verification failed: integrity {integrity}; differing tables {[t for t in tables if copied.get(t) != expected[t]]}.")
        return 1
    if any(marker in args.target.read_bytes()[:16] for marker in (b"SQLite format 3",)):
        print("Verification failed: the copy has a plaintext SQLite header.")
        return 1
    print(f"Encrypted copy verified: {len(tables)} tables, {sum(copied.values())} rows, integrity ok. The source was not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
