# Continued acceptance verification

Date: 2026-11-06. This follow-up preserves the existing application, original database and source files. No commit, push, deployment or clinical activation was performed.

## Repairs completed

- Historical comparison applies approved corrections to derived views, retains original values and correction provenance, and excludes withdrawn, superseded, unassociated and rejected evidence. Missing or excluded evidence cannot imply a finding resolved. Canonical anatomical spelling/case does not create a false change.
- Research baselines inspect measurement context before duplicate-date reduction. Incompatible contexts, undocumented laboratory methods/specimens and unverified lesion identity block unsupported estimates. Overflow and non-finite calculations return an explicit unavailable state instead of invalid JSON or invented values.
- Report-to-anatomy navigation selects the existing labelled parietal-lobe model when the requested atlas entry is a virtual group without its own mesh. The display remains a generic reference with explicit source and review status, not a patient registration or lesion localization.
- Detected films retain their panel previews and report synthesis. Incompatible native-image and chest-radiograph actions are hidden; historical native overlays are cleared on film inputs. A panel crop does not bypass the input applicability gate.
- The isolated browser preview serves existing public anatomy assets in check mode without duplicating the large asset collection. Normal production/development behavior is unchanged.

## Executed verification

| Check | Result |
| --- | --- |
| Full backend suite | 613 passed, 4 skipped; 10 existing dependency warnings |
| New longitudinal evidence boundary tests | All 9 passed, included in the full suite |
| Frontend `npm run check` | Type checking, lint and build passed; existing lint and large-chunk warnings remain |
| Browser acceptance | 4 passed: authenticated page smoke test, report/film workflow, synthetic chronological history, actual public-dataset CT checkpoint output |
| Screenshots | 17 real application PNG screenshots, plus 4 structured JSON exports |
| Visual inspection | Saved film gate and selected parietal-lobe views inspected; browser assertions also check rendered results and export contents |

Browser tests use the existing Playwright harness, installed Edge, an isolated temporary encrypted database and normal API-issued test authentication. They do not reuse the user's Chrome session or modify the original database. The separate persistent report-test API uses its existing dedicated database and retained signing key.

## Evidence scope and limits

The report workflow uses an identity-redacted, flattened derivative of the supplied five-page PDF and a derived film raster. It is not a byte-for-byte test of the original document or the separate ten-panel image pasted into chat. Report extraction preserves 18 statements in eight synthesis groups; repeat OCR mentions and repeat model attempts are not independent corroboration.

The film's native-image abstention remains appropriate. Source panel rectangles are uncalibrated pixels. No patient-space mask, independently confirmed hemorrhage, new examination date or clinical review was fabricated. A source-to-examination link and reviewer approval remain explicit actions.

The public digital CT control is separate from this report case. A real RSNA checkpoint completed multilabel inference on a public image from its own held-out distribution. This is a functional inference check, not an independent accuracy study, native DICOM geometry test or confirmation of the supplied patient's findings.

The three-date heart-rate case is synthetic software-test evidence. Its persistence estimate of 76 bpm and chronological backtest demonstrate the research pipeline and saved report history; they are not a patient prognosis. The supplied sparse qualitative CT report does not support a numerical disease trajectory, calibrated recovery probability, learned case-level fusion or patient-to-atlas registration. Those capabilities remain gated by real data, compatible models and validation.

## Saved outputs

`C:\Users\johnn\OneDrive\Pictures\MedTwin_Report_Test_2026-11-06\Continued_Verification`

The folder contains a screenshot index, three scenario folders, structured outputs, verification logs and a SHA-256 manifest. No test bearer token, password, signing key or browser trace is included. Earlier artifact folders remain historical and were not relabelled as newly captured screenshots.

## Reproduction

Run `npm run check` and `.venv\Scripts\python.exe -m pytest backend/tests -q --tb=short` from the project root. Run the existing browser harness in `tools/browser-qa` with `MEDTWIN_E2E_PYTHON`, `MEDTWIN_E2E_CHANNEL=msedge`, the explicitly selected redacted report/film/public CT input paths, and `MEDTWIN_E2E_SCREENSHOT_DIR`. The acceptance spec is `e2e/workflow.spec.mjs`; the page smoke test is in `e2e/regression.spec.mjs`. Do not substitute identifiable documents for the redacted test inputs.
