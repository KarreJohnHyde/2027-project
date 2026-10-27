"""12-lead ECG input for the PTB-XL research classifier: exact readers and applicability.

Signals are read without resampling, filtering, cropping or padding, so the network sees
what it saw in training (ml_training.ecg): physical millivolts at the trained sampling
rate and duration, leads in PTB-XL order, standardised per lead with the training-fold
mean and standard deviation stored in the checkpoint.

- WFDB: a header (.hea) and its single format-16 signal file (.dat), uploaded separately.
  Every lead is checked against the header's checksum and first sample, which also proves
  that the two uploads belong to the same record.
- CSV: a header row, one time column in seconds and one column per lead; the amplitude
  unit is declared by the requesting user because CSV carries none.

Anything outside the trained input contract is refused with a typed reason.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

PTBXL_LEADS = ["I", "II", "III", "AVR", "AVL", "AVF", "V1", "V2", "V3", "V4", "V5", "V6"]
# Input contract per registered preprocessing version; execution verifies that the
# checkpoint's own metadata agrees, so the API can check uploads without loading weights.
CONTRACTS = {"wfdb16-100hz-10s-leadstd-v1": {"sampling_rate_hz": 100.0, "samples": 1000, "leads": PTBXL_LEADS}}
SAMPLING_RATE_TOLERANCE = 0.005  # relative
# Signal-quality limits shared with the ECG preview validator (app.services.ecg_processor).
MAX_ABS_AMPLITUDE_MV = 10.0
MIN_LEAD_STD_MV = 1e-4
WFDB_INVALID_SAMPLE = -32768  # format 16 marker for a missing sample
UNIT_TO_MV = {"mv": 1.0, "uv": 1e-3, "µv": 1e-3, "v": 1e3}
TIME_COLUMNS = {"time", "t", "time_s", "time (s)", "time(s)", "time_sec", "seconds", "sec"}
INDEX_COLUMNS = {"sample", "index", "sample_index", "n"}
_GAIN = re.compile(r"^([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)(?:\(([+-]?\d+)\))?(?:/(\S+))?$")


class EcgInputError(ValueError):
    """The upload cannot be read exactly or lies outside the model's input contract."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code


@dataclass
class EcgRecord:
    signal_mv: np.ndarray  # (samples, leads), leads in `leads` order
    leads: list[str]
    sampling_rate_hz: float
    source_format: str
    notes: list[str] = field(default_factory=list)


def canonical_lead(name: str) -> str:
    """'Lead_I', 'aVR', 'v1' -> 'I', 'AVR', 'V1'; unknown names are returned upper-cased."""
    return re.sub(r"^LEAD[\s_-]*", "", name.strip().upper()).replace(" ", "")


