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
