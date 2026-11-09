"""One DICOM frame as the 8-bit raster a 2-D research model reads.

The 2-D models were trained on PNG/JPEG exports, so a DICOM frame is converted the way a viewer
exports it, and the conversion is recorded with the run:

- greyscale: Modality LUT (rescale slope/intercept or LUT), then the window. The window is the one
  the model's registry entry declares for DICOM input (``dicom_window``: centre, width and where the
  values come from) when there is one; otherwise the frame's own VOI (Window Center/Width with its
  VOI LUT Function, or the VOI LUT Sequence); otherwise the frame's full stored range.
  MONOCHROME1 is inverted after windowing so that higher attenuation is brighter, as in the exports.
- colour (RGB, YBR): decoded to RGB, unchanged otherwise. PALETTE COLOR is applied through its LUT.

The output grid equals the DICOM pixel grid (column, row); nothing is resampled, so model outputs are
in the frame's own pixel coordinates. The model's out-of-distribution reference still decides whether
the converted frame is like its training images; a declared window does not bypass it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image

# DICOM Modality (0008,0060) codes accepted for each declared input type. A frame whose tag names a
# different modality is refused before conversion; a frame without the tag is accepted with a warning.
DICOM_MODALITIES = {
    "CT": {"CT"},
    "HEAD_CT": {"CT"},
    "XRAY": {"CR", "DX", "RG"},
    "CHEST_XRAY": {"CR", "DX"},
    "ANGIOGRAPHY": {"XA", "RF"},
    "ENDOSCOPY": {"ES", "XC", "OT"},
    "MICROSCOPY": {"SM", "GM", "OT"},
}
COLOUR_INTERPRETATIONS = {"RGB", "YBR_FULL", "YBR_FULL_422", "YBR_ICT", "YBR_RCT", "YBR_PARTIAL_420"}
GREYSCALE_INTERPRETATIONS = {"MONOCHROME1", "MONOCHROME2"}
MAX_FRAME_PIXELS = 8192 * 8192


class DicomRasterError(ValueError):
    """The DICOM frame cannot be converted for a 2-D model."""


@dataclass
class DicomFrame:
    image: Image.Image
    provenance: dict[str, Any]


def _first(value: Any) -> Optional[float]:
    if value is None:
        return None
    if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
        if len(value) == 0:
            return None
        value = value[0]
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def window_linear(values: np.ndarray, centre: float, width: float, function: str) -> np.ndarray:
    """DICOM PS3.3 C.11.2.1.2: LINEAR, LINEAR_EXACT and SIGMOID windows to the range 0..1."""
    if function == "SIGMOID":
        return 1.0 / (1.0 + np.exp(-4.0 * (values - centre) / width))
    if function == "LINEAR_EXACT":
        return np.clip((values - (centre - width / 2.0)) / width, 0.0, 1.0)
    if width < 1:
        raise DicomRasterError(f"DICOM_WINDOW_INVALID: window width {width:g} is below 1 for a LINEAR window.")
    return np.clip((values - (centre - 0.5)) / (width - 1.0) + 0.5, 0.0, 1.0)


def frame_functional_values(dataset, index: int) -> dict[str, Any]:
    """Rescale and VOI of one frame of an enhanced multi-frame object (per-frame functional group first, then the
    shared group). Empty for classic objects, whose top-level attributes apply."""
    found: dict[str, Any] = {}
    groups = []
    per_frame = dataset.get("PerFrameFunctionalGroupsSequence")
    if per_frame is not None and index < len(per_frame):
        groups.append(per_frame[index])
    shared = dataset.get("SharedFunctionalGroupsSequence")
    if shared is not None and len(shared):
        groups.append(shared[0])
    for group in groups:
        transformation = group.get("PixelValueTransformationSequence")
        if transformation is not None and len(transformation) and "slope" not in found:
            item = transformation[0]
            if "RescaleSlope" in item or "RescaleIntercept" in item:
                found["slope"] = float(item.get("RescaleSlope", 1) or 1)
                found["intercept"] = float(item.get("RescaleIntercept", 0) or 0)
        voi = group.get("FrameVOILUTSequence")
        if voi is not None and len(voi) and "center" not in found:
            item = voi[0]
            if _first(item.get("WindowCenter")) is not None and _first(item.get("WindowWidth")) is not None:
                found["center"], found["width"] = _first(item.get("WindowCenter")), _first(item.get("WindowWidth"))
                found["function"] = str(item.get("VOILUTFunction") or "LINEAR").upper()
    return found


def modality_values(dataset, frame: np.ndarray, index: int) -> tuple[np.ndarray, dict[str, Any]]:
    """Stored values of one greyscale frame through its Modality LUT (rescale or LUT, functional groups included)."""
    from pydicom.pixels import apply_modality_lut

    functional = frame_functional_values(dataset, index)
    if "slope" in functional:
        values = frame.astype(np.float64) * functional["slope"] + functional["intercept"]
        source = "FUNCTIONAL_GROUP_RESCALE"
    else:
        values = apply_modality_lut(frame, dataset).astype(np.float64)
        source = "MODALITY_LUT_SEQUENCE" if "ModalityLUTSequence" in dataset else "TOP_LEVEL_RESCALE"
    return values, {**functional, "rescale_source": source}


def _greyscale(dataset, frame: np.ndarray, declared: Optional[dict], index: int = 0) -> tuple[np.ndarray, dict]:
    from pydicom.pixels import apply_voi_lut

    values, functional = modality_values(dataset, frame, index)
    rescaled = functional["rescale_source"] != "TOP_LEVEL_RESCALE" or float(dataset.get("RescaleSlope") or 1) != 1 \
        or float(dataset.get("RescaleIntercept") or 0) != 0
    window: dict[str, Any]
    if declared:
        centre, width = float(declared["center"]), float(declared["width"])
        function = str(declared.get("function") or "LINEAR_EXACT").upper()
        scaled = window_linear(values, centre, width, function)
        window = {"center": centre, "width": width, "function": function, "source": "MODEL_DECLARED_WINDOW",
                  "basis": declared.get("source", "")}
        if declared.get("rounding") == "floor":
            # The exporter truncated rather than rounded (measured for the RSNA PNGs); reproduce it exactly.
            window["rounding"] = "floor"
            inverted = str(dataset.get("PhotometricInterpretation") or "").upper() == "MONOCHROME1"
            scaled = 1.0 - scaled if inverted else scaled
            window.update(monochrome1_inverted=inverted, rescale_source=functional["rescale_source"])
            return np.floor(np.clip(scaled, 0.0, 1.0) * 255.0).astype(np.uint8), window
    elif "center" in functional:
        centre, width, function = functional["center"], functional["width"], functional["function"]
        if function not in ("LINEAR", "LINEAR_EXACT", "SIGMOID") or width <= 0:
            raise DicomRasterError(f"DICOM_WINDOW_INVALID: frame VOI {function} width {width:g}.")
        scaled = window_linear(values, centre, width, function)
        window = {"center": centre, "width": width, "function": function, "source": "DICOM_VOI_FRAME_FUNCTIONAL_GROUP"}
    elif "VOILUTSequence" in dataset and len(dataset.VOILUTSequence):
        item = dataset.VOILUTSequence[0]
        bits = int(item.LUTDescriptor[2]) if "LUTDescriptor" in item else 16
        scaled = np.clip(apply_voi_lut(values, dataset, index=0, prefer_lut=True).astype(np.float64) / float(2 ** bits - 1), 0.0, 1.0)
        window = {"function": "VOI_LUT_SEQUENCE", "lut_bits": bits, "source": "DICOM_VOI"}
    elif _first(dataset.get("WindowCenter")) is not None and _first(dataset.get("WindowWidth")) is not None:
        centre, width = _first(dataset.get("WindowCenter")), _first(dataset.get("WindowWidth"))
        function = str(dataset.get("VOILUTFunction") or "LINEAR").upper()
        if function not in ("LINEAR", "LINEAR_EXACT", "SIGMOID"):
            raise DicomRasterError(f"DICOM_VOI_FUNCTION_UNSUPPORTED: VOI LUT Function {function}.")
        if width <= 0:
            raise DicomRasterError(f"DICOM_WINDOW_INVALID: window width {width:g}.")
        scaled = window_linear(values, centre, width, function)
        window = {"center": centre, "width": width, "function": function, "source": "DICOM_VOI"}
    elif int(dataset.get("BitsStored") or 16) <= 8 and int(dataset.get("PixelRepresentation") or 0) == 0 and not rescaled:
        # 8-bit stored values without a VOI are shown as stored (0..255), as viewers and PNG exporters do.
        scaled = np.clip(values / 255.0, 0.0, 1.0)
        window = {"low": 0.0, "high": 255.0, "function": "IDENTITY", "source": "STORED_8_BIT_VALUES_NO_VOI"}
    else:
        low, high = float(values.min()), float(values.max())
        if high <= low:
            raise DicomRasterError("DICOM_FRAME_CONSTANT: every pixel of the frame has the same value.")
        scaled = (values - low) / (high - low)
        window = {"low": low, "high": high, "function": "LINEAR", "source": "FRAME_FULL_RANGE_NO_VOI"}
    inverted = str(dataset.get("PhotometricInterpretation") or "").upper() == "MONOCHROME1"
    if inverted:
        scaled = 1.0 - scaled
    window["monochrome1_inverted"] = inverted
    window["rescale_source"] = functional["rescale_source"]
    return np.round(scaled * 255.0).astype(np.uint8), window


def read_frame(path: Path, declared_input_type: str, frame_index: Optional[int] = None,
               declared_window: Optional[dict] = None) -> DicomFrame:
    """Convert one frame of a DICOM file for a 2-D model, recording how."""
    import pydicom

    try:
        dataset = pydicom.dcmread(str(path))
    except Exception as exc:
        raise DicomRasterError(f"DICOM_UNREADABLE: {type(exc).__name__}") from exc
    if "PixelData" not in dataset and "FloatPixelData" not in dataset and "DoubleFloatPixelData" not in dataset:
        raise DicomRasterError("DICOM_NO_PIXEL_DATA: the file holds no image (for example a structured report or presentation state).")
    warnings: list[str] = []
    tag = str(dataset.get("Modality") or "").strip().upper()
    allowed = DICOM_MODALITIES.get(declared_input_type)
    if allowed is None:
        raise DicomRasterError(f"DICOM_INPUT_TYPE_NOT_MAPPED: no DICOM modality is defined for {declared_input_type} models.")
    if tag and tag not in allowed:
        raise DicomRasterError(f"DICOM_MODALITY_MISMATCH: the file's Modality tag is {tag}; models for this input type take "
                               f"{', '.join(sorted(allowed))}.")
    if not tag:
        warnings.append("DICOM_MODALITY_TAG_ABSENT: the declared input type could not be checked against the file")
    rows, columns = int(dataset.get("Rows") or 0), int(dataset.get("Columns") or 0)
    if rows * columns == 0:
        raise DicomRasterError("DICOM_NO_PIXEL_DATA: Rows or Columns is missing.")
    if rows * columns > MAX_FRAME_PIXELS:
        raise DicomRasterError(f"DICOM_FRAME_TOO_LARGE: {columns} x {rows} pixels; the bound is {MAX_FRAME_PIXELS:,} pixels per frame.")
    frames = int(dataset.get("NumberOfFrames") or 1)
    if frames > 1 and frame_index is None:
        raise DicomRasterError(f"FRAME_INDEX_REQUIRED: the file holds {frames} frames; choose the frame to analyse (0 to {frames - 1}).")
    index = int(frame_index or 0)
    if not 0 <= index < frames:
        raise DicomRasterError(f"FRAME_INDEX_OUT_OF_RANGE: frame {index}; the file holds {frames} frame(s).")
    interpretation = str(dataset.get("PhotometricInterpretation") or "").upper()
    try:
        from pydicom.pixels import pixel_array

        frame = pixel_array(dataset, index=index if frames > 1 else None, raw=False)
    except Exception as exc:
        raise DicomRasterError(f"DICOM_PIXELS_UNDECODABLE: {type(exc).__name__} (the transfer syntax may need a codec that is not "
                               "installed)") from exc
    provenance: dict[str, Any] = {
        "source_container": "DICOM", "modality_tag": tag or None, "photometric_interpretation": interpretation,
        "frame_index": index, "frame_count": frames, "bits_stored": int(dataset.get("BitsStored") or 0),
        "pixel_grid": "Model input pixel (column, row) equals DICOM pixel (column, row); nothing is resampled.",
    }
    if interpretation in GREYSCALE_INTERPRETATIONS:
        if frame.ndim != 2:
            raise DicomRasterError(f"DICOM_FRAME_SHAPE: greyscale frame of shape {list(frame.shape)}.")
        pixels, window = _greyscale(dataset, frame, declared_window, index)
        provenance["window"] = window
        image = Image.fromarray(pixels, mode="L")
    elif interpretation in COLOUR_INTERPRETATIONS or interpretation == "PALETTE COLOR":
        if interpretation == "PALETTE COLOR":
            from pydicom.pixels import apply_color_lut

            frame = apply_color_lut(frame, dataset)
            bits = 16 if frame.dtype.itemsize > 1 else 8
            frame = (frame.astype(np.float64) / (2 ** bits - 1) * 255.0).round().astype(np.uint8)
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise DicomRasterError(f"DICOM_FRAME_SHAPE: colour frame of shape {list(frame.shape)}.")
        if frame.dtype != np.uint8:
            if int(dataset.get("BitsStored") or 8) > 8:
                raise DicomRasterError("DICOM_COLOUR_DEPTH_UNSUPPORTED: colour frames above 8 bits per sample are not converted.")
            frame = frame.astype(np.uint8)
        provenance["colour"] = "decoded to RGB (pydicom converts YBR to RGB); values unchanged"
        if declared_window:
            warnings.append("MODEL_DECLARED_WINDOW_NOT_APPLIED: the frame is colour; windows apply to greyscale frames only")
        image = Image.fromarray(np.ascontiguousarray(frame), mode="RGB")
    else:
        raise DicomRasterError(f"DICOM_PHOTOMETRIC_UNSUPPORTED: {interpretation or 'missing'}.")
    provenance["warnings"] = warnings
    return DicomFrame(image=image, provenance=provenance)