def read_wfdb(header_bytes: bytes, signal_bytes: bytes) -> EcgRecord:
    try:
        text = header_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise EcgInputError("WFDB_HEADER_UNREADABLE", "the header is not ASCII text") from exc
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise EcgInputError("WFDB_HEADER_UNREADABLE", "the header has no record line")
    record = lines[0].split()
    if len(record) < 4:
        raise EcgInputError("WFDB_HEADER_INCOMPLETE", "the record line must state signals, sampling frequency and samples per signal")
    if "/" in record[0]:
        raise EcgInputError("UNSUPPORTED_WFDB_RECORD", "multi-segment records are not supported")
    try:
        signal_count, frequency, sample_count = int(record[1]), float(re.split(r"[/(]", record[2])[0]), int(record[3])
    except ValueError as exc:
        raise EcgInputError("WFDB_HEADER_UNREADABLE", "the record line is malformed") from exc
    if signal_count < 1 or sample_count < 1 or len(lines) < 1 + signal_count:
        raise EcgInputError("WFDB_HEADER_INCOMPLETE", "the header declares no samples or lists fewer signal lines than signals")

    gains, baselines, factors, initials, checksums, leads, files = [], [], [], [], [], [], set()
    for line in lines[1:1 + signal_count]:
        tokens = line.split()
        if len(tokens) < 7:
            raise EcgInputError("WFDB_HEADER_INCOMPLETE", "every signal line must carry gain, ADC fields, initial value and checksum, which pair the header with its signal file")
        if tokens[1] != "16":
            raise EcgInputError("UNSUPPORTED_WFDB_FORMAT", f"only plain format 16 is supported (found {tokens[1]})")
        gain_match = _GAIN.match(tokens[2])
        if gain_match is None:
            raise EcgInputError("WFDB_HEADER_UNREADABLE", "a signal gain field is malformed")
        gain = float(gain_match.group(1))
        if gain == 0:
            raise EcgInputError("UNCALIBRATED_SIGNAL", "a gain of 0 marks an uncalibrated signal")
        unit = (gain_match.group(3) or "mV").lower()  # WFDB: an omitted unit is millivolts
        if unit not in UNIT_TO_MV:
            raise EcgInputError("UNSUPPORTED_SIGNAL_UNIT", f"amplitude unit '{gain_match.group(3)}' is not a voltage")
        adc_zero = int(tokens[4])
        gains.append(gain)
        baselines.append(int(gain_match.group(2)) if gain_match.group(2) is not None else adc_zero)
        factors.append(UNIT_TO_MV[unit])
        initials.append(int(tokens[5]))
        checksums.append(int(tokens[6]))
        leads.append(canonical_lead(" ".join(tokens[8:])) if len(tokens) > 8 else "")
        files.add(tokens[0])
    if len(files) != 1:
        raise EcgInputError("UNSUPPORTED_WFDB_RECORD", "all signals must be stored in one signal file")
    if not all(leads):
        raise EcgInputError("LEAD_NAMES_MISSING", "every signal line must name its lead")

    if len(signal_bytes) != sample_count * signal_count * 2:
        raise EcgInputError("WFDB_SIGNAL_SIZE_MISMATCH", f"the signal file holds {len(signal_bytes) // 2} samples; the header declares {sample_count} x {signal_count}")
    digital = np.frombuffer(signal_bytes, dtype="<i2").reshape(sample_count, signal_count)
    for column, lead in enumerate(leads):
        if int(digital[0, column]) != initials[column] or int(digital[:, column].astype(np.int64).sum()) % 65536 != checksums[column] % 65536:
            raise EcgInputError("WFDB_CHECKSUM_MISMATCH", f"lead {lead} does not match the header's checksum or first sample; the signal file does not belong to this header")
    if np.any(digital == WFDB_INVALID_SAMPLE):
        raise EcgInputError("MISSING_SAMPLES", "the record marks samples as invalid (format-16 value -32768)")
    physical = (digital.astype(np.float32) - np.asarray(baselines, dtype=np.float32)) / np.asarray(gains, dtype=np.float32)
    if any(factor != 1.0 for factor in factors):
        physical = physical * np.asarray(factors, dtype=np.float32)
    return EcgRecord(physical, leads, frequency, "WFDB_FORMAT_16")


def read_csv(content: bytes, amplitude_unit: str) -> EcgRecord:
    if amplitude_unit.lower() not in UNIT_TO_MV:
        raise EcgInputError("AMPLITUDE_UNIT_NOT_DECLARED", "declare the CSV amplitude unit (mV or uV)")
    try:
        rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    except UnicodeDecodeError as exc:
        raise EcgInputError("CSV_UNREADABLE", "the CSV is not UTF-8 text") from exc
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if len(rows) < 3:
        raise EcgInputError("CSV_TOO_SHORT", "a header row and samples are required")
    header = [cell.strip() for cell in rows[0]]
    time_columns = [index for index, name in enumerate(header) if name.lower() in TIME_COLUMNS]
    if len(time_columns) != 1:
        raise EcgInputError("SAMPLING_RATE_NOT_DOCUMENTED", "the CSV needs exactly one time column in seconds (for example 'time_s'); the sampling rate is never assumed")
    lead_columns = [index for index, name in enumerate(header) if index not in time_columns and name.lower() not in INDEX_COLUMNS]
    try:
        values = np.asarray([[float(row[index]) for index in time_columns + lead_columns] for row in rows[1:]], dtype=np.float64)
    except (ValueError, IndexError) as exc:
        raise EcgInputError("NON_NUMERIC_VALUES", "every sample row needs a numeric time and a numeric value for every lead") from exc
    steps = np.diff(values[:, 0])
    if np.any(steps <= 0):
        raise EcgInputError("TIME_NOT_INCREASING", "time stamps must increase strictly")
    step = float(np.median(steps))
    if float(np.max(np.abs(steps - step))) > 0.01 * step:
        raise EcgInputError("IRREGULAR_SAMPLING", "time stamps are not uniformly spaced")
    leads = [canonical_lead(header[index]) for index in lead_columns]
    signal = (values[:, 1:] * UNIT_TO_MV[amplitude_unit.lower()]).astype(np.float32)
    return EcgRecord(signal, leads, 1.0 / step, "CSV", notes=[f"Amplitude unit declared by the requesting user: {amplitude_unit}."])


