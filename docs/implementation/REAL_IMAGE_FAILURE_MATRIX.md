# Real image failure matrix (2026-10-30)

End to end for 2-D research inference: upload → route → model eligibility → weights → quality gates →
worker job → output → stored provenance → viewer overlay → anatomy association. Every row was executed
on 2026-10-30 against the isolated QA stack (`scripts/dev.ps1 -Mode qa`, worker job execution) or the
backend test suite. Inputs are **public de-identified research images only** (Kvasir-SEG, Kvasir v2,
C-NMC); no patient upload appears here. Browser checks: Microsoft Edge (headless) via Playwright.

## Summary

| # | Input | Expected | Observed before | Root cause | Fix / status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Kvasir-SEG held-out polyp frame (JPEG 560×529) | Mask in source pixels, aligned overlay, stored pending review | Works: worker job succeeded, mask stored, overlay drawn | — | DONE | Run Dice vs publisher mask 0.868; overlay edges coincide (0 px) at fit and at 197 % zoom with pan; server `image_size` = displayed natural size |
| 2 | Same upload after a browser reload | Stored run and overlay come back | Overlay gone; the run existed only in component state | No endpoint listed an upload's runs; the panel never reloaded them | DONE: `GET /uploads/{id}/research-inference` (runs + latest review); panel restores the newest stored run and offers every stored run | `test_runs_are_listed_per_upload_with_their_latest_review`; browser: overlay present after reload |
| 3 | Phone JPEG whose EXIF orientation tag is 5–8 | Overlay on the image as displayed | Browser shows the photo upright (EXIF applied) while metadata, models and gates used the raw sideways grid: overlay rotated and stretched | Server raster reads ignored the orientation tag | DONE: `imaging_readers.open_raster` applies the tag for metadata, all 2-D models, the printed-document and applicability gates and the chest-radiograph path; outputs record `exif_orientation_applied` | `test_exif_orientation_is_applied_before_inference_so_overlays_match_the_displayed_image` (synthetic phantom, mask IoU > 0.7 with the displayed block) |
| 4 | Viewer "Reset zoom" after zoom/pan | View resets | Button did nothing | Pointer capture for dragging retargeted the click to the viewer | DONE: drags do not start on the viewer's own buttons | Browser recheck: 197 % → 100 % |
| 5 | Kvasir-SEG held-out frames refused by the applicability gate | Typed refusal, no output | 14 of 120 test images refused (11.7 %); one example scored 4.12 against a 4.06 limit | Gate calibrated at the 0.99 quantile of 132 validation images; the publisher's test split is partly unlike validation | NOT CHANGED (coverage limit). Widening the limit was measured to admit CT and angiography (`docs/validation/IMAGE_APPLICABILITY_GATE.md`) | Parity run: 106/120 accepted; browser shows `MODEL_INPUT_OUT_OF_DISTRIBUTION` |
| 6 | Polyp-free GI frames (Kvasir v2 test) to the polyp segmenter | Either an empty mask or a refusal | Normal cecum refused 40/40; Kvasir v2 "polyps" accepted 22/40; esophagitis 33/40, pylorus 32/40, z-line 30/40 accepted | The gate measures appearance similarity to Kvasir-SEG, not polyp presence | OPEN limitation: a polyp-free colon frame gets a refusal, not a negative result | Script output recorded in this file |
| 7 | Blood-cell microscopy image declared as endoscopy | Refused before the model runs | Refused (applicability score 110 vs limit 4.06) | — | DONE | Browser run m1 (API) |
| 8 | Panel text about out-of-distribution input | Accurate | Said "MedTwin does not detect out-of-distribution inputs" although a gate exists | Text predated the gate | DONE: describes both gates and that genuine images can be refused | UI |
| 9 | Organ association of a confirmed mask | Schematic, organ-level, no location | Listed as "Schematic organ only", but the organ was not visibly marked in the single-organ view | `organ_schematic` was only drawn in the full-body view | DONE: the whole organ is blended toward the schematic colour; nothing is singled out; banner stays "L1 generic reference anatomy · not patient registered" | API: `SCHEMATIC_ORGAN_ONLY`, `atlas_structure_id` null, registration `REGISTRATION_UNAVAILABLE` |
| 10 | Reference (ground-truth) mask for comparison | Kept apart from model output; per-image agreement only | No way to attach one | Not implemented | DONE: `ReferenceAnnotation` table, `POST/GET /uploads/{id}/reference-annotations` (clinician/researcher, declared source, size must equal the upright image), `GET /research-inference/{run}/reference-comparison/{annotation}` (Dice, IoU, pixel precision/recall, HD95/ASSD in px, disagreement regions); viewer shows Input · Reference (GROUND_TRUTH) · Model (MODEL_PREDICTION) and an agreement overlay | `test_reference_mask_is_compared_per_image_without_touching_the_run`, `test_reference_masks_need_a_professional_role`; browser triptych |
| 11 | Clinician review from the imaging panel | Confirm/reject without changing the output | Only a static "pending" badge | No review controls in the panel | DONE: Confirm/Reject with comment (clinician/admin), latest review shown with the run | Browser: CONFIRMED, stored output byte-identical |
| 12 | Detection boxes (kidney stone, coronary stenosis), held-out test splits | Served boxes equal training-time boxes in source pixels | Served operating points reproduce the reports (kidney stone exactly; stenosis 537 vs 536 false positives, one image with a different box count under bfloat16) | — | DONE; drawn with the same source-pixel SVG viewBox as masks | `docs/validation/UPLOAD_INFERENCE_PARITY.json` → `images`; browser on one held-out kidney-stone slice (391×320): 4 boxes at or above 0.85 of 29 proposals, all 3 publisher boxes matched at IoU ≥ 0.5, 1 false positive, overlay edges coincide (0 px) |
| 13 | Masks of both 2-D segmenters, every test image | RLE decodes to the model grid mapped back to source pixels | 120/120 and 300/300 exact; source-pixel Dice 0.7677 vs 0.7679 at the model grid (Kvasir-SEG) | — | DONE | Same file |
| 14 | Missing or tampered weights, unverified licence, missing applicability reference | Model not runnable, typed blocker | Refused | — | DONE (existing gate) | `test_gate_refuses_models_without_a_verified_bundle` (7 cases) |
| 15 | Another clinician's case | 403 | 403 for runs, references and comparisons | — | DONE | New tests above |
| 16 | Demonstration images supplied as visual targets (a vendor CXR with drawn boxes, illustrative brain and polyp figures) | Not processed as patient evidence | Not uploaded | — | Treated as UI targets only; their boxes and colours were not transferred to any image | — |

## Coverage that remains blocked

- Polyp segmentation coverage is limited by the applicability gate (rows 5–6).
- No lesion detector exists for chest radiographs; the third-party chest model gives image-level scores
  and attention maps only.
- Reviewer mask editing (brush/eraser/polygon) is not implemented; a reviewer can confirm or reject, and
  a reference mask can be attached as a separate GROUND_TRUTH layer.

Reproduce: `.venv\Scripts\python.exe scripts\verify_upload_inference_parity.py --only images`;
backend `pytest tests/test_research_inference.py`.
