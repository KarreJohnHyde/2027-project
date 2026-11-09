# CASE-D head-CT audit and fixes (2026-11-06)

Scope: the master implementation brief of 2026-11-06, checked against the stored `CASE-D-NEURO-CT` record (identity-redacted report PDF plus two film-crop images, pseudonym chosen by the owner) in an isolated, encrypted QA database. No patient name, identifier, date of birth, clinician, centre or contact detail appears in this report, the tests or the commits. Nothing was committed, pushed or deleted.

## Starting point

- **Architecture as found.** The brief describes a Node gateway on 8787, FastAPI on 8790 and Supabase. The repository has none of the first two: it is a React/Vite frontend (8443 in development) and a FastAPI backend (`backend/app/main.py`, `/api/v1`, 8000 in development; isolated QA stacks via `scripts/dev.ps1`). Supabase is an optional, unconfigured browser client with no application tables. Work used the existing structure.
- **Parallel work.** Another coding agent worked through the same brief between 02:14 and 10:35 on 2026-11-06 (case workflow API, rule-based evidence synthesis, film-panel controls, persisted development signing key, read-only forecast reads, same-patient confirmation for comparisons; see `MASTER_IMPLEMENTATION_STATUS.md`). It verified on its own copy of the report. This pass started after its last write, checked its claims on the stored CASE-D record and fixed what was still wrong there.

## Reproduced on the stored record, and the result after this pass

| Check | Before (stored record) | After re-analysis with current code |
| --- | --- | --- |
| Report statements shown | 88 (two analyses of one report, both current) | 59 from the current analysis; 88 kept as history (`include_superseded=true`) |
| Haemorrhagic contusion | Affirmed, parietal lobe, **no laterality** | Affirmed, right, parietal lobe (atlas `nervous.parietal_lobe`) |
| Perilesional oedema | Affirmed, no laterality | Affirmed, right, SEVERITY cue "mild" |
| Midline shift | Negated | Negated |
| Scalp soft-tissue swelling | Only a bare model "swelling", no site or side | Affirmed, right, "right parietal region scalp" |
| Skull fracture | Negated, **no site** | Negated, site "cranium" (cue `SITE_FROM_PRECEDING_SENTENCE`) |
| Glued OCR runs as entities | "basalgangliaarenormal", "iscentral", "andnormal", "obviousfocal", one 35-letter garble | None; garbled runs excluded and counted |
| Evidence synthesis | 28 groups mixing rules and secondary NLP; stale groups from the old analysis | 8 report findings, 25 secondary NLP mentions listed apart, 0 contradictions |
| Film crop A (single panel), head-CT model | Refused, "applicability score 58899915.13; limit 2.50" with no reason | Refused; message names colour (73% of pixels) and a greyscale copy still outside (8,568) |
| Film crop B | Refused by the applicability score | Refused earlier by the photographed-film gate |
| Examinations / comparison / forecast | 0 linked; not run | Unchanged by design: linking needs a reviewer to confirm identity and the study date |
| Overall disease probability | None | None |

## Root causes and fixes in this pass

| Root cause | Fix | Where |
| --- | --- | --- |
| Re-analysing a report stored a second run, and every view read the statements of every run, so the report appeared twice with conflicting old and new extractions | The latest successful report analysis of each upload is current; earlier runs stay as history with their reviews and corrections. Applied to statements, effective evidence, documented attributes, synthesis, anatomy evidence, comparison, concordance, analytics, chest-radiograph report linking and the workflow's review count | `services/report_runs.py`, `routers/cases.py`, `services/evidence_synthesis.py`, `anatomy_evidence.py`, `comparison_service.py`, `concordance_service.py`, `analytics_service.py`, `cxr_research.py`, `case_workflow.py` |
| scispaCy and RadGraph-XL received the raw OCR text while the rules received the normalised text, so the models returned glued runs as entities | The models read `ocr_text.normalise` output; offsets are mapped back and every quote is re-read from the source. Entities containing an unsplittable 20-letter run are excluded and counted | `services/nlp_processor.py` (`statements_to_source`, `UNREADABLE_OCR_RUN`) |
| The synthesis counted secondary NLP readings of the same sentences as clinician-reported findings | Listed in `secondary_model_mentions`; never findings, never contradictions | `services/evidence_synthesis.py`, `EvidenceSynthesisPanel.tsx` |
| "Bony cranium is unremarkable. No fractures noted." splits into two sentences, so the fracture had no site | A finding with no site takes the single same-system site of the sentence just before it on the same line, marked for review; not across lines, systems or two candidate sites | `services/nlp_processor.py` (`_preceding_site`) |
| The applicability refusal gave a raw score (5.9e7) with no reason | Refusals state whether the input's colour/intensity statistics or the network's feature stages carry the distance; for a colour image, a greyscale copy is scored (never analysed) to separate "colour only" from "content differs too". Threshold unchanged | `services/model_inference.py` (`refusal_explanation`) |
| The overview read "0 of 28 activation-eligible" and "0 of 33 datasets eligible" as "nothing works" | Shown separately: runnable for research use 18 of 28 (16 trained and tested here, 2 third-party on their own routes), clinically activation-eligible 0 of 28, dataset tasks eligible for training 14 of 35 (task audit), and the 2026-10-23 discovery scan's folder flags (0 of 33; that scan lists folders and is not updated when a task is curated) | `pages/OverviewPage.tsx` |

