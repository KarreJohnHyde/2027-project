# Official terminology and external OCR resource completion

The active user constraint is commercial-use eligibility. A public download, Kaggle uploader licence or a software repository licence does not establish rights to underlying clinical data. The resource inventory records primary evidence and eligibility decisions; it is an automated engineering/source review, not human legal approval, clinical clearance or an upstream-rights warranty.

## Implemented official reference catalogue

`backend/app/services/universal_terminology.py` adds an optional read-only ICD-10-CM FY2027 index. Primary sources are the [CDC FY2027 release directory](https://ftp.cdc.gov/pub/health_statistics/nchs/publications/ICD10CM/2027/) and [official release explanation](https://www.cdc.gov/nchs/icd/icd-10-cm/files.html). The effective period is 2026-10-01 through 2027-09-30.

The downloaded official order file has **98,403 entries: 74,879 source-valid reporting codes and 23,524 headers**, across 22 chapters. All are indexed with unchanged source code/description, source validity flag and tabular ancestry. Codes retain the official order file's dotless representation; conventional decimal spelling is a search synonym. Seventh-character variants are read from actual official rows, never generated: variants represented by tabular extension instructions attach to their longest existing tabular ancestor for context.

The original 169 curated condition examples keep their empty code mappings and review status. An official reference entry has `kind: "classification"`, `CATALOGUE_ONLY`, an exact **source-self** ICD-10-CM code mapping and no model link. Source-self identity does not constitute a clinically reviewed crosswalk to a MedTwin example or a patient diagnosis. Classification includes headers, injuries, external causes and reasons for contact; these are not 98,403 separate diseases or AI-supported conditions. The combined local catalogue has **103,252 entries**, including the prior 4,849 curated/atlas/analyte entries.

All 25 application families receive explicitly declared `BROAD_CHAPTER_OR_CODE_RANGE_CONTEXT_ONLY` associations. These associations are navigation context: a cross-system chapter, injury or site-specific neoplasm may remain under systemic context. Per-organ results are not a comprehensive clinical coding crosswalk. Global classification search retains the complete imported official release. No ICD-11 import or ICD-11 commercial-rights determination is claimed.

Primary reuse evidence: the [CDC report on the ICD-10-CM injury framework](https://stacks.cdc.gov/view/cdc/27312/cdc_27312_DS1.pdf) explicitly identifies the ICD-10-CM structure as public-domain material; [CDC's agency-materials policy](https://www.cdc.gov/other/agencymaterials.html) describes attribution, unchanged substantive content, no-endorsement and no-charge source requirements, plus exceptions and international qualifications. This implementation preserves official descriptors, attributes CDC/NCHS and returns the notice with every official result/status. No CDC logo or endorsement is used. This review is limited to this official ICD-10-CM release; it does not clear unrelated WHO, CPT, SNOMED, third-party vocabulary or source-data rights.

Source fingerprints:

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| `icd10cm-code-descriptions-2027.zip` | 2,192,779 | `93e3ad6004badf470c55bfe679b748ae88fd9b2b421851e409eec382c7713b9a` |
| `icd10cm-table-and-index-2027.zip` | 20,923,571 | `99b5c2be16ff53eab861cc0be4b1dacba27f687b8ff4bc700679944355037ee0` |

The local SQLite index is 81,305,600 bytes. Logical rows have SHA-256 `f8f28b19e79722ef055bd5296dbd8a039eb98a1ca083acf980a75168e263179d`; the actual deployed index SHA is also exposed. The builder uses only Python's standard library, validates reviewed source hashes, bounds ZIP members, rejects custom XML entities and duplicate/missing source-parent data, and writes a new explicit reference-only database. An identical build is idempotent; different existing content is refused. Existing application databases, cases, users, model registries and weights are never changed.

```powershell
.venv/Scripts/python.exe scripts/fetch_external_resources.py --resource icd10cm-2027-codes --resource icd10cm-2027-tabular --directory data/external/completion-2026-11-13
.venv/Scripts/python.exe scripts/build_official_terminology.py --codes data/external/completion-2026-11-13/icd10cm-code-descriptions-2027.zip --tabular data/external/completion-2026-11-13/icd10cm-table-and-index-2027.zip --output data/external/icd10cm-fy2027/catalogue.sqlite3
```

## API and deployment contract

- `GET /universal/terminology/status` returns `available`, `state`, source/version/effective period, counts, source hashes, logical `data_sha256`, actual `index_sha256`, broad `system_counts`, rights evidence and attribution notice.
- `/universal/systems` includes `official_terminology` status and each family's `reference_classification_count`. Existing `condition_count` remains the curated condition count, avoiding an inflated disease claim.
- `/universal/catalogue` includes classification references for no kind filter or `kind=classification`. The bounded order is curated concepts, official references (exact source code first), then detailed atlas structures. Existing source groups retain stable internal order. A request materializes at most the requested 200 items; it does not expand 98k records into application memory. `kind=condition` preserves original curated-condition semantics.
- `/universal/catalogue/icd10cm:fy2027:e119` demonstrates exact source-code lookup; `q=E11.9` supports conventional decimal search. No code similarity adds a diagnosis, anatomy registration or model capability.
- The catalogue `data_version` includes official index availability/content fingerprints, so missing/different deployed resources produce different revisions.

Default local path: `data/external/icd10cm-fy2027/catalogue.sqlite3`. Configure `MEDTWIN_TERMINOLOGY_DB` for another explicit path. A container must mount the generated file read-only, for example `/data/external/icd10cm-fy2027/catalogue.sqlite3`, and set that environment variable. Downloads/indexes remain ignored local resources; they are not implicitly bundled into an image. Missing, unreadable, corrupt or incompatible indexes report `OFFICIAL_REFERENCE_INDEX_UNAVAILABLE`; the prior curated/atlas/analyte catalogue still works. The status does not silently pretend the optional release was imported.

## Actual OCR evaluation, with separate source/rights states

No OCR weights or preprocessing were changed or fitted to these corpora. Both executions used the existing `ocr_images` path, RapidOCR 1.4.4, ONNX Runtime 1.31.0 and Pillow 13.0.0 on Python 3.12.10. Transcript metrics use Unicode NFC, casefold and whitespace collapse, without spelling or clinical repair. CER/WER are edit counts divided by reference character/word counts; lower is better and values may exceed one. Results contain only pseudonymous IDs, hashes, counts/errors and confidence/rotation metadata. Raw source images, words, transcriptions and model-read text are not published in results or application cases.

| Corpus/run | Primary rights and actual nature | Actual units | CER | WER | Other observed results |
| --- | --- | ---: | ---: | ---: | --- |
| [ClinOCR-Bench v1.0](https://github.com/ClinOCR-Bench/ClinOCR-Bench/releases/tag/v1.0) | Primary release/readme explicitly MIT; synthetic clinical content, programmatic source transcription followed by author human audit | 48 held-out synthetic pages; 8 per each of 6 artifacts, all exemplars excluded | 0.324620 | 0.752572 | 2 empty outputs; 0 exact pages; 20 unique reference-text hashes across the 48 derivative pages |
| [RxHandBD Zenodo v1](https://zenodo.org/records/18478741) | Primary dataset API `metadata.license.id=mit-license`; author describes physical prescription-word crops. Publisher-supplied labels; individual annotator/reviewer method is unspecified | Entire 1,115-item upstream test split, real word crops | 0.579932 | 0.923201 | 111 exact words (9.955%); 252 empty outputs; 0 cross-split exact image duplicates among 4,463 train/1,115 test image hashes |

These are newly executed error measurements showing substantial weaknesses; they do not establish improvement, calibrated clinical confidence or accurate dispensing/report extraction. ClinOCR uses repeated templates/reference text and simulated handwriting fonts; its 48 pages are not 48 independent clinical patients. RxHandBD supports source-word recognition, not whole-page patient/report layout, laboratory row association, units, dates, intervals or dose verification. Writer, patient and original-prescription independence are not verified. Independent human checking of critical full-report references remains outstanding. Therefore **U-014 full real clinical report/laboratory validation remains partial**, even though commercial-eligible external synthetic-page and real-word evaluations have now executed. No model training or clinical activation was performed.

```powershell
.venv/Scripts/python.exe scripts/fetch_external_resources.py --resource clinocr-v1 --resource rxhandbd-v1 --directory data/external/completion-2026-11-13
.venv/Scripts/python.exe scripts/benchmark_external_ocr.py --archive data/external/completion-2026-11-13/ClinOCR-Bench-v1.0.zip --dataset clinocr --per-subset 8 --output artifacts/completion-2026-11-13/resources/clinocr-synthetic-ocr.json
.venv/Scripts/python.exe scripts/benchmark_external_ocr.py --archive data/external/completion-2026-11-13/RxHandBD-zenodo-v1.zip --dataset rxhandbd --output artifacts/completion-2026-11-13/resources/rxhandbd-real-word-ocr.json
```

Benchmark inputs must match the exact reviewed archive SHA before OCR can execute. Future executions include bundled ONNX weight hashes; the executed runs have a separately timestamped post-run runtime fingerprint supplement, `ocr-runtime-provenance.json`. The OCR source and bundled models were unchanged during both runs. Pipeline scripts execute no downloaded repository code, access no credentials and make no external model/API calls.

ClinOCR archive: 119,227,531 bytes, SHA-256 `ce1d231138050abf7f458ba5e6bd75c6ee2f3832b72f22296843da4c5ba45457`. RxHandBD archive: 32,464,605 bytes, SHA-256 `25d31c7bc1ceab4b3707d5e6d2205e518cadbd75d2f99efe1492a1aee5ef1951`; the source API also publishes MD5 `c096859fcccb33655edaf34e4c1e7a06`. Primary metadata/license receipts are retained separately from downloaded images; required attribution remains attached.

## Kaggle and alternative-source audit

`artifacts/completion-2026-11-13/resources/resource-inventory.json` records all 5 downloaded resource receipts plus 7 rejected/unavailable alternatives with primary URLs, versions, declared rights, actual byte count/hash and accepted/rejected reasons.

The original Mamun Kaggle prescription corpus explicitly permits research/education only. A separate educational run started under the earlier task scope and was interrupted immediately after the user's commercial-only instruction, before producing a result artifact. Its ignored archive is retained as audit history, excluded from all commercial-development results. The downloader and benchmark runner now refuse this source. An Apache-labelled downstream OCR mirror does not override the author's underlying rights, and OCR-derived text is not independent human reference data.

Other Kaggle clinical-text/image candidates were explicitly synthetic or offered no stronger real-human reference evidence; they were not downloaded. The courtotlab pipeline generates mock documents and has no current root licence file, so it was not imported as independent real validation. A potentially real CC BY bilingual Mendeley prescription corpus could not be inspected through its public file API (403); no access restriction was bypassed. BHCP-DOC's primary page contains noncommercial restrictions and release placeholders, so it is ineligible. These exclusions are concrete remaining resource limits, not a reason to substitute synthetic annotations for human clinical truth.

## Verification and handoff

Command: `.venv/Scripts/python.exe -m pytest backend/tests/test_universal_catalogue.py backend/tests/test_completion_resources.py -q` → **46 passed**. Tests cover original catalogue contracts plus offline miniature official-source parsing, seventh-character ancestry, exact source-code identity, optional/missing/corrupt deployment behavior, bounded source-group pagination, unchanged curated mappings, content revision, idempotence/checksum refusal, XML entity refusal, commercial-only source rejection, downloader receipts/budgets, external metric denominators and exemplar exclusion. Fixture labels test software contracts; measured OCR results come from the separate actual datasets above.

Actual index/API evidence: `official-terminology-verification.json`. Actual OCR evidence: `clinocr-synthetic-ocr.json`, `rxhandbd-real-word-ocr.json`, `ocr-runtime-provenance.json`. Rights and decisions: `resource-inventory.json` and primary metadata/license receipts. Root owns deployment mounts, shared UI notices and requirements reconciliation; these changes do not alter original model registries or commercial/clinical gates.
