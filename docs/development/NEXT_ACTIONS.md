# Next actions (resume list)

> Historical backlog. OCR row geometry/rotation, DICOM-series handling, corrected evidence views, reviewer demographic context and landmark review have since progressed. Use the [2026-10-29 remaining-work matrix](../verification/COMPLETENESS_AUDIT_2026-10-29.md) before repeating this work.

Only unfinished work after the 2026-10-25 verification run is listed here. Preserve the
verified work table at the end and do not reopen scientific claims without new evidence.

## Decisions and external inputs required

1. **Authorize or decline Git-history remediation** (`BLOCKED`, release blocker).
   Decide whether an encrypted, access-controlled incident-evidence copy must be
   retained. A new sanitized canonical repository is preferred. The controlled rewrite
   alternative remains:
   `scripts/purge_phi_history.ps1 -Authorization "I AUTHORIZE REWRITING MEDTWIN GIT HISTORY" -BackupDir "X:\approved-encrypted-evidence" -SecureBackupApproved`.
   Do not push, publish, attach, bundle, clone for transfer, or otherwise share this
   repository or its Git metadata until remediation and a clean history scan complete.
   The public code is a separate history-free snapshot (`45c25ce`,
   `https://github.com/KarreJohnHyde/2027-project`, working copy `D:\mtwin-publish`); to
   publish later changes, repeat the copy/verify/scan/push procedure in
   `docs/security/PHI_RELEASE_BLOCKER.md`, never a push from this repository.
2. **Choose the disposition of the local development transcript containing report text**
   (`BLOCKED`). Its scope is recorded only in `docs/security/PHI_RELEASE_BLOCKER.md`.
3. **Complete privacy review of `archive (5).zip`** (`BLOCKED`). Its real-looking DICOM
   demographics keep it excluded from experiments.
4. **Provide authoritative provenance and permissible-use terms for blocked datasets**
   (`BLOCKED`), including brain, pulmonary, ultrasound, musculoskeletal, pancreas,
   liver, and additional kidney tasks. The musculoskeletal-radiograph and
   echocardiography sets need your own research use agreement with their publisher.
   (Cardiac cine-MRI: training authorized by the repository owner on 2026-10-25 and
   recorded in the dataset registry.)
5. **Provide a lawfully usable, independently annotated clinical NLP/OCR corpus**
   (`BLOCKED`). The strict span/context/numeric and CER/WER evaluators already exist;
   define adjudication and acceptance criteria, then execute them on the registered
   bytes. Synthetic software-contract fixtures are not scientific accuracy evidence.
6. **Provide reviewed patient-registration evidence** (`BLOCKED`) if precise 2-D-to-3-D
   mapping is required: source/target landmarks, coordinate frames, fitting and held-out
   points, a predeclared TRE threshold, and observer review. Until then mappings remain
   source-linked or clinician-confirmed schematic organ associations.
7. **Provide lawful repeated longitudinal outcomes and define each forecasting target**
   (`BLOCKED`): population, time zero, endpoint, unit, horizon, chronological split,
   acceptance criteria, and missingness/censoring policy. PBC and heart-failure Cox
   baselines are evaluation-only and do not clear this gate. Treatment comparisons also
   require a target-trial estimand and defensible causal assumptions.
8. **Run the full Compose stack** (`DONE`, 2026-10-28). With the worker profile on a
   throwaway project: health and readiness, migrations (worker log), an analysis job run by
   the worker container, AES-GCM uploads and a SQLCipher database on the volume, non-root
   backend/worker (uid 100) and frontend (uid 101), frontend security headers, restart
   persistence and clean shutdown (the worker previously ignored SIGTERM during start-up;
   it now installs its handler first and Compose runs an init process).

## Engineering work still open

1. **Encrypt the application database and backup path** (`PARTIAL`). SQLCipher encryption of
   the whole SQLite file and WAL is implemented (`MEDTWIN_DB_ENCRYPTION=sqlcipher`, the Compose
   default) with a verified plaintext-to-encrypted copy (`scripts/encrypt_database.py`).
   Still open: key rotation (`PRAGMA rekey` procedure), backup/restore drills and operational
   key custody; PostgreSQL deployments rely on encrypted storage.
2. **Applicability gates for the seven 2-D upload models** (`DONE` for applicability; image
   quality `NOT_STARTED`). Each model refuses images unlike its training images (multi-stage
   feature Mahalanobis, limit from its validation split; `docs/validation/IMAGE_APPLICABILITY_GATE.md`).
   Open: GastroVision accepts most angiograms, the SYNTAX segmenter a third of endoscopy
   frames, and false refusals reach 9-12% where a test split is shifted.
3. **Run the existing OCR and Clinical NLP evaluators on lawful independent gold data**
   (`BLOCKED` on input). Preserve immutable byte digests, independent-gold and
   de-identification attestations, adjudication records, and error categories.
4. **Replace per-report WSL scispaCy cold startup with a persistent isolated worker**
   (`NOT_STARTED`). The adapter executes, but cold model startup is slow.
5. **Render and route assembled DICOM series** (`DONE`, research). Assembled series render
   plane by plane and run through the cardiac MRI segmenter with the same input checks as a
   NIfTI frame (98/98 identical masks on series written from the public test frames). The
   in-plane orientation convention of scanner series is assumed, not verified.
6. **ECG upload inference** (`DONE`, research-only). Digital WFDB format-16 pairs and CSV
   records at 100 Hz, 10 s, 12 leads run from Multimodal; parity with the held-out
   predictions is in `docs/validation/UPLOAD_INFERENCE_PARITY.md`. Other sampling rates, formats and photographed
   ECGs are refused. EDF/BDF recordings (EEG and other signals) are read and displayed; no
   EEG model exists pending data, labels, weights and validation.
