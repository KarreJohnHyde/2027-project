# Universal medical AI directive — progress ledger

Directive: `MEDTWIN_CLAUDE_CODEX_UNIVERSAL_MEDICAL_AI_MASTER.md` (copied into the repository root on
2026-10-30, SHA-256 prefix `cc80e74d78ab`). Earlier ledgers (`docs/development/MASTER_PROGRESS.md`,
`docs/verification/COMPLETENESS_AUDIT_2026-10-29.md`) record previous work and stay as history.
Statuses: DONE, IN_PROGRESS, BLOCKED, NOT_STARTED. A status is DONE only with the evidence named.

## Environment (2026-10-30)

Windows 11 26300; Python 3.12.15 (`.venv`); Node 24.22.1; GPU NVIDIA RTX 5060 Laptop, 8 GB (7.9 GB free);
free disk C: 179 GB, D: 142 GB. Codex CLI 0.164.0, signed in; the first review request returned a usage-limit
error (next available 2026-11-04 16:21), so **no Codex review has run in this cycle**. QA stack:
`scripts/dev.ps1 -Mode qa -StateDir %TEMP%\medtwin-ieee-case` (worker job execution).

Test baseline before changes: backend 495 passed, 2 skipped. After changes: 515 passed, 2 skipped.

## Milestones

