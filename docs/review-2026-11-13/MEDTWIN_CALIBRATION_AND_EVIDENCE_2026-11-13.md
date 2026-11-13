# Numerical calibration and model-evidence verification — 13 November 2026

## Implemented and verified

`backend/app/services/calibration_service.py` now includes confidence exactly zero in the first ECE bin. Internal boundaries retain the historical right-closed convention; zero and one each contribute exactly once. Empty/nonfinite observations, mismatched shapes, nonbinary correctness and invalid bin counts are refused instead of silently broadcasting or returning misleading metrics. Multiclass ECE requires explicit caller-selected top-label confidences/correctness or a declared per-class analysis.

Binary/multilabel Brier preserves the previous mean squared component-error definition. A new keyword-only `multiclass=True` requires N×C normalized probabilities and one-hot reference labels and uses the conventional sum over classes, averaged over observations. This value can range from zero to two and must not be compared to the class-normalized definition without disclosure. Ground-truth class indices cannot broadcast into a probability matrix.

Temperature scaling validates finite logits, a class axis and a finite positive scalar temperature. Stable centering precedes temperature division, including extreme finite logits/tiny temperatures. The historical 1.25 default is retained for compatibility and explicitly documented as unfitted. This helper applies multiclass softmax, not multilabel sigmoid calibration. No calibration parameter was fitted or changed for any trained model in this session.

The generic helper was referenced by tests, not the inspected model-serving code. These numerical repairs do not imply that previously saved model evaluations were recomputed or that predictive accuracy improved.

## Current executed tests

| Command | Result |
| --- | --- |
| `.venv\Scripts\python.exe -m pytest backend/tests/test_calibration_boundaries.py -q -p no:cacheprovider` | 42 passed in 0.71 s, regular application test initialization succeeded. |
| `.venv\Scripts\python.exe -m pytest backend/tests/test_evidence_and_fusion.py -q -p no:cacheprovider` | 11 passed in 4.89 s, covering existing calibration API compatibility and evidence/fusion regressions. |
| `.venv\Scripts\python.exe -m pytest scripts/tests/test_review_model_evidence.py scripts/tests/test_review_document_annotations.py -q -p no:cacheprovider` | 33 passed in 0.67 s (8 reconciler tests, 25 annotation-tool tests). |

After the complex-input refusal and final OCR fixes, a combined normal application-initialized suite passed **241 tests in 84.05 s**. It covers calibration boundaries (now 43 cases), original evidence/fusion compatibility, all 18 new glued-lab controls, existing photographed-report/OCR/document-integrity/clinical-NLP evaluation suites, and both new annotation/evidence tools. Output: `artifacts/review-2026-11-13/document-normalization-tests.log`. Earlier counts above describe earlier runs and overlap; do not sum them as unique tests.

Tests use hand-computed numerical references, boundary cases and synthetic fixtures. They are software verification, not independently annotated clinical evaluation.

## Read-only checkpoint reconciliation

Reproduce with `.venv\Scripts\python.exe scripts/review_model_evidence.py --out docs/review-2026-11-13`.

Outputs:

- `MEDTWIN_MODEL_RESULTS_2026-11-13.csv`: current registry rows with checkpoint hashes, dataset/permission declarations, preprocessing, sample counts where reported, original metrics, thresholds, exclusions, evidence binding and limitations.
- `MEDTWIN_MODEL_EVIDENCE_2026-11-13.json`: detailed audit context, current code revision/dirty-tree flag, registry hash and summary.

The inspected current registry contains 32 entries. Twenty-two primary checkpoint files matched their declared SHA-256s. All seven named TotalSegmentator component checkpoints matched, including fast-model components with their different trainer directory. These seven are component checks, not seven additional clinically validated models.

RadGraph's declared `weights_path` is an existing **directory**, not a missing checkpoint file. The audit reports `DIRECTORY_ADAPTER_UNPINNED`, because no single declared bundle checkpoint hash binds that directory. Its internal worker/runtime verification is separate. This is not a claim that RadGraph files are absent.

The TotalSegmentator LUNA16 lung reference report has a matching model identifier but does not record a dataset-version/checkpoint binding matching the current registry. The recorded lung agreement values remain historical and reference-specific. Current hash matches cannot retroactively bind the old evaluation to a particular fast checkpoint.

Three saved-snapshot discrepancies were recorded: the saved snapshot lacks the new fracture model and lacks primary checkpoint hashes for the separately handled chest/TotalSegmentator adapters. Missing adapter hash fields in that saved snapshot are not proof of tampering. The registry and saved snapshot were not overwritten.

All predictive scores in the CSV are marked `HISTORICAL_RECORDED_NOT_REPRODUCED`; this audit performs zero inference or predictive evaluations. Runtime is explicitly unverified by the read-only audit, and current input/purpose gates still decide eligibility. The failed renal-tumour checkpoint stays failed and blocked. No research or clinical activation was granted.

## Independent document annotation tooling

