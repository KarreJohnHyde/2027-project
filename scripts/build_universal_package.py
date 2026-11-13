"""Build the dated source/evidence manifest and requirement traceability.

This packages existing measured evidence; it does not create evaluation results.
"""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/universal"
OUT = ROOT / "artifacts/universal-2026-11-13"
PRIOR = "artifacts/review-2026-11-13"

# A broad requirement remains partial whenever an explicitly requested scientific
# or operational subrequirement lacks its prerequisite or evaluation evidence.
ROWS = [
 ("U-001", "All25-system anatomy/condition catalogue", "catalogue", "P1", "Catalogue", "PARTIAL", "backend/app/services/universal_catalogue.py", "backend/tests/test_universal_catalogue.py", "catalogue-verification.json", "4849 entries and25 systems; official exhaustive licensed disease codes not supplied"),
 ("U-002", "Synchronized case command center", "workspace", "P1", "Root", "PARTIAL", "src/pages/UniversalWorkspacePage.tsx;src/state/universalSelection.ts", "tools/browser-qa/universal-workflows.mjs", "browser/results.json", "Source/finding/history/shared state implemented; full atlas/source registration and all cross-view annotation modes unavailable"),
 ("U-003", "Native MPR/source3D/reviewer editing", "imaging", "P1", "Imaging", "PARTIAL", "src/components/UniversalImagingWorkbench.tsx;backend/app/services/universal_geometry.py", "backend/tests/test_universal_geometry.py;scripts/universal-geometry.test.mjs", "imaging-browser/proof.json", "Three index planes and actual3D/source mask/edit restore verified;4D channel selector and resampled anatomical-plane MPR unavailable"),
 ("U-004", "Actual overlays and applicability refusals", "model-routing", "P1", "Root/Imaging", "VERIFIED", "backend/app/services/model_router.py;src/components/ResearchModelPanel.tsx", "backend/tests/test_review_input_contracts.py", f"{PRIOR}/workflows/workflow-results.json", "Verified demonstrated checkpoint scopes only; universal image diagnosis is unavailable"),
 ("U-005", "Document OCR/NLP/source verification/history/export", "documents", "P0", "Root", "VERIFIED", "backend/app/services/nlp_processor.py;backend/app/services/ocr_text.py", "backend/tests/test_review_panel_context.py;tools/browser-qa/review-workflows.mjs", f"{PRIOR}/workflows/workflow-results.json", "Verified synthetic software controls; real independent accuracy addressed separately in U014"),
 ("U-006", "Strict digital ECG contract", "signals", "P1", "Root", "VERIFIED", "backend/app/services/ecg_inference.py", "backend/tests/test_review_input_contracts.py", f"{PRIOR}/parity-controls-final.json", "100Hz/10s/12-lead contract only; no EEG or photographed-ECG diagnosis"),
 ("U-007", "Model Arena and checkpoint-specific evaluations", "arena", "P1", "Root", "PARTIAL", "backend/app/services/universal_arena.py;src/pages/ModelArenaPage.tsx", "backend/tests/test_universal_arena.py;tools/browser-qa/universal-workflows.mjs", "integration/arena-comparison.json", "Actual saved metrics/bindings/matched cohorts verified; no new paired superiority study or fabricated missing curves"),
 ("U-008", "Evidence graph/conflicts/missingness/fusion", "intelligence", "P1", "Intelligence", "PARTIAL", "backend/app/services/universal_evidence.py", "backend/tests/test_universal_intelligence.py", "integration/fictional-conflict-graph.json", "Graph and seeded conflict controls verified; broad learned fusion lacks genuinely paired independent outcomes"),
 ("U-009", "Timepoints/comparable biomarkers/research forecasts", "history", "P1", "Root", "PARTIAL", "src/pages/UniversalWorkspacePage.tsx;backend/app/services/biomarker_trends.py", "tools/browser-qa/universal-workflows.mjs", f"{PRIOR}/workflows/workflow-results.json", "Observed changes verified; no general disease forecast or registered image subtraction without suitable data/transform"),
 ("U-010", "Restricted cited research copilot", "copilot", "P1", "Intelligence/Root", "VERIFIED", "backend/app/services/universal_copilot.py", "backend/tests/test_universal_intelligence.py", "integration/results.json;browser/results.json", "Local deterministic read-only tools; no autonomous clinical interpretation or cloud LLM"),
 ("U-011", "Dynamic evidence workspace for every listed family", "workspace/catalogue", "P1", "Catalogue/Root", "VERIFIED", "src/pages/UniversalWorkspacePage.tsx;backend/app/data/universal_catalogue.json", "tools/browser-qa/universal-workflows.mjs", "integration/system-coverage.json", "All25 browsable; absent dedicated assets/models explicitly remain unavailable"),
 ("U-012", "Combined/document/scan intake and provenance", "intake", "P1", "Root", "VERIFIED", "src/pages/UploadCenterPage.tsx", "tools/browser-qa/universal-workflows.mjs", "browser/results.json", "Modes declare batch context; actual content/server/model checks remain independent"),
 ("U-013", "Data rights/patient splits/duplicate audit", "data", "P0", "Root", "PARTIAL", "scripts/medtwin_dataset_audit.py", "scripts/tests/test_medtwin_dataset_audit.py", f"{PRIOR}/data-audit.json", "Known cross-split groups/unknown identities/archive budgets remain explicitly unresolved"),
 ("U-014", "Independent real report evaluation", "evaluation", "P0", "Root", "BLOCKED", "scripts/review_document_annotations.py", "scripts/tests/test_review_document_annotations.py", "docs/review-2026-11-13/MEDTWIN_DOCUMENT_EVALUATION_2026-11-13.md", "0 independently human-reviewed permissible real pages; tooling cannot replace an independent human reference"),
 ("U-015", "Trainer/upload parity and numerical metrics", "evaluation", "P1", "Root", "PARTIAL", "scripts/review_parity_controls.py;backend/app/services/calibration_service.py", "backend/tests/test_calibration_boundaries.py", f"{PRIOR}/parity-controls-final.json", "Current tensors/logits/source mapping checked; historical Kvasir one-pixel mismatch retained; not every model independently reproduced"),
 ("U-016", "Controlled weak-model development", "training", "P1", "Root", "BLOCKED", "scripts/prepare_review_experiments.py;ml_training/classify.py;ml_training/detect.py", "scripts/tests/test_review_model_evidence.py", f"{PRIOR}/data-experiments.json", "Existing six real-training rights checks blocked; no replacement weights or accuracy gain declared"),
 ("U-017", "Source-space versus L1/L2/L3 registration", "geometry", "P1", "Imaging", "PARTIAL", "backend/app/services/universal_geometry.py", "backend/tests/test_universal_geometry.py", "native-workflows/cardiac-native-evidence.json", "Source geometry/gates verified; no expert landmarks/held-out TRE or validated patient-to-atlas transform"),
 ("U-018", "Data preservation/isolation/audits/export", "security", "P0", "Root", "VERIFIED", "backend/app/services/auth.py;src/pages/UploadCenterPage.tsx", "backend/tests/test_auth_and_access.py;backend/tests/test_release_privacy.py", "integration/results.json;privacy-followup.log", "Verified local research engineering scope; history publication block remains separate"),
 ("U-019", "Approved runtime and actual worker inference", "runtime", "P0", "Root", "VERIFIED", "scripts/dev.ps1;scripts/universal_verify_workflows.py", "scripts/universal_verify_integration.py", "native-workflows/native-workflows.json", "Actual native Windows worker inference; earlier DLL denial did not recur and no policy bypass occurred"),
 ("U-020", "Responsive/accessibility/performance polish", "frontend", "P1", "Root/Imaging", "PARTIAL", "src/pages/UniversalWorkspacePage.tsx;src/pages/ModelArenaPage.tsx", "tools/browser-qa/universal-workflows.mjs;tools/browser-qa/universal-imaging.mjs", "browser/results.json;imaging-browser/proof.json", "Desktop/mobile/keyboard-labelled interactions checked; no exhaustive assistive-technology or maximum-volume performance study"),
 ("U-021", "Demo matrix/results/presentation artifacts", "qa", "P0", "Root", "PARTIAL", "docs/universal/DEMONSTRATION_MATRIX.md", "scripts/universal_verify_integration.py", "integration/results.json;native-workflows/publisher-reference-comparisons.json", "15 scenarios mapped to actual new/prior proofs; general scientific validation remains bounded"),
 ("U-022", "Reconcile rights/status/PHI/clinical release", "release", "P0", "Root", "PARTIAL", "docs/security/PHI_RELEASE_BLOCKER.md;docs/universal/CLINICAL_RELEASE_BLOCKERS.md", "backend/tests/test_release_privacy.py", "catalogue-verification.json", "No clinical activation; historical sensitive Git objects remain a publication blocker"),
 ("U-023", "Versioned environment/container/recovery", "operations", "P0", "Root", "PARTIAL", "scripts/dev.ps1;docker-compose.yml", "scripts/tests/test_review_worker_recovery.py", "integration/results.json;container-probe.txt", "Native persistence/recovery verified; Docker daemon unavailable, compose secret unset, off-host encrypted restore not executed"),
 ("U-024", "Separate fictional/public/independent/historical evidence", "provenance", "P0", "Root", "VERIFIED", "docs/universal/SOURCE_SCOPE.md;docs/universal/IMPLEMENTATION_STATUS.md", "scripts/universal_verify_integration.py", "native-workflows/publisher-reference-comparisons.json", "Public publisher references and synthetic controls are never represented as independent clinical validation"),
]


