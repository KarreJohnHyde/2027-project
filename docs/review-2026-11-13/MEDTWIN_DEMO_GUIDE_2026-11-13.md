# Demonstration and reproduction guide — 13 November 2026

Use the isolated research preview at `http://127.0.0.1:8458`. QA credentials stay only in `.cache/review-20261113/qa-credentials.json`; never copy them to slides or exported evidence. Normal visitor/guest entry behavior was not replaced.

1. Open the fictional document case #5. Show both PDFs, one text-derived and one OCR-derived.
2. Show extracted fields, page/source boxes, printed units/intervals, original source and append-only review. Explain the independent real reference-set count is zero.
3. Show old/current comparison, dated trends and source context. Show forecast refusal with no invented future disease value.
4. Open public imaging case #3, upload #3, run #3. The actual model output persists; no new inference is needed to view it.
5. Toggle the model layer and the independent publisher reference. Show source-grid alignment, review and the one-image Dice; do not call it cohort accuracy.
6. Show the blank/report-photograph refusal artifacts. No prediction was produced. Show the failed kidney model and strict one-pixel historical parity difference as known failures.
7. Open Reports, click **Export JSON**, and compare its displayed SHA-256 to the download. The selected-browser artifact proves this UI action was executed.
8. Reload, then open generic L1 anatomy. Explain that the organ highlight is a reference association, not patient-specific registration.

```powershell
# Start/reuse an isolated stack; does not reset the development database.
powershell -NoProfile -File scripts/dev.ps1 -Mode qa -StateDir .cache/review-20261113 -BackendPort 8018 -WebPort 8458

# New fictional/public research demonstrations (creates new QA cases only).
.venv\Scripts\python.exe scripts/review_run_workflows.py --state .cache/review-20261113

# After an actual QA restart, compare the stored outputs.
.venv\Scripts\python.exe scripts/review_run_workflows.py --state .cache/review-20261113 --only persistence

# Actual stored-model overlay/reference/reload/UI export/atlas checks.
node tools/browser-qa/review-workflows.mjs --state .cache/review-20261113 --out artifacts/review-2026-11-13/selected-browser-reproduced

# Runtime, technical refusals and bounded historical/current parity.
.venv\Scripts\python.exe scripts/review_runtime_probe.py --torch
.venv\Scripts\python.exe scripts/review_input_challenges.py --output artifacts/review-2026-11-13/input-challenges-reproduced.json
.venv\Scripts\python.exe scripts/review_parity_controls.py --output artifacts/review-2026-11-13/parity-reproduced.json
# Parity currently exits 1 for the recorded one-pixel historical mask difference.

.venv\Scripts\python.exe -m pytest backend/tests -q -p no:cacheprovider
npm run check
node --test scripts/report-evidence.test.mjs scripts/report-render.test.mjs scripts/finding-groups.test.mjs scripts/trained-report.test.mjs
.venv\Scripts\python.exe scripts/build_review_package.py
.venv\Scripts\python.exe scripts/verify_review_package.py
```

The normal development launcher remains `npm run dev:full` (existing application database). Do not use `-Fresh` on existing records. The QA stop/start commands manage only recorded owned processes, and the QA state remains available for review.