def check_record(record: EcgRecord, contract: dict) -> EcgRecord:
    """Refuse anything outside the trained contract; return the record in contract lead order."""
    expected = contract["leads"]
    duplicates = sorted({lead for lead in record.leads if record.leads.count(lead) > 1})
    if duplicates:
        raise EcgInputError("DUPLICATE_LEADS", ", ".join(duplicates))
    missing = [lead for lead in expected if lead not in record.leads]
    extra = [lead for lead in record.leads if lead not in expected]
    if missing or extra:
        raise EcgInputError("LEAD_SET_OUT_OF_SCOPE", f"the model takes exactly the 12 standard leads; missing {missing or 'none'}, unrecognised {extra or 'none'}")
    if abs(record.sampling_rate_hz - contract["sampling_rate_hz"]) > SAMPLING_RATE_TOLERANCE * contract["sampling_rate_hz"]:
        raise EcgInputError("SAMPLING_RATE_OUT_OF_SCOPE", f"{record.sampling_rate_hz:g} Hz; the model was trained on {contract['sampling_rate_hz']:g} Hz records and nothing is resampled")
    if record.signal_mv.shape[0] != contract["samples"]:
        seconds = contract["samples"] / contract["sampling_rate_hz"]
        raise EcgInputError("DURATION_OUT_OF_SCOPE", f"{record.signal_mv.shape[0]} samples; the model takes exactly {contract['samples']} ({seconds:g} s) and nothing is cropped or padded")
    ordered = record.signal_mv[:, [record.leads.index(lead) for lead in expected]]
    if not np.all(np.isfinite(ordered)):
        raise EcgInputError("NON_FINITE_SAMPLES", "the signal contains NaN or infinite values")
    peak = float(np.max(np.abs(ordered)))
    if peak > MAX_ABS_AMPLITUDE_MV:
        raise EcgInputError("SIGNAL_QUALITY_AMPLITUDE", f"peak |amplitude| {peak:.2f} mV exceeds {MAX_ABS_AMPLITUDE_MV:g} mV")
    flat = [lead for lead, value in zip(expected, ordered.std(axis=0)) if value < MIN_LEAD_STD_MV]
    if flat:
        raise EcgInputError("SIGNAL_QUALITY_FLATLINE", f"flat lead(s): {', '.join(flat)}")
    notes = list(record.notes)
    if record.leads != expected:
        notes.append("Leads were reordered by name into the PTB-XL order; samples were not altered.")
    return EcgRecord(np.ascontiguousarray(ordered), list(expected), record.sampling_rate_hz, record.source_format, notes)


def read_upload(primary: Path, companion: Path | None, amplitude_unit: str | None) -> EcgRecord:
    if primary.name.lower().endswith(".hea"):
        if companion is None:
            raise EcgInputError("WFDB_SIGNAL_FILE_REQUIRED", "select the record's .dat signal upload")
        return read_wfdb(primary.read_bytes(), companion.read_bytes())
    if primary.name.lower().endswith(".csv"):
        if not amplitude_unit:
            raise EcgInputError("AMPLITUDE_UNIT_NOT_DECLARED", "declare the CSV amplitude unit (mV or uV)")
        return read_csv(primary.read_bytes(), amplitude_unit)
    raise EcgInputError("UNSUPPORTED_ECG_FILE", "run the model on the WFDB header (.hea) or on a CSV record")


