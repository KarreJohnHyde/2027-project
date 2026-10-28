# Clinical NLP and laboratory-extraction error audit (photographed reports)

Date 2026-10-27. Sources: owner-provided phone photographs of printed reports for three different
people, plus one MedTwin report the owner exported. Laboratory, radiology, ENT, endoscopy,
pathology, neurology and echocardiography reports and bills are represented. The photographs
were OCR'd in memory on this workstation only, and nothing from them is stored in the
repository. Regression fixtures are synthetic and reproduce only the layout defects.

Status: `IMPLEMENTED_TESTED` against those fixtures (`backend/tests/test_report_photo_extraction.py`,
47 tests). Extraction **accuracy remains unvalidated**: no independently annotated corpus exists.

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

## Second private run (2026-10-28)

The same three packets were run again through the full pipeline (OCR → de-identification →
rules). Each failure below was reproduced in a synthetic fixture that fails on the previous code.

| # | Observed failure | Cause | Fix (code path) |
| --- | --- | --- | --- |
| 21 | Results printed at the right of a tilted photo joined the row above or below | Rows were grouped on raw image y | `ocr._rows`: rows are grouped on the de-skewed baseline (median angle of wide boxes, ≤ 15°); fullwidth punctuation is mapped to ASCII |
| 22 | "Focally at a" / "evidence of dysplasia/ malignancy." affirmed malignancy | The detector dropped the printed line holding "No granulomas … No" (box score 0.3–0.5) | `ocr.DETECTION_BOX_THRESHOLD` = 0.3 recovers it, and the finding reads NEGATED. A lower-case line after a lost-line gap gets a blank line, and any lower-case line start after a sentence end or blank line is `UNCERTAIN` with an `OCR_FRAGMENT` cue |
| 23 | A whole page (indication, findings, procedure) produced no statements | The page was photographed sideways; every row merged into one 1,456-character line, and a "home collection" advert on it excluded the line | Sideways pages (most text boxes ≥ 2× taller than wide) are turned both ways and read in the orientation that recognises with higher confidence; boxes map back to page pixels and `rotation_degrees` is recorded. Advert/disclaimer exclusion is per sentence on lines over 200 characters |
| 24 | "Calcification: Ni." affirmed after the "l" of "Nil" was lost | — | Post-negation "Ni" only directly after ":"/"-" and closing the item |
| 25 | HbA1c ADA bands, ESR age strata, WBC and differential age bands, vitamin D categories lost or mislabelled | "Method:…"/"Specimen:…" left-column lines ended the reference column; "50-Upto10" was read as a date fragment | Method/specimen lines (OCR variants "Methoo.", "Mtod:", "Spemn:") keep only their reference-column part; a "Upto" bound is never a date |
| 26 | MCV, MCH, vitamin B12 and CEA missing | The result sat on the method/specimen line above or below its test name | Cross-line pairing, only when the result line is led by a method/specimen label (or an ESR "one hour reading"), its unit belongs to the analyte, and the name row has no result of its own |
| 27 | Age-banded strata indeterminate (ages printed like "52Yr3M") | Age format | `AGE_RE` accepts unspaced years-months-days |
| 28 | Headings "IMPRESSION-…", "FINDINGS-…" and a heading after a sentence on the same line were missed; a heading carried over to the next document in a packet | Heading syntax; no page reset | Colon, dash or bare headings, also after ". "; headings do not cross a page break |
| 29 | "S/Ploopileostomyanastomotic site ulcer" made the ulcer historical | Glued shorthand hid the procedure | Glued runs are segmented after shorthand insertions, so "S/P" binds to the ileostomy |
| 30 | "Mitral regurgitation – Grade Trivial  Mitral stenosis – Nil" negated the regurgitation | Post-negation scope ran to the clause end | Scope stops at the next entity that is not coordinated with the negated one |
| 31 | Facility advert "All2D,3D,4D … Biopsy and Laboratory services" produced a biopsy; "Tniglycerides"; "Crohnsdisease"; "TO R/O RIGHT DIAPHRAGMATIC" / "HERNIA"; "H" flag after the unit | OCR gluing and layout | Advert pattern, OCR-variant triglyceride alias, glued Crohn's term, adjective line-wrap join, leading H/L flag |

Values that OCR could not read are not guessed: haemoglobin printed as "9." and units read as
"Ip/Bw" or "1p/6" (calcium, urea, creatinine, MCHC on two pages), and an RBC unit split as
"millioncells/" + "PL", produce no measurement.

## Residual limitations seen in the private run

- OCR did not read one lab page's printed sex/age header, so sex-stratified creatinine and
  age/pregnancy-stratified TSH intervals remained (correctly) indeterminate on that page.
- One impression's reading order was scrambled by OCR in the first run, and one result row lost
  its label (a ratio row printed without a readable name). De-skewed rows and sideways-page
  reading (fixes 21 and 23) address the reading-order causes found in the second run; the label
  is not recoverable from the text.
- Recognition of a line can change when other boxes are added to the same recognition batch
  (RapidOCR pads each batch to its widest crop); fix 24 covers the one case seen. Single-crop
  recognition was tried and read the recovered pathology line worse, so batching is unchanged.
- Coreference ("lesions are noted within it") is not resolved; the site stays empty.
- Accuracy needs a lawful, independently annotated report corpus (`NEXT_ACTIONS.md` item 5).