7. **Add golden-image and broader accessibility regression** (`PARTIAL`). A Playwright
   regression suite runs in CI against a throwaway stack (sign-in, every page, report, HL7
   and EDF uploads, the patient portal). There is still no approved pixel baseline or
   automated accessibility audit.
8. **Reduce the large Anatomy bundle and resolve recorded React lint warnings**
   (`NOT_STARTED`, non-blocking). Preserve current behavior and repeat the full 43/43 run.
9. **Production hardening** (`NOT_STARTED`): malware scanning, object storage,
   organization retention/deletion policy, backup recovery, tamper-evident audit
   retention, tenant/identity threat modeling, penetration testing, and human-factors
   work.
10. **Volume upload inference for the cardiac segmenter** (`DONE`, research-only). Single
    NIfTI frames inside the development spacing envelope run from Medical Imaging, with
    per-slice overlays and structure volumes; 98/98 held-out masks are reproduced. The
    cardiac phase and sequence are declared by the user, not detected, so ejection fraction
    is not computed from uploads.
11. **Record header pixdim in volumetric manifests** (`NOT_STARTED`). The manifest derives
    spacing from the affine, which is unit-scaled in the cardiac files; cardiac indices
    therefore read pixdim directly (`ml_training/volumetric_report.py`).
12. **Decide what, if anything, the configured Supabase project may store** (`NOT_STARTED`).
    Only the browser client is configured; no data is sent. Any use needs a
    data-protection assessment, row-level security policies and a de-identification rule;
    patient evidence must not leave the deployment by default.
13. **Install medspaCy in its own WSL environment** (`BLOCKED` in the shared one: 1.3.1 upgrades
    spaCy to 3.8 and would break scispaCy 0.5.5). Commands are in
    `docs/verification/REPOSITORY_INVENTORY.md`; then add a fail-closed second-opinion
    assertion adapter that reports disagreements with the rule engine for review.
14. **Use OCR layout geometry for table rows** (`NOT_STARTED`). Text-order parsing cannot
    recover a result row whose label OCR missed, or a scrambled reading order; line boxes
    are already stored per page.
15. **Separate printed demographics from report text** (`NOT_STARTED`). When OCR misses a
    page's sex/age header, stratified intervals stay indeterminate. A reviewer-entered case
    sex and date of birth, audited and never inferred, would let strata resolve.
16. **Rerun the relevant gate after any prerequisite or bundle changes**: dataset audit
    before training; internal plus external evaluation before activation; all seven
    image workflows after model changes; 43/43 anatomy after viewer/assets; and full
    build/start/health/worker checks when Docker becomes available.

## Verified work that must not be re-queued

| Area | Status | Evidence |
| --- | --- | --- |
| Twenty-four named archives | `IMPLEMENTED_TESTED` | 23 canonical matches plus one 6,795/6,795 safe extraction; 91 extras audited, 2 unsafe and refused. |
| Dataset/task audit | `IMPLEMENTED_TESTED` | 61 units / 32 tasks: 10 ready, 1 exploratory, 21 blocked; `dataset_registry/tasks.json`. |
| Model/evaluation bundles | `IMPLEMENTED_UNVALIDATED` | 21 entries / 11 research-runnable / 0 clinically activatable; nine upload models (seven 2-D, ECG, cardiac MRI) plus two evaluation-only survival bundles. |
| Browser acceptance | `IMPLEMENTED_TESTED` | `artifacts/verify/20261025T140444Z.json`: 17/17 desktop, 17/17 responsive, 43/43 anatomy, 7/7 image workflows, 11/11 reports, lifecycle/lab/evidence/correction/queue/evaluator/prognosis assertions, zero console, page or request errors. |
| Evaluated-precision inference | `IMPLEMENTED_TESTED` | Classifiers and segmenters run under their evaluated bfloat16 autocast on CUDA; parity 21/21 (max probability difference 0.0008); outputs state precision. |
| Medical naming and attribution | `IMPLEMENTED_TESTED` | Medical display names across the application; source names, creators, licences and citations only on `/attribution`. |
| Native BMP microscopy | `IMPLEMENTED_TESTED` | Signature, upload, metadata, display, C-NMC applicability/inference, and malformed-file rejection are covered. |
| Volumetric pipeline and cardiac MRI | `IMPLEMENTED_UNVALIDATED` | Owner-authorized training on 298 retained cases; 50 frozen test patients: macro Dice 0.750, LV EF MAE 9.1 points vs reference masks; research-only single-frame NIfTI upload inference inside the development spacing envelope (`docs/validation/models/acdc_cardiac_mri_3d_unet.json`). |
| Durable job queue | `IMPLEMENTED_TESTED` | Lease/retry/cancel/idempotency/GPU quota, separate worker, reload persistence, and restart recovery. |
| OCR/NLP evaluator software | `IMPLEMENTED_UNVALIDATED` | Strict schemas, CER/WER and span/context metrics, byte binding, hash-only provenance, and raw-text exclusion pass; real accuracy awaits lawful gold data. |
| Structured longitudinal analytics | `IMPLEMENTED_TESTED` | Source-linked comparisons, unit compatibility, deduplication, censored-value exclusion, and abstention. |
| Proposed clinician corrections | `IMPLEMENTED_TESTED` | Typed proposals are append-only; original evidence is preserved and the proposal is not silently applied. |
| Anatomy engine | `IMPLEMENTED_TESTED` | 43/43 variants across 10/10 systems. |
| Prognosis safety behavior | `IMPLEMENTED_TESTED` | Separate route, reason-coded abstention, and zero unsupported numeric risk statements. |
