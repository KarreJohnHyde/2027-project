# Completion reproduction

Run from `D:/project`. Commands use fictional/public QA data and preserve original weights and registries. The usage profile remains commercial. Do not print the generated local credentials or secret environment files.

```powershell
$env:MEDTWIN_USAGE_PROFILE = "commercial"
$env:MEDTWIN_COMPLETION_RIGHTS_REGISTRY = (Resolve-Path artifacts/completion-2026-11-13/research/ptb-dataset-rights-sidecar.json).Path
$env:MEDTWIN_COMMERCIAL_REVIEW_PATH = (Resolve-Path artifacts/completion-2026-11-13/research/ptb-model-rights-sidecar.json).Path
powershell -NoProfile -File scripts/dev.ps1 -Mode qa -StateDir .cache/review-20261113 -BackendPort 8018 -WebPort 8458
.venv/Scripts/python.exe -m pytest backend/tests -q
npm run check
npm run build
.venv/Scripts/python.exe scripts/completion_live_audit.py
.venv/Scripts/python.exe scripts/completion_word_review.py
node tools/browser-qa/completion-workflows.mjs
node tools/browser-qa/completion-word-review.mjs
node tools/browser-qa/completion-accessibility.mjs
.venv/Scripts/python.exe scripts/completion_container_drill.py
```

The live audit creates an additional isolated public ECG case on rerun. Existing named fictional source controls are reused. Container drills use the dedicated `medtwin-completion-20261113` project, bind only localhost, preserve separate existing projects, and leave generated keys in ignored `.cache/completion-container`. An actual Docker engine is required. No off-host restore is implied.

After the final source and evidence are stable, collect the actual full-suite count into `artifacts/completion-2026-11-13/backend-collection.log` and save the full run to `backend-final.log`. Then create the local source snapshot and reconciled package:

```powershell
.venv/Scripts/python.exe scripts/completion_source_snapshot.py
.venv/Scripts/python.exe scripts/build_universal_package.py
.venv/Scripts/python.exe scripts/universal_verify_package.py
```

`build_universal_package.py` dispatches to the completion package when its baseline exists; the prior implementation remains available as `build_legacy()` for historical reconstruction. The current verifier reads actual collection/run counts and source hashes. The initial24-row assessment is retained separately. Do not rerun a historical generator to relabel old results as new evidence.

Raw external reference/OCR resources remain under ignored `data/external`; the resource inventory records publisher URLs, versions, hashes, rights evidence and rejections. Reproduce those downloads with the corresponding `scripts/completion_*` resource tools and inspect the recorded source rights before reuse. Do not automatically download or execute a noncommercial alternative under the commercial profile.
