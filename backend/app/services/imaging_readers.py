"""Readers for uploaded medical images and volumes.

Supported containers: DICOM Part 10 (single and multi-frame), NIfTI-1
(.nii, .nii.gz), NRRD, MetaImage (.mha) and PNG/JPEG/BMP. Readers return
technical metadata only. DICOM patient-identifying elements are never
returned; their presence is reported as a de-identification warning.

Rendering produces an 8-bit PNG of one slice for display. Window/level is
applied to rescaled values (Hounsfield units for CT when the tags provide a
rescale); the mapping from display pixels back to source voxel indices and
physical spacing is returned with every slice.
"""

from __future__ import annotations

import gzip
import io
import struct
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

MAX_VOXEL_BYTES = 1_500_000_000
IDENTIFYING_DICOM_KEYWORDS = (
    "PatientName", "PatientID", "PatientBirthDate", "PatientAddress", "PatientTelephoneNumbers",
    "OtherPatientIDs", "OtherPatientNames", "ReferringPhysicianName", "InstitutionName", "AccessionNumber",
)
TECHNICAL_DICOM_KEYWORDS = (
    "Modality", "BodyPartExamined", "StudyDescription", "SeriesDescription", "Manufacturer", "ManufacturerModelName",
    "Rows", "Columns", "NumberOfFrames", "PixelSpacing", "SliceThickness", "SpacingBetweenSlices", "ImageOrientationPatient",
    "ImagePositionPatient", "PhotometricInterpretation", "BitsAllocated", "BitsStored", "PixelRepresentation", "SamplesPerPixel",
    "RescaleSlope", "RescaleIntercept", "WindowCenter", "WindowWidth", "KVP", "MagneticFieldStrength", "EchoTime", "RepetitionTime",
    "SOPClassUID", "TransferSyntaxUID", "ContrastBolusAgent", "PatientPosition", "ViewPosition", "Laterality", "ImageLaterality",
)

# DICOM BodyPartExamined (defined terms) -> studio systems, as a schematic association only.
BODY_PART_SYSTEMS = {
    "CHEST": ["lungs", "heart"], "THORAX": ["lungs", "heart"], "LUNG": ["lungs"], "HEART": ["heart"], "BREAST": [],
    "HEAD": ["brain"], "BRAIN": ["brain"], "SKULL": ["skeletal", "brain"], "NECK": [],
    "ABDOMEN": ["liver", "pancreas", "intestines", "kidneys"], "LIVER": ["liver"], "PANCREAS": ["pancreas"],
    "KIDNEY": ["kidneys"], "COLON": ["intestines"], "PELVIS": ["skeletal", "intestines"], "CHESTABDOMEN": ["lungs", "heart", "liver", "pancreas", "intestines", "kidneys"],
    "CSPINE": ["skeletal", "nervous"], "TSPINE": ["skeletal", "nervous"], "LSPINE": ["skeletal", "nervous"], "SPINE": ["skeletal", "nervous"],
    "KNEE": ["skeletal"], "HIP": ["skeletal"], "SHOULDER": ["skeletal"], "ELBOW": ["skeletal"], "WRIST": ["skeletal"], "HAND": ["skeletal"],
    "ANKLE": ["skeletal"], "FOOT": ["skeletal"], "EXTREMITY": ["skeletal"], "LEG": ["skeletal"], "ARM": ["skeletal"], "WHOLEBODY": ["hybrid"],
}


class ImagingReadError(ValueError):
    """Raised when an image cannot be read safely."""


def container_for(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".nii.gz") or name.endswith(".nii"):
        return "NIFTI"
    suffix = path.suffix.lower()
    if suffix == ".dcm":
        return "DICOM"
    if suffix == ".nrrd":
        return "NRRD"
    if suffix == ".mha":
        return "METAIMAGE"
    if suffix in (".png", ".jpg", ".jpeg", ".bmp"):
        return "RASTER"
    raise ImagingReadError(f"Unsupported image container '{suffix}'.")


