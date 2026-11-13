> **Current completion audit:** [Commercial-scope implementation, measurements and remaining evidence](COMPLETION_REPORT_2026-11-13.md), [reproduction](COMPLETION_REPRODUCTION.md) and [current24-row matrix](requirements.csv). The earlier narrative below is a retained initial snapshot; its missing-feature/runtime statements and test totals are superseded by the linked completion audit.

# Implementation status — 13 November 2026

Implemented an additive MedTwin Universal research workspace with 25 system families, 4,849 searchable reference entries, a live capability view, case-bound source graph, restricted cited copilot, native spatial workbench, explicit batch intake modes and Model Arena. The existing FastAPI backend, storage, sessions, durable workers, registries and prior document/GI workflows remain canonical.

New working application paths:

- `/universal`: body-system/condition search; actual registry availability; keyboard-selectable graph and observation list; source span/page/review trail; timepoint filtering; original document preview; linked reviewer/history/anatomy controls; explicit evidence snapshot download with byte hash; typed read-only copilot with citations. The whole-case evidence list is labelled separately from the browsed catalogue; selecting an organ does not reassign a finding to it.
- Spatial imaging tab: three synchronized voxel-index views, real source-plane 3D, crosshairs, window/level, zoom/reset, actual source-grid masks, separate reviewer corrections and mask-derived surfaces. Geometry and unknown units remain explicit.
- `/arena`: saved evaluation metrics and hashes, report/registry identity binding, task/target/dataset checks and a digest over actual held-out patient/record/label tuples. Unrelated comparisons refuse. Delayed responses cannot reappear under a changed selection.
- `/upload`: Combined, Document-only and Scan-only batch context; incompatible extensions are visibly excluded from submission; backend content checks remain authoritative. Pending files, examination context and attestations reset when the selected case changes. Intake context is retained in existing upload association notes.

Actual new native worker runs: ACDC cardiac MRI case 6/upload 11/run 11; ISLES diffusion MRI case 7/upload 12/run 12. Original registered checkpoints produced persisted masks and actual surfaces, were reviewed as research software outputs and survived a real backend/worker restart without changed predictions. The 4D diffusion channel stack is accepted by its specific model adapter and explicitly refused by the 3D-only spatial viewer.

New per-input publisher-reference agreement, with both input and reference hashes checked:

| Public input | Reference voxels / prediction voxels | Dice | IoU |
| --- | --- | --- | --- |
| ACDC right ventricular cavity | 4,822 / 5,117 | 0.841735 | 0.726720 |
| ACDC myocardium | 4,740 / 6,340 | 0.705415 | 0.544897 |
| ACDC left ventricular cavity | 8,270 / 8,871 | 0.949770 | 0.904344 |
| ISLES lesion | 281 / 280 | 0.855615 | 0.747664 |

These are **one public input per checkpoint**, not new population accuracy estimates, independently reviewed clinical truth, improved weights or a clinical release. The source-grid pixel comparisons do not validate physical volume measurements or atlas registration. ACDC's unknown source units require the saved development-convention warning; its displayed legacy model millilitre measurements are not independently established physical measurements.

Live API integration verifies all 25 systems, exact case-source/citation scope, actual report bindings and 2,163 matched ECG records, explicit injection/write/treatment refusals, foreign-case reference refusal, contradictory fictional reports and guest isolation. Browser proofs and full test results are in the dated artifact manifest. Initial invalid system/selector, mobile layout and synthetic fixture scan failures are retained as failed attempts alongside fixes and reruns.

Not established: exhaustive official disease-code coverage, independent accuracy on real reports (0 independently checked pages), new rights-cleared weak-model training, all specialty diagnostic adapters, broad learned fusion, disease-specific clinical forecasting, validated patient-to-atlas registration/TRE, general 4D viewer support, exhaustive accessibility/performance qualification, a running container deployment or off-host encrypted restore. The existing sensitive Git-history publication block and zero clinical activations remain. See `requirements.csv` for all 24 requirements, implemented portions, evidence and exact blockers.
