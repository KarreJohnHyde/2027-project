# Container security review — 9 November 2026

**Release remains blocked.** Available image updates were applied and all reported critical findings were removed. Four high-severity backend OS findings remain. Raw frontend scanning retains one musl finding that conflicts with Alpine's branch-specific fixed status; it is recorded for review, not silently suppressed. Neither dependency scans nor these changes establish clinical or commercial approval.

| Raw Docker Scout findings | Before | Reviewed image |
| --- | --- | --- |
| Backend | 7 high, 8 medium, 49 low | 4 high, 7 medium, 47 low |
| Frontend | 9 critical, 24 high, 5 medium, 5 low | 1 high; vendor says the installed branch version is fixed |

The machine-readable source, exact image IDs, raw SARIF paths and full finding lists are in `artifacts/audits/image-security-review-2026-11-09.json`. The raw scanner output is retained without severity overrides.

## Applied changes and verification

- Refreshed the existing base images and applied distribution package updates. Debian zlib and Alpine curl/brotli/zlib/expat/musl updates were available. The Nginx runtime returns to its unprivileged user after the build steps.
- Removed unused Nginx GeoIP, image-filter, njs and XSLT modules. The application serves static assets and proxies its API; these processors were not configured. Removing them also removed their unused XML/image dependencies, reducing the frontend inventory from 88 packages to 38.
- Installed setuptools 84.2.1, verified Python dependency consistency and removed the unused runtime pip installer from the immutable backend image. No runtime package declares pip as a dependency. The application installs its requirements during the image build. The backend package inventory fell from 331 to 314.
- The latest hardened local synthetic drill checks API and frontend readiness, frontend-to-API proxying, commercial gate refusal, encrypted database and referenced-upload backup/restore, authentication, case access and actual upload decryption. Evidence: `artifacts/audits/docker-drill-1c9c48f757/report.json`.
- Actual generated-image OCR recovered the expected token with network disabled and a read-only container. OpenCV, SimpleITK, Torch CPU, MONAI, ONNX Runtime and patched setuptools import successfully, with runtime pip absent. Evidence: `artifacts/audits/docker-final-runtime-probe-2026-11-09.log`.

## Open findings and vendor discrepancy

| Finding | Present source package | Current disposition |
| --- | --- | --- |
| CVE-2026-86140 | Debian libxml2 | Debian's trixie version remains listed as vulnerable; newer unstable distribution versions are fixed. Keep open. [Debian tracker](https://security-tracker.debian.org/tracker/CVE-2026-86140). |
| CVE-2026-74860 | Debian libxml2 | Stable source version remains listed as vulnerable. Its described Python SAX binding conditions need an application exposure review; no blanket non-applicability assertion is made. [Debian tracker](https://security-tracker.debian.org/tracker/CVE-2026-74860). |
| CVE-2026-117610 | Debian expat | Installed stable package remains listed as vulnerable; do not claim that apt upgrade fixed it. [Debian tracker](https://security-tracker.debian.org/tracker/CVE-2026-117610). |
| CVE-2026-118370 | Debian expat | Installed stable package remains listed as vulnerable. Existing upload limits are not a complete disposition of a native parser finding. [Debian tracker](https://security-tracker.debian.org/tracker/CVE-2026-118370). |
| CVE-2026-107891 | Alpine musl 1.2.6-r3, branch 3.24 | Scout expects edge's 1.2.6-r6, but Alpine explicitly lists **3.24-main 1.2.6-r3 as fixed** and the package page confirms this branch version. Retain the raw finding and evidence for release-owner review. [Alpine security status](https://security.alpinelinux.org/vuln/CVE-2026-107891), [branch package](https://pkgs.alpinelinux.org/package/v3.24/main/x86_64/musl). |

Next steps are a patched supported base/package source or a reviewed image redesign, application exposure analysis, a new image scan and the same functional/recovery checks. Do not mix unstable distribution packages into the clinical candidate merely to make a scanner green. Medium/low findings also require documented assessment; none are globally waived here. Pin the approved image digest and retain its SBOM/evidence through the actual release process.

The Windows workstation's separate advisory result (zero known findings among assessed packages; four unassessed local-version distributions) does not supersede this container report. Windows native-policy approval, off-host recovery, clinical evidence and exact-asset commercial rights remain separate blockers.
