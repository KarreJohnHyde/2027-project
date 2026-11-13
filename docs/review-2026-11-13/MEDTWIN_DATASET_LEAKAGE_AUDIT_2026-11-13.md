# MedTwin dataset integrity, leakage and controlled-development evidence

Assessment date: 13 November 2026. Scope: read-only manifest/registry inspection, bounded new input-byte verification and safe model-development tooling. This report does not certify all medical data on the workstation or establish clinical model performance.

## New measurements

The current registry contains 67 dataset entries. A fresh audit inspected **21 manifests/metadata files and 866,701 rows**, with no row-limit truncation. These include the full PTB-XL metadata (21,837 records), RSNA slice manifest (753,015 rows), 7 volume manifests, and prepared image/video indexes.

The audit newly SHA-256-hashed **127 input files / 536,734,461 bytes**, within a global 512 MiB budget. **Zero mismatches** were found where a recorded SHA-256 was available. A newly calculated hash without an earlier expected hash is a reproducibility fingerprint, not proof of publisher authenticity. All selected loose files resolved; 53 input checks were deferred by byte/file-size budgets. Nine RSNA archive-member checks were explicitly deferred: those members are stored inside `RSNA_PNG/rsna-ich-png.zip`, not missing loose files. The archive was not unpacked or its member payloads rehashed in this pass.

Evidence: [data-audit.json](../../artifacts/review-2026-11-13/data-audit.json). Its per-manifest records include split counts, grouping fields, recorded volume-shape counts, manifest hashes, source scope and newly checked input hashes. Registry license/label/preparation records are copied as **historical records**, not new permissions or readiness approvals.

## Leakage findings

| Manifest | Fresh row/group check | Interpretation |
| --- | --- | --- |
| PTB-XL full metadata | 21,837 rows; no patient key crosses train/validation/test | Official folds 1–8/9/10 preserved. This is the full metadata, not just the previously evaluated 21,430-record diagnostic-superclass subset. Nine low-rate waveform files were newly hashed against publisher checksum entries. |
| ARCADE stenosis | 1,500 rows; **11 groups cross splits** | Existing publisher split contains cross-split content groups. A future independent selection/evaluation must account for them. Do not silently relabel the existing test as untouched. |
| ARCADE SYNTAX | 1,500 rows; **2 groups cross splits** | Same restriction; the audit records overlap without moving original data. |
| Kvasir-SEG | 1,000 rows; no recorded group crosses splits | No source patient identity is available. This demonstrates separation of the recorded grouping keys, not independently verified patients. Nine images were newly hashed. |
| Kvasir v2 / GastroVision / fracture | 8,000 / 8,000 / 4,148 rows; no recorded group crosses splits | Patient independence remains unknown where the source has no patient identifiers. Near-duplicate grouping alone cannot establish it. |
| ACDC / ISLES / KiTS19 / LIDC / brain MSD / liver MSD / RCC-AID | 298 / 250 / 210 / 299 / 484 / 131 / 142 rows; no recorded patient key crosses splits | Manifest key separation was checked. Prior label/affine/voxel inspections are retained as earlier evidence; fresh byte checks were bounded and do not repeat every geometry/mask check. |
| RSNA | 753,015 rows; no patient key crosses splits | Metadata grouping inspected in full. Archive-member bytes were not reverified in this pass. |
| Other prepared image/video manifests | Grouping counts recorded in JSON | No new identity adjudication or observer-label review was performed. |

Fresh cross-split Hamming comparisons on up to 256 recorded dHashes per manifest produced **1,332 candidate pairs**. They are intentionally **not called confirmed near duplicates**: this bounded test did not independently compare the underlying image pixels. Existing pixel-confirmed overlap evidence remains separately recorded in the registry preparation metadata. There were no cross-manifest SHA-256 duplicates among the bounded newly hashed sample; that does not rule out overlap elsewhere or overlap with parent datasets.

The audit exit status means that the bounded audit ran without parse/hash errors. It does **not** mean the datasets are leakage-free: the two ARCADE overlap findings are retained explicitly.

## Implemented model-development changes

`ml_training/detect.py` and `ml_training/classify.py` now provide:

- `--development-only`, which removes test rows before image/annotation loading (and before classifier output classes are derived).
- `--max-train-samples` and `--max-val-samples`, deterministic caps available only in development mode, with a recorded seed.
- Refusal when selected development train/validation group keys overlap.
- Validation-only selection and a `development.json` artifact marked `DEVELOPMENT_COMPLETE_TEST_NOT_EVALUATED`.
- Experimental checkpoints in the new run directory, with no model-card or registry publication from development mode.
- The existing evidence-bound `enforce_training_license` gate **before manifest/sample/image loading**, for both development and standard training. This closes a legacy gap where these two trainers relied only on historical `training_eligible` flags.

