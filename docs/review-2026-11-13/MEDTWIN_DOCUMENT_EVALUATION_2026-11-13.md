# Document evaluation — 13 November 2026

Workflow A: **VERIFIED**. Inputs are two explicitly fictional PDF pages: one embedded-text page and one rendered scanned page. Worker jobs, extracted fields, review, source metadata, comparison, forecast refusal and export are retained in `artifacts/review-2026-11-13/workflows/document-evidence.json`.

- Extracted measurements: 18.
- Explicit known synthetic values checked/matched: 18 / 18.
- Explicit synthetic specimen matches: 18; printed method matches: 18.
- Numeric comparison rows: 9; descriptive trend series: 9.
- Single-page PDF/OCR measurements now retain page 1, exact text spans and OCR boxes. Source rows are preserved; review is appended.
- The final fictional fixtures explicitly print `Method: SYNTHETIC`. The original fixture lacked comparable assay context and correctly withheld numeric deltas. This fixture change is separate from the preprocessing improvement.

Visual review found that the preceding extraction borrowed the next biochemistry panel's serum label for platelet results, despite correct numeric values. Explicit laboratory-panel boundaries now prevent that forward borrowing and context inheritance across a new panel. Earlier numeric-only browser evidence is retained; the final workflow asserts specimen and method correctness separately. The original stored rows were never overwritten.

The original unchanged scanned page is independently bound by source SHA-256 in `document-normalization-comparison.json`: actual original API extraction retained 1 measurement; the final PDF/OCR/rules path recovers all 9 expected fields. The intermediate six-field observation is labelled as an earlier observation, not re-executed evidence. Catalog-aware boundaries insert spaces only; they do not reconstruct missing digits, invent units or guess unreadable values. Original strings and scaled-count units remain inspectable.

**Independent human-annotated real pages: 0.** No real-report clinical precision, recall, CER/WER or assertion accuracy is claimed. The new annotation CLI initializes blank labels from explicitly listed permitted/de-identified pages; requires distinct human attestations and content-bound review; and exports the existing strict OCR-gold schema only after review. It does not use OCR output as gold. Independent representative pages and human adjudication remain external prerequisites.

Clinical negation, uncertainty, temporality, page boundaries, laboratory associations and correction semantics were exercised by the targeted and complete software suites. Those synthetic tests are not a clinical corpus evaluation. See `MEDTWIN_CALIBRATION_AND_EVIDENCE_2026-11-13.md` for numerical and annotation details.
