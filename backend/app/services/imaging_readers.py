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
import re
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
    if suffix in (".svs", ".tif", ".tiff", ".ndpi"):
        return "WSI"
    raise ImagingReadError(f"Unsupported image container '{suffix}'.")


MAX_ITK_HEADER_BYTES = 65536
_NRRD_HEADER_END = re.compile(rb"\r?\n\r?\n")


def check_attached_data(path: Path, container: Optional[str] = None) -> None:
    """Refuse an NRRD or MetaImage file whose header points at a separate data file.

    ITK follows a 'data file' (NRRD) or 'ElementDataFile' (MetaImage) reference to any path on this
    machine, so an upload naming another local file would have that file's bytes read as voxels and
    shown. Only single-file uploads with the data attached after the header are read. ``container``
    is given when the path's suffix is not the upload's (an incoming temporary file)."""
    container = container or container_for(path)
    if container not in ("NRRD", "METAIMAGE"):
        return
    with open(path, "rb") as handle:
        head = handle.read(MAX_ITK_HEADER_BYTES)
    if container == "NRRD":
        end = _NRRD_HEADER_END.search(head)
        if end is None:
            raise ImagingReadError(f"NRRD_HEADER_UNTERMINATED: no blank line ends the header within {MAX_ITK_HEADER_BYTES} bytes.")
        for line in head[:end.start()].splitlines()[1:]:
            if line.startswith(b"#"):
                continue
            key = line.split(b":", 1)[0].strip().lower()
            if key in (b"data file", b"datafile"):
                raise ImagingReadError("NRRD_DETACHED_DATA_REFUSED: the header points at a separate data file; upload a single .nrrd "
                                       "with the data attached.")
        return
    for line in head.splitlines():
        key, separator, value = line.partition(b"=")
        if separator and key.strip().lower() == b"elementdatafile":
            if value.strip().upper() != b"LOCAL":
                raise ImagingReadError("METAIMAGE_DETACHED_DATA_REFUSED: ElementDataFile must be LOCAL (data attached after the header); "
                                       "detached .mhd/.raw pairs and references to other files are not read.")
            return
    raise ImagingReadError(f"METAIMAGE_HEADER_INCOMPLETE: no ElementDataFile field within {MAX_ITK_HEADER_BYTES} bytes.")


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


EXIF_ORIENTATION_TAG = 0x0112
# Orientation tags 5-8 include a quarter turn: the displayed image swaps width and height.
QUARTER_TURN_ORIENTATIONS = {5, 6, 7, 8}


def exif_orientation(image: Image.Image) -> int:
    """The EXIF orientation tag (1-8; 1 = stored upright, also when absent or invalid)."""
    try:
        value = int(image.getexif().get(EXIF_ORIENTATION_TAG, 1) or 1)
    except (TypeError, ValueError):
        return 1
    return value if 1 <= value <= 8 else 1


def open_raster(path: Path) -> tuple[Image.Image, int]:
    """Decode a PNG/JPEG/BMP upright, with its EXIF orientation applied.

    Browsers apply the orientation tag when they display the original bytes, so model input,
    returned pixel coordinates and the viewer must use the same upright grid; a phone photograph
    stored sideways would otherwise get its overlay rotated and stretched. Returns the loaded
    image and the tag that was applied."""
    from PIL import ImageOps

    with Image.open(path) as image:
        image.load()
        orientation = exif_orientation(image)
        upright = ImageOps.exif_transpose(image) if orientation != 1 else image.copy()
    return upright, orientation


