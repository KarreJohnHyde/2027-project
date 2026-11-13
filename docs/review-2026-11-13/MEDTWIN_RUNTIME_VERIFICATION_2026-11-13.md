# Runtime verification — 13 November 2026

Generated from local evidence at 2026-11-13T08:14:50.164017+00:00.

The earlier Windows `WinError 4551` PyTorch import refusal was not reproduced by the fresh probe or the subsequent real-checkpoint controls. No endpoint policy, security setting, DLL trust rule or original ML environment was changed. The precise cause of the earlier denial remains unestablished; this is observed recovery, not a claim that an institutional policy was repaired.

- Windows interpreter: `D:\project\.venv\Scripts\python.exe`; Python 3.12.10; package inventory and tensor/CUDA result: `artifacts/review-2026-11-13/runtime-windows.json`.
- Isolated QA API: `http://127.0.0.1:8018`; preview: `http://127.0.0.1:8458`; separate worker; state `.cache/review-20261113`. No development/patient database reset.
- Document API/worker workflow: **VERIFIED**; image API/worker workflow: **VERIFIED**.
- Evidence after an actual QA API/worker restart: **VERIFIED**; see `workflows/persistence.json`.
- A separate WSL Python 3.12.15 CPU environment was created from the repository's pinned requirements; torch import/tensor operation verified. It is a fallback environment, not an alternative deployment or a full GPU/API validation.
- Windows `uv pip check --python .venv/Scripts/python.exe` verified consistency of 290 installed packages; the isolated WSL environment's 78 packages also passed. Observed GPU: NVIDIA GeForce RTX 5060 Laptop GPU, driver 617.14, 8,151 MiB reported memory. Dependency consistency is not a security or clinical certification.
- Optional ML telemetry now catches missing/refused native-library imports, preserves document/API availability and reports an unavailable optional ML runtime. A controlled native-refusal regression passed; inference eligibility is not overridden.

| Check | Actual recorded summary |
| --- | --- |
| Final full backend | 922 passed, 5 skipped, 10 warnings in 307.04s (0:05:07) |
| Initial full backend (retained failure) | 1 failed, 878 passed, 11 skipped, 10 warnings in 519.60s (0:08:39) |
| Review tools | 55 passed in 30.35s |
| Document/calibration/annotation targeted | 241 passed in 84.05s (0:01:24) |
| Input contracts | 101 passed in 100.45s (0:01:40) |
| Frontend evidence/render | ℹ tests 37 / ℹ pass 37 / ℹ fail 0 |
| Panel-context targeted | 188 passed in 22.42s |
| Saved-report schema normalization | ℹ tests 8 / ℹ pass 8 / ℹ fail 0 |

`npm run check` passed typecheck, lint and check build (11 existing lint warnings). The initial complete backend run recorded one environment-dependent blank-OCR test failure; the fixture was corrected to explicitly exercise the empty-OCR branch, retaining the separate unavailable-OCR test. Final results above supersede that run but do not erase it. Frontend source/render checks also exposed stale schema-v3 and missing child-state fixtures; these were updated to the current v4 contract. No assertions were removed to obtain a pass.

Bounded checkpoint parity intentionally exits 1 because historical Kvasir exact-mask parity differs by one pixel. This is distinct from a failed model load or API workflow. See the parity report.
