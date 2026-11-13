# Universal catalogue and capabilities contract

Implemented source: `backend/app/routers/universal_catalogue.py`, prefix `/universal` (root mounts at `/api/v1`). These GET endpoints return public reference/catalogue metadata only; they do not access a case database, patient source, review or uploaded file. No endpoint runs inference or changes model eligibility.

## Endpoints

- `GET /universal/systems` → `{schema_version, catalogue_version, data_version, systems, notice}`. Each system has `id`, `label`, `synonyms`, `organs`, nullable `atlas_system`, `evidence_types`, `limitations`, `condition_count`, `capability_state: "EVIDENCE_SUPPORTED"`.
- `GET /universal/catalogue?q=&system=&kind=&limit=50&offset=0` → `{schema_version, catalogue_version, data_version, items, total, limit, offset, suggestions, counts, notice, terminology_scope}`. Search matches all query tokens across labels, synonyms, existing source codes and associated system vocabulary. `kind` is `organ|condition|structure|biomarker|investigation`. Limits: query ≤200 characters, limit 1–200, offset 0–100000. Invalid parameters/unknown systems return 422. Stable ordering ranks exact labels first, then reference concepts before detailed atlas structures, then label/ID.
- `GET /universal/catalogue/{concept_id}` → `{schema_version, data_version, item, notice}`. Identifiers are stable namespaced strings such as `condition:urinary:kidney-stone`, `biomarker:creatinine` or `atlas:<existing-structure-id>`. Missing identifiers return 404.
- `GET /universal/capabilities?system=<optional-system-id>` → capability shape below. Unknown systems return 422. No eligible/linked model returns an empty `items` array with `model_count: 0`; that is a usable evidence workspace, not an error.

The catalogue/data SHA covers the validated base bundle, all expanded atlas/analyte entries and the atlas file SHA. System-label or term changes change the data revision. It does not identify a new model evaluation.

## Entry shape

```ts
type CatalogueEntry = {
  id: string; label: string;
  kind: 'organ' | 'condition' | 'structure' | 'biomarker' | 'investigation';
  system_ids: string[]; synonyms: string[]; parent_id: string | null;
  laterality: 'left' | 'right' | 'bilateral' | 'midline' | null;
  code_mappings: Array<{
    system: string; version: string; code: string;
    relation: 'EXACT' | 'BROADER' | 'NARROWER' | 'RELATED';
    review_status: 'VERIFIED_SOURCE_MAPPING' | 'CURATED_UNVERIFIED'; source: string;
  }>;
  evidence_types: string[];
  anatomy_links: Array<{structure_id: string; relation: 'SCHEMATIC_ASSOCIATION' | 'REFERENCE_ATLAS_TERM'}>;
  model_targets: Array<{model_id: string; target: string}>;
  model_ids: string[];
  capability_state: 'CATALOGUE_ONLY' | 'EVIDENCE_SUPPORTED';
  model_link_semantics: string;
  code_mapping_status: 'NOT_MAPPED' | 'SOURCE_MAPPINGS_RETAINED_UNVERIFIED_WHERE_MARKED';
  source: string; source_version: string; licence: string;
  review_status: 'CURATED_RESEARCH_CATALOGUE' | 'EXISTING_REFERENCE_TERMINOLOGY'; note: string;
};
```

Condition entries stay `CATALOGUE_ONLY` even when they carry a candidate link. An organ, investigation, atlas term or biomarker is `EVIDENCE_SUPPORTED`: the workspace can organize source evidence. Neither state establishes any patient finding. `model_ids` are explicit target associations that pass an exact normalized match against the current registry's supported classes. Unknown IDs/targets are excluded. Candidate associations are never fuzzy concept-to-diagnosis mappings.

`anatomy_links` are generic reference/schematic associations, not patient registration, lesions or a new mesh. Atlas left/right are retained from the reference source; a side suffix distinguishes otherwise identical display labels and the original names remain synonyms. Attribution is linked to `/anatomy/derived/atlas/ATTRIBUTION.md`. `atlas_system` references only an existing dedicated generic reference asset where available; absent assets are null. Investigation entries are reference concepts, not a replacement for the existing clinical service/orderable catalogue.

## Capability response

