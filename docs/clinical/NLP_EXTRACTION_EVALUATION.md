# Clinical NLP extraction — evaluation status

Overall status: **IMPLEMENTED_UNVALIDATED**. The extractors run and are covered by
behavioural tests on synthetic sentences, but **no evaluation on an annotated clinical
corpus has been executed**, so no precision, recall or F1 is reported anywhere.

## Extractors

| Extractor | Version | What it produces | Status |
| --- | --- | --- | --- |
| Transparent rules (`app/services/nlp_processor.py`) | `rules-v2.0.0` | Entities from a curated lexicon with negation, certainty, temporality, experiencer, comparison, section and atlas-site context; numeric measurements with value, unit, printed reference interval and printed flag; documented dates/age/sex | IMPLEMENTED_UNVALIDATED |
| Local OCR (`app/services/ocr.py`) | RapidOCR 1.4.4 / ONNX Runtime 1.31.0, 300 DPI | Text for PDF pages without embedded text, per-page engine, line count and mean confidence; measurements from those pages are marked `OCR_RULE_BASELINE` | IMPLEMENTED_TESTED (functional), accuracy unvalidated |
| scispaCy secondary NER (`app/services/scispacy_adapter.py`) | `en_ner_bc5cdr_md` 0.5.4 on spaCy 3.7.5 / scispaCy 0.5.5 (WSL) | DISEASE / CHEMICAL spans, each given the rule extractor's context assessment, stored as separate statements with `extractor_version = scispacy:...`; off unless `MEDTWIN_SCISPACY=wsl` | IMPLEMENTED_UNVALIDATED (publisher-trained; no MedTwin evaluation) |
| FHIR R4 import (`app/services/fhir_import.py`) | — | Observations with codes, ranges and dates (structured, not NLP) | IMPLEMENTED_TESTED |
| MedCAT, RadGraph, clinical transformers | — | — | NOT_INSTALLED (`DEPENDENCY_MISSING` in the model registry) |

## What is tested (behaviour, not accuracy)

Synthetic-sentence tests in `backend/tests/test_medtwin2_capabilities.py`:
`test_sentence_split_keeps_decimals_and_abbreviations`,
`test_context_rules_do_not_turn_hedges_into_diagnoses`,
`test_negation_scope_ends_at_terminator`,
`test_documented_site_resolves_to_atlas_structure_with_laterality`,
`test_measurements_capture_documented_reference_flag_and_code_without_inference`,
`test_documented_dates_and_age_are_parsed_conservatively`,
`test_deidentification_keeps_dates_ranges_and_prose`, `test_deidentification_masks_identifiers`;
`test_measurements_and_longitudinal.py::test_numeric_measurements_preserve_values_units_and_exact_spans`;
OCR: `test_ocr.py` (2 tests), `test_document_parser_formats.py` (scanned-page handling),
and `test_ocr_evaluation.py` (strict contract, CER/WER, privacy, and API persistence);
scispaCy: `test_scispacy_adapter.py` (context on model spans, misaligned offsets dropped,
disabled by default, worker failure leaves rule output unchanged, and an opt-in real WSL
run, `MEDTWIN_TEST_WSL=1`, executed 2026-10-24: "No evidence of pneumonia." → `pneumonia`
NEGATED).

## Evaluation tooling that exists

`POST /api/v1/evaluation/lab_extraction` (Validation Center) computes value-and-unit exact
match at a tolerance, extracted-numeric rate and unit match rate per analyte from a
pre-matched CSV (`evaluate_lab_extraction`). It deliberately does not compute missed
observations, false positives or document-level span metrics.

`POST /api/v1/evaluation/clinical_nlp` (Validation Center) now accepts separate,
independently supplied gold and prediction JSON artifacts. It validates the schema before
persisting aggregate results and computes deterministic one-to-one:

- exact-span and label-aware overlap precision, recall and F1;
- per-label TP, FP, FN and context-error counts;
- geometric label-confusion counts, including missing and spurious entities;
- assertion, negation and temporality confusion/error counts on matched entities;
- optional normalized terminology-link accuracy with separate correct, missing and wrong
  counts; and
- document/sample counts, immutable manifest and artifact hashes, and per-document metrics
  keyed only by hashed document identifiers.

The endpoint is authenticated and requires explicit de-identification and independent-gold
attestations. Uploaded source text and raw document identifiers are not stored in the
evaluation result. Runs are visible only to their creator or an administrator.

### Clinical NLP span JSON contract (v1)

Both files use `schema_version = "medtwin.clinical-nlp-spans.v1"`. The gold file declares
`artifact_role = "gold"`; the prediction file declares `artifact_role = "prediction"`.
Their document manifests must be identical. This valid, empty-text illustration contains
no clinical content (the hash is SHA-256 of an empty byte string):

```json
{
  "schema_version": "medtwin.clinical-nlp-spans.v1",
  "artifact_role": "gold",
  "documents": [
    {
      "document_id": "example-001",
      "character_count": 0,
      "document_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  ],
  "spans": []
}
```

