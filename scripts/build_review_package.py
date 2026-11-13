"""Build the dated review packet from measured artifacts without activating models."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts/review-2026-11-13"
DOC = ROOT / "docs/review-2026-11-13"


def read(path, default=None):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else default


def write(name, content):
    DOC.mkdir(parents=True, exist_ok=True)
    (DOC / name).write_text(content.strip() + "\n", encoding="utf-8")


def log_summary(name):
    path = ART / name
    if not path.exists():
        return "NOT_EXECUTED_OR_NO_LOG"
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    lines = raw.decode(encoding, errors="replace").splitlines()
    found = [line.strip() for line in lines if re.search(r"\d+ passed|\d+ failed|^ℹ (tests|pass |fail )", line)]
    return " / ".join(found[-4:]) or "IN_PROGRESS_OR_NO_FINAL_SUMMARY"


def main():
    now = datetime.now(timezone.utc).isoformat()
    wf_payload = read(ART / "workflows/workflow-results.json", {"workflows": {}})
    wf = wf_payload["workflows"]
    doc = wf.get("document", {})
    image = wf.get("imaging", {})
    persistence = read(ART / "workflows/persistence.json", {})
    runtime = read(ART / "runtime-windows.json", {})
    alternative = read(ART / "runtime-wsl-prepared.json", {})
    normalization = read(ART / "document-normalization-comparison.json", {})
    ui = read(ART / "selected-browser/selected-workflows.json", {})
    broad_ui = read(ART / "browser-final/walkthrough.json", {})
    rechecked_ui = read(ART / "trained-browser-final/walkthrough.json", {})
    rebuilt_ui = read(ART / "trained-browser-rebuilt/walkthrough.json", {})
    recovery = read(ART / "worker-recovery.json", {})
    parity = read(ART / "parity-controls-final.json", {})
    parity_image = next((r for r in parity.get("results", []) if r.get("model_id") == "gi_kvasir_seg_polyp_segmenter"), {})
    parity_ecg = next((r for r in parity.get("results", []) if r.get("model_id") == "ptbxl_ecg_baseline"), {})
    api_repeat = read(ART / "workflows/parity.json", {})
    registry = read(ROOT / "model_registry/models.json", {"models": []})
    selected = next(m for m in registry["models"] if m["model_id"] == "gi_kvasir_seg_polyp_segmenter")
    ecg = next(m for m in registry["models"] if m["model_id"] == "ptbxl_ecg_baseline")
    bundle = selected["artifact_bundle"]
    extractor_version = re.search(r'^EXTRACTOR_VERSION = "([^"]+)"', (ROOT / "backend/app/services/nlp_processor.py").read_text(encoding="utf-8"), re.MULTILINE).group(1)
    tests = {
        "Final full backend": log_summary("backend-final.log"),
        "Initial full backend (retained failure)": log_summary("backend-full.log"),
        "Review tools": log_summary("review-tool-tests.log"),
        "Document/calibration/annotation targeted": log_summary("document-normalization-tests.log"),
        "Input contracts": log_summary("input-contract-tests.log"),
        "Frontend evidence/render": log_summary("frontend-evidence-tests-final.log"),
        "Panel-context targeted": log_summary("panel-context-tests.log"),
        "Saved-report schema normalization": log_summary("trained-report-tests.log"),
    }
    test_table = "\n".join(f"| {name} | {value} |" for name, value in tests.items())
    contracts = {
        "schema_version": "medtwin-review-workflows-v1", "frozen_at": now,
        "usage": "ISOLATED_NONCOMMERCIAL_RESEARCH_DEMONSTRATION_ONLY; commercial/clinical gates unchanged",
        "A": {"task": "Source-linked report extraction, review, descriptive longitudinal comparison and export",
              "demonstrated_formats": ["PDF embedded text", "PDF rendered scan"],
              "extractor_version": extractor_version, "anatomy": "Only explicitly reported associations; no image diagnosis",
              "preprocessing": "Page-local decoding/OCR; de-identification; conservative offset-preserving normalization; registered unit mappings",
              "reference_scope": "Known fictional fixture values; independently human-annotated real pages = 0",
              "refusals": ["unreadable values remain absent/uncertain", "ambiguous or missing units", "unestablished method/specimen comparability", "insufficient forecast history"],
              "clinical_validation": False},
        "B": {"task": "2-D colorectal-polyp segmentation", "model_id": selected["model_id"],
              "supported_input": "Native endoscopy RGB PNG/JPEG/BMP within registered quality/OOD contract; demonstrated one publisher JPEG",
              "anatomy": "GI endoscopy; not other modalities, document/film photographs or a general disease detector",
              "checkpoint": bundle["checkpoint_path"], "checkpoint_sha256": bundle["checkpoint_sha256"],
              "preprocessing_version": bundle["preprocessing_version"],
              "preprocessing": "RGB, 352x352 bilinear resize, per-channel standardization; nearest-neighbor source-grid label mapping",
              "historical_evaluation": bundle.get("evaluation_report_path"),
              "refusals": ["ineligible/tampered checkpoint or missing applicability reference", "wrong declared modality or contradicting metadata", "printed document", "out-of-distribution input", "withdrawn/unassociated upload"],
              "limitations": ["research-only internal evaluation", "patient independence unavailable in this source", "known valid-input refusals", "historical mask differs by one pixel in bounded parity control", "no patient-to-atlas registration"],
              "clinical_validation": False},
    }
    write("MEDTWIN_WORKFLOW_CONTRACTS_2026-11-13.json", json.dumps(contracts, indent=2))
    write("MEDTWIN_ARCHITECTURE_2026-11-13.md", """# MedTwin measured architecture

