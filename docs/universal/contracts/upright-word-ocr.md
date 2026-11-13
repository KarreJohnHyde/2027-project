# Opt-in upright word ROI OCR and bounded experiment

`backend/app/services/upright_word_ocr.py` and the standalone `upright_word_ocr` router implement a source-bound OCR proposal for an explicitly attested upright Latin word. Existing `ocr.py`, full-page preprocessing/orientation, original benchmark artifacts, model registries and checkpoints are unchanged. Root mounts the router and supplies the source-preview form.

## Why this narrow path exists

The exposed external tests were inspected for failure patterns, not reused to select or claim an untouched new test result. The 1,115-word test had 252 empty outputs. Its 65 crops selected for 180-degree retries had CER 0.966 versus 0.557 for the remaining 1,050; this association does not establish causality. Clean synthetic pages had mean raw line confidence 0.977 despite CER 0.186, so confidence is not transcript correctness. Simulated handwriting and mixed-artifact pages were particularly weak. Tesseract was absent from PATH and both standard Program Files locations; no new OCR model or weight was installed.

A new fixed experiment reserved 128 development and 256 previously unscored internal-holdout crops from the publisher's **Train_Set**, selected by a label-independent SHA ordering with no duplicate source images. `plan.json` was written before OCR; `frozen-policy.json` selected the candidate before reserved-holdout inference. The official 1,115 test crops and 48 exposed synthetic pages were not rescored or presented as untouched new evaluation. No labels, dictionary, weights, thresholds or calibrator were fitted.

| Fixed policy | Development CER | Development exact fraction | Development empty outputs |
| --- | ---: | ---: | ---: |
| Existing full OCR policy | 0.540351 | 0.132813 | 27 |
| Preserve source crop orientation | 0.520468 | 0.140625 | 27 |
| Preserve orientation, 2× upscale + 16px white border | 0.540351 | 0.117188 | 28 |
| Tight foreground crop + existing recognizer directly | 0.602339 | 0.085938 | 5 |

The direct recognizer produced fewer empty outputs but worse text; forcing nonempty output is not an improvement. Upscaling/border did not help this sample.

On the **256 newly reserved publisher-training crops**, the frozen preserve-orientation policy changed CER **0.583612 → 0.565217**, WER **0.893333 → 0.890000**, exact words **28 → 29**, and empty outputs remained **63**. Candidate-minus-baseline CER was −0.018395, with paired **word-level** bootstrap interval [−0.031041, −0.007671] (2,000 resamples, seed 20261113). This supports a modest internal word-instance CER reduction. Error levels remain high. The reserved set is not the publisher's official external test set; writer/patient/source-prescription independence and generic pretraining exposure are unknown. It does not establish clinical, medication, laboratory or full-report accuracy.

Experiment reproduction:

```powershell
.venv/Scripts/python.exe scripts/experiment_ocr_word_preprocessing.py --archive data/external/completion-2026-11-13/RxHandBD-zenodo-v1.zip --output-directory artifacts/completion-2026-11-13/resources/new-explicit-experiment-directory --development-n 128 --holdout-n 256
```

Existing experiment directories are refused, preserving prior results. Source must match reviewed MIT RxHandBD v1 SHA `25d31c7bc1ceab4b3707d5e6d2205e518cadbd75d2f99efe1492a1aee5ef1951`. Original artifacts are under `resources/ocr-word-experiment-v1/`; read-only error analysis is `resources/ocr-error-diagnosis.json`.

## HTTP contract

All paths below are relative to `/api/v1`. Authentication uses existing application users/cookies. Source access, guest/private case policy and active/nonwithdrawn/nonsuperseded state are checked by the existing `_report_upload` boundary.

`GET /universal/ocr/upright-word/capability` returns actual runtime availability, exact model/code hashes, bounds, source/rights provenance, narrow evaluation scope and fallback.

`POST /uploads/{file_id}/ocr/upright-word`:

```json
{
  "page": 1,
  "bbox_xyxy": [100, 100, 228, 228],
  "expected_image_size": [1200, 1600],
  "source_file_sha256": "<64-character current upload SHA-256>",
  "coordinate_space": "REPORT_PAGE_PREVIEW_110_DPI",
  "upright_attested": true,
  "single_word_attested": true,
  "latin_text_attested": true
}
```

Coordinates are native pixels of the exact existing `api.getReportPageImage` preview, not CSS pixels, 300DPI OCR pixels, PDF points or patient space. UI dragging must convert displayed coordinates to that preview's natural dimensions. Only PDF REPORT sources with existing OCR-backed cached geometry/identifier-mask metadata are accepted. The endpoint does not start whole-document OCR. Native embedded-text pages without masking metadata refuse and point to existing source text/reviewer controls. It renders/reads the same privacy-masked 110DPI page image used by source verification, never a newly unmasked image behind that preview. Current source SHA, page and expected dimensions must match; response records the exact PNG preview SHA.

