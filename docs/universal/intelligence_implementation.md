# Universal intelligence implementation evidence — 2026-11-13

Implemented additive case-scoped evidence graph and deterministic read-only copilot in the canonical backend. Root mounts `universal_intelligence.router`; the canonical-app mount is exercised by the new tests. No database migration, original evidence edit, model training, network call, clinical activation or parallel authentication/storage system was added.

| Requirement | Delivered and tested | Remaining scientific/product boundary |
| --- | --- | --- |
| U-008 evidence graph | Stable persisted-row graph, reproducible response hash, provenance edges, missing modalities, current/history/withdrawal/supersession semantics, duplicate edges, approved overlays, unresolved polarity/laterality/unit and recorded report-model discrepancy flags, explicit bounds | This projection is evidence synthesis, not learned fusion. Distinct dates are history; it does not infer sample identity or automatically adjudicate conflicting dates. Full graph UI integration belongs to root. |
| U-009 biomarker reuse | Typed history tool reuses canonical conversion, source, date, duplicate and comparability rules, preserving source citations | No new forecast, patient registration or lesion-change model is claimed. Existing qualified longitudinal workflows retain their independent gates. |
| U-010 restricted assistant | Nine strict typed tools, canonical case read authorization, every supplied child/model reference separately scoped, citation membership, relative navigation/page references, unsupported clinical/action refusals, unsaved draft, no writes or external calls | This is a deterministic retrieval/template assistant. General natural-language reasoning, clinical diagnosis and autonomous services are unavailable. Synthetic engineering checks do not measure medical accuracy. |
| U-018 preservation / privacy | Existing auth/database reused; historical rows remain immutable; guest/private/shared rules retained; storage paths omitted; administrator child-reference isolation tested | No deployment/patient-data migration or recovery exercise was performed by this workstream. |

Files delivered: `backend/app/schemas/universal_intelligence.py`, `backend/app/services/universal_evidence.py`, `backend/app/services/universal_copilot.py`, `backend/app/routers/universal_intelligence.py`, `backend/tests/test_universal_intelligence.py`, `docs/universal/contracts/intelligence.md`, and generated `docs/universal/contracts/intelligence.schemas.json`.

Verification executed in the native Windows `.venv` on CPU using disposable test storage:

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_universal_intelligence.py backend/tests/test_correction_decisions.py backend/tests/test_universal_correction_order.py -q
```

Observed result: **40 passed in 23.46s** (32 new intelligence tests, 6 existing correction-decision regressions and 2 root-owned tied-clock correction-order regressions). No GPU was used. The new cases cover canonical router integration, source excerpts and citation membership, actual-response hash recomputation, authentication/private-case/viewer access, all four cross-case child reference types including administrator requests, strict tool/argument/limit validation, injection in both query and uploaded text, diagnostic/treatment/write refusals, no mutation, historical examinations, duplicate bytes and observations, current report reanalysis, independent approved corrections/removals, rejected evidence under bounded review history, pinned case-model evaluation, source/finding scope consistency, relative allowlisted page navigation, anatomy association semantics and canonical biomarker history.

While testing, the workstream identified a pre-existing tied-decision-timestamp ordering issue in canonical effective evidence. Root fixed that helper with persisted decision-ID/review-ID tie breaks and supplied the two independent regressions included above. The graph now selects the authoritative latest review for each bounded finding before limiting displayed review history, preventing unrelated busy history from hiding a rejection. Original source rows and reviewer decisions remain preserved.

The full application/browser/scientific workflow test matrix belongs to root integration and is not implied by this focused result. No patient diagnosis, general hallucination rate, model superiority, independently validated extraction score or clinical readiness claim follows from these synthetic checks.

Integration follow-up: document navigation now uses the existing verification page's `upload` query parameter rather than `source`. Both the isolated router test and canonical-app mount test assert the exact URL including case, upload and page. Targeted rerun: **2 passed in 1.78s** using `test_navigation_uses_allowlisted_relative_path` and `test_canonical_app_mounts_graph_and_copilot`.
