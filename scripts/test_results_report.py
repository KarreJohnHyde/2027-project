"""Writes docs/testing/EXECUTED_TEST_RESULTS.md from a scripts/verify.ps1 run record.

Only steps that actually executed are listed, with their command, exit code, duration
and the tail of their output; a step counts as passed only if its exit code was 0.
  python scripts/test_results_report.py artifacts/verify/<stamp>.json [--walkthrough <walkthrough.json>]
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summary_line(step: dict) -> str:
    tail = step.get("output_tail") or ""
    if step["name"] == "backend-pytest":
        match = re.search(r"(\d+ passed[^\n]*)", tail)
        return match.group(1).strip() if match else "no pytest summary line"
    if step["name"].startswith("privacy-scan"):
        match = re.search(r"distinct values by category \(values withheld\): ([^\n]*)", tail)
        return f"findings: {match.group(1).strip()}" if match else "no scanner summary"
    if step["name"] == "frontend-lint":
        errors = re.search(r"Found (\d+) warnings? and (\d+) errors?", tail)
        return f"{errors.group(1)} warnings, {errors.group(2)} errors" if errors else "exit status only"
    if step["name"] == "frontend-build":
        return "built" if "built in" in tail else "exit status only"
    return "exit status only"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    parser.add_argument("--walkthrough", type=Path)
    args = parser.parse_args()
    record = json.loads(args.record.read_text(encoding="utf-8-sig"))
    steps = record["steps"] if isinstance(record["steps"], list) else [record["steps"]]
    lines = [
        "# Executed test results",
        "",
        f"Run {record['run_at']} by `scripts/verify.ps1` at commit `{(record.get('git_commit') or '—')[:10]}`"
        f"{' (working tree had uncommitted changes)' if record.get('working_tree_dirty') else ''}. "
        f"Overall: **{'ALL PASSED' if record['all_passed'] else 'FAILURES PRESENT'}**. Raw record: `{args.record.as_posix()}` (not committed).",
        "",
        "| Step | Command | Exit | Duration | Result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for step in steps:
        lines.append(f"| {step['name']} | `{step['command'].replace(str(ROOT), '.').replace('|', '/')}` | {step['exit_code']} | {step['seconds']} s | "
                     f"{'PASS' if step['passed'] else 'FAIL'} — {summary_line(step)} |")
    lines += ["", "A passing build or typecheck is not a browser pass; browser evidence is listed separately below.", ""]
    if args.walkthrough:
        walk = json.loads(args.walkthrough.read_text(encoding="utf-8"))
        sections = walk["sections"]
        lines += ["## Browser walkthrough", "",
                  f"{walk['browser']}, {walk['started_at']} → {walk['finished_at']}; details in `docs/anatomy/BROWSER_WALKTHROUGH.md`.", ""]
        if "routes" in sections:
            lines.append(f"- Routes rendered: {sections['routes']['passed']}/{sections['routes']['total']}")
        if "responsive" in sections:
            lines.append(f"- Phone-width routes passed: {sections['responsive']['passed']}/{sections['responsive']['total']}")
        if "anatomy" in sections:
            lines.append(f"- Anatomy variants rendered: {sections['anatomy']['variants_rendered']}/{sections['anatomy']['variants_total']} "
                         f"({sections['anatomy']['systems_with_all_variants_rendered']}/{sections['anatomy']['systems_total']} systems complete)")
        if "imaging" in sections:
            runs = sections["imaging"]["runs"]
            lines.append(f"- Research-model runs completed in the UI: {sum(1 for run in runs if run.get('completed'))}/{len(runs)}")
        if "trained" in sections:
            lines.append(f"- Trained-model evidence reports rendered: {sections['trained'].get('passed', 0)}/{sections['trained'].get('total', 0)}")
        if "labs" in sections:
            labs = sections["labs"]
            lab_ok = all(labs.get(key, False) for key in (
                "structured_lab_specimen_method_persisted",
                "censored_operator_persisted",
                "censored_result_not_range_classified",
                "duplicate_exclusion_persisted",
            ))
            lines.append(f"- Structured/censored labs, duplicate exclusion and provenance: {'PASS' if lab_ok else 'FAIL'}")
        if "corrections" in sections:
            corrections = sections["corrections"]
            correction_ok = all(corrections.get(key, False) for key in (
                "proposed_removal_persisted",
                "original_output_preserved_flag",
                "original_statement_unchanged",
                "proposal_not_applied_visible_in_ui",
            ))
            lines.append(f"- Typed correction proposal retained the original output and stayed not applied: {'PASS' if correction_ok else 'FAIL'}")
        if "validation" in sections:
            validation = sections["validation"]
            evaluator_ok = all(validation.get(key, False) for key in (
                "clinical_nlp_controls_exercised",
                "clinical_nlp_artifacts_hash_only",
                "ocr_controls_exercised",
                "ocr_raw_text_not_persisted",
            ))
            request_id_ok = validation.get("request_id_error_displayed", False) and validation.get("request_id_matches_error_response_header", False)
            lines.append(f"- Clinical NLP and OCR strict evaluator controls: {'PASS' if evaluator_ok else 'FAIL'}")
            lines.append(f"- Invalid-schema request ID matched the 422 response header: {'PASS' if request_id_ok else 'FAIL'}")
            lines.append(f"- Evaluator artifacts remained hash-only and raw fixture text was not persisted: {'PASS' if evaluator_ok else 'FAIL'}")
        if "prognosis" in sections:
            lines.append(f"- Prognosis abstention markers: {sections['prognosis']['abstention_markers']}; numeric risk statements: "
                         f"{sections['prognosis']['numeric_risk_statements']}")
        lines.append(f"- Unexpected console errors {len(walk['console_errors'])}, page errors {len(walk['page_errors'])}, "
                     f"failed requests {len(walk['failed_requests'])}; expected client-error probes {len(walk.get('expected_client_errors', []))}")
        if "assertions" in walk:
            lines.append(f"- Fail-closed walkthrough assertion gate: {'PASS' if walk['assertions'].get('all_passed') else 'FAIL'}")
        lines.append("")
    lines += ["## Required regression tests (directive §12)", "",
              "| # | Requirement | Test(s) |", "| --- | --- | --- |",
              "| 1 | Lab interval only from the report | `test_catalog_and_lab.py::test_record_lab_investigation_report` |",
              "| 2 | Missing specimen / lab = not documented | `test_catalog_and_lab.py::test_lab_report_never_assumes_laboratory_or_specimen` |",
              "| 3 | Manual lab does not double count | `test_catalog_and_lab.py::test_transcribed_results_join_trends_without_double_counting` |",
              "| 4 | Forecast endpoints never extrapolate | `test_evidence_and_fusion.py::test_forecasting_eligibility_enforcement` |",
              "| 5 | Earlier vs revised equation numbering, auth | `test_regression_contracts.py::test_earlier_and_revised_equation_numbering_stay_distinct_and_authenticated` |",
              "| 6 | Held-out checkpoint + dataset gate before reportability | `test_medtwin2_capabilities.py::test_validation_kit_formats_are_accepted_and_context_gates_reporting`, `test_model_registry.py::test_complete_bundle_requires_matching_checkpoint_hash` |",
              "| 7 | PHI not in release artifacts | `test_release_privacy.py` (2) |",
              "| 8 | OCR functional on scanned pages | `test_ocr.py` (2) |",
              "| 9 | Queue survives restart | `test_job_queue.py::test_jobs_survive_process_restarts` |",
              "| 10 | Encryption round trip and tamper | `test_storage_encryption.py` (15 cases) |",
              "| 11 | Browsers load and manipulate all ten assets | browser walkthrough, anatomy section |",
              "| 12 | Unsupported inference never hardcoded or random | `test_evidence_and_fusion.py::test_valid_inputs_do_not_create_unconfigured_model_predictions`, `test_research_inference.py::test_gate_refuses_models_without_a_verified_bundle`, `::test_classifier_output_is_deterministic_labelled_and_pending_review` |",
              "| 13 | ZIP import safety | `test_archive_import.py` (8) |",
              "| 14 | Separate anatomy and prognosis routes | browser walkthrough (routes and prognosis sections) |",
              "| 15 | Treatment / forecast displays abstain | `test_medtwin2_capabilities.py::test_prognosis_registry_covers_ten_organs_without_forecasts`, browser prognosis section |",
              "| 16 | 2D masks / boxes map to source geometry | `test_research_inference.py::test_detection_boxes_are_clipped_to_source_pixels`, `::test_segmentation_mask_maps_back_to_source_geometry` |",
              "| 17 | Hybrid layers keep schematic / alignment status | `test_regression_contracts.py::test_hybrid_atlas_layers_never_claim_patient_registration` |",
              "| 18 | Native BMP microscopy is validated and readable | `test_medtwin2_capabilities.py::test_bmp_microscopy_upload_is_validated_and_readable`, `test_research_inference.py::test_applicability_gate_rejects_unsupported_inputs` |",
              "| 19 | Clinical NLP strict evaluation and immutable artifact binding | `test_clinical_nlp_evaluation.py`, `test_evaluation_context.py` |",
              "| 20 | OCR CER/WER evaluation stores no raw text | `test_ocr_evaluation.py` |",
              "| 21 | API request IDs are returned and displayed | `test_request_ids.py`, browser validation section |",
              "| 22 | Structured/censored labs do not invent numeric trends | `test_catalog_and_lab.py`, `test_measurements_and_longitudinal.py`, browser labs section |",
              "| 23 | Typed correction proposals preserve original evidence | `test_human_review_workflow.py`, browser correction section |",
              ""]
    target = ROOT / "docs" / "testing" / "EXECUTED_TEST_RESULTS.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
