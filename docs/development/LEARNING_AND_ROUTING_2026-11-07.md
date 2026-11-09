# Verified resources, task routing and research learning

This implementation supports specific registered research tasks. It cannot identify every disease, choose treatments, infer ground-truth 3D anatomy from an arbitrary photograph, or establish a patient's future outcomes. No model currently passes clinical activation.

## Resource verification

`scripts/verify_project_readiness.py` reread every artifact in three pinned acquisition manifests and checked publisher hashes (SHA-256, MD5, Git blob hashes or CRC32C, as recorded in the manifest). All **1,669 artifacts / 33,374,576,084 bytes** passed: 217 public-acquisition artifacts, 328 multimodal artifacts, and 1,124 DeepFluoro artifacts. This is not a claim that every file on C: and D: or every available medical dataset was verified. Required publisher licences remain intact.

The installed environment contains 292 packages; `uv pip check --python .venv/Scripts/python.exe` passes. The optional multimodal stack's execution report is `artifacts/audits/multimodal-stack-2026-11-07.json`; it includes CUDA image/text encoding, volume/label resampling, DICOM geometry, lossless pixel codecs, mesh export and differentiable projection. Synthetic software checks establish execution, not clinical accuracy.

There are 28 registry entries. Sixteen pass the research artifact gate, including two survival baselines that have evaluation reports but no patient-upload serving adapter. Fourteen have registered upload adapters. The third-party chest-radiograph and CT-organ adapters retain their separate source attestations and endpoints. Gate success verifies registered artifacts, not correctness on every possible upload.

The older LIDC (selected 300-patient cohort), CQ500 and liver downloads are not certified complete. LIDC is making progress under the existing sequential worker; the audit preserves its last reported state without interpreting it as cohort completion. Its recent download log reports `xml=0`, so reader-annotation joins must also be verified before using it for supervised localization. CBIS-DDSM coordinate/ROI joins, DeepFluoro coordinate adaptation and the new fusion model training remain outstanding. Dataset presence does not activate a model.

## Automatic task selection

- `POST /api/v1/uploads/{id}/model-selection`: authenticated, read access to the upload's case; optional `declared_input_type`, `task`, exact `target` class, `anatomy`, and existing adapter options such as ECG units and DICOM frame index.
- `POST /api/v1/uploads/{id}/automatic-inference`: write access; recomputes selection and runs only a unique compatible model. Requires `attest_source_input: true` for model inference and reuses the original research inference function, content/OOD checks, durable queue, idempotency and provenance. A selection alone is not a successful applicability check.
- Report/CSV uploads route to source-linked extraction, not generic disease prediction. Digital ECG requires its existing signal/lead/unit contract. A generic CT metadata tag cannot establish kidney-stone anatomy. Filenames are never disease or modality evidence.
- Ambiguous models require more context or explicit manual selection. Metrics from different cohorts are not ranked as if they measure interchangeable tasks. Forecast requests abstain because no validated upload forecast model exists.

The imaging panel includes task matching and requires explicit selection when more than one manual model is compatible. A successful automatic match populates the existing model selector; source attestation and the Run action remain required.

## Implemented learning strategies

`ml_training/learning_strategies.py` operates on finite numeric feature matrices: numeric CSV features or frozen image/text/volume embeddings can be supplied by a research caller after verifying joins, excluding labels/identifiers from features, and separating subjects. `assert_disjoint_groups` rejects shared subjects across splits. The module implements:

1. Unsupervised training-only scaling/PCA and IsolationForest novelty. Scores describe distribution novelty; they are not disease probabilities.
2. Semi-supervised logistic self-training with seed labels, `-1` unlabeled rows and a fixed 0.9 confidence threshold. No hidden label is passed to the learner.
3. Offline masked tabular Q-learning. General logged transitions support discounting and next-action masks; unknown states, unobserved actions or nonpositive estimated utility defer. Actions represent research analysis workflows, never treatment or medication.

The actual experiment uses the verified local BloodMNIST28 benchmark:

```powershell
.venv\Scripts\python.exe scripts\benchmark_learning_strategies.py
```

Training preprocessing and novelty models use only training rows. Stratified 20% seed labels are visible; the rest are hidden. The official test split is preserved, removing 16 training duplicates and one validation duplicate by exact image content. Patient identifiers are unavailable, so patient-independent validation cannot be claimed. The workflow policy learns from public validation labels only. Its terminal one-step episodes are an offline contextual bandit, a restricted reinforcement-learning setting. Both experts' rewards are observable on this labeled benchmark; this is not off-policy evidence from patient care logs. Fixed utility is +1 correct, -1 incorrect, 0 deferred, with confidence eligibility at 0.7 and 30 seeded Q-learning passes. Test data is used only for frozen evaluation.

| Held-out test result (3,421 images) | Measured value |
| --- | --- |
| Seed-only classifier accuracy / macro F1 | 70.01% / 0.6744 |
| Self-training accuracy / macro F1 | 69.63% / 0.6695 |
| Pseudo-labeled training images | 4,282 of 9,555 unlabeled rows |
| Offline policy coverage / deferred | 60.77% / 1,342 |
| Offline policy accuracy on accepted images | 84.94% |

Self-training did not improve this experiment. Selective accuracy excludes deferred examples and is not comparable to full-coverage accuracy as an overall improvement. This is a small eight-category blood-cell benchmark, not a disease classifier for arbitrary microscopy.

Artifacts and their hashes are in `artifacts/research_learning/bloodmnist-v1/report.json`. Local serialized estimators are trusted research artifacts only; no endpoint unpickles uploads. `GET /api/v1/research-learning` exposes the public benchmark report, and the Model Registry page displays its measured results with activation disabled. Patient uploads never automatically retrain serving models.

Primary method documentation: [SelfTrainingClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.semi_supervised.SelfTrainingClassifier.html), [IsolationForest](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).

## Verification

120 distinct focused Python tests passed across upload routing, research inference, learning strategies, the model registry, longitudinal evidence/validation, DICOM series, scan contracts, volume surfaces, ECG fusion and acquisition safeguards. Two isolated Edge browser tests cover ambiguous selection, unique task matching, source attestation, unsupported forecasting, delayed-response protection and the displayed benchmark report. Frontend type checking, lint and the production check build pass; pre-existing lint warnings and the large-chunk build warning remain. The 292-package dependency consistency check also passes. These checks do not establish performance on every real patient upload.

## Remaining requirements

Each new disease/task needs suitable labels, source-specific input contracts, subject-separated training, external held-out evaluation, calibration, thresholds, applicability checks, model cards and an implemented serving adapter. Longitudinal forecasts additionally need a defined outcome/horizon, compatible dated observations and chronological validation. Treatment-effect or surgical recommendations require their own evidence and cannot be inferred from a generic forecast. The current system is an educational/research workspace with human review; installation and unit tests cannot establish clinical suitability.
