# MedTwin 2.0 implementation roadmap

## Delivery principle

Build one evidence-complete vertical slice at a time. A component moves from `CATALOGED` to `ACTIVATABLE` only through reproducible dependency, artifact, evaluation, calibration, safety, provenance, and UI gates. Keep optional adapters unavailable rather than filling missing output with demo data.

The target is one case workspace—not one process containing every repository:

```text
authorized upload
  -> immutable content hash and case/exam association
  -> modality-aware validation
  -> versioned optional adapter
  -> source-linked normalized evidence or explicit abstention
  -> persistent finding, provenance and review state
  -> longitudinal/display layer
  -> L1 reference anatomy association when justified
```

## Milestone 0 — Preserve and classify the workspace

Status: inventory delivered; repeat after material asset changes.

Outputs:

- `WORKSPACE_INVENTORY.md`
- `FILE_REGISTRY.json`
- `COMPONENT_REGISTRY.json`
- `DEPENDENCY_AUDIT.md`
- `INTEGRATION_MATRIX.md`
- this roadmap

Exit criteria:

- every root entry and ZIP is represented;
- every named repository has a strategy, license status, entry-point/dependency/test/weight evidence, and explicit non-operational status;
- no original archive, dataset, research document, or GLB is deleted or overwritten;
- potential duplicates are flagged, not removed.

## Milestone 1 — Close the canonical application gate

Priority: immediate.

Work:

1. Keep `backend/app/main.py` and the root React/Vite app as the only supported application entry points.
2. Finish authenticated browser verification of upload, SHA-256, job completion/failure, source-linked finding, audit history, reload persistence, and logout.
3. Exercise negative paths: unauthorized case, MIME/extension mismatch, oversized upload, unsafe filename, non-deidentified attestation, parser failure, unsupported modality, missing adapter, and abstention.
4. Make case/examination/upload/job/finding/provenance schemas authoritative and versioned.
5. Ensure the UI contains no synthetic confidence, “ready” model, model accuracy, or patient-specific anatomy state.
6. Verify Docker builds when a Docker engine is available and retain CI checks for frontend, backend, and containers.

Exit criteria:

- an automated browser test uploads a synthetic/de-identified fixture, records its exact SHA-256, processes it, reloads with a new client session, and observes identical evidence and audit IDs;
- successful and failure-path screenshots are produced from real application state;
- all startup commands and environment variables are documented;
- optional adapter outages cannot stop core case/document workflows.

## Milestone 2 — Enforce the artifact and capability registry

Priority: next; complete before training or exposing additional models.

Implement an immutable artifact bundle schema containing:

- artifact/model ID and semantic version;
- task and label definitions;
- dataset name/version/license and consent/de-identification status;
- patient/study-aware split manifest hash;
- preprocessing source/version/hash;
- checkpoint format and SHA-256;
- calibration method and parameters;
- decision thresholds and abstention policy;
- held-out per-example predictions;
- metrics with confidence intervals and subgroup/error analysis;
- hardware/software lock, model card, limitations and intended use; and
- reviewer approval plus activation/revocation history.

Add a capability endpoint and UI state machine with at least:

`UNAVAILABLE`, `DEPENDENCY_MISSING`, `WEIGHTS_MISSING`, `SMOKE_TESTED`, `EVALUATION_INCOMPLETE`, `EVALUATED`, `CALIBRATED`, `ACTIVATABLE`, and `REVOKED`.

Exit criteria:

- incomplete bundles fail schema validation;
- the UI cannot activate an incomplete/revoked bundle;
- every inference job stores the artifact bundle ID and checkpoint hash;
- artifact files are immutable and large binaries remain outside ordinary Git history or under a reviewed LFS/object-storage policy.

## Milestone 3 — Complete the reference-anatomy engine

Priority: can run in parallel with one evaluation pipeline because it has no clinical-model dependency.

Work:

1. Create a reviewed anatomy manifest instead of scanning arbitrary root GLBs at runtime.
2. Start with assets whose license and attribution are documented: the existing public reference model, then selected Human Atlas/BodyParts3D or Svitylo assets after review.
3. Record organ/system, node IDs, source URL, license, attribution, SHA-256, triangle/texture budget, coordinate system, compression extensions, and anatomy level.
4. Add one viewer with organ/system selection, lazy loading, cancel/retry, loading/error/empty states, keyboard controls, mobile fallbacks, and resource disposal.
5. Keep generic anatomy labeled “L1 reference anatomy.” Map evidence only through an explicit terminology-to-node crosswalk and show unsupported/laterality-ambiguous mappings as abstentions.

Exit criteria:

- at least three reviewed organs can be selected in the same viewer without loading all assets simultaneously;
- attribution is accessible in the UI and export;
- browser tests verify load success, invalid/missing GLB failure, selection, reload, and WebGL fallback;
- no visual state implies patient-specific geometry or lesion registration.

## Milestone 4 — Finish and evaluate document intelligence

Priority: first clinically relevant evaluation because an executable transparent baseline already exists.

Work:

1. Freeze the current rule processor as `clinical-rules-v1`; do not silently change its evaluation artifact.
2. Add deterministic numeric biomarker parsing with page/span coordinates, units, reference interval provenance, dates, negation/assertion/temporality, and ambiguity reasons.
3. Select a legally usable annotated report corpus. Keep entity, negation/assertion, temporality, and numeric extraction tasks separate.
4. Build isolated adapters for scispaCy, MedCAT v1 or CogStack MedCAT v2, and RadGraph only when their model artifacts exist.
5. Compare processors on the same frozen split; select per task rather than declaring one universal NLP engine.

Metrics:

- exact and overlap span precision/recall/F1;
- concept-linking accuracy where labels permit;
- assertion/negation and temporality precision/recall/F1;
- numeric value/unit/reference-range exact accuracy;
- document-level all-required-fields accuracy;
- failure, abstention, latency and memory rates.

Exit criteria:

- held-out predictions and confidence intervals are stored;
- every extracted item links to a page/span or explicitly lacks localization;
- calibrated confidence is shown only for a calibrated processor;
- the rule baseline remains selectable for comparison and audit.

## Milestone 5 — Reproduce one core ML experiment end to end

Priority: MURA first after the registry exists. Do not begin three training projects simultaneously.

### 5A. MURA study-level classification

- Acquire through an authorized source; MURA was not identified as a verified local dataset in this inventory.
- Define normal/abnormal study-level classification only.
- Freeze a patient-aware train/validation/test manifest and prove no patient/study leakage.
- Implement a ResNet or DenseNet baseline through a narrow MONAI/PyTorch adapter.
- Report AUROC, precision, recall, F1, confusion matrix, calibration curve/error, bootstrap confidence intervals, failure/abstention rate, latency and memory.
- Do not claim lesion detection or segmentation from MURA labels.

Exit: one complete artifact bundle can be activated and produces a persisted, provenance-linked, calibrated/abstaining study result.

### 5B. PTB-XL ECG

- Use official patient-aware folds and name the task: diagnostic superclass, rhythm, or multilabel.
- Preserve waveform sampling/preprocessing version and patient-level aggregation.
- Add signal-quality rejection before classification.
- Report macro/micro AUROC, F1, precision, recall, calibration, confidence intervals and abstention.
- Add a waveform viewer linked to the exact input interval; do not infer spatial anatomy from ECG alone.

### 5C. Clinical NLP comparison

- Reuse Milestone 4’s corpus/splits and artifact machinery.
- Evaluate entity, assertion/negation, temporality and document completeness separately.
- Promote only the task-specific winner; multiple adapters can remain available for research comparison.

## Milestone 6 — Domain-specific brain, lung and GI research

Priority: only after Milestones 2 and 5A produce a reusable evaluation pipeline.

