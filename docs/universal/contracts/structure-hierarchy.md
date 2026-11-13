# Whole-body source hierarchy and ICD-11 adapter

New implementation: `services/universal_structures.py`, `services/icd11_source_adapter.py`, `schemas/universal_structures.py`, `routers/universal_structures.py`, and `src/components/UniversalStructureBrowser.tsx`. Shared entrypoints, existing catalogue services/JSON, model weights and model registries are unchanged by this track. Root mounts the router and inserts the component.

## Actual source coverage and semantics

The current registry contains **4,907 nodes**: 25 application families, 92 existing curated organ/context concepts, 4,484 existing atlas terms, 43 existing asset variants, 100 explicitly source-named asset components, 7 registered segmentation tasks and 156 verbatim registered output labels. Model classes, including background/numeric labels, are task vocabulary, not new anatomy or diseases. No suborgan, anatomical parent, lesion, mesh or model-to-atlas semantic mapping is invented.

`parent_relation` distinguishes:

- `SOURCE_EXPLICIT_PARENT`: the existing atlas source's parent identifier.
- `SOURCE_ASSET_COMPONENT`: an existing manifest component with `label_source: SOURCE_NAME`; inferred/proposed component labels are not promoted into this new hierarchy.
- `REGISTERED_TASK_CLASS`: a verbatim output label grouped under its actual registered model task. This is not an anatomical parent.
- `APPLICATION_SYSTEM_CONTEXT`: the existing project's curated system/organ grouping. Model-task system membership comes from existing explicit catalogue target links; class labels inherit task context, not a per-label clinical or atlas mapping.
- `NONE`: a source/root node with no explicit parent.

System navigation is context and may differ from actual source ancestry. Explicit parent expansion preserves the source's complete children across application contexts. Source parent existence and cycles are validated. Laterality is copied only from explicit `atlas.side`; a model string such as `kidney_right` remains verbatim but has no guessed separate side field. Source labels and review states remain visible.

Source geometry references use existing atlas mesh-to-chunk ranges and manifest tier declarations. A tier is locally available only when its path remains under the configured public root, the file exists and its recorded size matches. A declared SHA is exposed; large geometry hashes are not newly reverified, and file presence is not patient geometry or rights clearance. Missing atlas geometry falls back to existing atlas terms without inventing mesh links; a missing manifest reports unavailable.

The atlas index's global source declarations include legacy noncommercial sources and multiple licence families. This alone cannot establish each chunk's commercial eligibility. Chunk results therefore explicitly require source-specific review, even when bytes are present. Existing asset variants retain their declared `license.commercial_use`, attribution and share-alike metadata; this is reported as an existing declaration, not new legal approval. The new component does not render, export or automatically approve a disputed asset.

Supported evidence types, condition examples and investigation concepts come from existing system-scoped catalogue records. They are contextual source definitions, not conditions inferred at the selected structure. Model capabilities use existing registry/research/usage gates. This commercial-purpose browser requires the active commercial profile and its existing review to pass; research-only profile availability is not relabelled commercially eligible. Clinical activation remains false.

## API contract

All endpoints require the existing authenticated application user and are relative to `/api/v1`:

- `GET /universal/structures/systems` → `{schema_version, systems, node_count, sources, icd11, notice}`. Every one of the 25 families is present with existing organ/evidence/atlas context plus `structure_count`.
- `GET /universal/structures?system=&parent_id=&q=&limit=50&offset=0` → `{schema_version, items, total, limit, offset, parent_id, navigation_relation, sources, notice}`. Query ≤200 characters, page size 1–200, offset 0–100000. Missing source parent returns 404, invalid system/bounds 422. Empty filters return the 25 navigation roots. System context returns appropriate source-entry roots. Explicit non-system parents return actual source children. Search returns source labels/Latin names/identifiers, without fuzzy clinical mappings.
- `GET /universal/structures/{node_id}/detail?case_id=<optional>` → `{node, assets, capabilities, supported_evidence_types, investigations, concepts, icd11, notice}`. Example: `atlas:regions.eyelashes_l`. An optional case independently calls existing read authorization first; only recorded graph source associations to the selected application system are summarized. Source IDs, assertion, review and active-evidence state remain attached. The response declares `exact_structure_mapping: false` and `diagnosis_inferred: false`; absence of an association is not normality.
- `GET /universal/structures/icd11/status` returns the separate WHO source/adapter and mapping prerequisites.
- `GET /universal/structures/icd11/lookup/{numeric_entity_id}` is a bounded native WHO MMS reference lookup; missing prerequisites return explicit unavailable status without a network call.

