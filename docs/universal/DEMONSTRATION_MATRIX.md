> **Current completion audit:** [Commercial-scope implementation, measurements and remaining evidence](COMPLETION_REPORT_2026-11-13.md), [reproduction](COMPLETION_REPRODUCTION.md) and [current24-row matrix](requirements.csv). The earlier narrative below is a retained initial snapshot; its missing-feature/runtime statements and test totals are superseded by the linked completion audit.

# Demonstration matrix

All cases below are fictional educational records or public research inputs in the isolated QA database. None is an independent clinical validation cohort. Existing and newly executed proof are distinguished.

| ID | Observable result | Proof / scope |
| --- | --- | --- |
| DEMO-01 | Mixed embedded-text/scanned synthetic PDF processing, source review, 18 measured fields, 9 comparable deltas, export/reload | Prior same-day `artifacts/review-2026-11-13/workflows/`; current source/citation/export browser checks use case 5 |
| DEMO-02 | Actual native ISLES DWI+ADC MRI checkpoint inference, stored lesion mask and mask-derived surface | New `native-workflows/brain-native-evidence.json`; channel-stack MPR explicitly refused; no patient atlas registration |
| DEMO-03 | Actual ACDC native cardiac MRI checkpoint, 3 structures, 3 planes/source 3D/surfaces/review/restart | New `native-workflows/cardiac-native-evidence.json`, imaging/native browser proofs; earlier digital ECG parity remains separately measured |
| DEMO-04 | Actual Kvasir GI mask on original source and publisher reference comparison | Prior same-day case 3/run 3, source-image Dice 0.9526 / IoU 0.9095 for one image only |
| DEMO-05 | All 25 systems; eye/glaucoma catalogue remains usable with no registered model | New system-coverage API artifact and browser screenshot; no eye prediction |
| DEMO-06 | Prior/current exam selection and compatible lab comparison links | Existing same-day 2-exam synthetic case; current browser time controls; registered image-difference overlays unavailable |
| DEMO-07 | Actual worker processes two deliberately contradictory fictional reports in one exam; graph flags possible polarity conflict | New `integration/fictional-conflict-graph.json`; seeded software control, not independently verified report-vs-scan conflict accuracy |
| DEMO-08 | Blank/report-photo input refuses a disease prediction; previews are separate | Existing same-day upload/refusal controls and routing tests; no native HU inference from photographs |
| DEMO-09 | Bad digital ECG rate/leads/nonfinite values explicitly refused | Earlier same-day digital input/parity controls plus final backend regression; ECG-photo diagnosis unavailable |
| DEMO-10 | Read-only copilot citations; injected commands/treatment/write/foreign-case requests refused | New live integration18 checks + typed API tests; browser tests delayed-response invalidation |
| DEMO-11 | Saved metrics, report/checkpoint bindings and 2163 matching labelled ECG records; unrelated comparison refused | New Arena API/browser artifacts; no superiority or fabricated ROC claim |
| DEMO-12 | Backend/worker restart retains exact native model outputs/reviews; previous safe worker recovery retained no duplicate result | New live persistence check + previous recovery artifacts |
| DEMO-13 | Existing isolated guest entry cannot access registered case graph/copilot | New live API guest checks and full existing isolation suite |
| DEMO-14 | Native coordinate transforms/plane orientation/crosshair known-point tests; actual source planes and mesh | New backend+Node geometry tests and browser11 checks; millimetre/world coordinates withheld for unknown units |
| DEMO-15 | Failed kidney target and unavailable/rights-blocked models remain unavailable | Catalogue live gate audit; existing model evidence/prepared rights-gated experiments; no weights/status promoted |

Use the ordinary application routes to inspect missing prerequisites. The two new native publisher comparisons are per-input source-grid agreement measurements with exact reference hashes. They are not aggregated accuracy, expert clinical annotations or newly improved weights.