def input_report(record: EcgRecord) -> dict:
    return {"format": record.source_format, "sampling_rate_hz": round(record.sampling_rate_hz, 6), "samples": int(record.signal_mv.shape[0]),
            "duration_s": round(record.signal_mv.shape[0] / record.sampling_rate_hz, 6), "leads": record.leads,
            "peak_abs_amplitude_mv": round(float(np.max(np.abs(record.signal_mv))), 4), "notes": record.notes,
            "processing": "No resampling, filtering, cropping or padding; physical mV standardised per lead with the training-fold mean and SD."}


def build_network(classes: int, leads: int = 12):
    """The compact 1D ResNet of ml_training.ecg; strict state-dict loading verifies every
    parameter name and shape against the checkpoint."""
    import torch
    from torch import nn

    class Block(nn.Module):
        def __init__(self, channels_in: int, channels_out: int, kernel: int, stride: int):
            super().__init__()
            self.body = nn.Sequential(
                nn.Conv1d(channels_in, channels_out, kernel, stride, kernel // 2, bias=False), nn.BatchNorm1d(channels_out), nn.ReLU(inplace=True),
                nn.Conv1d(channels_out, channels_out, kernel, 1, kernel // 2, bias=False), nn.BatchNorm1d(channels_out))
            self.shortcut = nn.Identity() if channels_in == channels_out and stride == 1 else nn.Sequential(
                nn.Conv1d(channels_in, channels_out, 1, stride, bias=False), nn.BatchNorm1d(channels_out))
            self.act = nn.ReLU(inplace=True)

        def forward(self, x):
            return self.act(self.body(x) + self.shortcut(x))

    class ResNet1d(nn.Module):
        def __init__(self):
            super().__init__()
            self.stem = nn.Sequential(nn.Conv1d(leads, 64, 15, 2, 7, bias=False), nn.BatchNorm1d(64), nn.ReLU(inplace=True), nn.MaxPool1d(3, 2, 1))
            self.layers = nn.Sequential(Block(64, 64, 7, 1), Block(64, 128, 5, 2), Block(128, 128, 5, 1), Block(128, 256, 3, 2), Block(256, 256, 3, 1))
            self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(512, classes))

        def forward(self, x):
            features = self.layers(self.stem(x))
            return self.head(torch.cat([features.mean(-1), features.amax(-1)], dim=1))

    return ResNet1d()


def verify_contract(payload: dict, contract: dict) -> None:
    stored = {"sampling_rate_hz": float(payload["sampling_rate_hz"]), "samples": int(payload["samples"]), "leads": list(payload["leads"])}
    if stored != {**contract, "sampling_rate_hz": float(contract["sampling_rate_hz"])}:
        raise EcgInputError("CHECKPOINT_INPUT_CONTRACT_MISMATCH", "the checkpoint's input metadata differs from the registered preprocessing contract")


def classify(network, payload: dict, device, record: EcgRecord, precision) -> dict:
    import torch

    mean = np.asarray(payload["lead_mean_mv"], dtype=np.float32)[:, None]
    std = np.asarray(payload["lead_std_mv"], dtype=np.float32)[:, None]
    standardised = (record.signal_mv.T - mean) / std
    context, precision_note = precision
    with torch.no_grad(), context:
        logits = network(torch.from_numpy(np.ascontiguousarray(standardised))[None].to(device)).float().cpu().numpy()[0]
    classes = []
    for index, name in enumerate(payload["classes"]):
        a, b = payload["platt"][index]
        probability = float(1 / (1 + np.exp(-(a * logits[index] + b))))
        threshold = float(payload["thresholds"][index])
        classes.append({"class": name, "probability": probability, "threshold": threshold, "at_or_above_threshold": probability >= threshold})
    return {"type": "ecg_multilabel", "classes": classes, "positive_classes": [item["class"] for item in classes if item["at_or_above_threshold"]],
            "numeric_precision": precision_note,
            "probability_semantics": "Per-class Platt scaling fitted on the PTB-XL validation fold; not a calibrated clinical probability.",
            "threshold_semantics": "Per-class maximum-F1 thresholds chosen on the PTB-XL validation fold; classes are not mutually exclusive.",
            "input": input_report(record)}
