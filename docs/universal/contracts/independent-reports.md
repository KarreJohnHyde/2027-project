# Independent full-report evaluation bridge

`scripts/evaluate_independent_reports.py` evaluates supplied, independently checked full-report references offline. It creates no gold, reviewer identities, permissions, approvals, model weights or database records. It never invokes the annotation finalizer. Existing source PDFs, rendered pages, annotations and permission evidence remain unchanged. Missing inputs remain **PENDING_REFERENCE_INPUTS** in application readiness; no real accuracy result is implied by having reports or application exports.

```powershell
.venv\Scripts\python.exe scripts/evaluate_independent_reports.py --inventory <local-inventory.json> --annotations <checked-annotations.json> --permissions <permission-records.json> --out <new-private-aggregate.json>
.venv\Scripts\python.exe -m pytest scripts/tests/test_independent_reports.py scripts/tests/test_review_document_annotations.py -q
```

The output must be a new file outside the project or under `.cache/` / `artifacts/` where `git check-ignore` confirms the exact destination is ignored. Tracked/source/documentation destinations are refused, including for synthetic controls. Existing output files are never overwritten. Refusals print only a fixed code with `metrics:null`; parser/OCR errors, source paths and report text are not printed. No partial successful accuracy artifact is written on failure.

## Required inputs

The inventory schema is `medtwin.independent-full-report-inventory.v1`, with `documents` and `reference_provenance`. Each document supplies:

- A pseudonymous `document_id`, local `source_pdf_path`, exact `source_pdf_sha256`, actual `page_count` and every page from 1 through that count.
- `rendering:{engine:"pypdfium2",dpi:150|200|300,crop:"FULL_PAGE",rotation_degrees:0}`.
- A `pages` array with `page`, local `source_image_path`, exact `source_image_sha256`, `width` and `height`. Every actual source page requires an annotation; selected crops/page subsets cannot pass as full reports.

Before OCR, the bridge hashes the native PDF, obtains its actual PDFium page count, verifies every raster's bytes and dimensions against the independently reviewed annotation, re-renders the actual PDF page at its declared DPI, and requires exact decoded RGB pixel equality. The PDF hash cannot substitute for the raster hash. Duplicate PDF/report inputs, different page sets, crops, unsupported rendering, changed bytes or wrong dimensions refuse evaluation. Sources are capped at 50 documents, 250 pages, 128 MiB per file and 40 million pixels per page; pages are reopened individually for processing rather than retaining all rendered images in memory.

`reference_provenance` must explicitly contain:

```json
{
  "independently_checked_full_reports": true,
  "target_annotations_complete": true,
  "created_without_system_predictions": true,
  "used_for_training_or_tuning": false,
  "predictions_visible_to_annotators": false,
  "evaluation_split": "HELD_OUT_UNEXPOSED"
}
```

These are supplied attestations, not machine-authenticated facts. Known application-generated, previously exposed or development-used references cannot legitimately be relabelled as untouched independent evidence. Exhaustive target annotations are needed to count missing and spurious outputs fairly. The script performs no training, test-driven tuning or reference-based correction.

The annotation input uses the existing `medtwin.review-document-annotation.v1` contract from `scripts/review_document_annotations.py`. Every page must already be `FINALIZED`, with distinct supplied annotator/reviewer IDs, independent transcription and checked-critical-field attestations, a timezone-aware review timestamp and matching `reviewed_content_sha256`. Existing validation is reused with `require_finalized=True`.

Readable pages need complete supplied `gold_text`, numeric-field references and clinical entity spans/boxes; unreadable pages need an explicit reason and no invented transcription. The strict initial adapter returns `FULL_TRANSCRIPTION_REQUIRED_BY_THIS_ANNOTATION_ADAPTER` for readable references lacking transcription. That does not invalidate an independently adjudicated lab-only reference, but it cannot support full OCR/NLP evaluation through this interface. Other schemas require an explicit reviewed adapter; application JSON with `findings`, `measurements` or `analysis_jobs` is not accepted as gold. No text, boxes, critical values, review digest or human identity is fabricated to fill missing fields.

Permissions use `medtwin.independent-report-permissions.v1` with `records`. Exactly one record per PDF binds:

| Field | Required meaning |
| --- | --- |
| `source_pdf_sha256` | Exact authorized PDF bytes |
| `annotations_sha256` | Exact supplied reviewed annotation file bytes |
| `commercial_evaluation_allowed:true` | Explicit permission for this commercial-development evaluation |
| `scope:"LOCAL_COMMERCIAL_DEVELOPMENT_EVALUATION"` | Local evaluation, not clinical deployment |
| `evidence_type` | `REAL_PERMITTED` or `SYNTHETIC`, matching all pages |
| `authority_id` | Supplied permission-authority attestation; not generated by the tool |
| `evidence_files:[{path,sha256}]` | Local, existing, hash-bound permission/license evidence |
| `review` | Supplied `reviewer_id`, timezone-aware `reviewed_at`, and content-bound `reviewed_content_sha256` |
| `publication_scope` | Optional separate `PRIVATE_OPERATOR_EVALUATION` or explicitly granted `PUBLIC_AGGREGATE_ALLOWED`; absence defaults private |

