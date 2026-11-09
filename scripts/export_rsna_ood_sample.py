"""Export a seeded sample of RSNA ICH slices per split for the image applicability reference.

The RSNA slices stay inside RSNA_PNG/rsna-ich-png.zip; scripts/build_image_ood_references.py reads image files,
so a sample (as many as it uses: 3,000 train, 1,500 validation, 1,500 test) is written to
_derived/datasets/rsna-ich/ood_sample/<split>/ with ood_sample.csv (entry, path, split). Splits are the trainer's.

    python scripts/export_rsna_ood_sample.py
"""

import csv
import random
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "RSNA_PNG" / "rsna-ich-png.zip"
BASE = ROOT / "_derived" / "datasets" / "rsna-ich"
COUNTS = {"train": 3000, "val": 1500, "test": 1500}
SEED = 20261104


def main() -> None:
    with (BASE / "samples.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    chosen = []
    for split, count in COUNTS.items():
        members = sorted(row["entry"] for row in rows if row["split"] == split)
        chosen += [(entry, split) for entry in random.Random(f"{SEED}:{split}").sample(members, min(count, len(members)))]
    out = []
    with zipfile.ZipFile(ARCHIVE) as archive:
        for entry, split in chosen:
            target = BASE / "ood_sample" / split / entry.rsplit("/", 1)[-1]
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(archive.read(entry))
            out.append({"entry": entry, "path": target.relative_to(ROOT).as_posix(), "split": split})
    with (BASE / "ood_sample.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["entry", "path", "split"])
        writer.writeheader()
        writer.writerows(out)
    print(f"exported {len(out)} slices: {dict((s, sum(1 for r in out if r['split'] == s)) for s in COUNTS)}")


if __name__ == "__main__":
    main()