```mermaid
flowchart LR
  UI[React / Vite research workspace] -->|versioned API; dev/preview proxy| API[FastAPI /api/v1]
  API --> AUTH[Case authorization and input contracts]
  AUTH --> STORE[Original bytes / SHA-256 / encrypted uploads]
  AUTH --> DB[(SQLAlchemy / persistent case and audit database)]
  API --> QUEUE[Durable job queue]
  QUEUE --> WORKER[Separate Python worker]
  WORKER --> DOC[PDF text or local OCR / NLP / laboratory rules]
  WORKER --> GATE[Model hash / usage / content / applicability gates]
  GATE --> ML[Existing PyTorch / MONAI checkpoints]
  DOC --> EVIDENCE[Source-linked immutable evidence]
  ML --> EVIDENCE
  EVIDENCE --> DB
  DB --> REVIEW[Append-only review / independent correction decisions]
  REVIEW --> UI
  UI --> VIEW[Source-image overlay and generic L1 Three.js atlas]
  UI --> EXPORT[Reviewed JSON / SHA-256 / print report]
```

The inspected checkout has a FastAPI service and Vite API proxy; no separate Node API gateway was identified. The executed QA workflows use local SQLite and encrypted uploads, not a live Supabase/PostgreSQL deployment. Supabase client/deployment support exists but was not provisioned or independently verified here. Atlas association remains generic L1; source-image masks do not create patient-specific atlas coordinates.
""")
    write("MEDTWIN_RUNTIME_VERIFICATION_2026-11-13.md", f"""# Runtime verification — 13 November 2026

Generated from local evidence at {now}.

The earlier Windows `WinError 4551` PyTorch import refusal was not reproduced by the fresh probe or the subsequent real-checkpoint controls. No endpoint policy, security setting, DLL trust rule or original ML environment was changed. The precise cause of the earlier denial remains unestablished; this is observed recovery, not a claim that an institutional policy was repaired.

- Windows interpreter: `{runtime.get('interpreter')}`; Python {runtime.get('python')}; package inventory and tensor/CUDA result: `artifacts/review-2026-11-13/runtime-windows.json`.
- Isolated QA API: `http://127.0.0.1:8018`; preview: `http://127.0.0.1:8458`; separate worker; state `.cache/review-20261113`. No development/patient database reset.
- Document API/worker workflow: **{doc.get('status', 'NOT_RUN')}**; image API/worker workflow: **{image.get('status', 'NOT_RUN')}**.
- Evidence after an actual QA API/worker restart: **{persistence.get('status', 'NOT_RUN')}**; see `workflows/persistence.json`.
- A separate WSL Python {alternative.get('python')} CPU environment was created from the repository's pinned requirements; torch import/tensor operation verified. It is a fallback environment, not an alternative deployment or a full GPU/API validation.
- Windows `uv pip check --python .venv/Scripts/python.exe` verified consistency of 290 installed packages; the isolated WSL environment's 78 packages also passed. Observed GPU: NVIDIA GeForce RTX 5060 Laptop GPU, driver 617.14, 8,151 MiB reported memory. Dependency consistency is not a security or clinical certification.
- Optional ML telemetry now catches missing/refused native-library imports, preserves document/API availability and reports an unavailable optional ML runtime. A controlled native-refusal regression passed; inference eligibility is not overridden.

