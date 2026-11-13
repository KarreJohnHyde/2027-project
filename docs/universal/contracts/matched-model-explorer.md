# Matched public model-record explorer

`POST /api/v1/universal/research/matched-records/query` is authenticated through the canonical session boundary. It is read-only and runs no model. The new router is `app.routers.matched_model_explorer.router`; the Arena embeds `MatchedModelExplorer` additively.

The strict request rejects unknown fields and invalid values:

```json
{
  "mode": "global",
  "label": "NORM",
  "order": "disagreement",
  "errors_only": false,
  "search": "",
  "offset": 0,
  "limit": 20,
  "expected_snapshot_id": null
}
```

`mode` is `global` (registered PTB ECG baseline versus fusion) or `same_run` (the original fusion experiment's saved ECG-only versus fused arm). Labels are `NORM`, `MI`, `STTC`, `CD`, `HYP`. Ordering is `disagreement`, `errors` or `probability_gap`; ties use stable pseudonyms. Search is a literal public-record pseudonym substring, up to 64 alphanumeric/underscore/hyphen characters. Offset is 0–100,000; limit is 1–50. A supplied snapshot must be 64 lowercase hexadecimal characters. The UI uses ten rows per page.

The response is `medtwin.matched-model-records.v1`, with `status` (`MATCHED_RECORDS_AVAILABLE`, `RIGHTS_BLOCKED`, `UNAVAILABLE`, `SNAPSHOT_CHANGED`), `reason`, request mode/label/order/page, `labels`, `total`, `total_filtered`, `snapshot_id`, `cohort`, `models`, `rows`, `never_writes:true`, `clinical_activation:false` and an explicit research notice. Exact Pydantic definitions are in `backend/app/schemas/matched_model_explorer.py`.

Each row contains a stable `ptb-<20 hex>` record pseudonym, the actual selected binary reference annotation, two saved probabilities/threshold decisions with `TRUE_POSITIVE`, `TRUE_NEGATIVE`, `FALSE_POSITIVE` or `FALSE_NEGATIVE`, decision disagreement, absolute score gap, age/sex missingness flags, and current header/waveform SHA-256 proof. Raw patient keys, raw publisher record IDs, dates, file paths and demographic values are withheld. No private case/upload is inferred to match a public record.

The canonical commercial source and model gates pass before reading any predictions or publisher metadata. The endpoint accepts neither arbitrary model IDs nor file paths. It verifies model task, ordered labels, target definition, dataset version, report/registry declaration binding, actual checkpoint bytes, both saved probability matrices, and exact record/patient/reference tuples. It independently rehashes current files rather than relying on stat-keyed cached digests: a changed prediction with unchanged size/mtime is refused. Publisher metadata/label tables must match the checksum manifest, preserve patient-disjoint folds, reproduce the registered dataset version and agree with every held-out tuple. For each displayed row, the current `.hea` and `.dat` bytes must match their publisher checksums. Source paths remain inside the fixed dataset root; selected files are bounded to 1 MiB each.

The fusion columns are explicitly `fusion_p_`; its matched ECG control uses `ecg_only_p_`, not the separately trained global baseline. Each arm uses its own frozen validation threshold, including the `score >= threshold` equality convention. Missing thresholds refuse the comparison. The original same-run ECG-only control checkpoint was **not archived**: its descriptor therefore has `checkpoint_sha256:null`, `checkpoint_binding_status:CONTROL_ARM_CHECKPOINT_NOT_ARCHIVED` and a separate `associated_run_checkpoint_sha256`. The fused checkpoint is never falsely attributed to the control scores. Model provenance includes current prediction hashes, threshold sources, column prefixes and links to the recorded evaluation artifact.

Snapshot hashes bind model/source bytes, decision policies, label, publisher metadata and cohort tuples. Pagination/filtering can pin this hash; changed evidence returns no rows with `SNAPSHOT_CHANGED`. The frontend suppresses replies for stale mode/label/filter/page requests. Publisher metadata caching is bounded to two content-hash keys; probability matrices reuse the bounded Arena cache, with independent current-byte verification before use.

This is a recorded same-input research comparison: current source files and recorded tuples are checked, while historical forward passes are not independently replayed. Reference annotations are ECG superclass labels, not adjudicated disease diagnoses. Scores are validation-calibrated research outputs, not clinical certainty. Per-record disagreements/errors do not establish model superiority. No new weights, inference, NC-data execution, case linkage or clinical activation occurs.

Verification on 13 November 2026: **18 focused backend tests passed in 6.51s**. They cover controlled reference errors, threshold equality, correct saved arms, missing control weights, rights refusal before data access, label/dataset/cohort/source/checkpoint mismatch, same-size/mtime mutation, stable pagination/search, snapshot invalidation, authentication, invalid parameters and absence of patient identifiers.

Actual permitted public-source proof: both modes contain **2,163 matching records / 1,881 patients**; pinned adjacent pages have no overlap; displayed header/waveform bytes passed checksums. MI reference-error filtering yields 401 records for the global comparison and 389 for the same-run comparison; these are internal benchmark review counts, not clinical accuracy or superiority claims. Evidence is in `artifacts/expansion-2026-11-13/research/api-proof.json`, with small pseudonymized first-page artifacts.

Headless Edge verified the real UI in **five checks**: source-row selection, pinned pagination, label/error ordering/filtering, correct same-run arm/provenance/search, and expanded Arena accessibility/mobile layout. There were zero page/server errors, zero new inference requests, zero automated axe violations, and no document overflow at 390 px. Proof/screenshots are in `artifacts/expansion-2026-11-13/research/ui-proof.json`. The initial whole-app build attempt encountered another workstream's temporarily missing structure-browser component; root owns the final whole-app build and integration suite. No unverified full-build result is claimed here.
