# Five-priority implementation and publication audit

The new whole-body expansion specification is implemented on the canonical MedTwin backend and React application, with the user's commercial-development requirement retained. Source evidence and capability gates remain authoritative. Universal disease detection, clinical deployment, validated patient-to-atlas alignment and disease-specific prognostic accuracy are not established by this work.

| Requested priority | Working result | Verification |
| --- | --- | --- |
| Patient-specific 3D reconstruction | Eligible source volumes have synchronized native/anatomical planes, explicit 4D selection and source-coordinate 3D. Selected findings pin their exact saved volumetric masks; selecting a source without a finding does not borrow another output. Original native mask editing and mask-derived surfaces remain available. | Actual public MRI source rendered in the unified workspace, with an explicit channel choice. Original registered checkpoints/weights preserved. |
| Explainable evidence-linked AI | A finding selects its original image/report, exact saved overlay, recorded model, checkpoint/source hashes, preprocessing and review state. New Trust & Refusal Center separates the original outcome from current execution eligibility. Original failure remains inactive even after a confirmation. | New refusal/provenance regression plus live browser source/overlay/hash checks. Two unused legacy components containing simulated heatmaps were retired to an explicit evidence-required view. Actual compatible chest-model attention remains separately labelled attribution. |
| Time-travel comparison | New hash/frame/user/case-bound ten-minute sessions support previous/current, shared-window blend, checkerboard and signed difference on a shared source-physical grid. Rigid transforms reject scaling/shear/reflection. Invalid field-of-view pixels are excluded and hatched. | Original synthetic controls gave measured mean difference 0.21875, exactly matching the independent expected value; all five render modes verified. Native uncalibrated MRI can be inspected geometrically but numeric differences refuse.9 focused tests and15 browser checks passed. |
| Research/uncertainty laboratory | Same-input record explorer adds matched labels, score differences, frozen-threshold disagreements, false positives/negatives, missingness, paging and actual source-byte identities to the existing ROC/PR/reliability/paired-comparison Arena. | 2,163 records / 1,881 patients. 18 focused tests; 5 browser checks; zero detected expanded-view axe violations. The unarchived same-run control checkpoint is disclosed instead of being attributed the fusion checkpoint. No new inference or superiority claim is made by browsing saved scores. |
| One synchronized workspace | Twin Control Room is the default case view. The source workstation, evidence list, source report, trust panel, examination controls and chronological research baselines share one selection. The time label uses documented examination/collection time, not processing time. |10 live browser controls passed, including inline volume 3D, raw raster overlay, source identities, dated history, keyboard tabs and desktop/mobile layout/accessibility. |

## Whole-body and terminology coverage

The new source-backed anatomy/capability hierarchy contains **4,907 nodes**: 25 navigation families, 92 curated organ contexts, 4,484 atlas terms, 43 declared asset variants, 100 explicitly source-named components, 7 segmentation tasks and 156 verbatim model labels. Source ancestry, application context, asset components and model classes have distinct parent relationships. Laterality is shown only when explicitly recorded. Per-chunk asset rights remain unreviewed where an index mixes source licenses; physical availability is not commercial clearance.

The existing official FY2027 ICD-10-CM index remains 98,403 source classifications, separate from the new hierarchy. The WHO ICD-11 native-reference adapter is prepared with explicit OAuth/release/terms gates. Missing credentials/accepted terms prevent network requests. Crosswalks require the separate WHO written agreement described in the recorded primary terms; no ICD-10-to-ICD-11 mapping is fabricated. See [structure hierarchy contract](contracts/structure-hierarchy.md).

## Evidence

- Full integrated backend suite: **1,109 passed, 5 skipped**, 10 warnings. Focused test counts above are included in this total.
- Frontend TypeScript/lint/check build and production build passed.
- Native browser proofs: control room 10, hierarchy 13, model explorer 5, temporal comparison 15 checks passed. Expanded views report zero detected automated axe violations at the stated desktop/mobile widths. Manual accessibility conformance is not claimed.
- The hardened localhost Linux stack is rebuilt and separately checked with encrypted backup/restore, original synthetic spatial inputs and a commercially permitted public ECG. Raw data and generated credentials stay local.
- The original user-modified model-registry hash remains `b56979e0591788b1d588fa11c590e0378a1f98db1114612df702f816aa5b65b7`.

Detailed local proofs are under `artifacts/expansion-2026-11-13/`. The committed aggregate evidence is [evidence/expansion-2026-11-13.json](evidence/expansion-2026-11-13.json). Previous dated reports and manifests describe their own source snapshots; their source hashes are not assertions about this later tree.

## Remaining limits

The 24-row scientific matrix remains 15 verified engineering requirements, 7 partial requirements and 2 blocked requirements within the previously documented scopes. Independent full real-report annotations, commercial prerequisites for six original weak-model families, known data leakage/unknown patient identities, exact historical Kvasir parity, independently validated patient/atlas registration and broad multimodal/disease-outcome cohorts remain open. A catalogue or interactive comparison does not replace those references. Zero models are clinically activated.

## GitHub publication scope

Only reviewed source, metadata, tests and documentation are published. Patient uploads, local databases, keys, downloaded datasets, new model weights, local 3D binaries and screenshots of third-party inputs are excluded. Previously reviewed remote assets and the owner's LICENSE are preserved. Publication uses a separate checkout of the existing public history, never this workspace's sensitive Git history. Tree/history privacy scans and source parity checks are required before push. No existing Git history is rewritten or force-pushed.

See [public source setup](PUBLIC_SOURCE_SETUP.md), the [spatial comparison contract](contracts/temporal-comparison.md) and the [same-input explorer contract](contracts/matched-model-explorer.md).
