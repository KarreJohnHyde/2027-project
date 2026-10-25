"""Training-pipeline correctness on deterministic synthetic fixtures: the PTB-XL WFDB
reader (physical units, header checksum, first sample, truncation) and the Cox /
survival evaluation maths (simulated hazard ratios, Breslow baseline, concordance,
Kaplan-Meier and the IPCW Brier score). No patient data are involved."""

import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("torch")
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml_training import ecg, survival  # noqa: E402


def _write_record(directory: Path, digital: np.ndarray, tamper: str | None = None) -> Path:
    (directory / "rec.dat").write_bytes(digital.astype("<i2").tobytes())
    lines = [f"rec 12 100 {digital.shape[0]}"]
    for column, lead in enumerate(ecg.LEADS):
        checksum = int(digital[:, column].astype(np.int64).sum()) % 65536
        initial = int(digital[0, column])
        if tamper == "checksum" and column == 3:
            checksum = (checksum + 1) % 65536
        if tamper == "initial" and column == 5:
            initial += 1
        lines.append(f"rec.dat 16 1000.0(0)/mV 16 0 {initial} {checksum} 0 {lead}")
    header = directory / "rec.hea"
    header.write_text("\n".join(lines) + "\n", encoding="ascii")
    return header


def test_wfdb_reader_returns_millivolts_and_rejects_corrupt_records(tmp_path):
    digital = np.random.default_rng(0).integers(-2000, 2000, size=(1000, 12)).astype(np.int16)
    signal = ecg.read_record(_write_record(tmp_path, digital))
    assert signal.shape == (1000, 12)
    np.testing.assert_allclose(signal, digital / 1000.0, atol=1e-6)
    for tamper in ("checksum", "initial"):
        with pytest.raises(ecg.WfdbError):
            ecg.read_record(_write_record(tmp_path, digital, tamper))
    header = _write_record(tmp_path, digital)
    (tmp_path / "rec.dat").write_bytes(digital.astype("<i2").tobytes()[:-2])
    with pytest.raises(ecg.WfdbError):
        ecg.read_record(header)


def test_cox_recovers_simulated_hazard_ratios_and_baseline_hazard():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(3000, 2))
    beta = np.array([0.6, -0.4])
    event_time = rng.exponential(1 / (0.05 * np.exp(X @ beta)))
    censor_time = rng.exponential(30, size=len(X))
    time, event = np.minimum(event_time, censor_time), (event_time <= censor_time).astype(int)
    fitted = survival.cox_fit(X, time, event, 0.0)
    assert np.allclose(fitted, beta, atol=0.08)
    times, cumulative = survival.breslow(X, time, event, fitted)
    assert abs(cumulative[np.searchsorted(times, 20.0) - 1] - 1.0) < 0.1  # true H0(20) = 0.05 * 20


def test_concordance_kaplan_meier_and_brier_reference_values():
    time = np.array([1.0, 2.0, 3.0, 4.0])
    event = np.ones(4, dtype=int)
    assert survival.harrell_c(time, event, np.array([4.0, 3.0, 2.0, 1.0])) == 1.0  # higher risk dies earlier
    assert survival.harrell_c(time, event, np.array([1.0, 2.0, 3.0, 4.0])) == 0.0
    _, surv = survival.kaplan_meier(time, event)
    assert np.allclose(surv, [0.75, 0.5, 0.25, 0.0])
    # Without censoring every IPCW weight is 1, so the Brier score is the plain mean squared error.
    predicted_survival = np.array([0.1, 0.4, 0.6, 0.9])
    expected = np.mean([0.1 ** 2, 0.4 ** 2, (1 - 0.6) ** 2, (1 - 0.9) ** 2])  # at t = 2.5 subjects 1-2 died, 3-4 alive
    assert abs(survival.ipcw_brier(time, event, predicted_survival, 2.5, (np.array([]), np.array([]))) - expected) < 1e-12
