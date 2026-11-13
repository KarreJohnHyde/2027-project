# MedTwin bounded training/serving parity — 13 November 2026

## Result

Two actual registered checkpoints were loaded through the existing eligibility and SHA-256 gates and executed on predetermined public test inputs. No weights, thresholds, normalization parameters or historical evaluation outputs were changed.

- **PTB-XL ECG: VERIFIED_BOUNDED_PARITY.** Physical signals, normalized tensors, current trainer-path logits and current serving probabilities agree exactly. Comparison with the saved historical trainer probabilities is within the predeclared numerical tolerance, with no threshold decisions changed.
- **Kvasir-SEG: DIFFERENCES_RECORDED.** Current trainer preprocessing, current logits and source-coordinate RLE mapping agree exactly. The newly executed model-grid mask differs from its saved historical trainer mask by **one pixel out of 123,904**. Strict historical exact-mask parity did not pass and is not described as exact equivalence.

These are bounded reproducibility controls, not new independent medical-performance evaluations. The image and ECG samples were predetermined; the script did not search the holdouts for passing cases.

## Reproduction and artifacts

```powershell
.venv\Scripts\python.exe scripts\review_parity_controls.py --output artifacts/review-2026-11-13/parity-controls-reproduced.json
.venv\Scripts\python.exe -m pytest scripts/tests/test_review_parity_controls.py -q -p no:cacheprovider
```

The first command intentionally returns a nonzero exit status whenever a required strict parity check differs, even if inference succeeds and a complete report is saved. The current image historical-mask mismatch produces exit **1**. Do not suppress that exit code or relabel the audit green.

Final execution evidence:

- `artifacts/review-2026-11-13/parity-controls-final.json`
- `artifacts/review-2026-11-13/parity-controls-final.log`
- `artifacts/review-2026-11-13/parity-comparator-tests.log`

Final measurement time: **2026-11-13 07:35:04 UTC**, 60.771 seconds. Runtime: `.venv/Scripts/python.exe`, Python 3.12.10, PyTorch 2.14.1+cu130, CUDA 13.0, NVIDIA GeForce RTX 5060 Laptop GPU. Both models used CUDA bfloat16 autocast as in their recorded evaluations. The JSON retains code revision, source-file hashes, preprocessing identity, input/reference/checkpoint hashes, measured differences and thresholds.

The initial `parity-controls.json` and log are retained as development evidence. That initial execution identified the same image mismatch but its ECG action stopped at a `verify_files` call-signature error in the new script. The caller was corrected to provide the existing publisher checksum manifest; the final execution above completed the ECG control. This was a script defect, not a model or ECG-data failure.

## Image checkpoint and comparisons

Model: `gi_kvasir_seg_polyp_segmenter`.

Checkpoint: `artifacts/training/gi_kvasir_seg_polyp_segmenter-20261025T080312Z/model.pt`.

Checkpoint SHA-256: `a5a2c88dc5af67a8993210ca8a3d40ea79b9cd5e0a7cd5f422c1356828115c36`.

Preprocessing: `rgb-resize352-standardise-v1`: RGB, bilinear resize to 352×352, per-channel standardization; class masks map back by nearest-neighbor interpolation.

Input selection: the first `test` row in the unchanged split manifest, `cju0s690hkp960855tjuaqvv0`. Native size: 621×530 pixels. Image SHA-256: `96696f7cbcdff52a62d26d51c2c4154ed7f6eebee43fe5ad4cf6c5fa55825476`.

The trainer dataset implementation `ml_training.segment.SegmentationSet(train=False)` constructs the reference tensor. The application tensor and logits are obtained through `model_inference.segmenter_tensor` and `run_model`. The script reuses the existing full-holdout verifier's manifest/image helpers, but never invokes its full-holdout loops or changes `UPLOAD_INFERENCE_PARITY.json`.

