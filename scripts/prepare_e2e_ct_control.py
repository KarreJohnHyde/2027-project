"""Prepare the optional public-CT control image for the browser test "public digital CT control shows real checkpoint
output separately" (tools/browser-qa/e2e/workflow.spec.mjs).

The control is one brain-window PNG from the held-out TEST split of the RSNA Intracranial Hemorrhage dataset that the
brain_ct_rsna_ich_classifier was trained on (split manifest _derived/datasets/rsna-ich/samples.csv). The first test-split
slice labelled "any haemorrhage" in manifest order is chosen, so the choice is reproducible. It is written to the
git-ignored .cache/e2e-controls/ folder with a provenance record. The dataset's terms allow non-commercial research use
only, so the image must never be committed or published.

This is a functional inference check of the served checkpoint on its own distribution, not an accuracy study or a
native DICOM geometry test.

  .venv\\Scripts\\python.exe scripts\\prepare_e2e_ct_control.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "RSNA_PNG" / "rsna-ich-png.zip"
MANIFEST = ROOT / "_derived" / "datasets" / "rsna-ich" / "samples.csv"
OUTPUT = ROOT / ".cache" / "e2e-controls" / "public-ct-control.png"
LABELS = ("edh", "sdh", "iph", "ivh", "sah", "any")


def main() -> int:
    if not ARCHIVE.exists() or not MANIFEST.exists():
        print(f"RSNA archive or split manifest not found ({ARCHIVE}, {MANIFEST}); the browser test stays skipped.")
        return 1
    with MANIFEST.open(newline="", encoding="utf-8") as handle:
        row = next((r for r in csv.DictReader(handle) if r["split"] == "test" and r["any"] == "1"), None)
    if row is None:
        print("No held-out test slice labelled 'any' in the manifest.")
        return 1
    with zipfile.ZipFile(ARCHIVE) as archive:
        payload = archive.read(row["entry"])
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        print("The selected archive entry is not a PNG.")
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(payload)
    record = {
        "purpose": "Optional browser control: served RSNA checkpoint on one image from its own held-out test split",
        "dataset": "RSNA Intracranial Hemorrhage Detection (PNG export)",
        "licence": "RSNA dataset terms, non-commercial research use; do not commit or publish this image",
        "archive": str(ARCHIVE.relative_to(ROOT)), "manifest": str(MANIFEST.relative_to(ROOT)),
        "manifest_entry": row["entry"], "split": row["split"], "labels": {label: int(row[label]) for label in LABELS},
        "selection": "first test-split row with any=1 in manifest order",
        "png_sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload),
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    OUTPUT.with_suffix(".json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"control written: {OUTPUT.relative_to(ROOT)} ({len(payload)} bytes, split {row['split']}, labels {record['labels']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
