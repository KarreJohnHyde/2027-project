# Executed test results

Run 2026-10-25T14:11:26.9832637Z by `scripts/verify.ps1` at commit `1aedb231dc`. Overall: **ALL PASSED**. Raw record: `artifacts/verify/20261025T140444Z.json` (not committed).

| Step | Command | Exit | Duration | Result |
| --- | --- | --- | --- | --- |
| backend-pytest | `".\.venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider` | 0 | 120 s | PASS — 260 passed, 1 skipped in 113.34s (0:01:53) |
| frontend-typecheck | `npm run -s typecheck` | 0 | 5 s | PASS — exit status only |
| frontend-lint | `npm run -s lint` | 0 | 0.7 s | PASS — exit status only |
| frontend-build | `npm run -s build` | 0 | 2.3 s | PASS — built |
| privacy-scan-tree | `".\.venv\Scripts\python.exe" -I scripts\privacy_scan.py --tree` | 0 | 2.9 s | PASS — findings: none |
| browser-walkthrough | `node walkthrough.mjs --state "C:\Users\johnn\AppData\Local\Temp\medtwin-qa" --out "C:\Users\johnn\AppData\Local\Temp\medtwin-qa\walkthrough-20261025T140444Z"   --model-image "gi_kvasir_v2_classifier:ENDOSCOPY=.\kvasir-dataset-v2\dyed-lifted-polyps\008aa3ed-1812-4854-954c-120ae85bb6bd.jpg" --model-image "angiography_stenosis_detector:ANGIOGRAPHY=.\data\stenosis\test\images\1.png" --model-image "kidney_stone_detector:CT=.\test\images\1-3-46-670589-33-1-63706052409136049800001-4885266517035478638_png_jpg.rf.403057fc6d27ba2b8a1020faf23ea6e8.jpg" --model-image "angiography_syntax_segmenter:ANGIOGRAPHY=.\data\syntax\test\images\1.png" --model-image "gi_gastrovision_27class_classifier:ENDOSCOPY=.\Gastrovision\Accessory tools\00367989-767a-483e-a312-1a74f6c72b0f.jpg" --model-image "gi_kvasir_seg_polyp_segmenter:ENDOSCOPY=.\Kvasir-SEG\Kvasir-SEG\images\cju0s690hkp960855tjuaqvv0.jpg" --model-image "hematology_cnmc_all_classifier:MICROSCOPY=.\C-NMC_Leukemia\validation_data\C-NMC_test_prelim_phase_data\1.bmp"` | 0 | 258.8 s | PASS — exit status only |

A passing build or typecheck is not a browser pass; browser evidence is listed separately below.

## Browser walkthrough

Microsoft Edge 156.0.4314.42 (playwright-core 1.63.0, headless), 2026-10-25T14:07:06.801Z → 2026-10-25T14:11:24.417Z; details in `docs/anatomy/BROWSER_WALKTHROUGH.md`.

- Routes rendered: 17/17
- Phone-width routes passed: 17/17
- Anatomy variants rendered: 43/43 (10/10 systems complete)
- Research-model runs completed in the UI: 7/7
- Trained-model evidence reports rendered: 11/11
- Structured/censored labs, duplicate exclusion and provenance: PASS
- Typed correction proposal retained the original output and stayed not applied: PASS
- Clinical NLP and OCR strict evaluator controls: PASS
- Invalid-schema request ID matched the 422 response header: PASS
- Evaluator artifacts remained hash-only and raw fixture text was not persisted: PASS
- Prognosis abstention markers: 5; numeric risk statements: 0
- Unexpected console errors 0, page errors 0, failed requests 0; expected client-error probes 1
- Fail-closed walkthrough assertion gate: PASS

## Required regression tests (directive §12)

| # | Requirement | Test(s) |
| --- | --- | --- |
| 1 | Lab interval only from the report | `test_catalog_and_lab.py::test_record_lab_investigation_report` |
| 2 | Missing specimen / lab = not documented | `test_catalog_and_lab.py::test_lab_report_never_assumes_laboratory_or_specimen` |
| 3 | Manual lab does not double count | `test_catalog_and_lab.py::test_transcribed_results_join_trends_without_double_counting` |
| 4 | Forecast endpoints never extrapolate | `test_evidence_and_fusion.py::test_forecasting_eligibility_enforcement` |
| 5 | Earlier vs revised equation numbering, auth | `test_regression_contracts.py::test_earlier_and_revised_equation_numbering_stay_distinct_and_authenticated` |
| 6 | Held-out checkpoint + dataset gate before reportability | `test_medtwin2_capabilities.py::test_validation_kit_formats_are_accepted_and_context_gates_reporting`, `test_model_registry.py::test_complete_bundle_requires_matching_checkpoint_hash` |
| 7 | PHI not in release artifacts | `test_release_privacy.py` (2) |
| 8 | OCR functional on scanned pages | `test_ocr.py` (2) |
| 9 | Queue survives restart | `test_job_queue.py::test_jobs_survive_process_restarts` |
| 10 | Encryption round trip and tamper | `test_storage_encryption.py` (15 cases) |
| 11 | Browsers load and manipulate all ten assets | browser walkthrough, anatomy section |
| 12 | Unsupported inference never hardcoded or random | `test_evidence_and_fusion.py::test_valid_inputs_do_not_create_unconfigured_model_predictions`, `test_research_inference.py::test_gate_refuses_models_without_a_verified_bundle`, `::test_classifier_output_is_deterministic_labelled_and_pending_review` |
| 13 | ZIP import safety | `test_archive_import.py` (8) |
| 14 | Separate anatomy and prognosis routes | browser walkthrough (routes and prognosis sections) |
| 15 | Treatment / forecast displays abstain | `test_medtwin2_capabilities.py::test_prognosis_registry_covers_ten_organs_without_forecasts`, browser prognosis section |
| 16 | 2D masks / boxes map to source geometry | `test_research_inference.py::test_detection_boxes_are_clipped_to_source_pixels`, `::test_segmentation_mask_maps_back_to_source_geometry` |
| 17 | Hybrid layers keep schematic / alignment status | `test_regression_contracts.py::test_hybrid_atlas_layers_never_claim_patient_registration` |
| 18 | Native BMP microscopy is validated and readable | `test_medtwin2_capabilities.py::test_bmp_microscopy_upload_is_validated_and_readable`, `test_research_inference.py::test_applicability_gate_rejects_unsupported_inputs` |
| 19 | Clinical NLP strict evaluation and immutable artifact binding | `test_clinical_nlp_evaluation.py`, `test_evaluation_context.py` |
| 20 | OCR CER/WER evaluation stores no raw text | `test_ocr_evaluation.py` |
| 21 | API request IDs are returned and displayed | `test_request_ids.py`, browser validation section |
| 22 | Structured/censored labs do not invent numeric trends | `test_catalog_and_lab.py`, `test_measurements_and_longitudinal.py`, browser labs section |
| 23 | Typed correction proposals preserve original evidence | `test_human_review_workflow.py`, browser correction section |