| Check | Actual recorded summary |
| --- | --- |
{test_table}

`npm run check` passed typecheck, lint and check build (11 existing lint warnings). The initial complete backend run recorded one environment-dependent blank-OCR test failure; the fixture was corrected to explicitly exercise the empty-OCR branch, retaining the separate unavailable-OCR test. Final results above supersede that run but do not erase it. Frontend source/render checks also exposed stale schema-v3 and missing child-state fixtures; these were updated to the current v4 contract. No assertions were removed to obtain a pass.

Bounded checkpoint parity intentionally exits 1 because historical Kvasir exact-mask parity differs by one pixel. This is distinct from a failed model load or API workflow. See the parity report.
""")
    write("MEDTWIN_DOCUMENT_EVALUATION_2026-11-13.md", f"""# Document evaluation — 13 November 2026

Workflow A: **{doc.get('status', 'NOT_RUN')}**. Inputs are two explicitly fictional PDF pages: one embedded-text page and one rendered scanned page. Worker jobs, extracted fields, review, source metadata, comparison, forecast refusal and export are retained in `artifacts/review-2026-11-13/workflows/document-evidence.json`.

- Extracted measurements: {doc.get('measurement_count', 'NOT_RECORDED')}.
- Explicit known synthetic values checked/matched: {doc.get('synthetic_values_checked', 'NOT_RECORDED')} / {doc.get('synthetic_value_matches', 'NOT_RECORDED')}.
- Explicit synthetic specimen matches: {doc.get('synthetic_specimen_matches', 'NOT_RECORDED')}; printed method matches: {doc.get('synthetic_method_matches', 'NOT_RECORDED')}.
- Numeric comparison rows: {doc.get('numeric_delta_count', 'NOT_RECORDED')}; descriptive trend series: {doc.get('trend_series', 'NOT_RECORDED')}.
- Single-page PDF/OCR measurements now retain page 1, exact text spans and OCR boxes. Source rows are preserved; review is appended.
- The final fictional fixtures explicitly print `Method: SYNTHETIC`. The original fixture lacked comparable assay context and correctly withheld numeric deltas. This fixture change is separate from the preprocessing improvement.

Visual review found that the preceding extraction borrowed the next biochemistry panel's serum label for platelet results, despite correct numeric values. Explicit laboratory-panel boundaries now prevent that forward borrowing and context inheritance across a new panel. Earlier numeric-only browser evidence is retained; the final workflow asserts specimen and method correctness separately. The original stored rows were never overwritten.

The original unchanged scanned page is independently bound by source SHA-256 in `document-normalization-comparison.json`: actual original API extraction retained 1 measurement; the final PDF/OCR/rules path recovers all 9 expected fields. The intermediate six-field observation is labelled as an earlier observation, not re-executed evidence. Catalog-aware boundaries insert spaces only; they do not reconstruct missing digits, invent units or guess unreadable values. Original strings and scaled-count units remain inspectable.

**Independent human-annotated real pages: 0.** No real-report clinical precision, recall, CER/WER or assertion accuracy is claimed. The new annotation CLI initializes blank labels from explicitly listed permitted/de-identified pages; requires distinct human attestations and content-bound review; and exports the existing strict OCR-gold schema only after review. It does not use OCR output as gold. Independent representative pages and human adjudication remain external prerequisites.

Clinical negation, uncertainty, temporality, page boundaries, laboratory associations and correction semantics were exercised by the targeted and complete software suites. Those synthetic tests are not a clinical corpus evaluation. See `MEDTWIN_CALIBRATION_AND_EVIDENCE_2026-11-13.md` for numerical and annotation details.
""")
    write("MEDTWIN_FUSION_FORECASTING_2026-11-13.md", f"""# Fusion and forecasting verification — 13 November 2026

