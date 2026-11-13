"""Bounded HTTPS downloads of explicitly reviewed free research/reference resources.

No credentials are read. No upstream code is executed. Archives remain local;
the downloader records bytes, SHA-256, exact source and declared rights.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import tempfile
import urllib.request

RESOURCES = {
    "icd10cm-2027-codes": {
        "url": "https://ftp.cdc.gov/pub/health_statistics/nchs/publications/ICD10CM/2027/icd10cm-code-descriptions-2027.zip",
        "filename": "icd10cm-code-descriptions-2027.zip", "version": "FY2027 effective 2026-10-01 through 2027-09-30",
        "publisher": "CDC/NCHS", "licence": "US government public-domain ICD-10-CM reference release",
        "commercial_eligible": True,
        "licence_evidence": "https://stacks.cdc.gov/view/cdc/27312/cdc_27312_DS1.pdf",
        "max_bytes": 4_000_000, "use_scope": "Terminology reference only; not ICD-11, patient diagnosis or model coverage",
    },
    "icd10cm-2027-tabular": {
        "url": "https://ftp.cdc.gov/pub/health_statistics/nchs/publications/ICD10CM/2027/icd10cm-table-and-index-2027.zip",
        "filename": "icd10cm-table-and-index-2027.zip", "version": "FY2027 effective 2026-10-01 through 2027-09-30",
        "publisher": "CDC/NCHS", "licence": "US government public-domain ICD-10-CM reference release",
        "commercial_eligible": True,
        "licence_evidence": "https://stacks.cdc.gov/view/cdc/27312/cdc_27312_DS1.pdf",
        "max_bytes": 30_000_000, "use_scope": "Official tabular parent/chapter metadata; application system links are broad context only",
    },
    "kaggle-rx-words-v1": {
        "url": "https://www.kaggle.com/api/v1/datasets/download/mamun1113/doctors-handwritten-prescription-bd-dataset?datasetVersionNumber=1",
        "filename": "kaggle-prescription-words-v1.zip", "version": "Kaggle v1, 2024-05-10",
        "publisher": "Mamun1113 and Mia et al., iCACCESS 2024",
        "licence": "Database ODbL; contents copyright original authors; author permits education/research only",
        "commercial_eligible": False,
        "licence_evidence": "https://www.kaggle.com/datasets/mamun1113/doctors-handwritten-prescription-bd-dataset",
        "max_bytes": 35_000_000, "use_scope": "Isolated noncommercial educational evaluation of real prescription-word OCR; no full-report validity claim, training or redistribution",
    },
    "clinocr-v1": {
        "url": "https://github.com/ClinOCR-Bench/ClinOCR-Bench/releases/download/v1.0/ClinOCR-Bench-v1.0.zip",
        "filename": "ClinOCR-Bench-v1.0.zip", "version": "v1.0",
        "publisher": "ClinOCR-Bench; Hsu, Zhou and Roberts (2026)", "licence": "MIT",
        "commercial_eligible": True,
        "licence_evidence": "https://github.com/ClinOCR-Bench/ClinOCR-Bench/blob/main/LICENSE",
        "max_bytes": 150_000_000, "use_scope": "External synthetic human-audited OCR robustness evaluation; never real clinical report validation",
    },
    "rxhandbd-v1": {
        "url": "https://zenodo.org/api/records/18478741/files/RxHandBD.zip/content",
        "filename": "RxHandBD-zenodo-v1.zip", "version": "Zenodo record18478741 v1, DOI10.5281/zenodo.18478741",
        "publisher": "Md. Masudul Islam; Bangladesh University of Business and Technology",
        "licence": "MIT (primary Zenodo dataset record metadata.license.id=mit-license)",
        "commercial_eligible": True,
        "licence_evidence": "https://zenodo.org/api/records/18478741",
        "max_bytes": 40_000_000,
        "use_scope": "Independent real prescription-word crop OCR on upstream test labels only; human annotation/reviewer method not specified by publisher; not full-page clinical validation",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
    return digest.hexdigest()


def fetch_resource(resource_id: str, directory: Path) -> dict:
    definition = RESOURCES[resource_id]
    if not definition.get("commercial_eligible"):
        raise ValueError("Resource is ineligible under the user's commercial-use requirement; no download or benchmark use permitted")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / definition["filename"]
    receipt = directory / (definition["filename"] + ".provenance.json")
    if destination.exists():
        if not receipt.exists(): raise ValueError("Existing file lacks a download provenance receipt; refusing overwrite")
        previous = json.loads(receipt.read_text(encoding="utf-8"))
        if previous.get("sha256") != sha256(destination) or previous.get("url") != definition["url"]:
            raise ValueError("Existing resource hash/source mismatch; refusing overwrite")
        return {**previous, "downloaded_now": False}
    request = urllib.request.Request(definition["url"], headers={"User-Agent": "MedTwin-research-resource-audit/1.0"})
    temporary = None
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if not response.geturl().startswith("https://"): raise ValueError("Non-HTTPS download redirect refused")
            announced = response.headers.get("Content-Length")
            if announced and int(announced) > definition["max_bytes"]: raise ValueError("Resource exceeds reviewed download budget")
            with tempfile.NamedTemporaryFile(dir=directory, prefix=".resource-", suffix=".part", delete=False) as handle:
                temporary = Path(handle.name)
                total = 0
                while block := response.read(1024 * 1024):
                    total += len(block)
                    if total > definition["max_bytes"]: raise ValueError("Resource exceeds reviewed download budget")
                    handle.write(block)
                handle.flush(); os.fsync(handle.fileno())
        if not total: raise ValueError("Empty download refused")
        # Every selected resource is a ZIP; HTML login/error pages are not data.
        with temporary.open("rb") as stream:
            if stream.read(4) != b"PK\x03\x04": raise ValueError("Expected ZIP resource; got another response")
        if destination.exists(): raise ValueError("Destination appeared during download; refusing replacement")
        temporary.replace(destination); temporary = None
        result = {"resource_id": resource_id, **definition, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                  "bytes": total, "sha256": sha256(destination), "local_file": str(destination.resolve()),
                  "accepted": True, "downloaded_now": True}
        receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource", action="append", choices=RESOURCES, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    for resource_id in args.resource:
        print(json.dumps(fetch_resource(resource_id, args.directory), ensure_ascii=True))


if __name__ == "__main__": main()
