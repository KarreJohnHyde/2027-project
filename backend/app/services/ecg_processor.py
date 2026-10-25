"""
Digital ECG input validation and preview module for MedTwin.
Supports digital ECG CSV records (columns representing leads, e.g., Lead_I, Lead_II, Lead_V1).
Extracts sampling rate, channels, signal duration, and units.
Applies rigorous signal quality assessment:
- Rejection of flatlines, extreme amplitudes (>10mV), NaNs, or insufficient lengths.
- Lead-wise z-score normalization for a non-diagnostic waveform preview.

No trained ECG checkpoint is bundled with this repository, so valid signals are
accepted for preview only and inference remains explicitly NOT_RUN.
"""

import csv
from pathlib import Path
from typing import Dict, Any, List, Tuple
import numpy as np


class ECGQualityError(Exception):
    pass


def parse_and_validate_ecg(ecg_path: Path) -> Tuple[np.ndarray, List[str], int, float]:
    """
    Parses digital ECG CSV file and verifies signal integrity.
    Returns: (signals_array: shape (num_samples, num_channels), channel_names, sampling_rate_hz, duration_sec)
    """
    try:
        with open(ecg_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            header = [h.strip() for h in next(reader, [])]
            rows = []
            for r in reader:
                if r:
                    rows.append(r)
    except Exception as e:
        raise ECGQualityError(f"Malformed or unreadable ECG CSV: {str(e)}")

    if not rows or len(rows) < 50:
        raise ECGQualityError(f"Insufficient ECG samples ({len(rows)}). Minimum required: 50.")

    # Identify numeric columns
    num_cols = len(header) if header else (len(rows[0]) if rows else 0)
    col_data: Dict[int, List[float]] = {i: [] for i in range(num_cols)}
    valid_numeric_col_indices = []

    for c_idx in range(num_cols):
        is_num = True
        vals = []
        for r in rows:
            if c_idx >= len(r):
                continue
            try:
                vals.append(float(r[c_idx].strip()))
            except ValueError:
                is_num = False
                break
        if is_num and vals:
            col_data[c_idx] = vals
            valid_numeric_col_indices.append(c_idx)

    if not valid_numeric_col_indices:
        raise ECGQualityError("No numeric signal channels found in ECG file.")

    sampling_rate = 250
    lead_indices = []
    lead_names = []

    for c_idx in valid_numeric_col_indices:
        col_name = header[c_idx] if c_idx < len(header) else f"Channel_{c_idx+1}"
        if col_name.lower() in ("time", "t", "timestamp", "sample", "sec", "seconds"):
            time_vals = np.array(col_data[c_idx])
            diffs = np.diff(time_vals)
            pos_diffs = diffs[diffs > 0]
            if len(pos_diffs) > 10:
                mean_dt = float(np.mean(pos_diffs))
                if mean_dt > 0:
                    sampling_rate = int(round(1.0 / mean_dt))
        else:
            lead_indices.append(c_idx)
            lead_names.append(col_name)

    if not lead_indices:
        lead_indices = valid_numeric_col_indices
        lead_names = [header[c] if c < len(header) else f"Lead_{c+1}" for c in valid_numeric_col_indices]

    signal_list = [col_data[c] for c in lead_indices]
    signal_data = np.array(signal_list, dtype=float).T # Shape: (samples, channels)

    # 1. NaN / Infinite value check
    if np.isnan(signal_data).any() or np.isinf(signal_data).any():
        raise ECGQualityError("ECG record contains NaN or Infinite signal values. Corrupted transmission.")

    # 2. Extreme amplitude check (|amplitude| > 10.0 mV indicates sensor detachment or artifact)
    max_amp = np.max(np.abs(signal_data))
    if max_amp > 10.0:
        raise ECGQualityError(f"Signal amplitude exceeds physiological limit: {max_amp:.2f} mV (limit: 10 mV).")

    # 3. Flatline check (lead variance near zero)
    lead_stds = np.std(signal_data, axis=0)
    for idx, s in enumerate(lead_stds):
        if s < 1e-4:
            raise ECGQualityError(f"Channel '{lead_names[idx]}' is a flatline (standard deviation: {s:.6f}).")

    duration_sec = len(signal_data) / max(sampling_rate, 1)

    return signal_data, lead_names, sampling_rate, duration_sec


def preprocess_ecg(signals: np.ndarray) -> np.ndarray:
    """
    Applies lead-wise normalization.
    """
    mean = np.mean(signals, axis=0, keepdims=True)
    std = np.std(signals, axis=0, keepdims=True)
    std[std == 0] = 1.0
    normalized = (signals - mean) / std
    return normalized


def analyze_ecg_record(ecg_path: Path, file_hash: str) -> Dict[str, Any]:
    """
    Parses, validates, and preprocesses an ECG record for waveform preview.
    """
    signals, channels, fs, duration = parse_and_validate_ecg(ecg_path)
    processed_signals = preprocess_ecg(signals)

    # Prepare downsampled waveform preview for frontend rendering (max 300 points per lead)
    num_samples = len(signals)
    step = max(1, num_samples // 300)
    sampled_indices = list(range(0, num_samples, step))

    waveform_preview = []
    primary_lead_idx = 0
    for idx in sampled_indices:
        waveform_preview.append({
            "sample": int(idx),
            "time_sec": round(float(idx / fs), 3),
            "amplitude_raw": round(float(signals[idx, primary_lead_idx]), 3),
            "amplitude_norm": round(float(processed_signals[idx, primary_lead_idx]), 3)
        })

    reason = "No compatible, validated ECG-classification checkpoint is configured."

    return {
        "modality": "ECG",
        "category": "Digital ECG Input",
        "label": "MODEL_UNAVAILABLE",
        "probabilities": {},
        "raw_confidence": None,
        "calibrated_confidence": None,
        "calibration_status": "NOT_APPLICABLE_MODEL_UNAVAILABLE",
        "signal_metadata": {
            "sampling_rate_hz": fs,
            "duration_seconds": round(duration, 2),
            "total_samples": num_samples,
            "channels": channels,
            "primary_lead": channels[primary_lead_idx],
            "signal_quality": "INPUT_VALIDATION_PASSED_NONDIAGNOSTIC"
        },
        "waveform_preview": waveform_preview,
        "model_name": "UNCONFIGURED",
        "model_version": "NONE",
        "preprocessing_version": "LeadWiseZScorePreviewOnly",
        "evidence_status": "NOT_RUN",
        "failure_reason": reason,
        "is_demo": False,
        "provenance": {
            "input_hash": file_hash,
            "channels_count": len(channels),
            "fs": fs,
            "inference_status": "NOT_RUN",
            "reason": reason,
        }
    }