| Milestone | Status | Evidence | Next small step |
| --- | --- | --- | --- |
| M0 Baseline and safety | DONE | Registry 22 entries (15 READY_UNVALIDATED, 4 WEIGHTS_MISSING, 2 DEPENDENCY_MISSING, 1 UNSUPPORTED); 12 checkpoints hash-matched (`docs/research/EXISTING_MODEL_CHECKPOINT_VERIFICATION.md`); failure matrix `REAL_IMAGE_FAILURE_MATRIX.md` | — |
| M1 Real 2-D polyp mask | DONE (research use) | Served Kvasir-SEG masks equal training-time masks (pixel agreement ≥ 99.954 %, RLE exact 120/120, source-pixel Dice 0.768); browser: overlay coincides with the image at fit and zoom, restored after reload, confirmed by a clinician account with the output unchanged, organ-level schematic link only; reference-mask comparison (Dice 0.868 on the shown held-out image); wrong-modality image refused; EXIF orientation fixed | Reviewer mask editing; a polyp-free GI set to measure negative behaviour |
| M2 Real boxes | DONE (research use) | Kidney-stone and stenosis detectors reproduce their reported operating points through the served path (`UPLOAD_INFERENCE_PARITY.json`); browser on a held-out kidney-stone slice: 3/3 publisher boxes matched at IoU ≥ 0.5, 1 false positive, overlay exact | Reference boxes as a GROUND_TRUTH layer (masks only today) |
| M3 Volumetric cardiac proof | DONE (research view) | ACDC served masks identical to saved for 98/98 frames (2 refused by the spacing envelope); new patient-derived surfaces from a run's own mask (marching cubes, scan voxel frame, not registered to the atlas), phantom tests for frame and volume; browser view on a held-out ACDC frame. Scanner series (2026-11-06): cine phase choice, short-axis plausibility and attestation, axis convention chosen by anatomy and checked in patient coordinates; 91 of 98 held-out frames accepted with simulated geometry, macro Dice 0.750 vs 0.753 (`docs/validation/CARDIAC_SCANNER_SERIES.md`) | A real scanner series with reference masks |
| M4 Anatomy L1/L2/L3 | IN_PROGRESS | L1 schematic organ association drawn on the single-organ view (pale organs such as the white brain models now get a stronger tint, checked in the browser on a confirmed stroke run); L2/L3 on the atlas blocked (no registration); patient-derived surfaces shown in their own frame, for cardiac MRI, CT organs (TotalSegmentator) and brain lesions (stroke, glioma) | Landmark-based registration needs patient CT/MRI with landmarks |
| M5 First new specialty model | DONE for MURA (research use); CT organs added (third-party) | MURA (owner confirmed the Stanford agreement): study-level AUROC 0.898 (0.880–0.917), kappa 0.677 (0.632–0.718) on the publisher's validation split (1,199 studies, 783 patients); applicability gate built. TotalSegmentator v2: LUNA16 lung Dice 0.974 (0.972–0.975), 60 scans. RSNA intracranial haemorrhage (owner-confirmed licence, 2026-11-04): per-subtype AUROC 0.969–0.992, study-level 0.980 on 1,894 held-out patients. Brain MRI (2026-11-05, licences declared in the archives): ischaemic stroke lesions on DWI + ADC (ISLES 2022) held-out Dice 0.752 (0.666–0.822, 38 patients), serving parity 32/37 identical with 6 voxels differing in all; glioma sub-regions (MSD BrainTumour, published 2026-11-06) whole tumour Dice 0.908 (0.890–0.923), tumour core 0.856, enhancing tumour 0.802 on 73 held-out patients, serving parity 73/73 accepted. DeepSA has weights but no licence | Infection needs licensed labelled data (the local TB archives are truncated downloads); DeepSA needs the authors' permission |
| M6 Video and other scopes | IN_PROGRESS | Since 2026-11-05: MP4/AVI uploads with a decode check; frames sampled at an interval, each measured (brightness, dark share, sharpness) and scored by a still-image endoscopy model after its applicability check; timeline viewer with the frame and its mask (`backend/tests/test_video_frames.py`). Not evaluated on video; no other scopes | Video-labelled, procedure-separated data to evaluate the per-frame timeline; tracking |
| M7 Model and longitudinal comparison | IN_PROGRESS | Same-image comparison of a model mask with a declared reference mask; reviewer corrections of 2-D masks stored beside the run with what changed (2026-11-05); paired held-out comparison of ECG-only vs ECG + age/sex fusion; held-out cohort metrics per model | Side-by-side runs of two same-task models in the viewer |
| M8 OCR/NLP on the owner's cases | IN_PROGRESS | See "Owner's cases" below. Secondary NLP beside the rules (2026-11-04): scispaCy on by default where installed, medSpaCy ConText agreement per report, RadGraph-XL observations with anatomy on imaging pages, MedCAT wired in (example pack only); about 13 s added per report on this PC, off on Vercel | A licensed MedCAT model pack; an annotated report set to measure any of them |
| M9 Forecasting | BLOCKED | No longitudinal outcome data for a defined target. Multimodal fusion now runs for ECG + age/sex (PTB-XL), with no measurable gain over the ECG alone (paired difference +0.001, 95% CI -0.001 to +0.004) | A dataset with repeated measurements and later outcomes (e.g. MIMIC-IV, credentialed) |
| M10 Whole-application QA | IN_PROGRESS | 2026-11-05 cycle (brain MRI, fusion, corrections, CXR marks, video): backend 576 passed, 4 skipped; frontend typecheck, lint and build pass; 38 node tests pass; Codex read-only review, 11 findings, all fixed; browser checks on an isolated QA stack with public held-out inputs (ISLES test case: run, slice overlay, 3-D surface, review, brain tint; Kvasir-SEG polyp: correction saved and compared; Kvasir slideshow video: 8/8 frames scored; PTB-XL fold-10 record with declared age/sex; NIH test radiograph: attention peak, region and measured rate). Earlier: after open access for every account, backend 517 passed, 2 skipped; frontend typecheck, lint and build pass; 38 node tests pass; privacy scan of every changed file clean. Codex returned a usage-limit error, so an independent review ran with the built-in code-review (high): 10 findings, 9 fixed (surfaces mounted only when opened, typed DEPENDENCY_MISSING and scikit-image added to the ML requirements, 0/1 label masks, runs made before orientation handling refused on rotated images, blocking upload endpoint, registry errors typed, review refresh, hyphenated echo modality, GPU buffers freed); the run listing still returns full outputs (N+1 query removed) | Done 2026-11-04: Codex (read-only) reviewed this cycle's code, 13 findings, 12 fixed, 1 declined with reason (`docs/CHANGELOG.md`) |

## Access policy (owner's decisions, 2026-10-30, 2026-11-04, 2026-11-05)

Every account uses every feature. Since 2026-11-04 people enter with name, age, gender and role (no password, no
registration); since 2026-11-05 there is one shared space in which every account lists and works on every case
(`MEDTWIN_SHARED_WORKSPACE=false` restores per-account privacy). What remains: only a case's creator deletes the whole
case, four-eyes on proposals, and the administrator-only global audit log. Reviews, corrections and
landmark manifests record whether each actor was a verified clinician, so an unverified confirmation is never shown
as professional confirmation. Details and browser check: `docs/CHANGELOG.md`, entry "every account has every feature".

## Owner's cases (processed separately, redacted copies only)

