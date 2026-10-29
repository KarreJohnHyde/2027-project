# MedTwin working-app demonstration

Prepared 2026-10-29. Demonstrate the implemented research software, including honest unavailable states. **Do not present this as a clinically validated product or as completion of every master directive.** Use synthetic data only; never display the owner's photographed reports or identifiers to an audience.

## Start and sign in

The isolated QA stack used for this audit is at **http://127.0.0.1:8453**, with API port **8010**. The older 8443 address was not serving when checked. The QA database, upload store, logs and generated credentials are outside the repository at:

`$env:LOCALAPPDATA\Temp\medtwin-audit-20261029`

The owner signs in manually using `qa-credentials.json` in that directory. Do not copy this file into slides, chat, source control or deployment settings. The public/unverified account shows the personal portal, not professional workflows. Do not elevate a public account solely for the demonstration.

To start the isolated stack if it is stopped, run from `D:\project`:

```powershell
./scripts/dev.ps1 -Mode qa -StateDir "$env:LOCALAPPDATA\Temp\medtwin-audit-20261029" -BackendPort 8010 -WebPort 8453
```

The helper refuses occupied ports. Do not use `-Fresh`, delete its database, start a second stack over an existing port, or stop unrelated processes. Source changes need a QA rebuild/restart because this stack serves a production preview, not Vite hot reload.

## Demonstration sequence (about 12 minutes)

| Step | What to show | What it demonstrates / does not prove |
| --- | --- | --- |
| 1. Access and health | Show the research notice, signed-in role, selected case and API indicator. | API/database reachability is distinct from model validity. Public accounts do not gain professional-review privileges. |
| 2. Evidence intake | Create an empty case with a clearly synthetic identifier such as `DEMO-SYNTHETIC-001`. | Do not upload fabricated reports or real patient records in a public demo. |
| 3. Source-linked extraction | Open Document Intelligence and show its empty state. | To demonstrate extraction, use only a separately authorised, de-identified source that is not included in this repository; do not claim accuracy from a walkthrough. |
| 4. Reviewed demographics | Open Case Workspace → Reviewed demographic context. Explain the blank/unknown state; optionally enter synthetic context with a verification basis. | Revisions and audit provenance are separate from OCR. This does not automatically select ranges, recalculate eGFR or infer risk. Never enter real demographic data for a public demonstration. |
| 5. Corrections and reports | Propose a correction to a synthetic extracted value. A separate authorised verified reviewer must approve it. Open Reports → Refresh report, compare original/effective evidence and inspect the version-3 JSON export (`original_extraction` / `correction_review`). | Pending corrections are not applied. Original extraction and decision IDs remain available. eGFR/anatomy summaries may be withheld if their inputs would be stale. Do not self-approve or disable independent review to make the demo pass. |
| 6. Model evidence | Open Model Registry and Dataset Registry. Inspect artifact hashes, internal evidence and missing resources. | 21 entries include frameworks/processors, not 21 clinically validated models. Nine trained research models accept supported uploads; zero external/clinical validations are recorded. |
| 7. Modality support | Open Medical Imaging. Show DICOM-series, NIfTI, WFDB and EDF/BDF support descriptions. | Readers, research inference, held-out parity and clinical validation are different capabilities. A photographed film or waveform printout is not equivalent to native data. |
| 8. Anatomy and registration | Open Anatomy Studio → Case landmark manifests. Inspect the empty proposal and review controls; use only actual measured correspondences from an approved study for a substantive run. | L1 generic atlas is not the patient's anatomy. L2 needs independently reviewed coordinates plus a passing held-out TRE gate; L3 reconstruction is still unavailable. No default patient geometry is fabricated. |
| 9. Unsupported outputs | Open Prognosis Studio, Risk and Multimodal. | Explain why a missing validated endpoint/cohort produces unavailable/abstention, not a softmax-derived risk percentage, treatment effect or synthetic future scan. |
| 10. Handoff | Show this guide and the completeness audit; present the remaining engineering and validation backlog. | A working prototype and passing tests are not regulatory or clinical approval. |

For independent correction/landmark review, the second reviewer needs verified professional credentials and explicit case edit access. Provisioning and real professional verification are separate administrative processes; the demo must not fabricate either.

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
