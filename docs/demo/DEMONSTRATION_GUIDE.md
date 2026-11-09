# MedTwin working-app demonstration

Prepared 2026-10-29. Demonstrate the implemented research software, including honest unavailable states. **Do not present this as a clinically validated product or as completion of every master directive.** Use synthetic data only; never display the owner's photographed reports or identifiers to an audience.

## Start and sign in

The isolated QA stack used for this audit is at **http://127.0.0.1:8453**, with API port **8010**. The older 8443 address was not serving when checked. The QA database, upload store, logs and generated credentials are outside the repository at:

`$env:LOCALAPPDATA\Temp\medtwin-audit-20261029`

The owner signs in manually using `qa-credentials.json` in that directory. Do not copy this file into slides, chat, source control or deployment settings. Since 2026-10-30 every signed-in account, including a self-registered public/unverified one, gets the whole workspace (dashboard, documents, imaging, uploads, studios, reports). Since 2026-11-05 there is one shared space: every account lists and works on every case (`MEDTWIN_SHARED_WORKSPACE=false` restores per-account privacy), so a demonstration must use synthetic or de-identified data only. There is no need to elevate an account for the demonstration.

To start the isolated stack if it is stopped, run from `D:\project`:

```powershell
./scripts/dev.ps1 -Mode qa -StateDir "$env:LOCALAPPDATA\Temp\medtwin-audit-20261029" -BackendPort 8010 -WebPort 8453
```

The helper refuses occupied ports. Do not use `-Fresh`, delete its database, start a second stack over an existing port, or stop unrelated processes. Source changes need a QA rebuild/restart because this stack serves a production preview, not Vite hot reload.

## Demonstration sequence (about 12 minutes)

| Step | What to show | What it demonstrates / does not prove |
| --- | --- | --- |
| 1. Access and health | Show the research notice, signed-in role, selected case and API indicator. | API/database reachability is distinct from model validity. Any account can review, but every review states whether the reviewer was a verified clinician. |
| 2. Evidence intake | Create an empty case with a clearly synthetic identifier such as `DEMO-SYNTHETIC-001`. | Do not upload fabricated reports or real patient records in a public demo. |
| 3. Source-linked extraction | Open Document Intelligence and show its empty state. | To demonstrate extraction, use only a separately authorised, de-identified source that is not included in this repository; do not claim accuracy from a walkthrough. |
| 4. Reviewed demographics | Open Case Workspace → Reviewed demographic context. Explain the blank/unknown state; optionally enter synthetic context with a verification basis. | Revisions and audit provenance are separate from OCR. This does not automatically select ranges, recalculate eGFR or infer risk. Never enter real demographic data for a public demonstration. |
| 5. Corrections and reports | Propose a correction to a synthetic extracted value. A second account with edit access to the case must approve it. Open Reports → Refresh report, compare original/effective evidence and inspect the version-3 JSON export (`original_extraction` / `correction_review`). | Pending corrections are not applied. Original extraction and decision IDs remain available. eGFR/anatomy summaries may be withheld if their inputs would be stale. Do not self-approve or disable independent review to make the demo pass. |
| 6. Model evidence | Open Model Registry and Dataset Registry. Inspect artifact hashes, internal evidence and missing resources. | 21 entries include frameworks/processors, not 21 clinically validated models. Nine trained research models accept supported uploads; zero external/clinical validations are recorded. |
| 7. Modality support | Open Medical Imaging. Show DICOM-series, NIfTI, WFDB and EDF/BDF support descriptions. | Readers, research inference, held-out parity and clinical validation are different capabilities. A photographed film or waveform printout is not equivalent to native data. |
| 8. Anatomy and registration | Open Anatomy Studio → Case landmark manifests. Inspect the empty proposal and review controls; use only actual measured correspondences from an approved study for a substantive run. | L1 generic atlas is not the patient's anatomy. L2 needs independently reviewed coordinates plus a passing held-out TRE gate; L3 reconstruction is still unavailable. No default patient geometry is fabricated. |
| 9. Unsupported outputs | Open Prognosis Studio, Risk and Multimodal. | Explain why a missing validated endpoint/cohort produces unavailable/abstention, not a softmax-derived risk percentage, treatment effect or synthetic future scan. |
| 10. Handoff | Show this guide and the completeness audit; present the remaining engineering and validation backlog. | A working prototype and passing tests are not regulatory or clinical approval. |

Added on 2026-11-05 (show only with public held-out inputs, never with patient data):

- **Brain MRI lesions** (Medical Imaging, NIfTI): an ISLES 2022 test case (DWI + ADC stacked in one 4-D NIfTI) with the stroke-lesion model gives the lesion per slice, its volume and a patient-derived 3-D surface; after Confirm, the Anatomy Studio tints the brain at organ level only. The glioma model needs FLAIR, T1, T1c and T2 co-registered on a 1 mm grid.
- **Mask correction**: on a polyp segmentation run, "Correct the model's mask" opens a brush and eraser; the saved correction appears as a REVIEWER_CORRECTION layer with what was added and removed. It is not ground truth.
- **Chest-radiograph attention marks**: the cross and dashed region show where the score depends on, with that finding's measured hit rate on NIH radiologist boxes (it is not a detector).
- **ECG + age/sex fusion** (Multimodal): the panel states that fusion did not beat the ECG alone on the held-out test; say so when you show it.
- **Endoscopy video** (MP4/AVI): a timeline of per-frame results from a still-image model; nothing is tracked or validated on video.

For independent correction/landmark review, the second reviewer must be a different account with edit access to the case. Reviews, corrections and landmark manifests record whether each actor was a verified clinician; the demo must not present an unverified review as professional confirmation.

## Acceptance checklist

- Source values and approved effective values are distinguishable; withdrawn/removed evidence is not silently used.
- Case membership and professional verification are enforced by the API, not only hidden buttons.
- Missing labels, geometry, model artifacts and independent evaluation are visibly acknowledged.
- A failed landmark gate does not claim a registered patient mesh.
- No clinical risk percentage, treatment recommendation or external-validation claim is improvised.
- No actual report photograph, password, database URL or storage key is shown to the audience.

## Verification and deployment boundary

See [the current audit](../verification/COMPLETENESS_AUDIT_2026-10-29.md) for executed tests and browser coverage. New browser regression files are not proof of an executed browser pass. The professional browser walkthrough requires the owner to sign in; it must not be described as completed until observed.

The Vercel configuration is a **local, release-blocked draft**. Nothing was deployed, pushed or committed in this work. Its two proposed services, routes and no-binding topology still need owner confirmation. Durable cloud uploads/jobs, secrets and licensed anatomy-asset provisioning remain prerequisites; see [Vercel Services notes](../deployment/VERCEL_SERVICES.md).
