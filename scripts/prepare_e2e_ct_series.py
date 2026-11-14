"""Prepare the optional native head CT series control for the browser test "native head CT series is analysed slice by
slice" (tools/browser-qa/e2e/workflow.spec.mjs).

The control is one real, de-identified head CT DICOM series from CQ500 (qure.ai; CC BY-NC-SA 4.0; downloaded for
evaluation with the owner's approval). The first scan in numeric order whose reader majority (at least 2 of 3 readers)
marks intracranial haemorrhage is used, and its series is chosen exactly as scripts/evaluate_head_ct_cq500.py chooses it,
so the choice is reproducible. The slices are written to the git-ignored .cache/e2e-controls/ folder with a provenance
record. The licence is non-commercial and share-alike: never commit or publish these files.

This is a functional check that the served checkpoint runs on native DICOM through the app, not an accuracy study.

  .venv\\Scripts\\python.exe scripts\\prepare_e2e_ct_series.py [--cq500 C:/MedTwin_Datasets/CQ500]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".cache" / "e2e-controls" / "cq500-head-ct-series"
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_head_ct_cq500 import choose_series, reference  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cq500", type=Path, default=Path(os.environ.get("MEDTWIN_CQ500", "C:/MedTwin_Datasets/CQ500")))
    args = parser.parse_args()
    reads = args.cq500 / "reads.csv"
    if not reads.exists():
        print(f"CQ500 reads not found ({reads}); the browser test stays skipped.")
        return 1
    truth = reference(reads)
    zips = sorted((args.cq500 / "zips").glob("CQ500-CT-*.zip"), key=lambda path: int(path.stem.rsplit("-", 1)[1]))
    archive_path = next((path for path in zips if truth.get(path.stem, {}).get("ICH") == 1), None)
    if archive_path is None:
        print("No downloaded CQ500 scan with a reader-majority haemorrhage.")
        return 1
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)  # only this script's own git-ignored output folder
    OUTPUT.mkdir(parents=True)
    with zipfile.ZipFile(archive_path) as archive:
        members, chosen = choose_series(archive)
        if not members:
            print(f"{archive_path.stem}: no soft-tissue series ({chosen}).")
            return 1
        hashes = []
        for index, member in enumerate(members):
            payload = archive.read(member)
            (OUTPUT / f"slice-{index:04d}.dcm").write_bytes(payload)
            hashes.append(hashlib.sha256(payload).hexdigest())
    record = {
        "purpose": "Optional browser control: served haemorrhage checkpoint on one native head CT DICOM series",
        "dataset": "CQ500 (qure.ai), de-identified head CT with three radiologists' reads",
        "licence": "CC BY-NC-SA 4.0, evaluation only; do not commit or publish these files",
        "scan": archive_path.stem, "reader_majority": truth[archive_path.stem],
        "selection": "first scan in numeric order with a reader-majority ICH; series chosen as in scripts/evaluate_head_ct_cq500.py",
        "series": chosen, "slices": len(members), "slice_sha256": hashes,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    (OUTPUT / "provenance.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"control written: {OUTPUT.relative_to(ROOT)} ({len(members)} slices of {archive_path.stem}; reader majority {record['reader_majority']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
