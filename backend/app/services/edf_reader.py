"""EDF, EDF+ and BDF/BDF+ recordings (EEG and other physiological signals): exact structural
reading and a waveform preview. No model is applied.

The header's local patient and recording identification fields are never returned, stored in
findings or logged; only whether they are empty, anonymised ("X X X X" in EDF+) or filled is
reported, so a filled field can be flagged against the upload's de-identification attestation.
Annotation texts (EDF+ TALs) pass through the same de-identification as report text.

Structure is checked before anything is decoded: header length, numeric fields, digital and
physical ranges, samples per record and the file size implied by the record count.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Optional

import numpy as np

EDF_EXTENSIONS = {".edf", ".bdf"}
ANNOTATION_LABELS = {"EDF Annotations", "BDF Annotations"}
MAX_PREVIEW_SECONDS = 60.0
MAX_PREVIEW_CHANNELS = 32
TAL = re.compile(rb"([+-]\d+(?:\.\d+)?)(?:\x15(\d+(?:\.\d+)?))?\x14((?:[^\x00]*?\x14)*)\x00")


class EdfError(ValueError):
    """The file is not a structurally valid EDF/BDF recording."""


@dataclass
class EdfSignal:
    index: int
    label: str
    transducer: str
    physical_dimension: str
    physical_min: float
    physical_max: float
    digital_min: int
    digital_max: int
    prefiltering: str
    samples_per_record: int
    sampling_rate_hz: float
    annotation: bool

    @property
    def gain(self) -> float:
        return (self.physical_max - self.physical_min) / (self.digital_max - self.digital_min)

    def summary(self) -> dict[str, Any]:
        return {
            "index": self.index, "label": self.label, "transducer": self.transducer, "physical_dimension": self.physical_dimension,
            "physical_min": self.physical_min, "physical_max": self.physical_max, "digital_min": self.digital_min,
            "digital_max": self.digital_max, "prefiltering": self.prefiltering, "samples_per_record": self.samples_per_record,
            "sampling_rate_hz": round(self.sampling_rate_hz, 6),
        }


@dataclass
class EdfHeader:
    format: str
    bytes_per_sample: int
    header_bytes: int
    records: int
    record_duration_s: float
    start: Optional[datetime]
    patient_field: str
    recording_field: str
    signals: list[EdfSignal] = field(default_factory=list)
    file_size: int = 0

    @property
    def record_bytes(self) -> int:
        return sum(signal.samples_per_record for signal in self.signals) * self.bytes_per_sample

    @property
    def data_signals(self) -> list[EdfSignal]:
        return [signal for signal in self.signals if not signal.annotation]


def _ascii(raw: bytes) -> str:
    return raw.decode("ascii", errors="replace").strip()


def _number(raw: bytes, name: str, integer: bool = False):
    text = _ascii(raw)
    try:
        return int(text) if integer else float(text)
    except ValueError as exc:
        raise EdfError(f"EDF_HEADER_FIELD_INVALID: {name} is not a number.") from exc


def _identification_state(text: str) -> str:
    if not text:
        return "EMPTY"
    if set(text.replace(" ", "")) <= {"X"}:
        return "ANONYMISED"
    return "FILLED_NOT_SHOWN"


def _start(date_field: str, time_field: str) -> Optional[datetime]:
    match_date = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{2})", date_field)
    match_time = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{2})", time_field)
    if not match_date or not match_time:
        return None
    day, month, year = (int(part) for part in match_date.groups())
    # EDF clipping date: years 85-99 are 1985-1999, 00-84 are 2000-2084.
    year += 1900 if year >= 85 else 2000
    try:
        return datetime.combine(date(year, month, day), time(*(int(part) for part in match_time.groups())))
    except ValueError:
        return None


def read_header(content: bytes, file_size: Optional[int] = None) -> EdfHeader:
    """Parse and check the fixed header and the signal headers."""
    if len(content) < 256:
        raise EdfError("EDF_TOO_SHORT: the file is shorter than the 256-byte EDF header.")
    version = content[:8]
    if version == b"\xffBIOSEMI":
        bytes_per_sample, family = 3, "BDF"
    elif _ascii(version) == "0":
        bytes_per_sample, family = 2, "EDF"
    else:
        raise EdfError("EDF_SIGNATURE_INVALID: not an EDF ('0') or BDF (0xFF 'BIOSEMI') file.")
    reserved = _ascii(content[192:236])
    variant = {"EDF+C": "EDF+C", "EDF+D": "EDF+D", "BDF+C": "BDF+C", "BDF+D": "BDF+D"}.get(reserved[:5], family)
    header_bytes = _number(content[184:192], "header byte count", integer=True)
    records = _number(content[236:244], "number of data records", integer=True)
    record_duration = _number(content[244:252], "data record duration")
    count = _number(content[252:256], "number of signals", integer=True)
    if count < 1 or count > 4096:
        raise EdfError("EDF_SIGNAL_COUNT_INVALID: the header declares no signals or an implausible number.")
    if header_bytes != 256 * (count + 1):
        raise EdfError(f"EDF_HEADER_LENGTH_MISMATCH: {header_bytes} header bytes declared, {256 * (count + 1)} expected for {count} signals.")
    if len(content) < header_bytes:
        raise EdfError("EDF_TOO_SHORT: the signal headers are incomplete.")
    if record_duration < 0:
        raise EdfError("EDF_RECORD_DURATION_INVALID: negative data-record duration.")

    def column(offset: int, width: int) -> list[bytes]:
        start = 256 + offset * count
        return [content[start + i * width:start + (i + 1) * width] for i in range(count)]

    widths = (("label", 16), ("transducer", 80), ("dimension", 8), ("physical_min", 8), ("physical_max", 8),
              ("digital_min", 8), ("digital_max", 8), ("prefiltering", 80), ("samples", 8), ("reserved", 32))
    columns: dict[str, list[bytes]] = {}
    offset = 0
    for name, width in widths:
        columns[name] = column(offset, width)
        offset += width
    signals = []
    for i in range(count):
        label = _ascii(columns["label"][i])
        annotation = label in ANNOTATION_LABELS
        samples = _number(columns["samples"][i], f"samples per record of signal {i + 1}", integer=True)
        physical_min = _number(columns["physical_min"][i], f"physical minimum of signal {i + 1}")
        physical_max = _number(columns["physical_max"][i], f"physical maximum of signal {i + 1}")
        digital_min = _number(columns["digital_min"][i], f"digital minimum of signal {i + 1}", integer=True)
        digital_max = _number(columns["digital_max"][i], f"digital maximum of signal {i + 1}", integer=True)
        if samples < 1:
            raise EdfError(f"EDF_SAMPLES_INVALID: signal {i + 1} has no samples per record.")
        if digital_max <= digital_min:
            raise EdfError(f"EDF_DIGITAL_RANGE_INVALID: signal {i + 1} digital maximum is not above its minimum.")
        if not annotation and physical_max == physical_min:
            raise EdfError(f"EDF_PHYSICAL_RANGE_INVALID: signal {i + 1} has equal physical minimum and maximum.")
        limit = 2 ** (8 * bytes_per_sample - 1)
        if digital_min < -limit or digital_max > limit - 1:
            raise EdfError(f"EDF_DIGITAL_RANGE_INVALID: signal {i + 1} digital range exceeds {8 * bytes_per_sample}-bit integers.")
        signals.append(EdfSignal(
            index=i, label=label, transducer=_ascii(columns["transducer"][i]), physical_dimension=_ascii(columns["dimension"][i]),
            physical_min=physical_min, physical_max=physical_max, digital_min=digital_min, digital_max=digital_max,
            prefiltering=_ascii(columns["prefiltering"][i]), samples_per_record=samples,
            sampling_rate_hz=samples / record_duration if record_duration > 0 else 0.0, annotation=annotation,
        ))
    header = EdfHeader(
        format=variant, bytes_per_sample=bytes_per_sample, header_bytes=header_bytes, records=records, record_duration_s=record_duration,
        start=_start(_ascii(content[168:176]), _ascii(content[176:184])), patient_field=_identification_state(_ascii(content[8:88])),
        recording_field=_identification_state(_ascii(content[88:168])), signals=signals, file_size=file_size if file_size is not None else len(content),
    )
    data_bytes = header.file_size - header_bytes
    if header.records == -1:  # recording still open when written: derive the count from the size
        if data_bytes % header.record_bytes:
            raise EdfError("EDF_SIZE_MISMATCH: the data length is not a whole number of data records.")
        header.records = data_bytes // header.record_bytes
    elif header.records < 0 or header.records * header.record_bytes != data_bytes:
        raise EdfError(f"EDF_SIZE_MISMATCH: {header.records} records of {header.record_bytes} bytes do not match {data_bytes} data bytes.")
    if record_duration == 0 and header.data_signals:
        raise EdfError("EDF_RECORD_DURATION_INVALID: a zero record duration is allowed only for annotation-only files.")
    return header


def _record_block(path: Path, header: EdfHeader, first: int, count: int) -> np.ndarray:
    with path.open("rb") as handle:
        handle.seek(header.header_bytes + first * header.record_bytes)
        raw = handle.read(count * header.record_bytes)
    data = np.frombuffer(raw, dtype=np.uint8).reshape(count, header.record_bytes)
    return data


def _decode(block: np.ndarray, bytes_per_sample: int) -> np.ndarray:
    if bytes_per_sample == 2:
        return block.view("<i2").astype(np.int32)
    triples = block.reshape(-1, 3).astype(np.int32)
    values = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)
    return np.where(values >= 1 << 23, values - (1 << 24), values)


def _signal_offsets(header: EdfHeader) -> list[int]:
    offsets, cursor = [], 0
    for signal in header.signals:
        offsets.append(cursor)
        cursor += signal.samples_per_record * header.bytes_per_sample
    return offsets


def annotations(path: Path, header: EdfHeader, limit: int = 500) -> list[dict[str, Any]]:
    """EDF+/BDF+ time-stamped annotations (texts are returned as recorded; callers de-identify)."""
    annotation_signals = [signal for signal in header.signals if signal.annotation]
    if not annotation_signals or header.records == 0:
        return []
    offsets = _signal_offsets(header)
    found: list[dict[str, Any]] = []
    batch = 256
    for first in range(0, header.records, batch):
        block = _record_block(path, header, first, min(batch, header.records - first))
        for row in block:
            for signal in annotation_signals:
                start = offsets[signal.index]
                raw = row[start:start + signal.samples_per_record * header.bytes_per_sample].tobytes()
                for match in TAL.finditer(raw):
                    texts = [text.decode("utf-8", errors="replace") for text in match.group(3).split(b"\x14") if text]
                    for text in texts:
                        found.append({"onset_s": float(match.group(1)), "duration_s": float(match.group(2)) if match.group(2) else None, "text": text})
                        if len(found) >= limit:
                            return found
    return found


def _significant(value) -> float:
    return float(f"{float(value):.6g}")


def preview(path: Path, header: EdfHeader, start_s: float = 0.0, duration_s: float = 10.0, channels: Optional[list[int]] = None,
            max_points: int = 1500) -> dict[str, Any]:
    """Physical values of a time window, reduced to a min/max envelope of at most ``max_points``
    pairs per channel so peaks survive the reduction."""
    if header.format.endswith("+D"):
        raise EdfError("EDF_DISCONTINUOUS: EDF+D/BDF+D records are not contiguous in time; the preview needs a continuous recording.")
    data_signals = header.data_signals
    if not data_signals or header.record_duration_s <= 0:
        raise EdfError("EDF_NO_SIGNALS: the file holds annotations only.")
    total = header.records * header.record_duration_s
    duration_s = float(min(max(duration_s, 0.1), MAX_PREVIEW_SECONDS))
    start_s = float(min(max(start_s, 0.0), max(total - duration_s, 0.0)))
    selected = [signal for signal in data_signals if channels is None or signal.index in channels][:MAX_PREVIEW_CHANNELS]
    if not selected:
        raise EdfError("EDF_CHANNELS_INVALID: none of the requested channels holds signal data.")
    first = int(start_s // header.record_duration_s)
    last = min(header.records, int(np.ceil((start_s + duration_s) / header.record_duration_s)))
    block = _record_block(path, header, first, max(last - first, 1))
    offsets = _signal_offsets(header)
    result = []
    for signal in selected:
        width = signal.samples_per_record * header.bytes_per_sample
        raw = np.ascontiguousarray(block[:, offsets[signal.index]:offsets[signal.index] + width]).reshape(-1)
        digital = _decode(raw, header.bytes_per_sample).astype(np.float64)
        physical = (digital - signal.digital_min) * signal.gain + signal.physical_min
        rate = signal.sampling_rate_hz
        begin = int(round((start_s - first * header.record_duration_s) * rate))
        values = physical[begin:begin + int(round(duration_s * rate))]
        bucket = max(1, int(np.ceil(len(values) / max_points)))
        usable = (len(values) // bucket) * bucket
        if usable:
            shaped = values[:usable].reshape(-1, bucket)
            lows, highs = shaped.min(axis=1), shaped.max(axis=1)
        else:
            lows = highs = values
        result.append({
            "index": signal.index, "label": signal.label, "unit": signal.physical_dimension, "sampling_rate_hz": round(rate, 6),
            "points": int(len(lows)), "seconds_per_point": bucket / rate if rate else None,
            "min": [_significant(v) for v in lows], "max": [_significant(v) for v in highs],
            "window_min": _significant(values.min()) if len(values) else None, "window_max": _significant(values.max()) if len(values) else None,
        })
    return {"start_s": start_s, "duration_s": duration_s, "recording_duration_s": total, "channels": result,
            "reduction": "min/max envelope per point; values in each channel's physical unit"}


def summary(path: Path, header: EdfHeader) -> dict[str, Any]:
    from app.services.nlp_processor import deidentify_text

    notes = [{**note, "text": deidentify_text(note["text"])[:200]} for note in annotations(path, header)]
    warnings = []
    if header.patient_field == "FILLED_NOT_SHOWN":
        warnings.append("The header's patient identification field is filled. It is not displayed or stored in findings, but the "
                        "file itself still holds it; confirm the export was de-identified.")
    if header.recording_field == "FILLED_NOT_SHOWN":
        warnings.append("The header's recording identification field is filled and is not displayed.")
    return {
        "format": header.format, "bytes_per_sample": header.bytes_per_sample, "records": header.records,
        "record_duration_s": header.record_duration_s, "duration_s": round(header.records * header.record_duration_s, 6),
        "start": header.start.isoformat(sep=" ") if header.start else None,
        "patient_identification_field": header.patient_field, "recording_identification_field": header.recording_field,
        "signals": [signal.summary() for signal in header.data_signals],
        "annotation_signals": sum(1 for signal in header.signals if signal.annotation),
        "annotations": notes, "warnings": warnings,
        "model": "NONE: no EEG or physiological-signal model is registered; the recording is shown as recorded.",
    }


def read_file_header(path: Path) -> EdfHeader:
    with path.open("rb") as handle:
        head = handle.read(256)
        if len(head) < 256:
            raise EdfError("EDF_TOO_SHORT: the file is shorter than the 256-byte EDF header.")
        count = _number(head[252:256], "number of signals", integer=True)
        handle.seek(0)
        content = handle.read(256 * (max(count, 0) + 1))
    return read_header(content, path.stat().st_size)


def analyze_signal_record(path: Path, file_hash: str) -> dict[str, Any]:
    """Analysis-job result for an EDF/BDF upload: the structure that was read, no model output."""
    header = read_file_header(path)
    info = summary(path, header)
    return {
        "modality": "SIGNAL", "category": f"{header.format} recording", "label": "READ_NO_MODEL",
        "probabilities": {}, "raw_confidence": None, "calibrated_confidence": None, "calibration_status": "NOT_APPLICABLE_NO_MODEL",
        "model_name": "edf-reader", "model_version": "1.0.0", "preprocessing_version": "none (physical units from header gains)",
        "evidence_status": "NOT_RUN", "failure_reason": "No EEG or physiological-signal model is registered; nothing was inferred.",
        "is_demo": False, "mapping_status": "NOT_MAPPABLE: WHOLE_RECORDING",
        "provenance": {"input_hash": file_hash, "format": header.format, "signals": len(info["signals"]),
                       "duration_s": info["duration_s"], "annotations": len(info["annotations"]),
                       "patient_identification_field": header.patient_field},
    }
