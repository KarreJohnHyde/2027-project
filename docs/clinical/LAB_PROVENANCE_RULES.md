# Laboratory provenance rules

Status: **IMPLEMENTED_TESTED** (rules below are enforced in code and pinned by the tests
listed). These are evidence-handling rules, not clinical interpretation: every position
(LOW / NORMAL / HIGH) is an interval comparison that stays `PENDING_HUMAN_REVIEW`.

## 1. Which reference interval may flag a value

| Situation | Stored `reference_source` | Position | Code |
| --- | --- | --- | --- |
| Interval printed on the specific source report (document extraction) | `DOCUMENTED_IN_SOURCE` | The printed interval (`reference_low/high/text`) is stored with the measurement; a flag printed on the report is kept verbatim as `documented_flag` | `nlp_processor.py` (reference parsing next to the value) |
| Interval entered from the performing laboratory's report (manual transcription) | `REPORTING_LABORATORY` | `LOW` / `NORMAL` / `HIGH` against that interval | `lab_service.evaluate_result` |
| No interval on the report | `NONE` | **`INDETERMINATE`** | `lab_service.evaluate_result` |
| Catalog default (typical adult or sex-specific) | returned only as `catalog_interval` + `catalog_interval_source` (`CATALOG_TYPICAL_ADULT_DEFAULT` / `CATALOG_SEX_SPECIFIC_DEFAULT`) | **Never** used to flag; shown "for orientation only" | `lab_service.evaluate_result`, `LAB_RESULTS_NOTICE` in `routers/catalog.py` |
| Qualitative test | `CATALOG_EXPECTED_RESULT` | `NORMAL` when equal to the catalog's expected result, otherwise `ABNORMAL` | `lab_service.evaluate_result` |

Trend series (`biomarker_trends.py`) carry reference limits only when the interval was
documented by the laboratory (`REPORTING_LABORATORY` / `DOCUMENTED_IN_SOURCE`); catalog
defaults never become trend reference bands.

## 2. Missing provenance is `NOT_DOCUMENTED`, never guessed

- Laboratory name, specimen / sample type and similar report fields that the source
  omits are stored as `NOT_DOCUMENTED` (`routers/catalog.py`, `NOT_DOCUMENTED`); the
  former default specimen value was removed from `LabInvestigationReport.sample_type`.
- Calculators report missing inputs explicitly, e.g. eGFR (CKD-EPI 2021) returns
  `AGE_NOT_DOCUMENTED` / `SEX_NOT_DOCUMENTED` / `..._CONFLICTING` instead of computing
  with an assumed value (`clinical_calculators.py`).
- Collection dates in the future are rejected (HTTP 400); transcriptions without a
  collection date carry `date_source = UNDATED`.

## 3. One observation is counted once

A manual transcription with the same analyte, date and value as a value already
extracted from an uploaded document is excluded from the trend with reason
`DUPLICATE_OF_M<measurement id>`; a new dated value joins the series
(`biomarker_trends._duplicate_of`). Transcriptions may reference a source file only
within the same case (404 across cases).

## 4. OCR-derived values

Values read from scanned pages carry `extraction_method = OCR_RULE_BASELINE`, the source
page number, and the page's OCR engine/confidence in provenance (`nlp_processor.py`,
`document_parser.extract_pdf_document`). Each OCR page also records its rendered image
dimensions and top-left pixel coordinate system. A measurement stores the union bounding
box of the OCR lines that support it, so a reviewer can return to the exact rendered-page
region without persisting OCR line text in the page-metadata API. OCR accuracy is not
validated; such values need review against the page image.

## 5. Censored values and interval boundaries stay explicit

- The operators `=`, `<`, `>`, `<=`, and `>=` are stored separately from the numeric
  value. A result such as `<0.01 mg/dL` is not silently converted into an exact 0.01.
- For a printed one-sided reference operator, the corresponding limit records whether
  the operator is inclusive. Plain two-sided ranges retain both limits but do not invent
  inclusivity semantics. This is source transcription, not a new clinical range.
- Censored results receive `INDETERMINATE_CENSORED_RESULT`, are excluded from arithmetic
  trends and numeric examination deltas, and cannot be used as exact inputs to eGFR.

## 6. Longitudinal arithmetic requires comparable observations

Extracted and manually entered quantitative results carry laboratory name, specimen, and
method when documented; missing values remain `NOT_DOCUMENTED`. A series is withheld with
`COMPARABILITY_NOT_ESTABLISHED` unless every included result has the same documented
specimen and method. This prevents a numerical slope or delta from implying comparability
that the source reports do not establish. The extractor version, exact source span, source
file hash, page/line location, and review state remain attached to each measurement.

## Tests

| Rule | Test |
| --- | --- |
| Interval from the report flags; absent interval → `INDETERMINATE` (flag counts HIGH 1 / NORMAL 2 / INDETERMINATE 3) | `test_catalog_and_lab.py::test_record_lab_investigation_report` |
| Omitted laboratory/specimen → `NOT_DOCUMENTED`; interval source stated per result | `test_catalog_and_lab.py::test_lab_report_never_assumes_laboratory_or_specimen` |
| Manual transcription deduplicated against extraction; future dates rejected; cross-case source refused | `test_catalog_and_lab.py::test_transcribed_results_join_trends_without_double_counting` |
| Documented reference text and flag captured without inference | `test_medtwin2_capabilities.py::test_measurements_capture_documented_reference_flag_and_code_without_inference` |
| eGFR requires every documented input | `test_medtwin2_capabilities.py::test_egfr_requires_every_documented_input` |
| Duplicate and missed values in the extraction audit | `test_medtwin2_capabilities.py::test_lab_extraction_audit_counts_missed_values_and_rejects_duplicates` |
| OCR values keep decimals and OCR provenance | `test_ocr.py::test_scanned_report_values_keep_decimals_and_ocr_provenance` |
| OCR pages and extracted measurements retain rendered-page bounding boxes without exposing line text in metadata | `test_ocr.py::test_scanned_page_is_read_with_page_level_provenance`, `test_ocr.py::test_scanned_report_values_keep_decimals_and_ocr_provenance` |
| Censored operators and lab context are preserved; censored creatinine is rejected by eGFR | `test_measurements_and_longitudinal.py::test_censored_lab_result_preserves_operator_and_never_becomes_exact` |
| Trends abstain when specimen or method comparability is missing | `test_medtwin2_capabilities.py::test_biomarker_trend_abstains_when_lab_context_is_not_documented` |
