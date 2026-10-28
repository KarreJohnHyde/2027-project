"""Check that the DICOM-series path feeds the cardiac MRI segmenter exactly what the NIfTI path does.

Each ACDC publisher test frame is written as a multi-file DICOM series (one MR slice per file,
geometry from the NIfTI header: in-plane pixel (column i, row j), slice k along the normal),
assembled by app.services.dicom_series, converted by volume_inference.from_series and segmented.
The input arrays, voxel spacing and predicted masks are compared with the NIfTI path
(volume_inference.read_volume) for the same frame. The series files are synthetic re-encodings of
public research frames in a temporary directory; nothing identifying is written. Writes counts
only to docs/validation/SERIES_INFERENCE_PARITY.json.

This proves the conversion path, not the orientation convention of scanner-native series: the
development NIfTI frames carry no orientation (see volume_inference.from_series).

  .venv\\Scripts\\python.exe scripts/verify_series_inference_parity.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services import dicom_series, model_inference, volume_inference  # noqa: E402
from app.services.model_registry import _resolve_artifact_path  # noqa: E402

OUTPUT = ROOT / "docs" / "validation" / "SERIES_INFERENCE_PARITY.json"


def write_series(image: np.ndarray, spacing: tuple[float, float, float], folder: Path) -> tuple[list[Path], float]:
    """One DICOM file per slice; returns the paths (shuffled, so ordering must come from geometry) and the
    largest absolute difference introduced by integer storage."""
    import pydicom
    from pydicom.dataset import FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

    dx, dy, dz = spacing
    integer = np.array_equal(image, np.round(image)) and image.min() >= -32768 and image.max() <= 32767
    slope = 1.0 if integer else float(np.abs(image).max()) / 32000.0 or 1.0
    stored = np.round(image / slope).astype(np.int16)
    series_uid = generate_uid()
    paths = []
    for k in range(image.shape[2]):
        dataset = pydicom.Dataset()
        dataset.file_meta = FileMetaDataset()
        dataset.file_meta.MediaStorageSOPClassUID = MRImageStorage
        dataset.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        dataset.SOPClassUID = MRImageStorage
        dataset.SOPInstanceUID = dataset.file_meta.MediaStorageSOPInstanceUID
        dataset.Modality = "MR"
        dataset.SeriesInstanceUID = series_uid
        dataset.InstanceNumber = k + 1
        dataset.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        dataset.ImagePositionPatient = [0.0, 0.0, round(k * dz, 6)]
        dataset.PixelSpacing = [dy, dx]  # row spacing, column spacing
        plane = np.ascontiguousarray(stored[:, :, k].T)  # rows j, columns i
        dataset.Rows, dataset.Columns = plane.shape
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = "MONOCHROME2"
        dataset.BitsAllocated = dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 1
        dataset.RescaleSlope = slope
        dataset.RescaleIntercept = 0
        dataset.PixelData = plane.tobytes()
        path = folder / f"slice_{k:03d}.dcm"
        dataset.save_as(path, enforce_file_format=True)
        paths.append(path)
    paths.reverse()  # input order must not matter
    return paths, float(np.abs(stored.astype(np.float64) * slope - image).max())


def main() -> int:
    model = model_inference.get_model("acdc_cardiac_mri_3d_unet")
    bundle = model["artifact_bundle"]
    envelope = volume_inference.load_envelope(_resolve_artifact_path(bundle["input_envelope_path"]), bundle["dataset_version"])
    manifest = json.loads((ROOT / bundle["split_manifest_path"]).read_text(encoding="utf-8"))
    root = Path(manifest["dataset_root"])
    root = root if root.is_absolute() else ROOT / root
    network, payload, device = model_inference.load_model(model)
    refused, results, started = Counter(), Counter(), time.perf_counter()
    storage_error, agreement = 0.0, []
    for case in (case for case in manifest["cases"] if case["split"] == "test"):
        try:
            nifti = volume_inference.read_volume(root / case["image_path"], envelope)
        except volume_inference.VolumeInputError as exc:
            refused.update(exc.codes)
            continue
        with tempfile.TemporaryDirectory() as folder:
            paths, error = write_series(nifti.image, nifti.spacing_mm, Path(folder))
            storage_error = max(storage_error, error)
            report = dicom_series.assemble_series(paths, load_pixels=True)
        if report["status"] != "ASSEMBLED":
            results["series_not_assembled"] += 1
            continue
        series = volume_inference.from_series(report["volume"], report["spacing_mm"], envelope)
        results["inputs_identical"] += int(np.array_equal(series.image, nifti.image) or (error > 0 and np.allclose(series.image, nifti.image, atol=error)))
        results["spacing_identical"] += int(np.allclose(series.spacing_mm, nifti.spacing_mm, rtol=1e-9))
        with model_inference._inference_lock:
            from_series = volume_inference.predict(network, payload, device, series)
            from_nifti = volume_inference.predict(network, payload, device, nifti)
        results["masks_identical"] += int(np.array_equal(from_series, from_nifti))
        agreement.append(float((from_series == from_nifti).mean()))
        results["compared"] += 1
    evidence = {
        "model_id": "acdc_cardiac_mri_3d_unet", "checkpoint_sha256": bundle["checkpoint_sha256"],
        "frames": "ACDC publisher test set (public research data), each re-encoded as a DICOM series in a temporary directory",
        "refused_by_envelope_gate": dict(refused), **dict(results),
        "voxel_agreement": {"min": min(agreement), "mean": float(np.mean(agreement))} if agreement else None,
        "integer_storage_max_abs_difference": storage_error,
        "precision": "float16 autocast on CUDA" if device.type == "cuda" else "float32 on CPU",
        "seconds": round(time.perf_counter() - started, 1),
        "scope": "Proves the series assembly and conversion feed the network the same voxels in the same order as the NIfTI path. "
                 "It does not establish the orientation convention of scanner-native series.",
    }
    OUTPUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
