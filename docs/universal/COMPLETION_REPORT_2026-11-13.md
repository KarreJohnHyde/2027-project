# MedTwin completion audit — 13 November 2026

The application now runs the expanded research workflows under the user's required **commercial-development** profile. Original weights, original model registry, existing data and prior evaluations are preserved. No model has been clinically activated. This is a measured implementation report, not a promise that every disease or every original model now produces accurate results.

The original assessment was 9 verified, 13 partial, 2 blocked. The reconciled 24-row matrix now has **15 verified engineering requirements,7 partial requirements and2 blocked scientific requirements**. “Verified” is limited to the contract and evidence stated in each row. The initial assessment is retained in `requirements-initial-2026-11-13.csv`; current paths and limitations are in `requirements.csv`.

## Implemented and measured

| Area | Working implementation | Evidence and limits |
| --- | --- | --- |
| Official reference | CDC/NCHS FY2027 ICD-10-CM local read-only index:98,403 classifications, including 74,879 valid codes and 23,524 headers; combined catalogue 103,252 entries across 25 context families | Exact publisher descriptions, source hashes, attribution and unavailable-index refusal. Broad family associations are not diagnoses or invented curated-condition crosswalks. `resources/official-terminology-verification.json` |
| Source review | Case-bound source graph, original raster with its exact saved finding overlay, source spans/pages, review/history/export and optional generic 3D context | Generic anatomy has an independent coordinate frame. It is never presented as registered patient anatomy. `browser/proof.json`; previous dated document/GI proofs remain valid within their original scope |
| Spatial preprocessing | Explicit 4D channel/time selection; three native planes; known-unit coded-affine RAS resampling; invertible view/native mappings; nearest-neighbour label sampling; native axial edit guards | Actual two-channel public ISLES source rendered in six native PNGs, plus anatomical planes and stored prediction mappings. Unknown-unit ACDC source retains its refusal/warning. `imaging/qa-proof.json`;15 browser checks |
| Registration | Bounded rigid SimpleITK candidates, same-subject/region attestations, source hashes and both transforms; landmark TRE | Three original synthetic controls have mean TRE about 0.0053/0.0070/0.0109mm. Live API phantom mean TRE 0.00667mm. These controlled phantoms do not validate clinical or atlas registration. `imaging/registration-benchmark-final.json` |
| Model Arena | Real saved-prediction ROC/PR, reliability bins, ECE/Brier, binary confusion and checkpoint/source identities; patient-cluster bootstrap | 2,163 records / 1,881 patients. Baseline-to-fusion AUROC delta 0.002237, 95% CI[-0.000405,0.004785]. Same-run ECG-only-to-fusion delta 0.001257, CI[-0.001173,0.003553]. Both show **no demonstrated difference**. `research/arena-measurements.json` |
| Paired sources/history | Examination-linked unique-source groups, explicit identity attestation, conflicts/missing modalities; read-only persistence versus linear chronological backtest | Eight fictional dated reports yield five matching historical targets. Backtest writes no forecast; missing images/signals never become a learned fusion prediction. `live/fictional-chronological-backtest.json` |
| Commercial development | Exact PTB-XL publisher license, architecture lineage, checkpoint hashes and dependency evidence in additive portable sidecars | Actual dataset/model gates pass for local development/evaluation, including a new real worker ECG run. Review is explicitly an automated operator source/artifact audit; it is not legal, redistribution, regulatory or clinical approval. Original registries are unchanged. `research/ptb-rights-gate.json`; `live/public-ecg-run.json` |
| Controlled experiment | PTB age/sex logistic experiment using 17,111 train and 2,156 validation records; no test-label parsing | Unweighted validation AUROC 0.692873, Brier 0.162497; balancing AUROC 0.692567, Brier 0.224930. **No improvement**, no promoted checkpoint. `research/development-experiment.json` |
| OCR evaluation | Permissively licensed primary resources measured rather than assumed accurate | 48 synthetic ClinOCR pages: CER 0.32462, WER 0.75257.1,115 real publisher-test word crops: CER 0.57993, WER 0.92320, 111 exact, 252 empty. Word-only data are not independent full-report clinical truth. `resources/clinocr-synthetic-ocr.json`; `resources/rxhandbd-real-word-ocr.json` |
| OCR improvement | Preregistered 128 development / 256 reserved publisher-training word crops; froze upright policy before reserved evaluation | Reserved CER 0.583612→0.565217; delta−0.018395,paired word-bootstrap 95% CI[-0.031042,-0.007671]. WER 0.893333→0.89; empty 63 unchanged. Narrow internal word-level improvement only; no independent patient/writer generalization established. `resources/ocr-word-experiment-v1/result.json` |
| OCR app integration | Opt-in single upright Latin-word crop, three attestations, exact canonical masked 110 DPI preview/source hash, bounded dimensions and unchanged original extraction | Pinned runtime/ONNX/base-parser hashes. Real fictional scanned PDF returns “Hemoglobin”; stale hash and missing attestation refuse. Text is a review-only proposal; it never silently changes a field. `word-review/proof.json`; `word-review/browser-proof.json` |
| Accessible interaction | Responsive layout, named controls, mobile sidebar inertness, skip link, roving keyboard tabs, expanded word-review form | Eight-page desktop/mobile axe audit has zero detected WCAG AA violations; this is automated scope, not complete manual certification. Expanded workflow proofs record additional controls. `accessibility/report.json` |
| Operations | Actual hardened localhost Linux backend/worker/frontend, SQLCipher DB and encrypted uploads; authenticated backup, independent restored backend and separate restored storage | Wrong-key and tampered backups refuse. No real patient DB or keys touched. This is same-host recovery, not an off-host disaster drill. `operations/proof.json` |
| Source packaging | Local history-free text-source snapshot, exact-line privacy scan and hash inventory | No Git metadata, weights, patient uploads or keys included. Original sensitive Git history is preserved and must not be published. `release/source-snapshot.json` |

