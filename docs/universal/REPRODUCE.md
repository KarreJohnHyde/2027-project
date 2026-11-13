# Reproduction commands

Run from `D:\project` in PowerShell. Use the existing project Python, not an unrelated global interpreter.

```powershell
npm run check
npm run build
.venv\Scripts\python.exe -m pytest backend/tests -q
node --test scripts/universal-geometry.test.mjs scripts/trained-report.test.mjs
.venv\Scripts\python.exe scripts/audit_universal_catalogue.py --output artifacts/universal-2026-11-13/catalogue-verification.json
```

Use the existing isolated QA database/worker stack; never pass `-Fresh` to preserve its evidence:

```powershell
powershell -NoProfile -File scripts/dev.ps1 -Mode qa -StateDir .cache/review-20261113 -BackendPort 8018 -WebPort 8458
.venv\Scripts\python.exe -X utf8 scripts/universal_verify_workflows.py
.venv\Scripts\python.exe -X utf8 scripts/universal_reference_comparison.py
.venv\Scripts\python.exe -X utf8 scripts/universal_verify_integration.py
node tools/browser-qa/universal-workflows.mjs
node tools/browser-qa/universal-imaging.mjs
.venv\Scripts\python.exe scripts/build_universal_package.py
```

Web: `http://127.0.0.1:8458/universal`; Arena: `http://127.0.0.1:8458/arena`; canonical API: `http://127.0.0.1:8018/api/v1`. Local QA credentials stay in the ignored QA state directory and are read locally by the scripts. No secret is included in reports or screenshots.

The native script reuses prepared QA case 6/upload 11 (the ACDC public source created by the spatial verification), creates/reuses a separate ISLES public research case, and uses fixed inference idempotency keys. It is an integration rehearsal, not a universal demo seeder or population reevaluation. Its prerequisites and input checks fail visibly rather than substituting dummy masks. The integration script adds/reuses a deliberately contradictory fictional case and exercises the existing isolated guest entry.

Previous complete report/GI demo and audit commands are documented in `docs/review-2026-11-13/`; those scripts produce synthetic report controls, rights-aware experiment preparations and explicit parity differences. Do not treat their historical evaluation metrics as newly retrained model results.

Stop only the owned QA processes when needed:

```powershell
powershell -NoProfile -File scripts/dev.ps1 -Mode qa -StateDir .cache/review-20261113 -BackendPort 8018 -WebPort 8458 -Stop
```

Container verification was attempted. Ordinary Compose interpolation refused absent `SECRET_KEY`; a static-only check passed with a disposable validation placeholder in the command environment, restored immediately afterwards. Docker's Linux daemon was unavailable. Native research execution succeeded independently. No production/container deployment or off-host encrypted restore was declared verified. Configure a real deployment secret and approved daemon/environment, then run `docker compose config --quiet`, build/start, health/worker and encrypted backup/restore checks before a deployment claim.