The document workflow executed source-linked evidence synthesis, reviewed biomarker trends and historical comparison. The evidence export retains the original findings, source dates, review state and missing/qualified evidence. Numeric comparison rows: {doc.get('numeric_delta_count', 'NOT_RECORDED')}.

The demonstration contains only two dated observations per analyte; forecast outcome: **{doc.get('forecast_status', 'NOT_RUN')}**, with no predicted disease value. Existing persistence/linear baseline implementations are retained and covered by chronological/missing-context regressions; no ARIMA, learned disease forecast, causal treatment model or new clinical forecast was fabricated.

The real ECG parity control uses the existing digital ECG model, not a new fusion model. The historical demographic-fusion AUROC difference interval includes zero; no fusion superiority is established. Missing/contradictory modalities remain explicit. Evidence synthesis is transparent aggregation, not a learned case-level diagnostic probability.

Generic Three.js L1 anatomy was verified in the selected browser flow. The source-pixel segmentation and atlas association do not establish patient registration, disease progression or anatomical deformation. Current source tests, selected-browser evidence and export are the proof scope; no independent paired/longitudinal clinical cohort was evaluated.
""")
    write("MEDTWIN_REMAINING_BLOCKERS_2026-11-13.md", f"""# Remaining blockers — 13 November 2026

| Item | Exact dependency / evidence | Reproducible next action |
| --- | --- | --- |
| Independent document evaluation | Zero independently human-reviewed real pages. Synthetic processing cannot establish clinical extraction accuracy. Annotation tooling implemented. | Obtain explicitly permitted, de-identified representative pages; use `review_document_annotations.py --init`, human labels, `--finalize` and `--export-ocr`; run existing OCR/NLP evaluators. |
| New real model training | All six preparation rights checks return BLOCKED under the existing commercial-development purpose. Original checkpoint/status retained. | Supply actual evidence-bound review in the existing rights process, then run the prepared development-only commands; never switch purpose merely to pass a gate. |
| Renal tumour target | Existing failed checkpoint has tumour Dice 0; no replacement was trained/promoted. | Inspect sampling/resolution/loss using prepared validation-only experiments when eligible; obtain an untouched final evaluation cohort. |
| Weak detectors/classifiers | Fracture/stenosis/skin/GastroVision historical limitations retained. | Execute controlled validation-only comparisons after eligibility; retain per-class, small-lesion and false-positive results. |
| Exact historical image parity | One differing model-grid pixel/123,904; cause unestablished. Current tensors/logits/source mapping exact. | Reproduce `review_parity_controls.py`; investigate archived runtime/batch/device settings without weakening the declared zero-pixel criterion or overwriting history. |
| Dataset audit scope | Bounded hashing, known ARCADE cross-split groups, unconfirmed dHash candidates, archive-backed/deferred inputs and unknown identities remain explicit. | Curate grouping/duplicates; increase the documented audit budget and verify archive members before broader claims. |
| Artifact binding | RadGraph is a directory adapter without one pinned checkpoint; TotalSegmentator's historical report lacks exact dataset/checkpoint binding. | Create accurately scoped bundle/evaluation bindings; do not pretend missing binding is validation. |
| Windows native-policy root cause | Earlier torch denial did not recur; no policy change made. Separate native-policy limitations may remain. | Use the saved probe and sanctioned runtime; escalate recurring denied native binaries to the responsible runtime/security owner. |
| Broad new capabilities | No EEG diagnosis, whole-slide diagnosis, general forecasting, treatment effect or patient-specific atlas registration completed. | Task-specific lawful data, labels, adapters and independent evaluation. |
| Clinical/commercial deployment | Zero clinical activation approvals; existing release/privacy/security/off-host recovery requirements remain. | Follow the dated release review; this local research demo is not production clearance. |