```ts
type CapabilityResponse = {
  schema_version: 'medtwin.universal-capabilities.v1';
  data_version: string; system: string | null;
  items: Array<{
    model_id: string; label: string; task: string | null;
    registry_state: string | null;
    capability_state: 'MODEL_AVAILABLE_RESEARCH_ONLY' | 'MODEL_BLOCKED';
    research_gate: {allowed: boolean; blockers: string[]};
    upload_supported: boolean; inference_input: string | null;
    supported_modalities: string[];
    targets: Array<{concept_id: string; label: string; target: string}>;
    checkpoint_sha256: string | null; preprocessing_version: string | null;
    evaluation_artifact: string | null;
    clinical_activation: 'CLINICAL_ACTIVATION_NOT_CLEARED'; limitations: string[];
  }>;
  model_count: number; clinical_activation_count: 0;
  notice: string; comparison_semantics: string;
};
```

For every explicit candidate, the service calls the existing `research_gate`, which checks existing usage/rights policy, status, failed-target assessment, research-inference registration, dataset licence, actual checkpoint and hash, evaluation-report existence and applicable OOD reference/hash. Gate errors fail closed. A model also needs a supported serving input contract. Actual upload, patient/data permissions, modality, quality, OOD, required channels and geometry are checked by the existing execution path when inference is requested. A green research capability is not successful inference on the current case, calibrated probability, diagnostic coverage or clinical approval. No registry status, failed checkpoint or use policy is changed here.

Fresh catalogue audit on 2026-11-13 found 18 explicitly linked registry models, 15 passing their current research preflight and 3 blocked. `ct_kidney_tumour_segresnet` remains failed/blocked; TotalSegmentator's generic research path and TorchXRayVision remain blocked by their current generic gates. This response is live and may differ as artifacts/rights change. Separate specialized adapters may have their own gates; catalogue code never bypasses one adapter's refusal using another.

## Sources and extension/import

Base JSON schema: `docs/universal/contracts/catalogue.schema.json`. Source bundle: `backend/app/data/universal_catalogue.json`. Version `2026.11.13.1` contains 25 families, 92 organ concepts, 169 condition examples and 12 investigations. Read-only expansion reuses 4484 existing attributed Z-Anatomy/Svitylo atlas terms (CC BY-SA 4.0) and 92 existing MedTwin analyte definitions. The total is 4849 entries, not 4849 model-supported diseases. Original curated condition examples retain the source specification SHA and date; they are a starting catalogue, not an exhaustive clinical ontology.

No official, licensed ICD-11 disease release was supplied locally. New disease code mappings remain empty/`NOT_MAPPED`. Existing analyte LOINC codes retain their source and explicitly use `RELATED`, `CURATED_UNVERIFIED`, `CURATED_NOT_RELEASE_VERIFIED`; no official-release verification or exact mapping is claimed. An `EXACT` imported code mapping is rejected unless its source review is explicitly `VERIFIED_SOURCE_MAPPING`. The importer validates this contract but cannot independently establish legal access or semantic correctness of an author's declared mapping; that remains source/reviewer work.

```powershell
.venv/Scripts/python.exe scripts/import_universal_catalogue.py --input authorized.json --output local-catalogue.json
.venv/Scripts/python.exe scripts/import_universal_catalogue.py --input authorized-extension.json --output local-catalogue.json --merge
```

Input and output are explicit. Input must be a complete valid bundle, including parent references; source file ≤32 MiB. A repeated identical import leaves bytes and mtime intact. Default import refuses different existing content. `--merge` only appends new system/entry IDs, refusing every conflicting existing ID and retaining each record's source/version/licence. Existing base bundle provenance remains the base provenance; merged content SHA identifies the revision. Output directory must already exist. Temporary output is flushed and atomically replaced only after validation and unchanged-target verification; a lock prevents concurrent importer writes. Import has no database, user, case, registry, activation or checkpoint effects.

## Verification

`python -m pytest backend/tests/test_universal_catalogue.py -q`: **31 passed** (ordinary pytest, isolated temporary backend storage). Covers all 25 families, non-model specialties, synonyms/spelling, attribution/laterality, expanded reference graph validation, bounded pagination, detail/unknown IDs, exact target matching, model/input gates, fail-closed exceptions, invalid graph/code schemas, data revision, idempotence and non-destructive extension. Capability mocks test interface semantics; they do not establish measured model accuracy.

Actual registry/file-gate audit: `artifacts/universal-2026-11-13/catalogue-verification.json`. This contains the source/catalogue/data hashes, per-system condition counts, all current candidate gate results, a separate pytest command and explicit unvalidated work. Reproduce using `.venv/Scripts/python.exe scripts/audit_universal_catalogue.py --output artifacts/universal-2026-11-13/catalogue-verification.json`. The audit does not execute pytest. No new model training, inference or accuracy evaluation was performed in the catalogue audit.
