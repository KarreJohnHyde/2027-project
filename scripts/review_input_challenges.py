"""Reproduce synthetic technical routing/ECG controls without loading a model.

This reports reader and metadata-contract behavior only. It never labels synthetic
controls as medical evidence, image/OOD coverage or clinical validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import numpy as np
from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import ecg_inference as ecg, model_router  # noqa: E402
from app.services.imaging_readers import open_raster, read_metadata  # noqa: E402


def run_challenges():
    results = []
    contract = ecg.CONTRACTS["wfdb16-100hz-10s-leadstd-v1"]
    times = np.arange(1000) / 100
    signal = np.stack([0.2 * np.sin(np.arange(1000) / (7 + lead)) for lead in range(12)], axis=1)

    def csv_bytes(sample_times, samples, leads):
        rows = ["time_s," + ",".join(leads)]
        rows.extend(str(time) + "," + ",".join(str(item) for item in row) for time, row in zip(sample_times, samples))
        return ("\n".join(rows) + "\n").encode()

    ecg_cases = [
        ("valid_100hz_12lead_mV", times, signal, ecg.PTBXL_LEADS, "mV", None),
        ("valid_uV_reverse_order", times, signal[:, ::-1] * 1000, ecg.PTBXL_LEADS[::-1], "uV", None),
        ("wrong_rate_250hz", np.arange(1000) / 250, signal, ecg.PTBXL_LEADS, "mV", "SAMPLING_RATE_OUT_OF_SCOPE"),
        ("short_record", times[:900], signal[:900], ecg.PTBXL_LEADS, "mV", "DURATION_OUT_OF_SCOPE"),
        ("missing_lead", times, signal[:, :11], ecg.PTBXL_LEADS[:11], "mV", "LEAD_SET_OUT_OF_SCOPE"),
        ("duplicate_lead", times, signal, ecg.PTBXL_LEADS[:11] + ["V5"], "mV", "DUPLICATE_LEADS"),
        ("undeclared_unit", times, signal, ecg.PTBXL_LEADS, "", "AMPLITUDE_UNIT_NOT_DECLARED"),
        ("extreme_amplitude", times, signal * 100, ecg.PTBXL_LEADS, "mV", "SIGNAL_QUALITY_AMPLITUDE"),
    ]
    for value in [float("nan"), float("inf")]:
        invalid_times = times.copy()
        invalid_times[27] = value
        ecg_cases.append((f"nonfinite_time_{value}", invalid_times, signal, ecg.PTBXL_LEADS, "mV", "NON_FINITE_TIMESTAMPS"))
        invalid_signal = signal.copy()
        invalid_signal[27, 0] = value
        ecg_cases.append((f"nonfinite_signal_{value}", times, invalid_signal, ecg.PTBXL_LEADS, "mV", "NON_FINITE_SAMPLES"))
    flat = signal.copy()
    flat[:, 4] = 0
    ecg_cases.append(("flat_lead", times, flat, ecg.PTBXL_LEADS, "mV", "SIGNAL_QUALITY_FLATLINE"))
    for name, sample_times, samples, leads, unit, expected in ecg_cases:
        content = csv_bytes(sample_times, samples, leads)
        try:
            record = ecg.check_record(ecg.read_csv(content, unit), contract)
            observed = None
            if name == "valid_uV_reverse_order" and not np.allclose(record.signal_mv, signal, atol=1e-7):
                observed = "PHYSICAL_SAMPLE_PARITY_MISMATCH"
        except ecg.EcgInputError as error:
            observed = error.code
        results.append({"case": name, "layer": "ECG_READER_CONTRACT", "input_sha256": hashlib.sha256(content).hexdigest(),
                        "expected": expected or "ACCEPTED", "observed": observed or "ACCEPTED", "passed": observed == expected})

    dicom_cases = [
        ("valid_head_ct_tag", "CT", "HEAD", "HEAD_CT", None),
        ("wrong_mr_declared_ct", "MR", "HEAD", "HEAD_CT", "DICOM_MODALITY_CONTRADICTS_DECLARATION"),
        ("wrong_knee_declared_head", "CT", "KNEE", "HEAD_CT", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
        ("wrong_hand_declared_chest", "DX", "HAND", "CHEST_XRAY", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
        ("valid_chest_xray_tag", "DX", "CHEST", "CHEST_XRAY", None),
        ("wrong_ct_declared_brain_mri", "CT", "BRAIN", "BRAIN_MRI_MULTISEQUENCE", "DICOM_MODALITY_CONTRADICTS_DECLARATION"),
        ("wrong_brain_declared_cardiac_mri", "MR", "BRAIN", "MRI", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
        ("wrong_head_declared_coronary", "XA", "HEAD", "ANGIOGRAPHY", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
        ("wrong_chest_declared_abdomen", "CT", "CHEST", "CT_ABDOMEN_VOLUME", "DICOM_BODY_PART_CONTRADICTS_DECLARATION"),
        ("missing_body_no_contradiction_not_verified", "CT", "", "HEAD_CT", None),
    ]
    with tempfile.TemporaryDirectory(prefix="medtwin-input-controls-") as temporary:
        scratch = Path(temporary)
        for name, modality, body, declared, expected in dicom_cases:
            path = scratch / f"{name}.dcm"
            meta = FileMetaDataset()
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
            meta.MediaStorageSOPInstanceUID = generate_uid()
            dataset = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
            dataset.Modality, dataset.BodyPartExamined = modality, body
            dataset.Rows, dataset.Columns = 2, 3
            dataset.save_as(path, enforce_file_format=True)
            observed = model_router.metadata_conflicts(declared, read_metadata(path))
            results.append({"case": name, "layer": "DICOM_METADATA_CONTRADICTION_ONLY", "expected": expected or "NO_KNOWN_TAG_CONTRADICTION",
                            "observed": observed or "NO_KNOWN_TAG_CONTRADICTION", "passed": observed == expected})
        path = scratch / "orientation.png"
        image = Image.new("RGB", (5, 7), "black")
        image.putpixel((0, 0), (255, 0, 0))
        exif = image.getexif()
        exif[0x0112] = 6
        image.save(path, exif=exif)
        upright, applied = open_raster(path)
        passed = applied == 6 and upright.size == (7, 5) and upright.getpixel((6, 0)) == (255, 0, 0)
        results.append({"case": "exif_6_source_landmark", "layer": "RASTER_COORDINATE_CONTROL", "expected": "EXACT_PIXEL_MAPPING",
                        "observed": "EXACT_PIXEL_MAPPING" if passed else "MISMATCH", "passed": passed})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/review-2026-11-13/input-contract-challenges.json")
    args = parser.parse_args()
    cases = run_challenges()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    sources = [ROOT / "backend/app/services/ecg_inference.py", ROOT / "backend/app/services/model_router.py",
               ROOT / "backend/app/services/model_inference.py", Path(__file__).resolve()]
    report = {
        "schema_version": "medtwin-input-contract-challenges-v1", "recorded_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": revision, "router_version": model_router.VERSION,
        "source_sha256": {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        "scope": "Synthetic technical reader/metadata/coordinate controls. No checkpoint loaded, no clinical accuracy or appearance/OOD evaluation.",
        "limitations": ["DICOM technical tags do not prove anatomy, protocol or image content.",
                         "Missing/unknown anatomy is not verified; source attestation and existing execution gates remain mandatory.",
                         "Real valid/wrong-modality model acceptance and false-refusal coverage require independent model-level input evaluation."],
        "summary": {"total": len(cases), "passed": sum(row["passed"] for row in cases), "failed": sum(not row["passed"] for row in cases)},
        "cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), **report["summary"]}))
    return 0 if all(row["passed"] for row in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
