"""Writes docs/anatomy/BROWSER_WALKTHROUGH.md from a walkthrough.json (tools/browser-qa).

Screenshots stay in the QA scratch directory (synthetic QA data and public-dataset images
only); the document lists what was asserted and the outcome of each check.
  python scripts/browser_walkthrough_report.py --walkthrough %TEMP%/medtwin-qa/walkthrough-final/walkthrough.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--walkthrough", required=True, type=Path)
    args = parser.parse_args()
    walk = json.loads(args.walkthrough.read_text(encoding="utf-8"))
    sections = walk["sections"]
    lines = [
        "# Browser walkthrough",
        "",
        f"Run {walk['started_at']} → {walk['finished_at']} with {walk['browser']} against the isolated QA stack "
        f"({walk['base_url']}; started by `scripts/dev.ps1 -Mode qa`: isolated scratch SQLite database, encrypted upload store, "
        "worker-mode job queue with a separate worker process, synthetic QA login). The QA database contains no patient record; "
        "browser-created inputs are explicitly synthetic, and optional imaging inputs must be public research examples supplied on the command line.",
        "",
        "Reproduce from a new synthetic QA state: `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Mode qa -Fresh`, then "
        "`node tools/browser-qa/walkthrough.mjs --state %TEMP%\\medtwin-qa --out <dir> --sections routes,responsive,anatomy,lifecycle,labs,evidence,corrections,queue,imaging,validation,trained,prognosis "
        "--model-image MODEL_ID:MODALITY=<public-research-image> ...`, repeating `--model-image` once for every runnable `image_2d` model listed by `/research-models`, "
        "or `scripts/verify.ps1 -Browser`. Screenshots are written to the output directory, outside the repository.",
        "",
        f"Unexpected browser errors over the whole run: **{len(walk['console_errors'])} console errors, {len(walk['page_errors'])} uncaught page errors, "
        f"{len(walk['failed_requests'])} failed requests**. Expected client-error probes recorded separately: "
        f"**{len(walk.get('expected_client_errors', []))}**.",
        "",
    ]
    if "assertions" in walk:
        lines += [f"Fail-closed walkthrough assertion gate: **{verdict(bool(walk['assertions'].get('all_passed')))}**.",
                  f"Raw evaluator fixture text absent from `walkthrough.json`: **{verdict(bool(walk['assertions'].get('evaluator_raw_text_absent_from_walkthrough_json')))}**.", ""]
    if "routes" in sections:
        routes = sections["routes"]
        lines += ["## Routes", "", f"{routes['passed']} of {routes['total']} routes rendered a page heading without an error boundary.", "",
                  "| Route | Heading | Result | New browser errors |", "| --- | --- | --- | --- |"]
        lines += [f"| `{item['route']}` | {item['heading']} | {verdict(item['rendered'])} | {item['new_errors']} |" for item in routes["routes"]]
        lines.append("")
    if "responsive" in sections:
        responsive = sections["responsive"]
        viewport = responsive["viewport"]
        mobile_nav = responsive.get("mobile_navigation", {})
        lines += ["## Phone-width route checks", "",
                  f"**{responsive['passed']} of {responsive['total']} routes passed at {viewport['width']} × {viewport['height']} CSS pixels.** "
                  "A pass requires a rendered page heading, the requested viewport, no error boundary and no page-level horizontal overflow. "
                  "Wide tables may scroll inside their own containers. A screenshot was captured for every route.", "",
                  f"Mobile navigation opened and closed through its visible controls: "
                  f"{verdict(bool(mobile_nav.get('button_visible') and mobile_nav.get('opened') and mobile_nav.get('closed')))}.", "",
                  "| Route | Heading | Viewport | Page overflow | New browser errors | Result |",
                  "| --- | --- | --- | ---: | ---: | --- |"]
        lines += [
            f"| `{item['route']}` | {item['heading']} | {verdict(item['viewport_matches'])} | {item['horizontal_overflow_px']} px | "
            f"{item['new_errors']} | {verdict(item['rendered'] and item['viewport_matches'] and item['no_page_overflow'])} |"
            for item in responsive["routes"]
        ]
        lines.append("")
        failed_layouts = [item for item in responsive["routes"] if not item["no_page_overflow"]]
        if failed_layouts:
            lines += ["Page-level overflow diagnostics:", ""]
            for item in failed_layouts:
                edge_entries = item.get("page_edge_elements") or item.get("overflowing_elements", [])
                offenders = "; ".join(
                    f"`{entry.get('selector') or entry['tag']}` ({entry.get('width', '?')} × {entry.get('height', '?')} px, "
                    f"left {entry.get('left', '?')}, right {entry.get('right', '?')}, +{entry['excess']} px; "
                    f"{entry.get('aria_label') or entry.get('text') or entry.get('class_name') or 'unlabelled'})"
                    for entry in edge_entries
                ) or "no individual element identified"
                widest_entries = item.get("overflowing_elements", [])
                widest = widest_entries[0] if widest_entries else None
                widest_note = ""
                if widest and all(widest.get("selector") != entry.get("selector") for entry in edge_entries):
                    widest_note = (
                        f" Widest descendant: `{widest.get('selector') or widest['tag']}` "
                        f"({widest.get('width', '?')} × {widest.get('height', '?')} px, right {widest.get('right', '?')}, "
                        f"scroll/client {widest.get('scroll_width', '?')}/{widest.get('client_width', '?')}, "
                        f"overflow-x {widest.get('overflow_x', '?')})."
                    )
                lines.append(
                    f"- `{item['route']}`: page +{item['horizontal_overflow_px']} px "
                    f"(viewport {item.get('viewport_width', viewport['width'])}, document {item.get('document_width', '—')}, "
                    f"body {item.get('body_width', '—')}); page-edge boxes: {offenders}.{widest_note}"
                )
            lines.append("")
    if "anatomy" in sections:
        anatomy = sections["anatomy"]
        lines += ["## Anatomy Studio — ten systems", "",
                  f"**{anatomy['variants_rendered']} of {anatomy['variants_total']} variants rendered; {anatomy['systems_with_all_variants_rendered']} of "
                  f"{anatomy['systems_total']} systems with every variant rendered.** Each variant was opened at "
                  "`/anatomy-studio?system=<id>&variant=<id>`, orbited with a mouse drag, and counted as rendered only when the viewer's WebGL "
                  "counters reported triangles or points and the canvas showed real content (luminance σ > 3, > 1 % non-background pixels). "
                  "Per-variant numbers: `docs/anatomy/ASSET_QA.md`.", "",
                  "| System | Variants | Rendered |", "| --- | --- | --- |"]
        lines += [f"| {item['system']} | {item['variants']} | {item['rendered']} |" for item in anatomy["systems"]]
        lines.append("")
    if "lifecycle" in sections:
        life = sections["lifecycle"]
        queue_records = life.get("queued_jobs") or ([life["queued_job"]] if life.get("queued_job") else [])
        jobs = ", ".join(f"#{job['id']} {job['kind']} {job['status']} ({job['execution_mode']}, attempts {job['attempts']})" for job in queue_records) or "none"
        lines += ["## Upload lifecycle (synthetic report)", "",
                  f"- Upload Center: file chosen, case-match and de-identification confirmations ticked, uploaded and processed: "
                  f"{verdict(life['upload_completed_in_ui'])} (row reached *Completed*).",
                  f"- Queue transition message was visible in the upload row: {verdict(life.get('queued_message_visible_in_ui', False))} "
                  f"(`{life.get('queued_message') or 'not observed'}`).",
                  f"- Durable jobs recorded for the case: {jobs}.",
                  f"- Document Intelligence: {life['document_statements_rendered']} source-linked statements rendered; measurement text visible: "
                  f"{verdict(life['measurement_text_visible'])}.", ""]
    if "labs" in sections:
        labs = sections["labs"]
        lines += ["## Manual laboratory entry and deduplication", ""]
        if labs.get("skipped"):
            lines += [f"**BLOCKED:** {labs['blocker']}", ""]
        else:
            lines += [
                f"- Submitted a synthetic creatinine transcription through the real dialog: {verdict(labs['manual_submission_completed_in_ui'])}.",
                f"- Linked the selected synthetic source upload: {verdict(labs['source_document_linked'])}.",
                f"- Blank laboratory/specimen rendered as *not documented*: {verdict(labs['omitted_lab_and_specimen_render_not_documented'])}.",
                f"- No printed interval rendered *Indeterminate*, while the catalog interval was labelled orientation-only: "
                f"{verdict(labs['missing_printed_interval_renders_indeterminate'] and labs['catalog_interval_labelled_orientation_only'])}.",
                f"- Duplicate exclusion was visible in Biomarker Analytics and persisted in the returned series: "
                f"{verdict(labs['duplicate_exclusion_visible_in_ui'] and labs['duplicate_exclusion_persisted'])} "
                f"(`{labs.get('duplicate_reason') or 'no duplicate reason recorded'}`).",
                f"- Dated creatinine points after deduplication: {labs.get('creatinine_points_after_dedup', '—')}.",
                f"- Entered a second, unlinked software fixture with laboratory, specimen and assay fields plus a `<` comparator: "
                f"{verdict(labs.get('censored_submission_completed_in_ui', False) and labs.get('structured_lab_specimen_method_visible', False) and labs.get('censored_operator_visible', False))}.",
                f"- Structured provenance and the censoring operator round-tripped through the API; the censored value remained *Indeterminate* instead of being range-classified: "
                f"{verdict(labs.get('structured_lab_specimen_method_persisted', False) and labs.get('censored_operator_persisted', False) and labs.get('censored_result_not_range_classified', False))}.",
                "",
            ]
    if "evidence" in sections:
        evidence = sections["evidence"]
        lines += ["## Source evidence to Anatomy Studio", ""]
        if evidence.get("skipped"):
            lines += [f"**BLOCKED:** {evidence['blocker']}", ""]
        else:
            lines += [
                f"- Synthetic source statement and its Lungs link rendered in Document Intelligence: "
                f"{verdict(evidence['source_statement_visible'] and evidence['anatomy_link_visible'])}.",
                f"- Clicking the link opened the Lungs workspace and displayed the exact source span with a schematic-only mapping: "
                f"{verdict(evidence['navigated_to_lungs_studio'] and evidence['source_span_visible_in_anatomy'] and evidence['schematic_mapping_status_visible'] and evidence['schematic_mapping_persisted'])}.",
                f"- Submitted *Needs landmark registration* through the hybrid placement-review UI and re-read the persisted review: "
                f"{verdict(evidence['registration_review_recorded_in_ui'] and evidence['registration_review_persisted'] and evidence['registration_status_not_upgraded'])}. "
                "The review deliberately does not promote the layer to patient registration.",
                "",
            ]
    if "corrections" in sections:
        corrections = sections["corrections"]
        lines += ["## Clinician correction proposal", ""]
        if corrections.get("skipped"):
            lines += [f"**BLOCKED:** {corrections['blocker']}", ""]
        else:
            lines += [
                f"- Opened the synthetic finding's clinician-review controls and submitted a typed removal proposal: "
                f"{verdict(corrections.get('correction_controls_visible', False) and corrections.get('modified_review_notice_visible', False) and corrections.get('proposed_removal_persisted', False))}.",
                f"- The API retained `PROPOSED_NOT_APPLIED`, set the original-output-preserved flag, and left the source statement unchanged: "
                f"{verdict(corrections.get('original_output_preserved_flag', False) and corrections.get('original_statement_unchanged', False))}.",
                f"- The UI separately displayed *Original evidence · preserved* and *Proposed correction · not applied*: "
                f"{verdict(corrections.get('original_preserved_visible_in_ui', False) and corrections.get('proposal_not_applied_visible_in_ui', False))}.",
                "",
            ]
    if "queue" in sections:
        queue = sections["queue"]
        lines += ["## Durable queue evidence", ""]
        if queue.get("skipped"):
            lines += [f"**BLOCKED:** {queue['blocker']}", ""]
        else:
            lines += [
                f"- Upload UI displayed a queued-job transition: {verdict(queue['queued_message_was_visible_in_upload_ui'])}.",
                f"- Case Workspace still displayed persisted analysis job #{queue['analysis_job_id']} after a hard browser reload: "
                f"{verdict(queue['persisted_processing_history_visible_after_reload'])}.",
                f"- Queue record #{queue['queued_job_id']} remained queryable after reload: {verdict(queue['queued_job_api_record_persisted_after_reload'])}; "
                f"status `{queue.get('status_after_reload')}`, execution mode `{queue.get('execution_mode')}`, attempts {queue.get('attempts')}.",
                f"- Scope: {queue['durability_scope']}",
                "",
            ]
    if "imaging" in sections:
        imaging = sections["imaging"]
        expected = imaging.get("expected_model_ids", [])
        missing = imaging.get("missing_model_ids", [])
        unexpected = imaging.get("unexpected_model_ids", [])
        duplicates = imaging.get("duplicate_requested_model_ids", [])
        contract_drift = imaging.get("registry_missing_contract_ids", []) + imaging.get("registry_unexpected_contract_ids", [])
        coverage_ok = bool(expected) and not missing and not unexpected and not duplicates and not contract_drift
        lines += ["## Research models in Medical Imaging", "",
                  f"- Runnable `image_2d` registry contract: {len(expected)} models ({', '.join(f'`{item}`' for item in expected) or 'none'}).",
                  f"- Every model had exactly one explicit `MODEL_ID:MODALITY=image` binding, with no missing, unexpected or duplicate IDs: {verdict(coverage_ok)}. "
                  f"Missing: {', '.join(missing) or 'none'}; unexpected: {', '.join(unexpected) or 'none'}; duplicates: {', '.join(duplicates) or 'none'}.",
                  f"- Seven-workflow regression contract (including Kvasir-SEG and C-NMC) matches the live registry: {verdict(not contract_drift)}.",
                  "",
                  "| Input type | Model | Task | Upload stored (row badge) | Completed in UI | Overlay shapes drawn | Probability rows |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for run in imaging["runs"]:
            if run.get("status"):
                lines.append(f"| {run['input_type']} | `{run.get('requested_model_id') or '—'}` | — | — | {run['status']} | — | — |")
                continue
            stored = "not recorded" if "upload_stored" not in run else f"{verdict(run['upload_stored'])} ({run.get('upload_status_badge') or '—'})"
            lines.append(f"| {run['input_type']} | `{run['model_id']}` | {run['task']} | {stored} | {verdict(run['completed'])} | {run['overlay_shapes']} | "
                         f"{run['probability_rows'] if run['probability_rows'] is not None else '—'} |")
        lines += ["", "Each run required the input-type confirmation checkbox, went through the worker queue (GPU resource), and showed the "
                  "*Research only · not clinically validated* banner with the model's internal held-out evaluation. Detection boxes are "
                  "drawn as an SVG layer in source-pixel coordinates over the original image; classification draws no overlay. "
                  "The C-NMC workflow used its native `.bmp` file through upload, display, applicability confirmation, and inference.", ""]
    if "validation" in sections:
        validation = sections["validation"]
        lines += ["## Validation Center evaluator controls", "",
                  f"- A schema-invalid Clinical NLP upload produced a visible API request ID matching the 422 response header: "
                  f"{verdict(validation.get('request_id_error_displayed', False) and validation.get('request_id_matches_error_response_header', False))}.",
                  f"- Clinical NLP strict-schema controls ran, persisted hash-only artifact provenance and remained exploratory: "
                  f"{verdict(validation.get('clinical_nlp_controls_exercised', False) and validation.get('clinical_nlp_run_persisted', False) and validation.get('clinical_nlp_schema_accepted', False) and validation.get('clinical_nlp_artifacts_hash_only', False) and validation.get('clinical_nlp_remained_exploratory', False))}.",
                  f"- OCR strict-schema controls ran, displayed and persisted `raw_text_persisted=false`, and remained exploratory: "
                  f"{verdict(validation.get('ocr_controls_exercised', False) and validation.get('ocr_run_persisted', False) and validation.get('ocr_schema_accepted', False) and validation.get('ocr_raw_text_not_persisted_visible', False) and validation.get('ocr_raw_text_not_persisted', False) and validation.get('ocr_remained_exploratory', False))}.",
                  "The inputs are de-identified, hand-authored software-contract fixtures. Their numeric scores are deliberately not reproduced here and are not scientific model evidence.",
                  ""]
    if "trained" in sections:
        trained = sections["trained"]
        lines += ["## Registered trained-model reports", "",
                  f"{trained.get('passed', 0)} of {trained.get('total', 0)} registry reports rendered the task-specific evidence view, provenance and applicable evaluation-only/exploratory badges.", ""]
    if "prognosis" in sections:
        prognosis = sections["prognosis"]
        lines += ["## Prognosis Studio", "",
                  f"- Separate route `/prognosis-studio` with no 3D canvas of its own: {verdict(prognosis.get('separate_route_without_3d_canvas', False))}.",
                  f"- Capability panel shows unavailability states before evaluation (not trained / not validated / estimand undefined): "
                  f"{prognosis.get('unavailable_states_before_evaluate', 0)} markers.",
                  f"- *Evaluate* for {prognosis.get('organ', 'the default system')} renders the two scenario panels "
                  f"({prognosis.get('scenario_panels', 0)} scenario headings) with abstention reason codes "
                  f"(`MODEL_NOT_VALIDATED`, `INTERVENTION_NOT_SPECIFIED`, ...): {prognosis['abstention_markers']} markers — "
                  f"{verdict(prognosis['abstention_markers'] > 0)}.",
                  f"- Numeric risk or probability statements: {prognosis['numeric_risk_statements']} — "
                  f"{verdict(prognosis['numeric_risk_statements'] == 0)} (none may appear without a validated model).", ""]
    if walk["console_errors"] or walk["page_errors"] or walk["failed_requests"]:
        lines += ["## Errors recorded", ""]
        lines += [f"- console: {item['url']} — {item['text']}" for item in walk["console_errors"][:20]]
        lines += [f"- page: {item['url']} — {item['text']}" for item in walk["page_errors"][:20]]
        lines += [f"- HTTP {item['status']}: {item['url']}" for item in walk["failed_requests"][:20]]
        lines.append("")
    not_covered = ["Automated pixel-diff visual-regression baselines (screenshots are captured but not compared against a golden image)."]
    if "responsive" not in sections:
        not_covered.append("Responsive layouts at phone width.")
    if "labs" not in sections or sections.get("labs", {}).get("skipped"):
        not_covered.append("Manual lab entry and deduplication through the UI.")
    if "evidence" not in sections or sections.get("evidence", {}).get("skipped"):
        not_covered.append("Source-evidence click-through and the registration-review dialog.")
    if "corrections" not in sections or sections.get("corrections", {}).get("skipped"):
        not_covered.append("Clinician correction proposal UI and original-output preservation.")
    if "queue" not in sections or sections.get("queue", {}).get("skipped"):
        not_covered.append("Persisted queue evidence in the UI.")
    if "imaging" not in sections:
        not_covered.append("Per-model 2-D research inference through Medical Imaging.")
    if "validation" not in sections:
        not_covered.append("Clinical NLP/OCR evaluator controls and request-ID error display.")
    if "trained" not in sections:
        not_covered.append("Registered trained-model report views.")
    not_covered += [
        "A worker-process restart during this browser run; restart persistence remains covered by the backend queue regression test.",
        "Docker images (engine not running).",
    ]
    lines += ["## Not covered by this walkthrough", "", *[f"- {item}" for item in not_covered]]
    target = ROOT / "docs" / "anatomy" / "BROWSER_WALKTHROUGH.md"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
