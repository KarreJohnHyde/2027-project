# GitHub CI and local full-stack check

The frontend at `http://localhost:8443`, backend at `http://localhost:8000` and the frontend's `/api/v1` proxy were responding successfully when this work began. The existing native stack is retained; jobs execute inline. Use `npm run dev:full` to start the stack when it is stopped, and `npm run dev:stop` to stop its recorded processes.

GitHub had no open issues or pull requests. The latest [CI run on the previous main commit](https://github.com/KarreJohnHyde/2027-project/actions/runs/42660337869) failed in four backend tests; downstream browser and Docker jobs were consequently skipped. Its frontend and dependency-security jobs passed.

The fixes address three causes:

- **Portable WSL paths:** a Linux `Path` does not expose a Windows drive in `.drive`. Parse Windows paths with `PureWindowsPath`, retain absolute Linux paths, and reject ambiguous drive-relative and UNC locations. Tests exercise both path styles on either host and preserve shell quoting, including apostrophes and spaces.
- **Explicit development dependency:** declare the tested `imagecodecs==2026.10.10` encoder used by tifffile while constructing generated JPEG slide fixtures. It has Python 3.12 Linux wheels. The application slide reader continues to decode supported baseline JPEG tiles through Pillow; this dependency belongs to development/test requirements.
- **Optional private model artifacts:** check availability before loading the RSNA checkpoint in the held-out serving regression. Only the explicit `InferenceNotPermitted` availability exception triggers that skip. Model thresholds and serving restrictions remain intact; synthetic refusal tests continue running on CI.

Repository dependency alerts had been disabled. After enabling them, GitHub's asynchronous scan reported seven Vite advisories against the stale `pnpm-lock.yaml` (Vite 8.0.5). The installed application and npm lock already used 8.3.5. Raise the manifest floor to the tested 8.3.5, regenerate the pnpm lock from the npm lock, and audit both locks in frontend CI. No advisory is dismissed or allowlisted. Secret scanning reported no open alerts. Code scanning returned `no analysis found`; these checks do not establish that code scanning has run or that all software vulnerabilities are absent.

The current source also includes the private-reference report implementation. Its actual documents, OCR, measurements, case contents, keys, account database and local review cache are excluded from publication. Tests use synthetic records only.

Publication uses the existing separate clean checkout, preserving the upstream licence and public history. Source files are compared by staged blob IDs and the publication tree/history are scanned before push. The local repository's older sensitive history is never transferred; its separate history blocker remains open.

Local validation: 783 backend tests passed with five optional skips; 14 browser tests passed with one optional public-CT control skipped. The 31 targeted regressions passed, as did frontend type-check/lint/build and the privacy scan of source and built frontend. Existing frontend lint warnings and third-party model warnings remain visible. These are software checks, not clinical validation or a complete security assessment.

The subsequent clean-runner browser check exposed workstation-only fixture assumptions. Model-form and routing UI tests now declare synthetic availability/selection responses, while a direct API control still verifies that missing real artifacts prevent selection. Synthetic job and benchmark fixtures are labelled explicitly. Case names are unique across retries. The full workflow checks a selected atlas region when its derivative exists; otherwise it checks the explicit missing-asset state and retained report evidence, allowing only that exact expected asset-load error. `MEDTWIN_E2E_NO_DERIVED_ASSETS=1` reproduces the absent-geometry branch locally. No production model gates are relaxed.

The full browser suite then passed again (14 passed, one optional skip) with its backend reading the clean publication checkout and optional derived geometry deliberately absent. Twelve routing and job-progress backend tests also passed.

The separate Vercel `backend` project also lacked the documented large-function opt-in. Its 834.76 MB uncompressed bundle failed the standard 500 MB limit. Add the non-secret `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` setting to that project's Production and Preview environments, then rebuild the same reviewed Git deployment. The rebuilt backend reached Ready and its health endpoints responded successfully. This configuration repair does not establish clinical or commercial readiness.