The permission review digest hashes all record keys except `review` using sorted compact UTF-8 JSON, `ensure_ascii=False` and `allow_nan=False`. Source/reference/evidence hashes are checked before OCR. Commercial purpose is not interpreted as public publication consent. The bridge checks recorded scope, evidence bytes and attestations; it does not independently authenticate identities, sign a human review, interpret a legal grant or provide legal/clinical approval. The readiness integration remains admin-only for configured private report evaluations.

## Pipeline and scoring

Only existing local RapidOCR/PDFium and transparent rule lab/clinical-entity functions run. The wheel's bundled local ONNX files must already exist; no weights are downloaded or changed. Optional external/non-commercial learned NLP is not invoked. The bridge records package versions, code fingerprint, bundled OCR model hashes, input/reference/permission hashes and a hash of all in-memory predictions. Raw predictions/transcriptions are never saved.

- OCR uses the canonical privacy-minimising CER/WER evaluator over all readable source-bound pages. Human-unreadable pages and their unverified machine output are counted separately, never assigned guessed reference text.
- Numeric lab pairing is one-to-one by normalized analyte identity and at least 0.5 coverage of the independently annotated source region by an OCR-line-associated prediction region. Values/units are **not** used to choose favourable matches. Missing reference fields and spurious predictions remain in precision/recall denominators. Every readable gold numeric observation, including missed ones, enters the existing value/unit audit at zero numeric tolerance. Comparator, unit, value, specimen, collection date, report date and reference-interval discrepancies have separate counts. Human-unreadable fields remain explicitly unscored; `NOT_REPORTED` references do not become invented numeric positives.
- `nlp_given_human_text` uses the existing exact/overlap span evaluator on rule extraction from the independently supplied transcription. This isolates extraction and **is not end-to-end OCR/NLP accuracy**.
- `nlp_end_to_end_source_regions` scores actual OCR/rule output against source regions using exact normalized entity surface/category and the same fixed region-coverage condition, with separate assertion/negation/temporality mismatch counts. Its boxes are associated OCR lines, not exact token boxes or patient registration.

The initial adapter's targets are numeric lab fields and rule clinical-entity categories. Qualitative lab-only schemas or other annotation taxonomies require a reviewed adapter; full PDF page coverage does not imply every imaginable medical field was evaluated. Undefined rates are `null`, never coerced to zero or 100%. Existing canonical evaluator work bounds still apply; exceeding them refuses the run rather than silently selecting easy pages.

## Aggregate result

`medtwin.independent-report-evaluation.v1` returns `EVALUATED_INDEPENDENT_REPORTS` only for exclusively real permitted references; mixed real/synthetic corpora are rejected. Explicit `--synthetic-software-control` runs return `SYNTHETIC_SOFTWARE_CONTROL`, with all independent-real counts zero. Custom test predictors are forbidden for real reports.

The aggregate contains:

- `counts`: documents/pages, readable/unreadable pages, annotated fields/entities, independent real documents/pages/readable pages. For real runs, document/page totals equal their real totals; real readable pages equal readable pages.
- `metrics`: OCR rates/counts, lab precision/recall/F1 and canonical value/unit audit, NLP given human text, and end-to-end source-region scores. Missing/spurious and critical-field/context errors are separate aggregate counts.
- `references`: all five source/review/coverage/permission/exposure flags, plus explicit metadata-only verification scope.
- `provenance`: inventory/annotation/permission/source-manifest/prediction/pipeline hashes, package versions, local OCR model hashes, source PDF/page hash arrays, `verified_source_bindings:true`, `raw_text_persisted:false`, `raw_identifiers_persisted:false`, and no optional external/NC NLP use.
- Separate publication scope, limitations and `clinical_activation:false`.

Source PDF/page hash arrays remain private local operator evidence; readiness must omit them along with raw paths, report text, reviewer identities and any per-record data. Only allowlisted aggregate counts/finite metrics and appropriate aggregate provenance may be shown to an authorized administrator. Metadata declarations do not establish corpus representativeness, clinical validity or model improvement.

Verification on 13 November 2026: **45 tests passed in 1.67s**, including existing annotation regressions. Synthetic controls exercise exact full-page binding, no inner-join bias, missed/spurious fields, every listed critical mismatch, permission/content/exposure refusal before OCR, rejection of application exports and incomplete transcription, source/raster/page-count mismatch, strict non-overwrite and ignored-output privacy policy. They are software controls, not independent real-report accuracy. No supplied private source was scored because independently checked annotations and permission records were not available in the provided file list.