Each span must contain exactly `document_id`, `start`, `end`, `label`, `assertion`,
`negation`, and `temporality`. Offsets are zero-based Unicode code-point offsets with an
exclusive end and must satisfy `0 <= start < end <= character_count`. Labels are
pre-normalized uppercase tokens. Context values are closed to the extractor vocabulary:
`assertion` is `CERTAIN`, `UNCERTAIN`, or `HYPOTHETICAL`; `negation` is `AFFIRMED` or
`NEGATED`; and `temporality` is `CURRENT` or `HISTORICAL`. A span may additionally provide
`code_system` and `concept_id`, but they must appear together. Unknown keys, duplicate
document IDs, duplicate `(document_id, start, end, label)` entities, invalid offsets,
unmatched manifests, and unnormalized values are rejected.
For reportability binding, the pair uses `SHA256_ORDERED_PART_DIGESTS_V1`: SHA-256 each
uploaded artifact, concatenate the 32-byte gold digest then the 32-byte prediction digest,
and SHA-256 that 64-byte value.

### OCR page JSON contract (v1)

`POST /api/v1/evaluation/ocr` accepts independent gold and prediction artifacts using
`schema_version = "medtwin.ocr-pages.v1"`. Each root contains exactly
`schema_version`, `artifact_role`, and `pages`. Every page contains exactly a pseudonymous
`document_id`, positive `page` number, lowercase `source_image_sha256`, and `text`. Gold and
prediction manifests must have identical document/page keys and source-image hashes.

The evaluator normalizes Unicode to NFC and line endings to LF, remains case- and
punctuation-sensitive, and computes aggregate character error rate, word error rate,
exact-page rate, edit counts, and bounded per-page metrics. Persisted per-page identifiers
are SHA-256 digests; raw transcription text and raw document IDs are not persisted. The API
requires de-identification and independent-transcription attestations. Its two uploaded JSON
files use the ordered combined-digest contract
`SHA256_ORDERED_PART_DIGESTS_V1` (gold first, prediction second) for reportability binding.

This is executable CER/WER tooling, not a measured accuracy claim. No lawful representative
medical-document transcription corpus or fully registered OCR model/checkpoint/evaluation-
input bundle has been run, so all current OCR evaluations remain `EXPLORATORY`.

Aggregation pre-groups documents, labels and matches rather than rescanning every span for
each output row. The parser also bounds each artifact to 10,000 documents, 100,000 spans
and 1,000 labels, and rejects evaluations requiring more than 5,000,000 candidate overlap
comparisons or 2,000,000 overlap edges; larger corpora must be divided by a fixed,
predeclared document partition.

The result remains `EXPLORATORY` and non-reportable unless all provenance resolves exactly:
the model ID and immutable `sha256:<64 lowercase hex characters>` checkpoint must match the
local model registry and checkpoint bytes; the model's registered evaluation report must
agree on model, checkpoint, dataset ID, dataset version, and task ID; and that dataset/task
must resolve in `dataset_registry/tasks.json` as validation-ready with the requested
registered `test` or `external_test` split. The digest of the actual uploaded evaluator input
(an ordered combined digest for gold/prediction pairs) must also match a nonzero SHA-256
registered identically in the model artifact bundle and evaluation report. The locally
registered input artifact's path, byte length, format, split, and bytes are verified before
eligibility. At least one gold span is also required. Missing, malformed, unknown, ambiguous,
stale, or contradictory evidence is retained as an explicit reporting blocker and the run
stays `EXPLORATORY`.

No clinical-NLP model/dataset/checkpoint/evaluation-input bundle currently satisfies this
gate, so clinical-NLP runs remain exploratory even when the uploaded schema and attestations
are valid.
`ELIGIBLE_FOR_REPORTING`, where available for another supported evaluation task, means only
that the exact registered held-out evaluator bytes were recomputed under registry-bound
internal research provenance. It is never clinical activation, external or clinical
validation, generalization evidence, or proof that an uploader's annotation/adjudication
claim is correct.

Focused behavioural and API coverage is in
`backend/tests/test_clinical_nlp_evaluation.py`. Fixture results are test assertions only
and are not reported as corpus performance.

Still not implemented or not validated: table-cell extraction accuracy, any measured
clinical NLP accuracy on a lawful independently adjudicated corpus, and OCR CER/WER on a
lawful representative medical-document transcription corpus. No such corpus has been
registered or executed.

## Blocker

`BLOCKED_NO_ANNOTATED_CORPUS`. Evaluation needs independently annotated clinical text
that MedTwin may lawfully use:

- The case reports in the workspace are identifiable patient records; the directive
  forbids using them for experiments (see `docs/security/PHI_RELEASE_BLOCKER.md`).
- No annotated corpus is present locally (searched the imported repositories for NegEx /
  assertion / BioScope-style test sets on 2026-10-24; none found).
- Candidates requiring a separate decision: the NegEx test annotations (check licence),
  the i2b2/n2c2 2010 assertion corpus (data-use agreement), MIMIC-derived corpora
  (credentialed access). Downloading or registering any of them is a user decision.

Until one is available, every extracted statement stays `PENDING_HUMAN_REVIEW`, the
provenance reports `BASELINE_NOT_EVALUATED_ON_ANNOTATED_CORPUS`, and model-derived
statements are marked "Model inference · unvalidated" in Document Intelligence.
