# Clinical NLP and laboratory-extraction error audit (photographed reports)

Date 2026-10-27. Sources: owner-provided phone photographs of printed reports for three different
people, plus one MedTwin report the owner exported. Laboratory, radiology, ENT, endoscopy,
pathology, neurology and echocardiography reports and bills are represented. The photographs
were OCR'd in memory on this workstation only, and nothing from them is stored in the
repository. Regression fixtures are synthetic and reproduce only the layout defects.

Status: `IMPLEMENTED_TESTED` against those fixtures (`backend/tests/test_report_photo_extraction.py`,
31 tests). Extraction **accuracy remains unvalidated**: no independently annotated corpus exists.

## Failures found and fixes

| # | Observed failure | Cause | Fix (code path) |
| --- | --- | --- | --- |
| 1 | "No pleural effusion or pneumothorax", "No focal consolidation or suspicious pulmonary mass lesion", "No mass lesion is seen" came out **AFFIRMED** | OCR dropped spaces ("Nopleural … orpneumothorax", "masslesion"), so neither cue nor term matched as a word | `ocr_text.normalise`: segments a glued run only when every piece is a known word; an exact offset map keeps evidence quoting the page as printed |
| 2 | "…within normal limits.No" / "pericardial effusion." gave an affirmed effusion | Every newline was a sentence boundary | `split_sentences` / `_line_wraps`: a break continues the sentence after a dangling function or negation word, or before a lower-case line. Unbulleted impression items stay separate, so a "No" never reaches the next item |
| 3 | "…WITHOUT … INVAGINATION-likely due to phrenic nerve palsy" negated the palsy | Negation crossed the explanatory dash | Dash-before-"likely/due to" ends the clause, and the nearer uncertainty cue governs |
| 4 | "tor/oright diaphragmatic hernia" stayed CERTAIN | Glued shorthand | Shorthand splitting ("to r/o right") → HYPOTHETICAL |
| 5 | "FNAC to rule out …", "follow up with biopsy report" read as performed | No planned/advised context | Advised-procedure cues and plan/recommendation/advice sections → HYPOTHETICAL |
| 6 | Bill rows ("SMALL BIOPSY … 970.00 1.0 0.00 970.00") and facility footers ("All … FNAC, Biopsy and Laboratory services") produced performed procedures | No document-type awareness | Billing lines and pages, facility and disclaimer lines produce no statements; counts are recorded in provenance |
| 7 | Tumour-marker interpretive text ("may be found in patients with … cancer") produced patient malignancies | No generic-population experiencer | Clause-wide `GENERIC_POPULATION` cue → experiencer `OTHER` |
| 8 | "American Diabetes Association" produced diabetes | Organisation name in the reference column | Excluded from the diabetes term |
| 9 | "No evidence of dysplasia/ malignancy" (wrapped after "No") affirmed malignancy | Line wrap | Fix 2 |
| 10 | "No features suggestive of myelomalacia" would read as uncertain-affirmed | "suggestive of" was an uncertainty cue | Strong negation cue checked first |
| 11 | "Mitral stenosis – Nil" not negated | No post-negation for "Nil" | Post cue "– (Grade) Nil" |
| 12 | HbA1c, triglycerides, LDL and T3 missing | Asterisk flag between value and unit ("7.8*%") | Flag-before-unit; `documented_flag` = ABNORMAL |
| 13 | HDL missing; risk of HDL read as total cholesterol | Method text between label and value; loose "cholesterol" alias | Method chunk, VLDL/ratio analytes, and `forbid_prefix` guards (HDL/LDL/VLDL before "Cholesterol"; Direct/Indirect before "Bilirubin"; Estimated Average before "Glucose"; Corpuscular before "Haemoglobin") |
| 14 | "Estimated Average Glucose" recorded as glucose; "Indirect Bilirubin" as total bilirubin | Same | Distinct analytes |
| 15 | "Documented interval: —" for every row | Single-space intervals and stratified reference columns were never parsed | Reference-column parser: ranges, one-sided limits, "up to", "& above", thousands separators, sex/age/pregnancy/category strata over continuation lines. A stratum is applied only from documented sex and age; otherwise `INDETERMINATE_PRINTED_STRATA` with all options stored |
| 16 | CBC, ESR, vitamins, CEA, thyroid T3/T4, absolute counts, MPV, CK missing | Analytes, units (`gm/dL`, `cells/cumm`, `lakhs/cumm`, `million cells/µL`, `mlU/L`) | Terminology additions |
| 17 | Reprinted pages produced 3× CRP, creatinine and eGFR rows, n=3 "trends" and 3 calculated eGFRs | No source-occurrence identity | `measurement_identity`: one observation per analyte/value/unit/date (or same file if undated); every occurrence kept and linked; trends, eGFR and report tables count it once |
| 18 | Calculated eGFR shown without the laboratory's own eGFR | — | Same-report documented eGFR returned beside the calculation, with the difference flagged for review; neither overwrites the other |
| 19 | Throat video endoscopy mapped to the intestines | Generic "endoscopy" term | ENT endoscopy term, no organ system |
| 20 | Photographed report pages could be sent to image models | Only the declared modality was checked | Content gate (`docs/validation/DOCUMENT_PHOTO_GATE.md`) |

## Residual limitations seen in the private run

- OCR did not read one lab page's printed sex/age header, so sex-stratified creatinine and
  age/pregnancy-stratified TSH intervals remained (correctly) indeterminate on that page.
- One impression's reading order was scrambled by OCR, and one result row lost its label
  (a ratio row printed without a readable name). Neither is recoverable from text alone and needs
  layout geometry.
- Coreference ("lesions are noted within it") is not resolved; the site stays empty.
- Accuracy needs a lawful, independently annotated report corpus (`NEXT_ACTIONS.md` item 5).