## Why the score was 58.9 million (applicability audit)

The head-CT model (`brain_ct_rsna_ich_classifier`) was trained only on greyscale PNG slices replicated to three channels. The first stage of its applicability reference is the statistics of the model's input tensor (per-channel mean and spread, quantiles, channel differences). Across greyscale training images those statistics lie in a lower-dimensional subspace, so the fitted Gaussian has eigenvalues at the floor (1e-6 of the largest) along every colour direction. Any colour (a photograph's cast, coloured marks) lands about 10^7 times further away along those directions.

| Input, through the exact serving path | n | Refused | Score |
| --- | --- | --- | --- |
| RSNA held-out test PNGs | 200 | 0 | median 1.08, 95th percentile 1.79 |
| The same slices with a 3-8% warm colour cast | 50 | 50 | median 1.46e7 |
| CASE-D crop A as uploaded | 1 | 1 | 5.89e7 (stage 0: 5.3e8) |
| CASE-D crop A, greyscale copy | 1 | 1 | 8,568 (every network stage elevated) |
| CASE-D crop B as uploaded / greyscale copy | 1 | 1 | 2.51e7 / 39.6 |

There is no preprocessing defect: in-distribution slices pass, and the refusal is correct. The magnitude only reflects the degenerate colour directions. The film crops are also outside the training images once colour is removed (glare, grain, perspective, film borders, burnt-in annotations), so no preprocessing change would make them valid inputs. The threshold was not changed. `scripts/diagnose_brain_ct_applicability.py` (from the parallel pass) and `backend/tests/test_case_d_regressions.py` reproduce this.

## Input-type classification of the five source photographs

Classification only (no pixels reproduced): three are `FILM_MONTAGE_CANDIDATE`. They had 14, 15 and 2 detected panels, the last an under-detection; coloured source marks were flagged on two, with `is_ai_mask: false`. Two photographs had no detected skull panel (`AMBIGUOUS_RASTER`). The single-panel crop A is `AMBIGUOUS_RASTER` and is stopped by the applicability gate; crop B is `FILM_SLICE_CANDIDATE` and is stopped by the film gate. Panel detection is an unvalidated viewing heuristic that can miss panels.

## Status against the brief

| Area | Status | Boundary |
| --- | --- | --- |
| Input-type detection | Working, heuristic | Pixels cannot prove native origin; HU, spacing and patient coordinates are unrecoverable from film |
| Film / montage panels | Working (viewing) | Can miss panels; coloured marks are source annotations, not AI masks |
| Preprocessing / OOD audit | Done; refusals explained | No threshold change; gate has internal cross-domain tests only |
| Model inventory | 28 registered; 18 runnable for research; 0 clinically activated | Research use only |
| Document intelligence | Five required findings correct on CASE-D | Rules and OCR are not clinically validated; a misspelt second copy ("contuson") is not matched (the impression still is) |
| Multimodel inference | Separate runs per model | No validated cross-model probability combination |
| Missing-modality fusion | Rule-based evidence concordance: "Report findings retained; independent image confirmation is unavailable" | No learned fusion; no probability is produced |
| Anatomy L1 | "Reported anatomical association — not patient registered" | L2/L3 need a validated registration; none exists for film |
| Examination timeline | Report dates extracted with parse status (ambiguous day/month refused) | Linking is an explicit reviewer action; upload time is never a study date. CASE-D has no linked examination |
| Historical comparison | Needs two examinations and same-patient confirmation | CASE-D: insufficient evidence |
| Forecasting | 1 dated value: none; 2: observed difference only; 3 / 5 reviewed values: persistence / linear research baselines with backtests | Qualitative CT findings give no numeric trajectory |
| Registry | Counts separated (above) | Discovery-scan flags are stale by design |
| Data preservation | No record deleted; superseded analyses retained | QA database only for CASE-D |

## Open items and risks

- **Lost session for the case owner account.** The committed code (HEAD) signed tokens with a random per-process key, so every restart invalidated all sessions; an entry-page visitor account has no password, so its token was its only key. The case's visitor account cannot sign in again; the case was reached through the QA reviewer account in shared-workspace mode. The persisted development key (parallel pass, uncommitted) prevents this from now on; it does not restore earlier tokens. Any deployment that ran HEAD and restarted has visitor accounts in the same state.
- **Synced output folder.** The parallel pass saved screenshots, structured outputs and a redacted report derivative under `C:\Users\johnn\OneDrive\Pictures\MedTwin_Report_Test_2026-11-06`. OneDrive synchronises that folder to the cloud. Check that this is acceptable under the no-upload rule; nothing there was changed in this pass.
- **Concurrent agents.** Two agents edited the same repository on the same day. This pass edited only after the other's last write; the uncommitted tree now holds both sets of changes.
- Job messages stored before this pass keep their old wording.

## Verification

- `backend/tests/test_case_d_regressions.py`: 14 tests on synthetic text and images (required findings, site borrowing and its refusals, normalised NER with source quotes, garbled-entity exclusion, re-analysis supersession across statements/attributes/synthesis/workflow, secondary mentions, refusal explanations, and the real RSNA checkpoint on held-out slices when present).
- Live: CASE-D re-analysed on the QA stack; statements, synthesis, workflow and both film-crop refusals checked through the API.
- Glioma model (`brain_mri_glioma_segresnet`) published with its card, report, input envelope and serving-parity record (see the change log).
