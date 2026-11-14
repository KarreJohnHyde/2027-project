"""Download the public datasets the owner approved on 2026-11-14, from their original publishers only.

Resumable: rerun after an interruption and partial files continue (HTTP Range). Each finished file gets a receipt
(<file>.receipt.json) with the source URL, byte count, SHA-256, licence and the licence page it was checked against
(the page's SHA-256 is stored as evidence). A file whose size differs from the size the publisher reported when the
owner approved it is kept as .part and reported, never accepted. Nothing outside APPROVED is fetched.

  .venv\\Scripts\\python.exe scripts\\acquire_approved_public_datasets.py [--only NAME ...] [--list]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

C = Path("C:/MedTwin_Datasets")
D = Path("D:/MedTwin_Archives")
AGENT = "medtwin-research-downloader"
MSD = "https://msd-for-monai.s3-us-west-2.amazonaws.com"
UCI_LICENCE = ("CC BY 4.0", "Creative Commons Attribution 4.0")


def uci(number: int, slug: str, title: str) -> dict:
    return {"name": f"uci-{number}", "title": title, "url": f"https://archive.ics.uci.edu/static/public/{number}/{slug}.zip",
            "dest": C / "UCI_Tables" / f"uci-{number}-{slug.split('+')[0]}.zip", "bytes": None,
            "licence": UCI_LICENCE[0], "licence_page": f"https://archive.ics.uci.edu/dataset/{number}", "licence_marker": UCI_LICENCE[1],
            "batch": "tables-ecg-malaria"}


APPROVED = [
    uci(45, "heart+disease", "Heart Disease (Cleveland and others)"),
    uci(336, "chronic+kidney+disease", "Chronic Kidney Disease"),
    uci(296, "diabetes+130-us+hospitals+for+years+1999-2008", "Diabetes 130-US hospitals 1999-2008"),
    uci(17, "breast+cancer+wisconsin+diagnostic", "Breast Cancer Wisconsin (Diagnostic)"),
    uci(102, "thyroid+disease", "Thyroid Disease"),
    uci(225, "ilpd+indian+liver+patient+dataset", "ILPD (Indian Liver Patient Dataset)"),
    uci(46, "hepatitis", "Hepatitis"),
    uci(174, "parkinsons", "Parkinsons"),
    uci(383, "cervical+cancer+risk+factors", "Cervical Cancer (Risk Factors)"),
    {"name": "mitdb", "title": "MIT-BIH Arrhythmia Database 1.0.0",
     "url": "https://physionet.org/static/published-projects/mitdb/mit-bih-arrhythmia-database-1.0.0.zip",
     "dest": C / "MIT_BIH" / "mit-bih-arrhythmia-database-1.0.0.zip", "bytes": None,
     "licence": "Open Data Commons Attribution License v1.0", "licence_page": "https://physionet.org/content/mitdb/1.0.0/",
     "licence_marker": "Open Data Commons Attribution License", "batch": "tables-ecg-malaria"},
    {"name": "malaria", "title": "NIH/NLM malaria cell images (thin blood smears)",
     "url": "https://data.lhncbc.nlm.nih.gov/public/Malaria/cell_images.zip", "dest": C / "NIH_Malaria" / "cell_images.zip",
     "bytes": None, "licence": "NLM public research release (free public use; cite the dataset paper)",
     "licence_page": "https://lhncbc.nlm.nih.gov/LHC-research/LHC-projects/image-processing/malaria-datasheet.html",
     "licence_marker": None, "batch": "tables-ecg-malaria"},
    {"name": "msd-task09-spleen", "title": "Medical Segmentation Decathlon Task09 Spleen", "url": f"{MSD}/Task09_Spleen.tar",
     "dest": C / "MSD" / "Task09_Spleen.tar", "bytes": None, "licence": "CC BY-SA 4.0 (Medical Segmentation Decathlon)",
     "licence_page": "http://medicaldecathlon.com/", "licence_marker": "CC-BY-SA", "batch": "spleen-prostate-hippocampus"},
    {"name": "msd-task05-prostate", "title": "Medical Segmentation Decathlon Task05 Prostate", "url": f"{MSD}/Task05_Prostate.tar",
     "dest": C / "MSD" / "Task05_Prostate.tar", "bytes": None, "licence": "CC BY-SA 4.0 (Medical Segmentation Decathlon)",
     "licence_page": "http://medicaldecathlon.com/", "licence_marker": "CC-BY-SA", "batch": "spleen-prostate-hippocampus"},
    {"name": "msd-task04-hippocampus", "title": "Medical Segmentation Decathlon Task04 Hippocampus", "url": f"{MSD}/Task04_Hippocampus.tar",
     "dest": C / "MSD" / "Task04_Hippocampus.tar", "bytes": None, "licence": "CC BY-SA 4.0 (Medical Segmentation Decathlon)",
     "licence_page": "http://medicaldecathlon.com/", "licence_marker": "CC-BY-SA", "batch": "spleen-prostate-hippocampus"},
    {"name": "hc18-train", "title": "HC18 fetal head circumference, training set", "url": "https://zenodo.org/records/1327317/files/training_set.zip",
     "dest": C / "HC18" / "training_set.zip", "bytes": None, "licence": "CC BY 4.0", "licence_page": "https://zenodo.org/api/records/1327317",
     "licence_marker": "cc-by-4.0", "batch": "fetal-ultrasound"},
    {"name": "hc18-test", "title": "HC18 fetal head circumference, test set", "url": "https://zenodo.org/records/1327317/files/test_set.zip",
     "dest": C / "HC18" / "test_set.zip", "bytes": None, "licence": "CC BY 4.0", "licence_page": "https://zenodo.org/api/records/1327317",
     "licence_marker": "cc-by-4.0", "batch": "fetal-ultrasound"},
    {"name": "hc18-train-csv", "title": "HC18 training pixel size and HC", "url": "https://zenodo.org/records/1327317/files/training_set_pixel_size_and_HC.csv",
     "dest": C / "HC18" / "training_set_pixel_size_and_HC.csv", "bytes": None, "licence": "CC BY 4.0",
     "licence_page": "https://zenodo.org/api/records/1327317", "licence_marker": "cc-by-4.0", "batch": "fetal-ultrasound"},
    {"name": "hc18-test-csv", "title": "HC18 test pixel size", "url": "https://zenodo.org/records/1327317/files/test_set_pixel_size.csv",
     "dest": C / "HC18" / "test_set_pixel_size.csv", "bytes": None, "licence": "CC BY 4.0",
     "licence_page": "https://zenodo.org/api/records/1327317", "licence_marker": "cc-by-4.0", "batch": "fetal-ultrasound"},
    {"name": "fetal-planes", "title": "FETAL_PLANES_DB common maternal-fetal ultrasound images",
     "url": "https://zenodo.org/records/3904280/files/FETAL_PLANES_ZENODO.zip", "dest": C / "FETAL_PLANES_DB" / "FETAL_PLANES_ZENODO.zip",
     "bytes": None, "licence": "CC BY 4.0", "licence_page": "https://zenodo.org/api/records/3904280", "licence_marker": "cc-by-4.0",
     "batch": "fetal-ultrasound"},
    {"name": "msd-task07-pancreas", "title": "Medical Segmentation Decathlon Task07 Pancreas", "url": f"{MSD}/Task07_Pancreas.tar",
     "dest": D / "MSD" / "Task07_Pancreas.tar", "bytes": None, "licence": "CC BY-SA 4.0 (Medical Segmentation Decathlon)",
     "licence_page": "http://medicaldecathlon.com/", "licence_marker": "CC-BY-SA", "batch": "pancreas"},
]


def _request(url: str, start: int = 0) -> urllib.request.Request:
    headers = {"User-Agent": AGENT}
    if start:
        headers["Range"] = f"bytes={start}-"
    return urllib.request.Request(url, headers=headers)


def remote_size(url: str) -> int | None:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        value = response.headers.get("Content-Length")
        return int(value) if value and int(value) > 0 else None


def licence_evidence(item: dict) -> dict:
    with urllib.request.urlopen(_request(item["licence_page"]), timeout=60) as response:
        page = response.read()
    text = page.decode("utf-8", errors="replace")
    marker = item.get("licence_marker")
    return {"page": item["licence_page"], "page_sha256": hashlib.sha256(page).hexdigest(), "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "marker": marker, "marker_found": (marker.lower() in text.lower()) if marker else None}


def fetch(item: dict) -> str:
    dest: Path = item["dest"]
    receipt = dest.with_name(dest.name + ".receipt.json")
    if receipt.exists():
        return "ALREADY_COMPLETE"
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    expected = remote_size(item["url"]) or item.get("bytes")
    for attempt in range(1, 6):
        start = part.stat().st_size if part.exists() else 0
        if expected and start == expected:
            break
        try:
            with urllib.request.urlopen(_request(item["url"], start), timeout=120) as response:
                if start and response.status != 206:
                    start = 0  # the server ignored the range: restart cleanly
                with part.open("ab" if start else "wb") as handle:
                    while True:
                        chunk = response.read(1 << 20)
                        if not chunk:
                            break
                        handle.write(chunk)
            if not expected or part.stat().st_size == expected:
                break
        except OSError as exc:
            print(f"  {item['name']}: attempt {attempt} interrupted ({type(exc).__name__}); resuming", flush=True)
            time.sleep(min(60, 5 * attempt))
    size = part.stat().st_size
    if expected and size != expected:
        return f"INCOMPLETE ({size} of {expected} bytes kept as {part.name})"
    digest = hashlib.sha256()
    with part.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    evidence = licence_evidence(item)
    part.replace(dest)
    record = {"title": item["title"], "source_url": item["url"], "bytes": size, "sha256": digest.hexdigest(), "licence": item["licence"],
              "licence_evidence": evidence, "batch": item["batch"], "approved_by": "project owner, chat instruction 2026-11-14",
              "downloaded_at": datetime.now(timezone.utc).isoformat()}
    receipt.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return f"COMPLETE {size} bytes sha256 {digest.hexdigest()[:16]} licence marker {'found' if evidence['marker_found'] else 'not checked' if evidence['marker_found'] is None else 'NOT FOUND'}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", nargs="*", help="Item names (default: all approved items)")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    items = [item for item in APPROVED if not args.only or item["name"] in args.only]
    if args.list:
        for item in items:
            print(f"{item['name']:24} {item['batch']:28} {item['dest']}")
        return 0
    failures = 0
    for item in items:
        try:
            outcome = fetch(item)
        except Exception as exc:  # report and continue with the next approved item
            outcome = f"FAILED ({type(exc).__name__}: {exc})"
        failures += not outcome.startswith(("COMPLETE", "ALREADY"))
        print(f"{item['name']:24} {outcome}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
