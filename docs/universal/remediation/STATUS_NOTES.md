# Status notes for the remaining deliverables (14 November 2026)

These are the short forms of `REAL_REPORT_REFERENCE_STATUS`, `REGISTRATION_EVALUATION`, `FUSION_FORECAST_EVALUATION` and `SECURITY_RECOVERY`. None of these areas gained new reference evidence in this pass. Writing separate long documents would only restate that.

## Real report reference (U-014)

- Independently reviewed real pages: **0**.
- Reviewers or attestations: none.
- Field metrics: not computable.
- Tooling (`scripts/review_document_annotations.py`, `evaluate_independent_reports.py`, `qa_independent_reports.py`) passes its tests on synthetic fixtures; those are not report accuracy.
- The redacted CASE-D report is one real page of a relative's report. It cannot serve as an independent reference without a second, independent checker and documented permission.

## Registration (U-017)

- Source-space rendering and refusal of incompatible geometry: tested.
- Held-out TRE on an independent expert-landmark cohort: **not available**.
- Atlas (L2/L3) placement stays disabled. Generic organ association is shown as schematic L1.

## Fusion and forecasting (U-008, U-009)

- Paired same-patient cohorts with outcomes: **none**. The app reports `LEARNED_FUSION_UNAVAILABLE`.
- The PTB-XL ECG + age/sex comparison shows no improvement (paired interval includes zero).
- Forecasting: observed history, descriptive trends and persistence/linear baselines only. Disease-specific forecasts abstain.
- The new UCI tables are cross-sectional, so they are not forecasting cohorts.

## Security and recovery (U-022, U-023)

- Privacy scan of the current tree (2026-11-14): 1,126 files, clean apart from allow-listed synthetic fixtures.
- Publication only through the history-free snapshot; the original history is not pushed.
- Backend suite: the request-boundary, guest-isolation and open-workspace tests pass (latest full run 1138 passed, 5 skipped; the one failure was the updated registry-count test, which now passes).
- Encrypted backup and restore to separate local storage were verified earlier (completion report). Off-host recovery is **blocked**: no approved destination.
- No dependency or container scanner was run in this pass; the most recent results are in the 13 November completion report.