Each packet was redacted on this computer before upload: OCR in four orientations, identifier labels and
the values after them, ID-like header values, text on dark backgrounds (endoscopy overlays, a photographed
monitor), QR-code and barcode shapes, letterhead and footer bands, signature blocks, and manual masks for
handwriting and small print. Every page was checked by eye; printed dates and age/sex stay readable. Only the
redacted copies entered the isolated QA stack; nothing was sent anywhere. Figures below are counts only.

| Case | Pages | Page types (rules v3) | Results | Statements | Change from today's fixes |
| --- | --- | --- | --- | --- | --- |
| IEEE demo case (lab panel, abdominal ultrasound, chest CT, chest-film photo) | 5 + 1 image | processed on 2026-10-29 | see `FIGURE_CAPTIONS.txt` in the 2026-10-29 gallery | — | — |
| CASE-B-GASTRO (colonoscopy, histopathology, laboratory, bills, clinic note) | 19 | procedure 1; pathology 2 (one page photographed sideways and read upright); laboratory 13; billing 2; consultation 1 — 19/19 as a reader would type them | 64 values; 30 linked as reprints of earlier pages; 59 dated by the printed collection date; sex/age-specific intervals chosen from the printed sex and age, abstaining on a page whose age was not printed; vitamin D and CEA kept as category bands | 36; colitis affirmed; granulomas, dysplasia and malignancy negated; "to rule out neoplasia" hypothetical; laboratory leaflet text attributed to OTHER, not the patient | dated values 7 → 59; reprint links 26 → 30; correctly typed pages 13 → 19 |
| CASE-C-NEURO (requisitions, printed ECG, bill, laboratory, brain and spine MRI, clinic notes, echocardiography) | 16 | request form 2; billing 1; laboratory 4; imaging 4; consultation 3; printed ECG and a near-empty page unclassified | 32 values (blood count with the printed H/L flags, chemistry, blood pressure at two visits, LVEF) | 36; 15 negated as printed (normal cord signal, no Chiari, nil valve lesions, no wall-motion abnormality, no PAH, no clot); stroke historical | correctly typed pages 7 → 14; no laboratory dates because redaction covered them, and none were invented |

| CASE-D-NEURO-CT (non-contrast head CT: photographed film and printed report), added 2026-11-06 | 4 of 5 (two film close-ups, two photographs of the same report); the whole-sheet film photo was left out because its small overlay text could not be masked without covering anatomy | report pages typed as imaging; film pages unclassified | none (no laboratory values) | haemorrhagic contusion and perilesional oedema affirmed in the parietal lobe (linked to the atlas parietal lobe, shown as named in a report, unconfirmed); midline shift, fractures and a focal brainstem/cerebellar lesion negated as printed; the head-CT haemorrhage model refused both film crops as outside its training images (photographs of film, not native slices) | before the fix the main finding was missed: OCR read the bold lines without spaces and the vocabulary had no contusion term |

Fixed on 2026-11-06 from CASE-D: one short OCR slip no longer stops a long glued sentence from being split (`ocr_text`, runs of 20+ letters, one unknown piece of at most four letters); "haemorrhagic/cerebral contusion" and "perilesional/vasogenic/cerebral oedema" added to the vocabulary; lobe sites tolerate OCR-merged words ("PARIETALLOBE"); SQLite writers wait up to 30 s for a worker's lock instead of failing after 5 s.

Fixed today from these cases: abbreviated collection-date labels ("BLOOD COLLECTION DT"), which had split
reprinted results across two dates; page-type cues for histopathology, clinic notes, request forms, MRI,
hyphenated echocardiography and colonoscopy headings, tolerant of OCR-glued words (`page-type-rules-v3`).

Fixed on 2026-11-06 (synthetic tests in `backend/tests/test_report_extraction_gaps.py`): qualitative urinalysis rows
become statements with the printed result (Nil/Absent negated); ESR printed as "ONE HOUR READING" and "RDW (SD)" are
read; printed ECG values (ventricular rate, PR, QRS, QT, QTc and the QT/QTc pair) and echocardiography M-mode
dimensions (IVSd, LVIDd, LVIDs, LVPWd, FS, LA, aortic root) are measurements; symptom phrases (memory impairment,
neck pain, numbness and 18 others) are SYMPTOM statements; OCR letter drops in "contuson"/"perilesonal ...dema" are read.

Still open from these cases: a test name printed over two lines (MCHC) was missed on the original page, but both
two-line layouts tried synthetically are read, so the failing layout is not reproduced; a specimen line printed
after a result row is attached to that row; one microscopy sentence is mapped to "endoscopic procedure". The last two
need the source layout to fix without guessing.