def build_legacy():
    DOC.mkdir(exist_ok=True)
    with (DOC / "requirements.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "feature", "component", "priority", "owner", "status", "implementation_paths", "test_paths", "evidence_paths", "blocker"])
        for row in ROWS:
            fixed = list(row)
            fixed[8] = ";".join(p if p.startswith(("artifacts/", "docs/")) else f"artifacts/universal-2026-11-13/{p}" for p in row[8].split(";"))
            writer.writerow(fixed)
    source_paths = [ROOT / "src/pages/UniversalWorkspacePage.tsx", ROOT / "src/pages/ModelArenaPage.tsx", ROOT / "src/pages/UploadCenterPage.tsx", ROOT / "src/state/universalSelection.ts", ROOT / "backend/app/main.py", ROOT / "backend/app/services/effective_evidence.py", ROOT / "scripts/privacy_allowlist.json"]
    source_paths += [ROOT / p for p in ("README.md", "src/App.tsx", "src/navigation.ts", "src/services/universal.ts", "src/lib/universalGeometry.ts", "src/components/UniversalImagingWorkbench.tsx", "src/pages/ValidationCenterPage.tsx", "backend/app/data/universal_catalogue.json", "scripts/build_universal_package.py", "scripts/universal-geometry.test.mjs")]
    for directory, pattern in [(ROOT / "backend/app", "universal*.py"), (ROOT / "backend/tests", "test_universal*.py"), (ROOT / "docs/universal", "*"), (OUT, "*")]:
        source_paths += [p for p in directory.rglob(pattern) if p.is_file() and p.name not in {"run-manifest.json", "package-verification.json"} and "__pycache__" not in p.parts]
    source_paths += list((ROOT / "scripts").glob("universal*.py")) + list((ROOT / "tools/browser-qa").glob("universal*.mjs"))
    registry_hash = hashlib.sha256((ROOT / "model_registry/models.json").read_bytes()).hexdigest()
    expected = "b56979e0591788b1d588fa11c590e0378a1f98db1114612df702f816aa5b65b7"
    if registry_hash != expected:
        raise ValueError("Original user registry changed: inspect before packaging")
    for row in ROWS:
        for path in (*row[6].split(";"), *row[7].split(";")):
            if not (ROOT / path).exists():
                raise ValueError(f"Traceability references a missing implementation/test path: {path}")
    backend_bytes = (OUT / "backend-final.log").read_bytes()
    backend_log = backend_bytes.decode("utf-16" if backend_bytes.startswith(b"\xff\xfe") else "utf-8", errors="replace")
    counts = re.search(r"(?:(\d+) failed, )?(\d+) passed, (\d+) skipped", backend_log)
    verification = {"backend": {"log": "backend-final.log", "complete": counts is not None,
                                "failed": int(counts[1] or 0) if counts else None, "passed": int(counts[2]) if counts else None, "skipped": int(counts[3]) if counts else None}}
    for key, filename in (("browser", "browser/results.json"), ("imaging_browser", "imaging-browser/proof.json"), ("live_api", "integration/results.json")):
        item = json.loads((OUT / filename).read_text(encoding="utf-8"))
        checks = item["checks"]
        verification[key] = {"file": filename, "passed": sum(bool(c["passed"]) for c in checks), "total": len(checks), "failure": item.get("failure"), "status": item.get("status", "VERIFIED" if all(c["passed"] for c in checks) and not item.get("failure") else "FAILED")}
    manifest = {"schema_version": "medtwin.universal-run-manifest.v1", "recorded_at": datetime.now(timezone.utc).isoformat(),
                "root": str(ROOT), "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "uncommitted_work": True, "python": sys.version, "interpreter": sys.executable, "platform": platform.platform(),
                "baseline": "artifacts/universal-2026-11-13/baseline.json", "registry_sha256_preserved": registry_hash,
                "requirement_count": len(ROWS), "statuses": {s: sum(row[5] == s for row in ROWS) for s in sorted({r[5] for r in ROWS})},
                "verification": verification,
                "clinical_activation": False, "published": False, "evidence_scope": "RESEARCH_SOFTWARE_WITH_EXPLICIT_BLOCKED_SCIENTIFIC_SUBREQUIREMENTS",
                "files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in sorted(set(source_paths))]}
    (OUT / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"requirements": len(ROWS), "statuses": manifest["statuses"], "hashed_files": len(manifest["files"]), "registry_preserved": True}))


def main():
    if (ROOT / "artifacts/completion-2026-11-13/baseline.json").exists():
        from build_completion_package import main as build_current
        build_current()
    else:
        build_legacy()


if __name__ == "__main__": main()
