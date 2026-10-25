"""Upload-store key management: status, encryption of legacy plaintext, key rotation.

Uses the same key configuration as the backend (MEDTWIN_STORAGE_KEY_FILE or
MEDTWIN_STORAGE_KEYS; the active key encrypts) and UPLOAD_DIR (or --upload-dir).
Dry run by default: --apply performs the change. Each rewrite streams plaintext into
new ciphertext, verifies that it decrypts to the same SHA-256, then atomically replaces
the file. Only counts are printed, never file contents.

  python scripts/storage_keys.py status
  python scripts/storage_keys.py encrypt-legacy --apply
  python scripts/storage_keys.py rotate --apply     # after adding a new active key; keep the old key until done
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.storage_crypto import StorageCryptoError, file_key_id, load_keyring, reencrypt_in_place  # noqa: E402


def stored_files(upload_dir: Path) -> list[Path]:
    """Every stored upload, excluding the private decryption work area and partial writes."""
    return sorted(path for path in upload_dir.rglob("*")
                  if path.is_file() and ".work" not in path.relative_to(upload_dir).parts and not path.name.endswith(".enc-part"))


def classify(paths: list[Path], keyring) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {"plaintext": [], "active_key": [], "other_known_key": [], "unknown_key": []}
    for path in paths:
        key_id = file_key_id(path)
        if key_id is None:
            groups["plaintext"].append(path)
        elif key_id == keyring.active_id:
            groups["active_key"].append(path)
        elif key_id in keyring.keys:
            groups["other_known_key"].append(path)
        else:
            groups["unknown_key"].append(path)
    return groups


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "encrypt-legacy", "rotate"])
    parser.add_argument("--upload-dir", type=Path)
    parser.add_argument("--apply", action="store_true", help="Perform the change (default: dry run).")
    args = parser.parse_args(argv)
    if args.upload_dir is None:
        from app.config import UPLOAD_DIR

        args.upload_dir = UPLOAD_DIR
    keyring = load_keyring()
    groups = classify(stored_files(args.upload_dir), keyring)
    print("files:", {name: len(paths) for name, paths in groups.items()}, "| active key:", keyring.active_id.hex() if keyring.active_id else None)
    if args.command == "status":
        return 1 if groups["unknown_key"] else 0
    if keyring.active_id is None:
        print("No active storage key is configured; nothing can be encrypted.")
        return 2
    targets = groups["plaintext"] if args.command == "encrypt-legacy" else groups["plaintext"] + groups["other_known_key"]
    if not args.apply:
        print(f"dry run: {len(targets)} file(s) would be rewritten under the active key; rerun with --apply")
        return 0
    outcome: Counter = Counter()
    for path in targets:
        try:
            reencrypt_in_place(path, keyring)
            outcome["rewritten"] += 1
        except (OSError, StorageCryptoError) as exc:
            outcome[f"failed:{type(exc).__name__}"] += 1
    print("result:", dict(outcome))
    return 0 if not any(key.startswith("failed") for key in outcome) else 1


if __name__ == "__main__":
    raise SystemExit(main())