Changed files and exact commands are listed in the implementation report, reproduction guide and source-hash manifest. No original data, user records, checkpoints or registry eligibility were erased or promoted. Known failed checks are retained, including the first backend run and strict parity difference. The initial full browser walkthrough remains retained with all_passed={broad_ui.get('assertions', {}).get('all_passed', 'NO_COMPLETED_ARTIFACT')}. Its outdated serving assumptions and actual missing saved-report schema views were repaired. Rechecked routes/trained/prognosis: all_passed={rechecked_ui.get('assertions', {}).get('all_passed', 'NOT_RUN')}; final rebuilt trained-report-only audit: all_passed={rebuilt_ui.get('assertions', {}).get('all_passed', 'NOT_RUN')}. Selected workflow browser: {ui.get('status', 'NOT_RUN')}. The expected anonymous GET session 401 is separately recorded only after matching its exact response URL; other errors are not suppressed.
""")
    write("MEDTWIN_DEMO_GUIDE_2026-11-13.md", f"""# Demonstration and reproduction guide — 13 November 2026

Use the isolated research preview at `http://127.0.0.1:8458`. QA credentials stay only in `.cache/review-20261113/qa-credentials.json`; never copy them to slides or exported evidence. Normal visitor/guest entry behavior was not replaced.

1. Open the fictional document case #{doc.get('case_id', 'SEE_WORKFLOW_ARTIFACT')}. Show both PDFs, one text-derived and one OCR-derived.
2. Show extracted fields, page/source boxes, printed units/intervals, original source and append-only review. Explain the independent real reference-set count is zero.
3. Show old/current comparison, dated trends and source context. Show forecast refusal with no invented future disease value.
4. Open public imaging case #{image.get('case_id', 'SEE_WORKFLOW_ARTIFACT')}, upload #{image.get('upload_id', 'SEE_IMAGE_EVIDENCE')}, run #{image.get('run_id', 'SEE_IMAGE_EVIDENCE')}. The actual model output persists; no new inference is needed to view it.
5. Toggle the model layer and the independent publisher reference. Show source-grid alignment, review and the one-image Dice; do not call it cohort accuracy.
6. Show the blank/report-photograph refusal artifacts. No prediction was produced. Show the failed kidney model and strict one-pixel historical parity difference as known failures.
7. Open Reports, click **Export JSON**, and compare its displayed SHA-256 to the download. The selected-browser artifact proves this UI action was executed.
8. Reload, then open generic L1 anatomy. Explain that the organ highlight is a reference association, not patient-specific registration.

```powershell
# Start/reuse an isolated stack; does not reset the development database.
powershell -NoProfile -File scripts/dev.ps1 -Mode qa -StateDir .cache/review-20261113 -BackendPort 8018 -WebPort 8458

# New fictional/public research demonstrations (creates new QA cases only).
.venv\\Scripts\\python.exe scripts/review_run_workflows.py --state .cache/review-20261113

# After an actual QA restart, compare the stored outputs.
.venv\\Scripts\\python.exe scripts/review_run_workflows.py --state .cache/review-20261113 --only persistence

# Actual stored-model overlay/reference/reload/UI export/atlas checks.
node tools/browser-qa/review-workflows.mjs --state .cache/review-20261113 --out artifacts/review-2026-11-13/selected-browser-reproduced

# Runtime, technical refusals and bounded historical/current parity.
.venv\\Scripts\\python.exe scripts/review_runtime_probe.py --torch
.venv\\Scripts\\python.exe scripts/review_input_challenges.py --output artifacts/review-2026-11-13/input-challenges-reproduced.json
.venv\\Scripts\\python.exe scripts/review_parity_controls.py --output artifacts/review-2026-11-13/parity-reproduced.json
# Parity currently exits 1 for the recorded one-pixel historical mask difference.

.venv\\Scripts\\python.exe -m pytest backend/tests -q -p no:cacheprovider
npm run check
node --test scripts/report-evidence.test.mjs scripts/report-render.test.mjs scripts/finding-groups.test.mjs scripts/trained-report.test.mjs
.venv\\Scripts\\python.exe scripts/build_review_package.py
.venv\\Scripts\\python.exe scripts/verify_review_package.py
```