The original failed renal-tumour checkpoint and all model registry entries were left unchanged. No experiment overwrote an existing model, no test-driven hyperparameter tuning occurred, and no clinical activation was granted.

## Controlled experiments prepared, not launched

Evidence: [data-experiments.json](../../artifacts/review-2026-11-13/data-experiments.json).

| Family | Prepared comparison | Current live execution gate |
| --- | --- | --- |
| Kidney tumour | Same 3 mm development baseline; separately compare weighted loss and higher foreground sampling | **BLOCKED:** recorded non-commercial data terms conflict with current commercial-development purpose. Exposed 32-patient test remains excluded from development. |
| Stroke | Same preprocessing/seed, baseline versus higher lesion foreground sampling | **BLOCKED:** evidence-bound commercial-development data review absent. |
| Fracture | Same seed/development subset, baseline versus larger input resolution; correct six fracture classes merged and non-fracture class excluded | **BLOCKED:** canonical registry has no explicit verified training authorization accepted by the live gate. |
| Stenosis | Same seed/development subset, baseline versus larger input resolution | **BLOCKED:** canonical explicit training authorization absent; development group-overlap curation may also be required. |
| GastroVision | Same architecture/seed/development subset, unweighted versus training-only inverse-frequency loss | **BLOCKED:** canonical explicit training authorization absent. Rare-class and class-absent subsets must still refuse. |
| Skin | Image-only and matched image/tabular baseline configuration with patient-aware evaluation requirements | **BLOCKED:** source not registered under the configured dataset identifier in the canonical training gate, and `skin_fusion.py` still lacks a safe development-only nonpublishing path. It was not executed. |

The preparation script actually called the existing live training-rights gate using `--verify-rights` and recorded its exact exceptions. **All six real-data training gates were blocked**. No purpose flag, license record or evidence review was changed to make them pass. Their command vectors are experimental preparation, not measured improvements. No training was launched and there are no new real-data model accuracy claims from this workstream.

## Verification

**11 tests passed**, exit code 0. [Test log](../../artifacts/review-2026-11-13/data-tests.log).

Coverage includes zero-valued grouping keys, distinct patient versus byte/path overlaps, changed/missing/deferred hashes, manifest truncation, dHash-candidate labeling, PTB-XL publisher-fold/checksum mapping, nonexecuting preparation, both new development trainer main paths, test-only class/image exclusion, no publication and permission refusal before data loading. The two trainer control-flow tests use explicitly synthetic fixtures and tiny/mocked CPU components; they are not real model performance measurements.

Python compilation passed for the audit script, experiment preparation and both modified trainers. `git diff --check` passed for the modified trainers. These checks do not substitute for full application integration or real checkpoint inference, which belongs to the main execution report.

## Reproduction

```powershell
.\.venv\Scripts\python.exe scripts\medtwin_dataset_audit.py --output artifacts/review-2026-11-13/data-audit.json --sample-per-split 3 --byte-budget-mib 512 --near-limit 256
.\.venv\Scripts\python.exe scripts\prepare_review_experiments.py --verify-rights
.\.venv\Scripts\python.exe scripts\tests\test_medtwin_dataset_audit.py -v
.\.venv\Scripts\python.exe -m py_compile scripts\medtwin_dataset_audit.py scripts\prepare_review_experiments.py ml_training\detect.py ml_training\classify.py
```

Before future real training, resolve the exact live rights gate, curate overlapping groups, keep original/checkpoint manifests immutable, choose development settings without looking at the exposed test, and reserve an independent final evaluation cohort. Increasing the audit byte budget can verify more existing input bytes but does not resolve permissions or identity uncertainty.

## Explicit scope limits

- No recursive workstation discovery, bulk download, data deletion, archive extraction or split mutation.
- MIT-BIH CSV presence is not a patient-grouped eligible waveform cohort; no such claim was made.
- Requested but unregistered datasets (including GRAZPEDWRI-DX and unidentified pneumonia/brain collections) were not inferred licensed, indexed or usable from names alone.
- No independent human annotations were created; document-reference tooling/evaluation is covered by the integration workstream.
- New byte sampling rehashed input files; full paired-mask, voxel and geometry verification remains the earlier manifest evidence rather than a repeated measurement.
- No GPU training, checkpoint replacement, model activation, repository publication or database operation was performed in this workstream.
