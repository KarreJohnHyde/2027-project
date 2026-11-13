# MedTwin input routing and signal preprocessing — 13 November 2026

## Implemented changes

The automatic-selection router is now `capability-router-v2`. An explicit source declaration no longer skips DICOM metadata checks. Known modality or body-part contradictions cause an explicit refusal before a model is selected. Examples include MR declared as head CT, knee CT declared as head CT, hand radiography declared as chest radiography, brain MR declared as cardiac MRI and head angiography declared as coronary angiography.

The same contradiction function is called from `model_inference.check_input`, so choosing a checkpoint directly does not bypass the checks. Its imports are lazy to avoid an import cycle, and reading technical metadata does not decode pixel arrays. Existing direct-inference `DICOM_MODALITY_MISMATCH` reason compatibility is preserved. Existing model eligibility, source attestation, DICOM conversion, image-quality and appearance/OOD execution gates remain in place.

Missing or unknown body-part metadata is **not verified anatomy**. It remains subject to declaration and execution gates. Technical tags can be wrong; no automatic medical-image classifier or new general modality-recognition model is claimed.

Digital ECG input validation now rejects:

- NaN/Inf timestamps before sampling-rate inference.
- Nonfinite/nonpositive WFDB or in-memory sampling rates.
- Nonfinite/zero ADC gain.
- Missing/extra CSV cells, nonfinite amplitudes and values that overflow physical-millivolt representation.
- A signal array whose dimensions do not match its named leads.

This fixes a concrete NaN loophole: comparisons involving a NaN sampling rate had previously evaluated false, allowing the numerical sampling-rate check to be bypassed. Existing 100 Hz / 1,000 samples / 12-lead contracts, lead-name reordering, mV conversion, flatline and amplitude limits, no-resampling behavior and research-only outputs are retained.

No checkpoint, weights, clinical activation flag, eligibility decision, patient database or preprocessing normalization statistics was changed.

## Files

- `backend/app/services/model_router.py`: source-tag contradictions and consistent selection behavior.
- `backend/app/services/ecg_inference.py`: finite-value, timing, shape and CSV-integrity checks.
- `backend/app/services/model_inference.py`: only the authorized `check_input` integration for direct selection.
- `backend/tests/test_review_input_contracts.py`: synthetic contract controls and direct-endpoint refusal regression.
- `scripts/review_input_challenges.py`: standalone, reproducible technical challenge artifact.

The existing `imaging_readers.py` and ECG waveform-preview implementation were inspected and retained. A known EXIF source landmark is checked against its expected upright pixel location; this verifies the existing orientation mapping rather than introducing a replacement renderer.

## Measured challenge results

Command:

```powershell
.venv\Scripts\python.exe scripts\review_input_challenges.py
```

Artifact: `artifacts/review-2026-11-13/input-contract-challenges.json`. It records execution timestamp, code revision, source SHA-256 values and each observed reason code.

| Layer | Expected valid controls | Invalid/contradictory controls | Observed |
| --- | --- | --- | --- |
| ECG reader/contract | 2: physical mV and reversed-lead uV | 11: wrong rate/duration, missing/duplicate lead, absent unit, extreme/flat/nonfinite signals and nonfinite times | 2/2 accepted; 11/11 refused with expected codes; uV/reordering preserves physical samples. |
| DICOM technical tags | 2 with matching declared modality/body part | 7 with explicit modality/body contradictions | 2/2 had no known tag contradiction; 7/7 contradictions refused by the shared function. This does not establish model acceptance or anatomical truth. |
| Missing DICOM body-part tag | 1 intentionally incomplete control | Not considered verified anatomy | No contradiction asserted; the test explicitly retains missing-context limitations. |
| EXIF/source geometry | 1 orientation-6 pixel landmark | — | Exact expected source-pixel mapping. |

**24/24 technical challenges passed.** All inputs here are deliberately synthetic engineering controls. They are not real clinical scans, independent patient cases, newly measured OOD sensitivity or clinical diagnostic results.

## Software regression evidence

The first full-application regression run after the ECG/router changes passed **69 tests** across the new contracts and existing routing, digital signal/volume inference and ECG fusion suites. This establishes compatibility with these existing readers and adapters, including synthetic checkpoint inference; it does not reproduce their historical medical accuracy estimates.

A subsequent run includes the direct model endpoint and existing research-inference suite after the direct-path integration: **101 passed in 100.45 seconds**, with no skips or failures. Its final command and output are retained in `artifacts/review-2026-11-13/input-contract-tests.log`:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_review_input_contracts.py backend/tests/test_model_router.py backend/tests/test_signal_and_volume_inference.py backend/tests/test_ecg_fusion_inference.py backend/tests/test_research_inference.py -q -p no:cacheprovider
```

The direct endpoint control uses a declared synthetic registry entry and verifies HTTP 400, the body-part contradiction code, no model preparation, and zero stored `InferenceRun` rows for the refused upload. That is API refusal evidence, not inference from a trained head-CT checkpoint.

## Scope still requiring model-level evaluation

This pass does not recalibrate or widen the existing appearance/OOD gate. Historical wrong-input acceptance and valid-input false refusals remain limitations until re-evaluated independently. The technical challenge counts above must not be substituted for an image-level confusion matrix.

The separate real-checkpoint workflow evidence must report accepted-case predictive performance and all refusals. Broader model-level challenges still need independently sourced supported images plus wrong-body-part/wrong-modality images, screenshots/film photographs, blur, overexposure, compression and missing-sequence cases. Metadata contradiction checks do not recognize all such inputs.

No new ECG rate, duration, image-to-waveform, EEG interpretation or clinical claim is enabled. Real ECG model inference and training/serving parity are separate from these synthetic reader controls.
