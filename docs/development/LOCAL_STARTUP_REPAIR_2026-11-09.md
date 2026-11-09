# Local full-stack startup repair — 9 November 2026

The Windows development launcher used a 1.5-second loopback connection deadline. This workstation can take approximately two seconds to report a refused connection, so a free port was incorrectly classified as occupied and neither service started. The deadline is now five seconds; a timeout is reported as inconclusive instead of asserting that another service owns the port.

Workspace case restoration also waited for optional registry requests, including expensive research-checkpoint hashing. Authorised cases, health and case evidence now load independently of those registries. A browser regression holds the model request open, then returns a synthetic 503, while confirming that the selected case and its document page remain available. Results from another signed-in user are discarded if the session changes during loading.

Start from PowerShell:

```powershell
cd D:\project
npm run dev:full
```

The launcher starts the approved existing Python environment and Vite, or reuses services it verifies as MedTwin. The development services run in the background. Stop services recorded as started by this launcher with `npm run dev:stop`; reused managed services are left running. Logs and stack state are under `.cache/dev-stack`.

Verified on the actual running stack:

- `http://localhost:8443/` and `http://127.0.0.1:8443/`: HTTP 200, with the sign-in interface visible in Edge.
- Backend health and API documentation on port 8000: HTTP 200 through both hostnames.
- Frontend `/api/v1/system/health` proxy: HTTP 200; no uncaught browser errors on the entry page.
- Real-socket regression coverage is available through `powershell -NoProfile -File scripts/tests/test_dev_ports.ps1`.

The final backend/script run passed 804 tests with five optional skips. Frontend typechecking, lint execution and the build pass. The complete browser suite passed 13 tests, with the explicitly supplied public CT control skipped because no control file was selected. This includes the delayed-model-metadata regression and the full report/photographed-film workflow. Earlier narrower browser counts are historical.

Local development startup is separate from clinical or commercial release approval. Existing model, rights and image-security holds remain in force.

GitHub publication uses the existing sanitized snapshot checkout for `KarreJohnHyde/2027-project`. Only Git-eligible source, configuration, documentation and curated tracked assets are included. Local Git metadata, secrets, databases, environments, model checkpoints, acquired medical datasets, temporary outputs and logs are excluded. The affected local history is not uploaded or rewritten; the publication checkout's current tree and history must pass the privacy scan before push.
