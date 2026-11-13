"""Validate/import an explicitly supplied Universal catalogue without resetting data.

Examples:
  python scripts/import_universal_catalogue.py --input incoming.json --output local-catalogue.json
  python scripts/import_universal_catalogue.py --input extension.json --output local-catalogue.json --merge

Importing has no database, user, case, registry or model side effects. Existing IDs
are immutable through this command: conflicting records require an explicit,
reviewed source-file revision rather than a bulk importer overwriting them.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from app.schemas.universal_catalogue import CatalogueBundle

MAX_BYTES = 32 * 1024 * 1024


def canonical(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def read_validated(path: Path) -> dict:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Catalogue exceeds the 32 MiB import limit")
    return CatalogueBundle.model_validate_json(path.read_text(encoding="utf-8-sig")).model_dump()


def merge_records(existing: dict, incoming: dict) -> dict:
    """Append new IDs, preserve original records and bundle provenance.

    Every imported record retains its own source/version/licence. The original
    bundle version identifies the base source; the content SHA identifies the
    merged revision. No model is activated by any association in this file.
    """
    combined = deepcopy(existing)
    for key in ("systems", "entries"):
        by_id = {row["id"]: row for row in combined[key]}
        for row in incoming[key]:
            if row["id"] in by_id:
                if row != by_id[row["id"]]:
                    raise ValueError(f"Conflicting existing {key} ID: {row['id']}")
            else:
                combined[key].append(deepcopy(row))
                by_id[row["id"]] = row
    return CatalogueBundle.model_validate(combined).model_dump()


def import_catalogue(input_path: Path, output_path: Path, *, merge: bool = False) -> dict:
    input_path, output_path = input_path.resolve(), output_path.resolve()
    if output_path.suffix.casefold() != ".json":
        raise ValueError("An explicit .json catalogue output is required")
    incoming = read_validated(input_path)
    if not output_path.parent.is_dir():
        raise ValueError("The explicit output directory must already exist")
    lock_path = output_path.with_name(output_path.name + ".import.lock")
    lock_fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    temporary_path = None
    try:
        original = output_path.read_bytes() if output_path.exists() else None
        if original is not None:
            existing = read_validated(output_path)
            if existing == incoming:
                result = existing
            elif merge:
                result = merge_records(existing, incoming)
            else:
                raise ValueError("Output already exists with different contents; --merge only appends non-conflicting IDs")
        else:
            result = incoming
        encoded = canonical(result)
        # An idempotent import preserves original formatting, bytes and mtime.
        changed = original is None or CatalogueBundle.model_validate_json(original).model_dump() != result
        if changed:
            with tempfile.NamedTemporaryFile(dir=output_path.parent, prefix=".catalogue-import-", suffix=".tmp", delete=False) as handle:
                temporary_path = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            if (output_path.read_bytes() if output_path.exists() else None) != original:
                raise ValueError("Output changed during import; no replacement performed")
            os.replace(temporary_path, output_path)
            temporary_path = None
        return {"schema_version": result["schema_version"], "output": str(output_path), "changed": changed,
                "systems": len(result["systems"]), "entries": len(result["entries"]),
                "content_sha256": hashlib.sha256(canonical(result)).hexdigest(),
                "file_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
                "clinical_activation": "CLINICAL_ACTIVATION_NOT_CLEARED"}
    finally:
        os.close(lock_fd)
        lock_path.unlink()
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Explicit authorized source JSON")
    parser.add_argument("--output", type=Path, required=True, help="Explicit catalogue JSON destination (no default)")
    parser.add_argument("--merge", action="store_true", help="Append new IDs; reject edits to every existing ID")
    args = parser.parse_args()
    try:
        report = import_catalogue(args.input, args.output, merge=args.merge)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Catalogue import refused: {exc}\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