Artifact paths in this table are relative to `artifacts/completion-2026-11-13/`. Full-source/file hashes and completed check summaries are in `run-manifest.json`; `package-verification.json` verifies that manifest against the current tree.

## Verification

- Full current backend suite: **1,072 passed, 5 skipped**, 10 warnings; collected 1,077 tests. Skips are retained, not counted as passes.
- Frontend TypeScript/lint/check build and production build passed. Tool warnings are retained in logs.
- Live integration9/9, spatial browser15/15, focused workflow browser6/6 and expanded word-review browser36/36 controls passed. The stored GI overlay matched the independently decoded source mask with zero differing source pixels. Desktop/mobile expanded OCR forms also had zero detected axe violations. Test subsets reported by agents are included in the full suite where applicable and are not added a second time.
- Container recovery and history-free source packaging have separate operational scope; passing functional tests does not clear historical image-security or clinical-release findings.

## What still needs evidence

1. **Independent full real-report references:** zero independently human-reviewed permissible complete real report pages. Publisher word crops and synthetic reports cannot fill this requirement. Obtain representative de-identified reports with documented commercial permission, have independent reviewers annotate fields/units/specimens/methods/page spans, freeze held-out pages, then run existing evaluators.
2. **Six original weak-model families:** commercial-development rights/review prerequisites remain incomplete. Downloading another free resource does not establish compatible labels, patient separation or commercial model rights. Keep kidney-tumour Dice 0 and historical fracture recall 0.222 / AP50 0.155 visible. Do not promote a replacement without controlled evaluation.
3. **Data and parity:** resolve known ARCADE cross-split duplicate groups and unknown identities before new performance claims. Preserve the historical one-pixel Kvasir mismatch; exact historical source/environment is unavailable and noncommercial reruns remain blocked.
4. **Clinical spatial/fusion/forecast validation:** expert held-out landmarks, patient-to-atlas reference transforms, genuinely paired multimodal outcomes and chronological clinical outcome cohorts are missing. The new tools make those experiments executable when suitable data exist.
5. **Release:** original Git history remains a privacy publication blocker; no off-host recovery exercise or clinical/regulatory clearance has been completed. The clean local source snapshot is preparation, not publication authorization.

## Review preparation for 18 November

| Date | Work to perform | Acceptance evidence |
| --- | --- | --- |
| 13 Nov | Freeze this source/evidence package; retain original and new statuses separately | Manifest verification, original registry hash, current test logs |
| 14 Nov | Obtain commercially permitted real reports and independent annotation; reconcile patient-level duplicates in development datasets | Signed/source-bound permissions, reviewed annotation file, leakage-free manifest |
| 15 Nov | Evaluate full-page OCR/field extraction; run only rights-cleared targeted development experiments | Frozen policy, train/validation records, independent reference metrics with errors and abstentions |
| 16 Nov | Assess external image landmarks and paired/time-split cohorts where available; preserve explicit refusal where unavailable | Held-out TRE, cohort overlap checks, baseline comparisons and uncertainty |
| 17 Nov | Rehearse document source-review, spatial MRI, commercial ECG, terminology, abstention and recovery demonstrations | Reproducible scenario outputs, screenshots, concise limitations slide |
| 18 Nov | Present measured engineering outcomes and narrow experimental results | Do not describe synthetic/word-crop controls as clinical accuracy or all-disease diagnosis |

Local QA runs at 8018/8458; the isolated hardened container demonstration runs at 8028/8468. Both use separate generated credentials kept in ignored local state. Reproduction commands are in `COMPLETION_REPRODUCTION.md`.
