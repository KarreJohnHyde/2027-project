# Screenshot issue fixes — 2026-11-06

This follow-up addresses the Medical Imaging and Multimodal Intelligence screens supplied by the user. It preserves the existing application, source evidence, reviews, examination identity checks and model applicability gates.

| Issue in the screenshots | Implemented behavior |
| --- | --- |
| Native-image attestation and inference offered for a detected film montage | Imaging passes its source assessment into the single-model and batch controls. Film inputs offer panel inspection, report review, synthesis and native-image upload actions. They cannot be submitted again through these native-image controls. Backend refusals remain enforced. |
| Tiny montage in a large black viewer | The first candidate panel loads automatically at a readable size. Other panels remain selectable, and the complete original montage is available in a disclosure. Clicking the current panel no longer clears its preview indefinitely. Asynchronous crops discard stale responses and release object URLs. |
| Public evaluation metrics dominate the model panel | Evaluation and licence details are collapsed. Other raster inputs require an explicit image type before models are offered, so a gastrointestinal model is not selected by default for an unidentified CT image. |
| Metadata claims that no model is configured | Metadata describes the actual preview state: film abstention or no inference run. Raster dimensions are labelled in pixels, a raster frame is not called a CT slice, and missing physical calibration is explained. DICOM-only fields are omitted for raster images. |
| Job execution success looks like a successful prediction | Batch results include `analysis_status`, attempted/output counts and independent per-model outcomes. All abstentions produce `ABSTAIN`; execution errors produce `ERROR`; mixed outputs produce `PARTIAL`. Queue completion messages and the batch UI explain the result. One adapter error no longer prevents later independent models from running. |
| Duplicate contusions and oedema from repeated pages and OCR variants | Synthesis v2 normalizes case, spacing and bounded parietal-lobe OCR variants. Cerebral oedema synonyms are merged only with cerebral context. Opposite sides, assertions, certainty, temporality and examination/source scopes stay distinct. All original statements, offsets, page numbers, review states and corrections remain in provenance. |
| Different negative lesion statements combined | Pituitary and nonspecific lesion negatives retain separate scopes. Source statements remain inspectable. |
| Repeated abstention cards after reruns | Identical source-hash/model/status/reason outcomes are grouped with attempt counts and all run/job/upload references. Historical records remain intact. |
| Missing anatomy says only “Unavailable” | The UI distinguishes an unspecified site from a reported region with no atlas mapping. Affirmed mapped brain findings link to the brain atlas and request the reported structure. This is an unregistered reference region, not a patient lesion. |
| Present image appears absent from the fusion mask | Live evidence availability and independent model-output masks are separate. The saved processed-finding gate is labelled separately from report synthesis. A report and image can both be present with zero model predictions. |
| Examination linking is disconnected | A linker is available directly on Multimodal Intelligence and Case Workspace. Date candidates are deduplicated and can open a dated-examination form. Source/target/date changes reset confirmation; saved links have visible feedback. No identity/date attestation or clinical review is fabricated. |

## Report retest

The supplied PDF was tested using the previously prepared identity-redacted raster derivative. The original PDF was preserved. This derivative omits identifiers and some film panels; it does not establish native image geometry or independent diagnostic confirmation.

The fresh authenticated HTTP test created `CASE-D-NEURO-CT-FIX-VERIFICATION` in the isolated `.cache/report-app-test/medtwin.db` runtime. The original application database and earlier test case were retained.

- 18 extracted statements become eight distinct synthesis rows.
- Four contusion mentions merge into one row; two cerebral oedema mentions merge into one row.
- The pituitary and nonspecific focal-lesion negatives remain separate.
- Four genuine native-model refusals become one displayed outcome with four retained run IDs, including a final batch with the corrected completion message.
- Evidence mask: report present, image present, ECG absent, signal absent.
- Independent model-output mask: all zero. The montage does not produce a prediction or lesion overlay.
- No examination identity was attested automatically. Historical comparison and forecasting retain their real evidence requirements.

Structured outputs are saved in `C:\Users\johnn\OneDrive\Pictures\MedTwin_Report_Test_2026-11-06\After_Fixes`.

## Verification

`npm run check` passes (type checking, lint with existing warnings, production check build). The full backend suite passes: 597 passed, four skipped, ten existing dependency warnings. Commands: `npm run check` and `.venv\Scripts\python.exe -m pytest backend/tests -q --tb=short`. Regression coverage includes the pictured OCR variants, distinct negative scopes, preservation of every source statement, film metadata, grouped refusal provenance, all-abstention batch outcomes and continuing after an adapter failure.

Browser screenshot refresh requires an authenticated test workspace. A stopped or expired entry session is not evidence that the updated result pages were visually verified; do not substitute the earlier screenshots for new captures.