def read_metadata(path: Path) -> dict[str, Any]:
    container = container_for(path)
    if container == "WSI":
        from app.services import wsi_reader

        try:
            slide = wsi_reader.describe(path)
        except wsi_reader.WsiError as exc:
            raise ImagingReadError(str(exc)) from exc
        mpp = slide["microns_per_pixel"]
        return {"container": "WSI", "dimensions": slide["dimensions"], "slices": 1, "wsi": slide,
                "spacing_mm": [mpp / 1000, mpp / 1000] if mpp else None,
                "spatial_metadata": "MICRONS_PER_PIXEL_FROM_SCANNER" if mpp else "NOT_AVAILABLE",
                "modality_tag": "SM", "body_part": None, "deidentification_warnings": []}
    if container == "RASTER":
        try:
            with Image.open(path) as image:
                width, height = image.size
                mode = image.mode
                orientation = exif_orientation(image)
        except Exception as exc:
            raise ImagingReadError(f"Image could not be decoded: {exc}") from exc
        if orientation in QUARTER_TURN_ORIENTATIONS:
            width, height = height, width
        return {
            "container": {".png": "PNG", ".bmp": "BMP"}.get(path.suffix.lower(), "JPEG"),
            "dimensions": [width, height],
            "exif_orientation": orientation,
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

    check_attached_data(path)
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
    if container == "WSI":
        from app.services import wsi_reader

        try:
            image, thumb = wsi_reader.thumbnail(path)
        except wsi_reader.WsiError as exc:
            raise ImagingReadError(str(exc)) from exc
        info.update({"slice_index": 0, "slice_count": 1, "wsi_thumbnail": thumb,
                     "display": "Thumbnail of the slide (a reduced pyramid level); full-resolution regions are read on request."})
        return wsi_reader.png(image), info
    if container == "DICOM":
        from app.services import dicom_raster

        dataset = _dicom(path, stop_before_pixels=False)
        # Frames are counted from the header, so colour multi-frame data (frames, rows, columns, 3) is indexed correctly.
        frames = max(1, int(dataset.get("NumberOfFrames") or 1))
        frame_index = min(max(int(index or 0), 0), frames - 1)
        try:
            from pydicom.pixels import pixel_array

            frame = pixel_array(dataset, index=frame_index if frames > 1 else None)
        except Exception as exc:
            raise ImagingReadError(f"DICOM pixel data cannot be decoded (transfer syntax may need an extra codec): {exc}") from exc
        interpretation = str(dataset.get("PhotometricInterpretation") or "").upper()
        spacing = dataset.get("PixelSpacing")
        info.update({"slice_index": frame_index, "slice_count": frames,
                     "pixel_spacing_mm": [float(spacing[1]), float(spacing[0])] if spacing else None,
                     "display_to_source": "Display pixel (column, row) equals source pixel (column, row); no resampling."})
        if frame.ndim == 3 or interpretation == "PALETTE COLOR":
            # Colour frames are shown as decoded (YBR converted to RGB), without a window.
            if interpretation == "PALETTE COLOR":
                from pydicom.pixels import apply_color_lut

                frame = apply_color_lut(frame, dataset)
                frame = (frame.astype(np.float64) / (65535.0 if frame.dtype.itemsize > 1 else 255.0) * 255.0).round()
            rgb = np.clip(frame, 0, 255).astype(np.uint8)
            buffer = io.BytesIO()
            Image.fromarray(np.ascontiguousarray(rgb), mode="RGB").save(buffer, format="PNG")
            info.update({"window": {"low": 0.0, "high": 255.0, "source": "COLOUR_AS_DECODED"}, "display_dimensions": [int(rgb.shape[1]), int(rgb.shape[0])]})
            return buffer.getvalue(), info
        values, functional = dicom_raster.modality_values(dataset, frame, frame_index)
        if center is None:
            if "center" in functional:
                center, width = functional["center"], functional["width"]
            elif "WindowCenter" in dataset and "WindowWidth" in dataset:
                center, width = dicom_raster._first(dataset.WindowCenter), dicom_raster._first(dataset.WindowWidth)
        image8, low, high, source = _window(values.astype(np.float32), center, width)
        if interpretation == "MONOCHROME1":
            image8 = 255 - image8
        rescaled_ct = str(dataset.get("Modality")) == "CT" and (functional["rescale_source"] != "TOP_LEVEL_RESCALE" or "RescaleIntercept" in dataset)
        info["rescale"] = {"source": functional["rescale_source"], "slope": functional.get("slope", float(dataset.get("RescaleSlope") or 1.0)),
                           "intercept": functional.get("intercept", float(dataset.get("RescaleIntercept") or 0.0)),
                           "units": "HU" if rescaled_ct else "STORED_VALUE_RESCALED"}
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