`scripts/review_document_annotations.py` creates blank manual annotation records from an explicit page inventory. It never invokes OCR, copies extracted predictions into gold, or manufactures reference labels. Actual independently human-completed real pages during this task: **0**.

Inventory schema:

```json
{
  "schema_version": "medtwin.review-page-inventory.v1",
  "pages": [
    {
      "document_id": "permitted-report-001",
      "page": 1,
      "source_image_path": "page-001.png",
      "width": 1200,
      "height": 1600,
      "deidentified": true,
      "permission_scope": "Record the actual source and evaluation permission here",
      "evidence_type": "REAL_PERMITTED"
    }
  ]
}
```

This is an illustrative schema, not an acquired page or permission grant. The source must name an individually rendered raster page, not an entire PDF masquerading as a page image. Hashes are computed from the named page bytes; dimensions and permission/de-identification declarations must be checked by the responsible human. No private reports were opened to populate it.

Run against files outside the repository:

```powershell
.venv\Scripts\python.exe scripts/review_document_annotations.py --init C:\permitted-review\inventory.json --out C:\permitted-review\draft.json
.venv\Scripts\python.exe scripts/review_document_annotations.py --validate C:\permitted-review\draft.json
```

The annotator fills `gold_text`, `readability`, `fields` and optional `entities` by examining the actual source. Each lab field records analyte, decimal-string value or explicit unreadable/not-reported state, unit, specimen, dates, printed reference interval, assertion/negation/temporality and source-pixel box. Unavailable values remain null; comparisons such as `<` are stored separately from the decimal. Entity spans use offsets into the manually transcribed page and the existing strict NLP evaluator vocabulary.

After the responsible humans actually perform independent transcription and review:

```powershell
.venv\Scripts\python.exe scripts/review_document_annotations.py --finalize C:\permitted-review\draft.json --annotator human-a --reviewer human-b --attest-manual-transcription --attest-independent-critical-review --out C:\permitted-review\reviewed.json
.venv\Scripts\python.exe scripts/review_document_annotations.py --export-ocr C:\permitted-review\reviewed.json --out C:\permitted-review\gold-ocr.json
```

The CLI enforces distinct pseudonymous identities, both attestations, timestamp and a digest of reviewed content. It cannot prove human identity or annotation independence by itself. Editing reviewed text, boxes, fields or source context invalidates the digest. Existing destination files are never overwritten.

OCR export matches the existing `medtwin.ocr-pages.v1` evaluator schema exactly. Draft/unreviewed records and empty gold sets are refused. Explicitly unreadable pages are counted and excluded from text scoring; their missingness is not converted into text. Synthetic pages retain a separate counter and never count as independently checked real pages.

The tool captures clinical span labels for review but does not automatically convert them into evaluated NLP results. Use the existing clinical NLP evaluator with a separately assembled, source-bound gold/prediction artifact; no clinical metrics are claimed from schema validation.

## Actual synthetic scanned-page preprocessing repair

The full workflow exposed compact OCR rows such as `FastingGlucose112mg/dL70-100H`, `TotalLeucocyteCount6.810^3/uL4.0-11.0`, and `Urea38mg/dL15-40`. Existing normalization recovered some words, but the extractor correctly refused units directly adjacent to the reference digits; count results were also glued to the explicit `10^3/uL` scale.

`ocr_text.py` now inserts only spaces at catalog-bound name/result/unit/reference boundaries. The complete known analyte, decimal result, compatible unit and explicit two-sided reference interval must be present. Known leucocyte spellings were added to the domain vocabulary. Original digits, units and coordinates are never replaced. The existing offset map continues to quote exact original OCR text. Unknown units, incomplete decimals and incomplete reference ranges stay refused. A literal `/uL` unit without an exponent retains the whole observed number; a missing `10^3` scale is never inferred.

On the **same original scanned synthetic PDF bytes**, SHA-256 `aef9e755be7be024cb1c0d04816d8dfeb40922f8bae78cfcbe13e036ee6cf107`, the saved original API/worker output contained one measurement. The first boundary repair was observed to recover six. The final direct PDF/RapidOCR/extraction rerun recovered all nine printed rows with their correct numerical reference intervals: haemoglobin, WBC, platelets, glucose, creatinine, urea, sodium, potassium and HbA1c. WBC/platelet raw units remain `10^3/uL`, with the existing equivalent canonical unit `10^9/L` and unchanged numerical values.

`artifacts/review-2026-11-13/document-normalization-comparison.json` preserves the original saved measurement, source PDF and original API-artifact hashes, actual OCR transcript/hash, final measured rows and exact source spans, extractor version and normalization-source hash. The intermediate six-row count is explicitly labelled a retained earlier observation, not a newly rerun result. The final parser rerun is separate from the subsequent API/worker integration replay performed by the integration owner.

This is a synthetic software control with known printed content. It is not independent real-report annotation, clinical validation, or evidence of a population accuracy percentage. The original source comparison was recorded before later demonstration fixtures received explicit method/date context.
