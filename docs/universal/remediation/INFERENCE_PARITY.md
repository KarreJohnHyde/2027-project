# Training/serving parity status (U-015), 14 November 2026

| Check | Method | Result | Status |
|---|---|---|---|
| Haemorrhage classifier, native head CT series (new path) | App path (`model_inference.run_head_ct_series`, per-slice mode) vs CQ500 evaluator (`single_slice_scan`) on identical assembled series, same checkpoint `39b8068e…`, CPU float32 | CQ500-CT-1: max \|Δ\| 0.0 on all 6 labels, 33/36 slices analysed by both. CQ500-CT-0: max \|Δ\| 0.0, 30/30 slices | **Exact** |
| Same path, unit level | `series_model_images` vs evaluator image construction on synthetic HU arrays (`backend/tests/test_head_ct_per_slice_series.py`) | Pixel-identical | **Exact** (tested) |
| Skin classifier | Stored predictions vs serving (`backend/tests/test_skin_research.py`) | Exact within 0.005 on CUDA. On CPU float32 the difference from the evaluated precision is declared, not hidden. | Device-aware |
| Kvasir-SEG historical one-pixel mismatch | Requires the original training environment | The environment archive is absent; the strict-equality regression is kept, not relaxed | **Unresolved** |
| 9 UCI tabular models (serving function `tabular_inference.score_frame`) | `scripts/remediation_tabular_audit.py`: the same checkpoint (SHA-256 verified) re-scores the rebuilt test rows through the serving function and is compared with the stored test predictions | Max \|Δ\| ≤ 5×10⁻⁷ for every model, which is the 6-decimal storage rounding declared before the comparison. Every reported metric reproduces exactly from full-precision re-scoring. | **Exact within storage rounding**; new runs store full precision |
| Fetal planes, MSD organs | Planned: stored held-out predictions vs the serving path on the same files | Not yet run; still training (MIT-BIH is exploratory, so it has no serving path) | Pending |
| Malaria classifier (new, 14 Nov) | `model_inference.run_model` vs stored test predictions, 40 evenly spaced test cells, same checkpoint, CPU float32 | Same decision 40/40; max \|Δp\| 7.3×10⁻⁷ (6-decimal storage plus float32 noise). Serving now states "float32, as in the held-out evaluation" (`evaluation_device: cpu`) | **Exact within storage rounding** |

Numeric tolerance: exact equality on the same device and precision. A cross-precision difference is reported as a declared difference, not as a pass.