ROI bounds: integer coordinates inside the source, width 12–1024, height 12–256, aspect 0.5–16, ≤262,144 crop pixels, ≤10% of page area, ≤20 million source-preview pixels and source ≤50MiB. Uniform/blank/masked crops abstain. Exactly one detected line with one bounded Latin/digit/punctuation token is required; no/multiple lines, whitespace/multiple tokens, unsupported script, invalid confidence or out-of-source boxes abstain. These checks plus requesting reviewer attestations are contextual safeguards, not independent verification of word meaning or correct orientation. Unsupported context must use the original source review workflow.

Successful output has:

```ts
{
  schema_version: 'medtwin.upright-word-ocr.v1',
  status: 'AVAILABLE', code: 'OCR_WORD_PROPOSAL_REVIEW_REQUIRED',
  text_proposal: string, raw_ocr_confidence: number,
  source: { upload_id: number, case_id: number, file_sha256: string,
    page: number, preview_dpi: 110, preview_sha256: string, privacy_masking: string },
  roi_bbox_xyxy: number[], crop_word_bbox_xyxy: number[],
  source_word_bbox_xyxy: number[], crop_to_preview_affine: number[][],
  coordinate_space: 'REPORT_PAGE_PREVIEW_110_DPI', rotation_degrees: 0,
  runtime: object, review_required: true,
  persisted_finding_or_correction: false, clinical_activation: false
}
```

Crop boxes translate by `(x0,y0)` into the same preview coordinates; no rotation, rescaling, PDF-point or anatomical transform is implied. Refusal responses use `status: REFUSED|ABSTAIN`, a stable `code`, explanation, `text_proposal: null`, source identity where available and fallback. Invalid request schemas return 422; unauthorized/withdrawn resources use existing 401/403/409 semantics; changed source identity/dimensions return 409. Processing is single-request bounded with 429 while busy and 10 requests/minute per client address. The helper creates no finding, measurement, correction or model activation. Audits record source IDs/hashes/box/status without OCR text.

## Exact engine and licensing provenance

The helper uses the installed RapidOCR 1.4.4 detector, recognizer, preprocessing, detection threshold and reading-order code. It omits page-level rotation retries only for the attested word ROI. `ocr.py` must match SHA `bd4e41fb67bd45ee41011e431f6208ec729b6c70b5a892a01ff7da419808f531`; a changed runtime/artifact fails closed until explicitly reviewed.

| Existing bundled model | SHA-256 |
| --- | --- |
| `ch_PP-OCRv4_det_infer.onnx` | `d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9` |
| `ch_PP-OCRv4_rec_infer.onnx` | `48fc40f24f6d2a207a2b1091d3437eb3cc3eb6b676dc3ef9c37384005483683b` |
| `ch_ppocr_mobile_v2.0_cls_infer.onnx` | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |

The classifier artifact is inventoried but not executed (`use_cls=False`). Installed wheel metadata declares Apache-2.0, consistent with the primary [RapidOCR licence](https://github.com/RapidAI/RapidOCR/blob/main/LICENSE); the existing bundled model family comes from [PaddleOCR under Apache-2.0](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE). Primary licence blob SHAs, installed metadata SHA and all local artifact hashes are recorded in `resources/upright-word-runtime-license.json`. This is automated source/package provenance, not an independent human legal or clinical approval. No new OCR weights, noncommercial models, credentials or network model calls are introduced.

## Verification

- `python -m pytest backend/tests/test_upright_word_ocr.py -q`: **18 passed**. Covers private-case/auth/active source enforcement, source/page/dimensions, strict geometry/attestations, mapped boxes, blank/masked/multitoken/bad-score refusals and no finding/raw-text audit writes.
- `python -m pytest scripts/tests/test_ocr_word_preprocessing.py -q`: **7 passed**. Covers label-independent disjoint partitioning, duplicate refusal, blank guards, fixed foreground transforms and correctly paired metric denominators.
- Actual helper parity on 16 previously used public development crops pasted into a **synthetic canvas**: 13 proposals and 3 abstentions. Every proposal exactly matched the frozen upright policy's text; every source box translated correctly, including asymmetric `(73,109)` source offsets. This is functional parity, not a new accuracy sample. Evidence: `resources/upright-word-helper-parity-asymmetric.json`.

Root owns router mounting, the actual authorized case/PDF endpoint and frontend QA. Independent full clinical report/lab extraction validation remains outstanding.
