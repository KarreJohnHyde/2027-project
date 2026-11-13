# Same-page laboratory panel context repair — 13 November 2026

## Observed failure

The actual synthetic demonstration showed a numeric-correct but context-wrong result: both digital and scanned pages assigned platelet count 225 to `Serum`, although the printed haematology specimen was `Whole blood (EDTA)`. The next panel was explicitly labelled `BIOCHEMISTRY`, followed by its serum specimen.

`assign_measurement_context` bounded a result's forward context by the next result/page and a three-line limit. For the final haematology row, that window crossed the panel heading and captured the next panel's specimen. Its nearest-above specimen/method logic also lacked an explicit same-page panel boundary.

## Implemented behavior

`backend/app/services/nlp_processor.py` now recognizes explicit known laboratory panel heading lines through `LAB_PANEL_RE`. The row's forward metadata window stops at the next heading. Nearest-above specimen inheritance and heading-method inheritance are restricted to the current panel. A new panel without documented context receives `NOT_DOCUMENTED` rather than borrowing an earlier panel's specimen or method.

Existing safeguards remain: source offsets and numeric values are unchanged; named specimens still apply to their own result; legitimate specimen/method lines beneath a result remain usable within that panel; a row-specific method is not inherited by all later rows; page boundaries remain authoritative. Laboratory name remains page-scoped because a facility name can apply to multiple panels.

Only explicit known headings are recognized. Unknown headings or OCR corruption can still require reviewer verification; this is not a general table-layout or clinical-validation claim.

## Actual same-source verification

`artifacts/review-2026-11-13/panel-context-comparison.json` preserves:

- Original actual API/worker measurements and source-PDF hashes before the repair.
- Newly reproduced direct PDF/OCR/extraction/context results from the same unchanged PDF bytes.
- All 18 numeric rows retained across the two synthetic pages.
- Both platelet specimens corrected from `Serum` to `Whole blood (EDTA)`.
- Exact source spans, method/specimen context, OCR transcript hashes and source-code hash.

No stored original measurements or uploaded evidence were modified. Integration requires a new API/worker process and ordinary new processing; its separate replay evidence is recorded by the integration owner.

## Executed software checks

Initial focused panel/document-integrity verification: **61 passed in 0.71 s**, including 14 new panel-context cases.

Broader final verification: **188 passed in 22.42 s**. Output: `artifacts/review-2026-11-13/panel-context-tests.log`.

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_review_panel_context.py backend/tests/test_document_integrity.py backend/tests/test_review_glued_labs.py backend/tests/test_report_extraction_gaps.py backend/tests/test_report_photo_extraction.py backend/tests/test_ocr.py backend/tests/test_ocr_evaluation.py backend/tests/test_clinical_nlp_evaluation.py backend/tests/test_catalog_and_lab.py backend/tests/test_case_d_regressions.py -q -p no:cacheprovider
```

The synthetic workflow and regression fixtures measure software behavior. Independently annotated real-report pages supplied/completed during this work remain **zero**.
