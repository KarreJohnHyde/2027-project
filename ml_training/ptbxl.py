"""PTB-XL data access without deep-learning dependencies (shared by ml_training.ecg and the
dataset audit): exact WFDB format-16 reader, labels, publisher checksums, folds, version.

Integrity is checked three ways: every file against the publisher's SHA256SUMS.txt, and
every lead against its header checksum (16-bit sum of the samples) and first sample.
Labels: the five diagnostic superclasses aggregated from SCP codes whose scp_statements
row has diagnostic == 1 (multi-label); records without one are excluded and counted.
Splits: strat_fold 1-8 train, 9 validation, 10 test (the publisher's recommendation).
"""

from __future__ import annotations

import ast
import csv
import hashlib
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.1"
SUPERCLASSES = ["NORM", "MI", "STTC", "CD", "HYP"]
LEADS = ["I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2", "V3", "V4", "V5", "V6"]
LICENSE = {"status": "VERIFIED", "name": "CC BY 4.0 (Creative Commons Attribution 4.0 International)",
           "source": "LICENSE.txt shipped with the dataset; https://physionet.org/content/ptb-xl/1.0.1/", "verified_on": "2026-10-25",
           "citation": "Wagner P, Strodthoff N, Bousseljot R-D, et al. PTB-XL, a large publicly available electrocardiography dataset. Sci Data 7, 154 (2020)."}


class WfdbError(ValueError):
    """A record that does not match its header or the publisher's checksums."""


def read_header(path: Path) -> dict:
    lines = [line for line in path.read_text(encoding="ascii").splitlines() if line.strip() and not line.startswith("#")]
    name, signal_count, frequency, sample_count = lines[0].split()[:4]
    signals = []
    for line in lines[1:1 + int(signal_count)]:
        filename, fmt, gain_units, _resolution, adc_zero, initial, checksum, _block, *description = line.split()
        gain_text = gain_units.split("/")[0]
        gain = float(gain_text.split("(")[0])
        baseline = int(gain_text.split("(")[1].rstrip(")")) if "(" in gain_text else int(adc_zero)
        signals.append({"file": filename, "format": fmt, "gain": gain, "baseline": baseline, "initial": int(initial),
                        "checksum": int(checksum), "lead": " ".join(description).upper()})
    return {"record": name, "frequency": float(frequency), "samples": int(sample_count), "signals": signals}


def read_record(header_path: Path) -> np.ndarray:
    """Physical signal in mV, shape (samples, leads), validated against the header."""
    header = read_header(header_path)
    signals = header["signals"]
    if {signal["format"] for signal in signals} != {"16"} or len({signal["file"] for signal in signals}) != 1:
        raise WfdbError(f"{header_path.name}: only single-file format-16 records are supported")
    raw = np.fromfile(header_path.with_name(signals[0]["file"]), dtype="<i2")
    if raw.size != header["samples"] * len(signals):
        raise WfdbError(f"{header_path.name}: {raw.size} samples on disk, header declares {header['samples']} x {len(signals)}")
    digital = raw.reshape(header["samples"], len(signals))
    for column, signal in enumerate(signals):
        if int(digital[0, column]) != signal["initial"]:
            raise WfdbError(f"{header_path.name} lead {signal['lead']}: first sample differs from the header")
        if int(digital[:, column].astype(np.int64).sum()) % 65536 != signal["checksum"] % 65536:
            raise WfdbError(f"{header_path.name} lead {signal['lead']}: checksum mismatch")
    if [signal["lead"] for signal in signals] != LEADS:
        raise WfdbError(f"{header_path.name}: unexpected lead order")
    gains = np.array([signal["gain"] for signal in signals], dtype=np.float32)
    baselines = np.array([signal["baseline"] for signal in signals], dtype=np.float32)
    return (digital.astype(np.float32) - baselines) / gains


def publisher_checksums(dataset_dir: Path = DATASET_DIR) -> dict[str, str]:
    sums = {}
    for line in (dataset_dir / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        digest, _, name = line.strip().partition(" ")
        sums[name.strip().lstrip("*")] = digest
    return sums


def verify_files(paths: list[str], sums: dict[str, str], dataset_dir: Path = DATASET_DIR) -> dict:
    mismatched, missing = [], []
    for name in paths:
        expected = sums.get(name)
        if expected is None:
            missing.append(name)
            continue
        if hashlib.sha256((dataset_dir / name).read_bytes()).hexdigest() != expected:
            mismatched.append(name)
    if mismatched or missing:
        raise WfdbError(f"publisher checksum verification failed: {len(mismatched)} mismatched, {len(missing)} not listed")
    return {"files_verified": len(paths), "against": "SHA256SUMS.txt (publisher)"}


def load_metadata(dataset_dir: Path = DATASET_DIR) -> tuple[list[dict], dict[str, str], dict]:
    statements = {}
    with (dataset_dir / "scp_statements.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            code = row[""] if "" in row else next(iter(row.values()))
            if str(row.get("diagnostic", "")).strip() in {"1", "1.0"}:
                statements[code] = row["diagnostic_class"]
    records, excluded = [], Counter()
    with (dataset_dir / "ptbxl_database.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            codes = ast.literal_eval(row["scp_codes"])  # a dict literal; literal_eval executes no code
            classes = sorted({statements[code] for code in codes if code in statements})
            if not classes:
                excluded["no_diagnostic_superclass"] += 1
                continue
            fold = int(row["strat_fold"])
            records.append({"ecg_id": int(row["ecg_id"]), "patient_id": str(int(float(row["patient_id"]))), "fold": fold,
                            "split": "train" if fold <= 8 else ("val" if fold == 9 else "test"), "file": row["filename_lr"],
                            "labels": classes})
    return records, statements, dict(excluded)


def assert_patient_disjoint(records: list[dict]) -> dict:
    patients = {split: {record["patient_id"] for record in records if record["split"] == split} for split in ("train", "val", "test")}
    overlaps = {f"{a}&{b}": len(patients[a] & patients[b]) for a, b in (("train", "val"), ("train", "test"), ("val", "test"))}
    if any(overlaps.values()):
        raise WfdbError(f"patients appear in more than one split: {overlaps}")
    return {"patients_per_split": {split: len(ids) for split, ids in patients.items()}, "patient_overlap": overlaps}


def used_files(records: list[dict]) -> list[str]:
    return [f"{record['file']}{suffix}" for record in records for suffix in (".dat", ".hea")] + ["ptbxl_database.csv", "scp_statements.csv"]


def dataset_version(records: list[dict], sums: dict[str, str]) -> str:
    """Hash of the publisher's SHA-256 for every file a model uses (the records kept and the label tables)."""
    files = used_files(records)
    return hashlib.sha256("\n".join(sorted(f"{name} {sums[name]}" for name in files)).encode()).hexdigest()
