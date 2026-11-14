> **Current completion audit:** [Commercial-scope implementation, measurements and remaining evidence](COMPLETION_REPORT_2026-11-13.md), [reproduction](COMPLETION_REPRODUCTION.md) and [current24-row matrix](requirements.csv). The earlier narrative below is a retained initial snapshot; its missing-feature/runtime statements and test totals are superseded by the linked completion audit.

# Integration handoff

Checkout: `D:/project`, branch `feature/medtwin-2-integration`, unchanged HEAD `2a6d8e4aa04f447aea14e948f04800bd2414c1b1`. All implementation changes remain uncommitted and local. Exact initial worktree and source hashes: dated baseline artifact. Existing user changes and model registry hash are preserved.

Ownership was recorded before parallel work. Catalogue, imaging and intelligence agents delivered additive modules, contracts and bounded tests; root reviewed and mounted them in the canonical FastAPI entrypoint and integrated React navigation, shared selection, sources, intake and Arena. Review found and fixed source-ID URL mismatch, stale async response/context races, universal/atlas identifier mismatch, insufficient report provenance checks and mobile overflow. A canonical approved-correction ordering fix now breaks tied clock timestamps by persisted decision order; no original extraction row is changed.

Migrations: **none**. The catalogue is a versioned source bundle with an explicit-target, idempotent, append-only import tool. The graph is a bounded projection, not a duplicate database. No data reset or additional authentication/storage stack was introduced.

New router modules: `universal_catalogue`, `universal_imaging`, `universal_intelligence`, `universal_arena`, mounted at the existing `/api/v1` prefix. Existing inference/review/render/export/queue endpoints remain in use. Contracts are in `docs/universal/contracts/`.

New routes `/universal` and `/arena` coexist with all previous sections. Validation Center accepts `?model=` to open the exact saved model evaluation. Upload Center now has case-keyed pending state and batch intake context. Shared selections are ephemeral and clear across account/case changes.

See `artifacts/universal-2026-11-13/run-manifest.json` for file hashes, exact test logs, current source identities and scopes. The initial privacy test failure came from one explicitly invented DICOM fixture. It was reviewed using the repository's existing exact-line hash allowlist; scanner rules and identifier-detection regression remain active. Failed artifacts were retained, not overwritten as successes.

QA stack uses `.cache/review-20261113` on ports8018/8458; native case6/upload11 and case7/upload12 are persistent. Earlier case5 synthetic reports and case3 public GI inference remain. Keep credentials, encryption keys, uploads and databases local/ignored. Do not push or transfer this checkout's Git history while `docs/security/PHI_RELEASE_BLOCKER.md` remains open.

Required science/operations beyond current scope are listed per requirement and in `CLINICAL_RELEASE_BLOCKERS.md`. Reproduction commands are in `REPRODUCE.md`. Do not promote failed/blocked models, treat reference anatomy as registered patient geometry or describe this implementation as universal diagnosis.

## 2026-11-14 · Claude (integration review), touching model-track files

Codex had no writes in these files during the change; please review on your next pass.

- **CQ500 external evaluation shown in the registry** (commit `44056ef75f`). `backend/app/services/external_evaluations.py` attaches a saved evaluation in `docs/validation/models/*.json` to a registry entry only when it measured the registered checkpoint (same SHA-256) and states `clinical_validation: false`. The Model Registry card and evidence matrix show it. `scripts/evaluate_head_ct_cq500.py` excludes a missing scan only when a repair record documents a defective public source (CQ500-CT-120).
- **Single-slice head CT model on an assembled DICOM series.** New registry field `series_inference: "head_ct_per_slice"` (set on `brain_ct_rsna_ich_classifier`, which already declares its `dicom_window`). `model_inference.head_ct_series_mode()` returns `neighbours` (2.5-D, unchanged), `per_slice` or `None`. `prepare_series`, `run_head_ct_series` and the run path accept the per-slice mode; `series_model_images()` gives each slice alone, exactly as the CQ500 evaluator's `single_slice_scan` reads it. The series output adds `label_maxima`, `slice_input` and `series_pipeline_external_evaluation`. `/research-models` adds `head_ct_series_mode`. A precomputed series run now reports its real execution time instead of 0 ms.
- **Parity on real data** (CPU, float32): app path versus the evaluator on CQ500-CT-1 (reader-majority ICH) and CQ500-CT-0 (none). Maximum absolute difference 0.0 across all six labels, with the same analysed-slice counts. CT-1: any-ICH 0.9998 (threshold 0.442). CT-0: 0.360, below threshold. On CT-1 the model also flagged IVH, which the reader majority did not mark.
- **Tests:** `backend/tests/test_head_ct_per_slice_series.py` (synthetic network and DICOM fixtures). Browser test "native head CT series is analysed slice by slice" uses the git-ignored control from `scripts/prepare_e2e_ct_series.py` (CQ500, CC BY-NC-SA 4.0, evaluation only; never commit or publish).