Node fields: `id,label,kind,parent_id,parent_relation,system_ids,laterality,laterality_source,source_id,source,review_state,asset_ids,model_ids,synonyms,child_count,capability_state`. Reference state is separate from live model/rights results. Exact source identifiers are retained; node namespacing does not rename a source concept.

Component props: `{ caseId?: number|null, systemId?: string|null, onSelect?: (node) => void }`. External system selection updates the context; a user structure choice can update root selection using the original `source_id`/`system_ids`. The full-width collapsible placement is root-owned. The component supports source search, real child expansion/back navigation, pagination, explicit laterality, source details and model/rights/unavailable states. It does not trigger inference or mutate a case.

## WHO ICD-11: native reference versus crosswalk

Primary sources reviewed on 2026-11-13:

- [WHO ICD API authentication](https://icd.who.int/docs/icd-api/API-Authentication/) documents OAuth2 client credentials, scope `icdapi_access`, and the official token endpoint.
- [WHO API version2 documentation](https://icd.who.int/docs/icd-api/APIDoc-Version2/) specifies HTTPS, `API-Version: v2`, language negotiation and MMS linearization for coded classification; Foundation entities are distinct and do not themselves supply MMS codes.
- [WHO classification copyright policy](https://www.who.int/about/policies/publishing/copyright) and [current terms](https://icd.who.int/en/docs/icd11-license.pdf) allow attributed unchanged classification incorporation for commercial/noncommercial software under CC BY-ND3.0 IGO, with additional software terms. Source code, title and URI must remain together. **Section1.2.4 requires a separate written agreement for mappings/crosswalks and translations.** Native reference access does not grant that mapping permission.

The adapter needs `WHO_ICD_CLIENT_ID`, `WHO_ICD_CLIENT_SECRET`, an explicitly pinned `WHO_ICD_RELEASE` (`YYYY-MM`) and operator-recorded `MEDTWIN_WHO_ICD_TERMS_ACCEPTED=true`. It does not inspect credential files or expose secret values. Credentials and release/terms acceptance are currently missing, so live WHO content has not been fetched and connectivity is not claimed verified. Test-only environment fixtures/mock transport are not operator acceptance.

When genuinely configured, the adapter sends only a numeric reference ID to official WHO endpoints, rejects redirects and bounded/invalid responses, and preserves original MMS code/title/URI/release together with attribution. Case text, patient evidence and search queries are never transmitted. It has no automatic crosswalk operation, and `crosswalk_mapping_available` stays false because no reviewed crosswalk or separate WHO agreement was supplied. Existing local **ICD-10-CM FY2027 remains ICD-10-CM**, never relabelled ICD-11. WHO endorsement and clinical coding approval are not implied. No gated data or new weights were downloaded.

## Verification

`python -m pytest backend/tests/test_universal_structures.py -q` → **9 passed**: all25 contexts/source parent links, all4484 atlas terms, no guessed side/atlas mappings for class strings, missing geometry, path/size/rights separation, mixed source licences, bounded queries, WHO missing-credential no-network behavior, mocked native reference preservation, authentication and optional private-case boundaries. `npm run typecheck` passed.

Actual local source proof: `artifacts/expansion-2026-11-13/catalogue/proof.json`. Actual mounted QA API/UI proof: `catalogue/browser-proof.json` (**13 checks passed**). It verified authentication, all25 families/4907 nodes, real left-side/source-parent detail, uncleared per-chunk rights, unavailable WHO mapping, source search/child expansion/back navigation and no browser exceptions. The expanded hierarchy had **0 reported axe A/AA violations at1440px and390px**, with no horizontal page overflow; incomplete checks remain recorded and full manual conformance is not claimed. Browser tool: `tools/browser-qa/expansion-structures.mjs`, existing local Playwright/axe packages, local credentials never logged. Initial selector loading was explicitly awaited; no UI data was mocked.