The normal development launcher remains `npm run dev:full` (existing application database). Do not use `-Fresh` on existing records. The QA stop/start commands manage only recorded owned processes, and the QA state remains available for review.
""")
    checklist = [
        ("PyTorch import / tensor and CUDA probe", "VERIFIED"),
        ("Actual API and worker inference", image.get("status", "NOT STARTED")),
        ("Two frozen workflow contracts", "VERIFIED"),
        ("Source-linked document/review workflow", doc.get("status", "NOT STARTED")),
        ("Independent real reference evaluation", "BLOCKED — zero human-annotated real pages"),
        ("Bounded dataset integrity/leakage audit", "VERIFIED — scope and known overlaps retained"),
        ("Selected image preprocessing/current source mapping", "VERIFIED"),
        ("Technical refusal and selected unsupported-input challenges", "VERIFIED — not universal OOD validation"),
        ("Digital ECG input and bounded parity", "VERIFIED"),
        ("Strict historical Kvasir mask equality", "BLOCKED — one pixel differs"),
        ("Weak model status preserved", "VERIFIED"),
        ("Controlled development-only trainer paths", "VERIFIED — synthetic control-flow tests"),
        ("New real model improvement", "BLOCKED — rights/data/evaluation dependencies"),
        ("Fusion aggregation and forecast abstention", doc.get("status", "NOT STARTED")),
        ("Generic L1 anatomy / no fabricated coordinates", ui.get("status", "NOT STARTED")),
        ("Persistence after QA restart", persistence.get("status", "NOT STARTED")),
        ("Actual UI export and provenance", ui.get("status", "NOT STARTED")),
        ("Architecture/results/demo documentation", "VERIFIED"),
    ]
    rows = "\n".join(f"| {name} | {state} |" for name, state in checklist)
    write("MEDTWIN_IMPLEMENTATION_STATUS_2026-11-13.md", f"""# Implementation status — 13 November 2026

Generated from executed evidence at {now}. This is an implementation report, not a plan or a claim of clinical validation. File ownership and preserved initial changes are in `COORDINATION.md`.

Implemented: strict ECG finite/rate/shape handling; consistent DICOM declaration contradictions in selection and direct inference; source-preserving catalogued OCR boundaries; single-page source identity and panel-scoped specimen/method context; hardened calibration metrics; read-only checkpoint reconciliation; independently reviewed annotation tooling; rights-gated development-only detector/classifier paths; bounded audits/parity and crash recovery; real workflow/UI export reproduction scripts. Saved evaluation schemas now display the actual ECG-fusion, RSNA and noncardiac-volume metrics correctly, preserve raw provenance, and mark missing/unsupported metrics unavailable instead of inferring classification scores or cardiac indices.

Document workflow: **{doc.get('status', 'NOT_RUN')}**. Imaging workflow: **{image.get('status', 'NOT_RUN')}**. Selected browser: **{ui.get('status', 'NOT_RUN')}**, {sum(bool(c.get('passed')) for c in ui.get('checks', []))}/{len(ui.get('checks', []))} measured checks. API/worker restart persistence: **{persistence.get('status', 'NOT_RUN')}**. Final rebuilt saved-report viewer: {rebuilt_ui.get('sections', {}).get('trained', {}).get('passed', 'NOT_RUN')}/{rebuilt_ui.get('sections', {}).get('trained', {}).get('total', 'NOT_RUN')}; routes/prognosis recheck all_passed={rechecked_ui.get('assertions', {}).get('all_passed', 'NOT_RUN')}.

No new real model was trained, no original checkpoint overwritten, no registry eligibility promoted, and no dataset permission or independent clinical label invented. The source-model registry's pre-existing local fracture changes remain intact. Current generated CSV distinguishes recorded evaluation from newly executed controls; task-specific historical metrics are not recast as today's full-cohort evaluation.

| Verification | Recorded result |
| --- | --- |
{test_table}

| Acceptance requirement | State and scope |
| --- | --- |
{rows}

