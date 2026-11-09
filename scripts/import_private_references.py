r"""Import private case reports without creating shared cases or public seeds.

Usage: .venv\Scripts\python.exe scripts/import_private_references.py --owner-username <exact username> --manifest <private JSON file>
The manifest is {"studies": [{"import_key": "revision", "title": "...", "summary": "...", "sources": [{"id": "doc1", "path": "...", "label": "..."}], ...}]}.
Keep the manifest outside Git. Facts, measurements, timeline and insights require refs: [{"source": "doc1", "page": 1}].
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner-username", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    from app.database import SessionLocal
    from app.models.entities import User
    from app.services.private_references import import_packet
    with SessionLocal() as db:
        owner = db.query(User).filter(User.username == args.owner_username).one_or_none()
        if owner is None:
            parser.error("Exact owner username not found; no data imported.")
        definitions = json.loads(args.manifest.read_text(encoding="utf-8"))
        for index, definition in enumerate(definitions["studies"], 1):
            study_id = import_packet(owner, definition)
            print(f"Imported private reference {index}: {study_id}", flush=True)


if __name__ == "__main__":
    main()