| Check | Measurement | Criterion | Result |
| --- | --- | --- | --- |
| Trainer/application tensor | 371,712 values, max absolute difference 0 | Exact | Passed |
| Current trainer/application logits | 247,808 values, max absolute difference 0 | Absolute tolerance 1e-5, relative tolerance 0 | Passed |
| Historical saved trainer mask | 1 differing pixel / 123,904 | Exact | **Difference recorded** |
| Served RLE versus nearest-neighbor mapped model grid | 329,130 source pixels, 0 differences | Exact | Passed |
| Existing appearance gate | Score 1.681, limit 4.061 | Existing registered gate, unchanged | Passed |

The historical trainer mask exists as a separate saved PNG; its SHA-256 is `db86a5f53a2f82a2ee032dde7454a6fde3d391ab43630a1636a6d4016e9afebf`. The mismatch recurred in both executions. Its cause is not established by these controls; software/device/batch effects remain hypotheses, not verified explanations.

Comparison of the served source mask to this sample's publisher mask gives **Dice 0.9526142411**, **IoU 0.9095161290**. These are one-image agreement values, not newly reproduced cohort accuracy or clinical validation.

Historical raw logits were not saved. The current logit comparison uses the same immutable checkpoint/network with independently constructed trainer and application input tensors; it is not an independent architecture implementation test. The historical PNG comparison is distinct evidence and remains non-exact.

## Digital ECG checkpoint and comparisons

Model: `ptbxl_ecg_baseline`.

Checkpoint: `artifacts/training/ptbxl_ecg_baseline-20261025T072058Z/model.pt`.

Checkpoint SHA-256: `687f69a2ff1cb50dcd0c5a26759f2d2154090c71746518db150c7638d9efb067`.

Preprocessing: `wfdb16-100hz-10s-leadstd-v1`. Exactly 1,000 samples, 100 Hz, 12 standard leads in PTB-XL order; physical mV standardized with stored training-fold mean/SD. No resampling, filtering, cropping or padding.

Input selection: ECG identifier **9**, the first saved test-prediction row, resolved through the publisher metadata to **strat_fold 10**. Both WFDB files passed the publisher SHA-256 checks (**2/2**), along with the current reader's signal/header checks. Input and saved-prediction file hashes are retained in the final JSON; no private patient identifiers are exported.

| Check | Measurement | Criterion | Result |
| --- | --- | --- | --- |
| Trainer/application physical waveforms | 12,000 values, max absolute difference 0 | Exact | Passed |
| Trainer/application normalized tensor | 12,000 values, max absolute difference 0 | Exact | Passed |
| Current trainer/application logits | 5 values, max absolute difference 0 | Absolute tolerance 1e-5 | Passed |
| Current trainer/application Platt-scaled probabilities | 5 values, max absolute difference 0 | Absolute tolerance 1e-6 | Passed |
| Historical saved probabilities | Maximum absolute difference **0.0003502802235**, mean **0.0001198914465** | Absolute tolerance **0.003**, fixed before execution | Passed |
| Historical/current threshold decisions | **0 differences / 5** | Zero | Passed |

The probability tolerance was chosen before execution from the earlier documented bfloat16 batch-versus-single-record drift (historical maximum 0.0024), not fitted to this record. Historical CSV probabilities were rounded to six decimals and scored in batches of 256. Current `predict_logits` and serving are also compared directly on a single record, separately from the historical CSV.

The observed current research output has only `NORM` at or above its frozen threshold. This is a public-dataset model prediction under its existing research contract, not a newly verified patient diagnosis or externally calibrated probability.

## Tests and remaining scope

The comparator suite passed **8 tests in 0.26 seconds**. It checks exact values, retained material differences, empty/mismatched/nonfinite input refusal and the serving threshold-equality convention. It does not substitute for real-checkpoint execution, which is recorded separately above.

The earlier input/router/signal/research-inference regression suite passed **101 tests**; that separate result remains unchanged.

Remaining work: reconcile the one-pixel historical image difference through a separately designed numerical investigation if historical bitwise reproduction is required. Do not adjust the declared criterion after seeing the result. Broader parity requires additional prespecified inputs/devices and full checkpoint-specific gates; this bounded run does not re-establish every historical holdout result or independent diagnostic validity.