### Dataset qualification first

For every discovered local collection, establish:

- authoritative source and version;
- license and redistribution/training terms;
- modality and file integrity;
- label provenance and annotation format;
- patient/study/series/video identifiers;
- duplicate/near-duplicate audit;
- protected-health-information review;
- train/validation/test split policy; and
- explicit exclusion reasons.

### One task per domain

- Brain: choose one CT or MRI study-level task supported by actual labels; do not combine DICOM, PNG and NIfTI collections without a harmonization protocol.
- Lung: choose classification or segmentation, not both under one claim; lung GLBs are visualization assets, not ground truth.
- GI: resolve the Kvasir duplicate archives and use patient/video-aware grouping if identifiers exist; choose classification or segmentation according to labels.

Exit criteria per model are identical to Milestone 5: immutable artifact, held-out predictions, confidence intervals, calibration, abstention, failure analysis and honest UI limitations. A model that fails a gate remains a catalog item.

## Milestone 7 — Longitudinal evidence and interoperability

1. Normalize biomarkers with explicit source units and reversible conversions.
2. Match concepts using versioned terminology mappings while retaining original text.
3. Compare old/new evidence only when identity, units, method and time semantics are compatible.
4. Display deltas, missingness, contradictions and corrections without producing unsupported causal or diagnostic summaries.
5. Freeze the canonical data model, then implement a narrow FHIR/CDA adapter informed by Metriport/Health Assistant.
6. Use synthetic/de-identified conformance fixtures; no live HIE credentials or external patient exchange until separately authorized.

Exit criteria:

- deterministic longitudinal fixtures cover unit conversions, method changes, missing ranges, contradictory observations and rejected findings;
- import/export round trips preserve provenance and tenant/case boundaries;
- interoperability failures are auditable and cannot silently drop data.

## Milestone 8 — Advanced capabilities as independent studies

These do not share an activation claim:

- Fusion: only truly paired same-patient modalities with compatible timestamps and disjoint patient splits; compare against unimodal baselines.
- Registration: patient source/target volumes and real landmarks; separate fitting/held-out landmarks and a predeclared target-registration-error threshold.
- Forecasting: one numeric target, unit and horizon; adequate longitudinal density; chronological hold-out and calibration. TwinWeaver/Foresight remain references until this exists.
- DeepSA: reproduce independently, resolve sliding-window and severity-threshold inconsistencies, create a versioned angiography adapter, then evaluate before integration.
- L3 anatomy: defer until genuine patient-specific volumetric reconstruction and registration are available.

## Milestone 9 — Security and deployment readiness

Before any clinical pilot:

- formal threat model and independent penetration testing;
- malware scanning, sandboxed parsers and decompression limits;
- encryption in transit/at rest, managed secrets and rotation;
- role-based authorization, tenant isolation and object-level access tests;
- append-only/tamper-evident audit retention;
- backups, restore drills and disaster recovery objectives;
- retention/deletion/legal-hold policy;
- supply-chain/SBOM and license review;
- human-factors, misuse, downtime and failure-mode testing; and
- independent privacy, regulatory, clinical-safety and clinical-validation review.

Do not state HIPAA compliance, diagnostic effectiveness, clinical effectiveness, real-time capability, or clinical validation until the applicable independent assessment is complete.

## Immediate next work queue

1. Complete the authenticated browser/reload completion gate and failure screenshots.
2. Validate the artifact-registry schema and enforce it in API/UI activation logic.
3. Build the reviewed multi-organ L1 anatomy manifest/selector.
4. Freeze and evaluate the document rule baseline on a licensed annotated corpus.
5. Finish one MURA artifact pipeline end to end.
6. Reuse that pipeline for PTB-XL and clinical NLP.
7. Qualify one local brain, lung, or GI dataset only after the core experiment infrastructure is stable.

This sequence produces visible application value while preventing unverified repositories, datasets, or example checkpoints from being represented as medical models.
