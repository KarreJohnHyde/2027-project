# Verified execution results

Final native Windows backend command:

`.venv\Scripts\python.exe -m pytest backend/tests -q`

**1,014 passed, 5 skipped, 10 warnings in289.48 seconds.** Full log: `artifacts/universal-2026-11-13/backend-final.log`. Skips are retained as skips, not passes. Existing third-party TorchXRayVision source/deprecation warnings remain. Earlier full runs and the reviewed synthetic-fixture scan failure are retained separately. Privacy-only follow-up:2 passed; exact-line test-fixture allowlist entry is documented and scanner rules/detection regression remain active.

Frontend: `npm run check` passed TypeScript, lint and check build; `npm run build` passed production build. Existing lint warnings remain. Logs: `frontend-check.log` and `production-build.log`. New/source-report Node checks:11 passed with0 failures; the geometry-only subset is3 tests.

Actual Edge browser checks:19 Command Center/Arena/intake/mobile tests and11 native spatial tests passed with no uncaught page exceptions. Earlier selector/stale-bundle/mobile failures were retained before reruns. Tests cover exact source page, citations, hash-named exports, delayed reply invalidation, task mismatch refusal, exact evaluation deep links, intake compatibility and clearing pending context on case change. The native checks cover actual source PNGs, shared voxel selection/crosshairs, window/reset, actual mask-derived surfaces, explicit unknown scale, and page-width bounds.

Live isolated API checks:18 passed, including all25 systems, case-scoped citations, typed/injection/treatment refusals, foreign-case reference refusal, actual2163-record report-bound Arena cohort, two fictional contradictory source reports through the worker, exact native prediction/review persistence across backend/worker restart and guest isolation. These are software controls, not medical accuracy estimates.

Native runtime: `D:/project/.venv/Scripts/python.exe`, Python3.12.10, Torch2.14.1+cu130, torchvision0.29.1+cu130, MONAI1.6.1, RTX5060/CUDA verified in the preceding same-day runtime probe and actual inference. Cardiac and brain MRI ran on the existing durable worker; numeric precision and preprocessing are stored in their run outputs. No Windows security policy was changed and the earlier DLL denial was not reproduced. A separate prepared WSL environment remains separately scoped; it is not presented as the native worker runtime.

QA: worker-mode stack on API8018/web8458, `.cache/review-20261113`, encrypted local research uploads and cookie sessions. The existing development/patient database was not reset. Actual native MRI masks/reviews and earlier synthetic/GI evidence persisted across restart.

The ordinary container configuration check refused an unset deployment secret and the Docker Linux daemon pipe was unavailable. Static Compose interpolation was then verified with an explicitly disposable validation-only environment placeholder; the previous environment was restored and no container started. No production deployment, cloud inference verification, off-host encrypted restore or clinical readiness claim is made.