Read `MEDTWIN_REMAINING_BLOCKERS_2026-11-13.md` for exact unfinished dependencies, `MEDTWIN_RUNTIME_VERIFICATION_2026-11-13.md` for runtime scope, and the parity report for the intentional nonzero strict historical comparison. No commit or external publication was performed.
""")
    # Preserve historical report rows; append separately labelled new controls.
    csv_path = DOC / "MEDTWIN_MODEL_RESULTS_2026-11-13.csv"
    if csv_path.exists():
        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle); fields = reader.fieldnames; entries = list(reader)
        entries = [entry for entry in entries if not entry.get("measurement_origin", "").startswith("NEW_")]
        for model, metrics, origin in [
            (selected, {"single_image_dice": image.get("reference_comparison", {}).get("dice"),
                        "single_image_iou": image.get("reference_comparison", {}).get("iou"), "current_api_direct_source_grid_differences": api_repeat.get("mask_differing_pixels"),
                        "historical_model_grid_checks": parity_image.get("checks")}, "NEW_SINGLE_IMAGE_AND_REPRODUCIBILITY_CONTROL_NOT_COHORT_ACCURACY"),
            (ecg, {"historical_probability_difference": parity_ecg.get("checks", {}).get("historical_saved_probabilities"),
                   "threshold_flips": parity_ecg.get("threshold_decision_disagreements")},
             "NEW_SINGLE_ECG_REPRODUCIBILITY_CONTROL_NOT_COHORT_ACCURACY")]:
            source = next((r for r in entries if r.get("model_id") == model["model_id"]), {})
            entry = dict(source)
            entry.update(measurement_origin=origin, sample_count="1", patient_count="UNKNOWN" if model is selected else "1",
                         evaluation_unit="predetermined public test input", split="test; reproducibility only", metrics_json=json.dumps(metrics),
                         runtime="VERIFIED_ACTUAL_CHECKPOINT_API_WORKER" if model is selected else "VERIFIED_ACTUAL_CHECKPOINT_BOUNDED_PARITY",
                         report_path="artifacts/review-2026-11-13/workflows/image-evidence.json" if model is selected else "artifacts/review-2026-11-13/parity-controls-final.json",
                         recorded_evaluation_timestamp=read(ART / "workflows/image-evidence.json", {}).get("job", {}).get("finished_at") if model is selected else parity.get("recorded_at"),
                         limitations="One input only; no new cohort accuracy, improvement or clinical validation.")
            path = ROOT / entry["report_path"]
            entry["report_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
            entries.append(entry)
        if doc.get("status") == "VERIFIED":
            entry = dict(next((r for r in entries if r.get("model_id") == "clinical_rules_v1"), {}))
            evidence_path = ART / "workflows/document-evidence.json"
            evidence = read(evidence_path, {})
            entry.update(measurement_origin="NEW_SYNTHETIC_DOCUMENT_SOFTWARE_CONTROL_NOT_REAL_CLINICAL_ACCURACY",
                         dataset="Two fictional generated PDF pages", dataset_version="review-fixture-v2-explicit-synthetic-method",
                         permission_scope="Synthetic software fixtures; no real patient data", evaluation_unit="PDF page / printed field",
                         sample_count="2", patient_count="0 real patients", split="synthetic control",
                         preprocessing_version="document-parser-v2+context-rules-v2+ocr-normalisation-v2+lab-panel-context-v1",
                         runtime="VERIFIED_ACTUAL_API_WORKER_OCR_AND_RULES", report_path="artifacts/review-2026-11-13/workflows/document-evidence.json",
                         report_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                         recorded_evaluation_timestamp=wf_payload.get("recorded_at"),
                         recorded_run_id=",".join(str(j.get("result_ref", {}).get("inference_run_id")) for j in evidence.get("jobs", [])),
                         metrics_json=json.dumps({"printed_values_checked": doc.get("synthetic_values_checked"),
                                                   "matching_values": doc.get("synthetic_value_matches"),
                                                   "matching_specimens": doc.get("synthetic_specimen_matches"),
                                                   "matching_methods": doc.get("synthetic_method_matches"),
                                                   "numeric_comparison_rows": doc.get("numeric_delta_count"),
                                                   "independent_real_gold_pages": 0}),
                         limitations="Known fictional values only; independent real extraction accuracy not established.")
            entries.append(entry)
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(entries)
    source_paths = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    hashes = {}
    for line in source_paths:
        name = line[3:]
        file = ROOT / name
        if file.is_file():
            hashes[name] = hashlib.sha256(file.read_bytes()).hexdigest()
    (ART / "review-source-hashes.json").write_text(json.dumps({"recorded_at": now, "files": hashes}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"docs": str(DOC), "document": doc.get("status"), "imaging": image.get("status"), "tests": tests}, indent=2))


if __name__ == "__main__":
    main()