def _dicom(path: Path, stop_before_pixels: bool = True):
    import pydicom

    try:
        return pydicom.dcmread(str(path), stop_before_pixels=stop_before_pixels)
    except Exception as exc:
        raise ImagingReadError(f"DICOM could not be parsed: {exc}") from exc


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        return [_json_value(item) for item in value]
    if isinstance(value, (int, float, str)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def _nifti_expected_bytes(path: Path) -> int:
    """Read dims and bit depth from the NIfTI header without loading voxels."""
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    with opener(path, "rb") as handle:
        header = handle.read(352)
    if len(header) < 348:
        raise ImagingReadError("NIfTI header is truncated.")
    for endian in ("<", ">"):
        sizeof_hdr = struct.unpack(f"{endian}i", header[:4])[0]
        if sizeof_hdr == 348:
            dims = struct.unpack(f"{endian}8h", header[40:56])
            bitpix = struct.unpack(f"{endian}h", header[72:74])[0]
            break
    else:
        raise ImagingReadError("Only NIfTI-1 headers are accepted.")
    count = 1
    for dim in dims[1 : 1 + max(1, min(dims[0], 7))]:
        count *= max(1, int(dim))
    return count * max(1, bitpix // 8)


def _guard_size(expected_bytes: int) -> None:
    if expected_bytes > MAX_VOXEL_BYTES:
        raise ImagingReadError(f"Volume would need {expected_bytes / 1e9:.2f} GB in memory; the safety bound is {MAX_VOXEL_BYTES / 1e9:.1f} GB.")


def read_metadata(path: Path) -> dict[str, Any]:
    container = container_for(path)
    if container == "RASTER":
        try:
            with Image.open(path) as image:
                width, height = image.size
                mode = image.mode
        except Exception as exc:
            raise ImagingReadError(f"Image could not be decoded: {exc}") from exc
        return {
            "container": {".png": "PNG", ".bmp": "BMP"}.get(path.suffix.lower(), "JPEG"),
            "dimensions": [width, height],
            "pixel_mode": mode,
            "spacing_mm": None,
            "spatial_metadata": "NOT_AVAILABLE_RASTER_IMAGE",
            "modality_tag": None,
            "body_part": None,
            "slices": 1,
            "deidentification_warnings": [],
        }
    if container == "DICOM":
        dataset = _dicom(path)
        technical = {keyword: _json_value(dataset.get(keyword)) for keyword in TECHNICAL_DICOM_KEYWORDS if keyword in dataset}
        try:
            technical["TransferSyntaxUID"] = str(dataset.file_meta.TransferSyntaxUID)
        except AttributeError:
            pass
        warnings = [keyword for keyword in IDENTIFYING_DICOM_KEYWORDS if keyword in dataset and str(dataset.get(keyword) or "").strip()]
        frames = int(dataset.get("NumberOfFrames") or 1)
        spacing = technical.get("PixelSpacing")
        body_part = str(dataset.get("BodyPartExamined") or "").strip().upper() or None
        return {
            "container": "DICOM",
            "dimensions": [technical.get("Columns"), technical.get("Rows")],
            "slices": frames,
            "spacing_mm": [float(spacing[1]), float(spacing[0])] if isinstance(spacing, list) and len(spacing) == 2 else None,
            "spatial_metadata": "DICOM_PATIENT_COORDINATES" if "ImagePositionPatient" in technical and "ImageOrientationPatient" in technical else "PIXEL_SPACING_ONLY" if spacing else "NOT_AVAILABLE",
            "modality_tag": technical.get("Modality"),
            "body_part": body_part,
            "body_part_systems": BODY_PART_SYSTEMS.get((body_part or "").replace(" ", ""), []),
            "technical_tags": technical,
            "deidentification_warnings": [f"{keyword} is present and non-empty" for keyword in warnings],
        }
    if container == "NIFTI":
        _guard_size(_nifti_expected_bytes(path))
        import nibabel as nib

        try:
            image = nib.load(str(path))
        except Exception as exc:
            raise ImagingReadError(f"NIfTI could not be parsed: {exc}") from exc
        header = image.header
        # NIfTI stores pixdim as float32; round away representation noise.
        zooms = [round(float(value), 6) for value in header.get_zooms()[:3]]
        return {
            "container": "NIFTI",
            "dimensions": [int(value) for value in image.shape],
            "slices": int(image.shape[2]) if len(image.shape) >= 3 else 1,
            "spacing_mm": zooms,
            "orientation": "".join(nib.aff2axcodes(image.affine)),
            "affine": [[round(float(value), 6) for value in row] for row in image.affine],
            "qform_code": int(header["qform_code"]),
            "sform_code": int(header["sform_code"]),
            "data_type": str(header.get_data_dtype()),
            "spatial_metadata": "NIFTI_AFFINE" if int(header["sform_code"]) > 0 or int(header["qform_code"]) > 0 else "AFFINE_UNSPECIFIED",
            "modality_tag": None,
            "body_part": None,
            "deidentification_warnings": [],
        }
    import SimpleITK as sitk

    try:
        reader = sitk.ImageFileReader()
        reader.SetFileName(str(path))
        reader.ReadImageInformation()
    except Exception as exc:
        raise ImagingReadError(f"{container} could not be parsed: {exc}") from exc
    size = list(reader.GetSize())
    # Conservative bound: assume 8 bytes per component (float64).
    _guard_size(int(np.prod(size)) * int(reader.GetNumberOfComponents()) * 8)
    return {
        "container": container,
        "dimensions": size,
        "slices": size[2] if len(size) >= 3 else 1,
        "spacing_mm": [float(value) for value in reader.GetSpacing()],
        "origin_mm": [float(value) for value in reader.GetOrigin()],
        "direction": [float(value) for value in reader.GetDirection()],
        "data_type": sitk.GetPixelIDValueAsString(reader.GetPixelID()),
        "spatial_metadata": "ITK_PHYSICAL_SPACE",
        "modality_tag": None,
        "body_part": None,
        "deidentification_warnings": [],
    }


def _volume(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Load a 3D array as (z, y, x) plus spacing information."""
    container = container_for(path)
    if container == "NIFTI":
        _guard_size(_nifti_expected_bytes(path))
        import nibabel as nib

        image = nib.load(str(path))
        data = np.asanyarray(image.dataobj)
        if data.ndim == 4:
            data = data[..., 0]
        if data.ndim == 2:
            data = data[:, :, None]
        array = np.transpose(data, (2, 1, 0))
        zooms = image.header.get_zooms()
        return array.astype(np.float32), {"spacing_xyz_mm": [float(zooms[0]), float(zooms[1]), float(zooms[2]) if len(zooms) > 2 else None], "array_axes": "z,y,x (voxel index order)"}
    import SimpleITK as sitk

    read_metadata(path)  # applies the memory-safety bound before voxels are read
    image = sitk.ReadImage(str(path))
    array = sitk.GetArrayFromImage(image)
    if array.ndim == 2:
        array = array[None, :, :]
    if array.ndim == 4:
        array = array[..., 0]
    return array.astype(np.float32), {"spacing_xyz_mm": [float(value) for value in image.GetSpacing()], "array_axes": "z,y,x (ITK index order)"}


def _window(array: np.ndarray, center: Optional[float], width: Optional[float]) -> tuple[np.ndarray, float, float, str]:
    finite = array[np.isfinite(array)]
    if finite.size == 0:
        raise ImagingReadError("Image contains no finite values.")
    if center is None or width is None or width <= 0:
        low, high = np.percentile(finite, [0.5, 99.5])
        source = "PERCENTILE_0.5_99.5"
    else:
        low, high = center - width / 2.0, center + width / 2.0
        source = "REQUESTED_OR_DICOM_WINDOW"
    if high <= low:
        high = low + 1.0
    scaled = np.clip((array - low) / (high - low), 0.0, 1.0)
    return (scaled * 255.0).astype(np.uint8), float(low), float(high), source


def render_slice(path: Path, index: Optional[int] = None, axis: str = "axial", center: Optional[float] = None, width: Optional[float] = None) -> tuple[bytes, dict[str, Any]]:
    container = container_for(path)
    info: dict[str, Any] = {"container": container}
    if container == "RASTER":
        raise ImagingReadError("Raster images are displayed from their original bytes.")
    if container == "DICOM":
        dataset = _dicom(path, stop_before_pixels=False)
        try:
            pixels = dataset.pixel_array.astype(np.float32)
        except Exception as exc:
            raise ImagingReadError(f"DICOM pixel data cannot be decoded (transfer syntax may need an extra codec): {exc}") from exc
        frames = pixels.shape[0] if pixels.ndim == 3 and int(dataset.get("NumberOfFrames") or 1) > 1 else 1
        frame_index = min(max(int(index or 0), 0), frames - 1)
        frame = pixels[frame_index] if frames > 1 else pixels
        if frame.ndim == 3:
            frame = frame.mean(axis=2)
        slope = float(dataset.get("RescaleSlope") or 1.0)
        intercept = float(dataset.get("RescaleIntercept") or 0.0)
        frame = frame * slope + intercept
        if center is None and "WindowCenter" in dataset and "WindowWidth" in dataset:
            wc, ww = dataset.WindowCenter, dataset.WindowWidth
            center = float(wc[0] if hasattr(wc, "__len__") and not isinstance(wc, str) else wc)
            width = float(ww[0] if hasattr(ww, "__len__") and not isinstance(ww, str) else ww)
        image8, low, high, source = _window(frame, center, width)
        if str(dataset.get("PhotometricInterpretation") or "") == "MONOCHROME1":
            image8 = 255 - image8
        spacing = dataset.get("PixelSpacing")
        info.update({
            "slice_index": frame_index,
            "slice_count": frames,
            "rescale": {"slope": slope, "intercept": intercept, "units": "HU" if str(dataset.get("Modality")) == "CT" and "RescaleIntercept" in dataset else "STORED_VALUE_RESCALED"},
            "pixel_spacing_mm": [float(spacing[1]), float(spacing[0])] if spacing else None,
            "display_to_source": "Display pixel (column, row) equals source pixel (column, row); no resampling.",
        })
    else:
        volume, spacing = _volume(path)
        axes = {"axial": 0, "coronal": 1, "sagittal": 2}
        if axis not in axes:
            raise ImagingReadError("Axis must be axial, coronal or sagittal (voxel-index planes).")
        dim = axes[axis]
        count = volume.shape[dim]
        slice_index = count // 2 if index is None else min(max(int(index), 0), count - 1)
        plane = np.take(volume, slice_index, axis=dim)
        plane = np.flipud(plane) if dim != 0 else plane
        image8, low, high, source = _window(plane, center, width)
        info.update({
            "slice_index": slice_index,
            "slice_count": int(count),
            "axis": axis,
            "plane_definition": "Voxel-index plane; not resampled to patient anatomical planes.",
            **spacing,
            "display_to_source": "Rows are flipped vertically for coronal/sagittal display; columns are not resampled.",
        })
    buffer = io.BytesIO()
    Image.fromarray(image8).save(buffer, format="PNG")
    info.update({"window": {"low": low, "high": high, "source": source}, "display_dimensions": [int(image8.shape[1]), int(image8.shape[0])]})
    return buffer.getvalue(), info
