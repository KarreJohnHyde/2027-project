"""Create or stage an encrypted offline recovery bundle; keys stay external.

Stop API/worker/maintenance writers first. Restore refuses existing destinations.
This command never stops services, overwrites a live database or activates a restore.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.recovery_bundle import create_bundle, restore_bundle
from app.services.storage_crypto import load_keyring


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backup", "restore"))
    parser.add_argument("--database", type=Path)
    parser.add_argument("--uploads", type=Path)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--writers-stopped", action="store_true")
    args = parser.parse_args()
    if not os.environ.get("MEDTWIN_BACKUP_KEY_FILE"):
        parser.error("MEDTWIN_BACKUP_KEY_FILE must name a separately retained backup key-ring JSON")
    keys = load_keyring({"MEDTWIN_STORAGE_KEY_FILE": os.environ["MEDTWIN_BACKUP_KEY_FILE"]})
    key_file = os.environ.get("MEDTWIN_DB_KEY_FILE")
    database_key = Path(key_file).read_text().strip() if key_file else os.environ.get("MEDTWIN_DB_KEY")
    if args.command == "backup":
        if not args.database or not args.uploads:
            parser.error("Backup requires --database and --uploads")
        result = create_bundle(args.database, args.uploads, args.bundle, keys,
                               database_key=database_key, writers_stopped=args.writers_stopped)
    else:
        if not args.destination:
            parser.error("Restore requires a new --destination")
        result = restore_bundle(args.bundle, args.destination, keys, database_key=database_key)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
