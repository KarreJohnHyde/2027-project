"""Reconcile the original24 requirements against measured completion evidence."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import re
import subprocess
import sys
from build_universal_package import ROWS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/completion-2026-11-13"
DOC = ROOT / "docs/universal"

# Preserve the initial assessment; scope reductions never silently become model gains.
UPDATES = {
 "U-001": ("VERIFIED", "resources/official-terminology-verification.json", "Official FY2027 ICD-10-CM98403 source classifications plus4849 existing entries; exact-source codes only, no invented clinical crosswalk or diagnostic model."),
 "U-002": ("VERIFIED", "browser/proof.json", "Case-bound source selection, actual raster overlay, optional independent-frame anatomy and chronological panels work; patient/atlas registration remains separately gated in U017."),
 "U-003": ("VERIFIED", "imaging/qa-proof.json;imaging/browser/proof.json", "Explicit4D channel/time selection and physical RAS MPR work for eligible coded, known-unit affines; native editing and nearest mask mappings are guarded."),
 "U-007": ("VERIFIED", "research/arena-measurements.json;browser/proof.json", "Actual saved prediction ROC/PR, reliability, binary confusion and patient-cluster comparisons operate under commercial gates. Both measured ECG comparison confidence intervals cross zero; no superiority shown."),
 "U-008": ("PARTIAL", "live/proof.json", "Exam/source missingness, identity attestation, conflicts and permitted ECG-demographic comparisons work. Broad learned multimodal fusion still lacks genuinely paired independent outcomes."),
 "U-009": ("PARTIAL", "live/fictional-chronological-backtest.json;browser/proof.json", "Read-only persistence/linear backtests evaluated five matching targets in an eight-date fictional control. General disease forecasts and validated registered progression measurements remain unavailable."),
 "U-013": ("PARTIAL", "resources/resource-inventory.json;research/ptb-rights-gate.json", "Added publisher-bound resource/license receipts and passing scoped PTB commercial-development audit. Original known cross-split groups and unknown patient identities remain unresolved."),
 "U-014": ("BLOCKED", "resources/rxhandbd-real-word-ocr.json;resources/ocr-word-experiment-v1/result.json;word-review/proof.json", "1115 publisher-test handwritten words and48 synthetic pages were measured, plus a frozen256-word reserved development comparison. None supplies independently human-reviewed full real laboratory/report pages; that reference remains missing."),
 "U-015": ("PARTIAL", "research/strict-parity-investigation.json", "Current source/tensor mapping and permitted ECG parity checked. Historical Kvasir one-pixel mismatch remains; the exact old source/environment archive is absent and NC reruns remain refused."),
 "U-016": ("BLOCKED", "research/development-experiment.json;research/ptb-rights-gate.json", "A permitted PTB age/sex development experiment ran with train/validation separation and no test-label parsing; balancing did not improve results. Six originally targeted weak-model families still lack complete commercial rights/review prerequisites; no replacement weights promoted."),
 "U-017": ("PARTIAL", "imaging/registration-benchmark-final.json;imaging/qa-proof.json", "Bounded same-subject/region-attested rigid registration candidates and held-out synthetic TRE work. Independent expert patient landmarks, cross-patient validation and patient-to-atlas validation remain missing."),
 "U-020": ("VERIFIED", "accessibility/report.json;word-review/browser-proof.json;browser/proof.json", "Automated WCAG AA scans at desktop/mobile sizes, keyboard tabs and real workflow controls verified. This is bounded engineering evidence, not exhaustive manual assistive-technology or maximum-volume certification."),
 "U-021": ("VERIFIED", "live/proof.json;operations/proof.json", "Reconciled24 requirements, reproducible proofs and dated review agenda; scientific, licensing and historical evidence remain distinct."),
 "U-022": ("PARTIAL", "release/source-snapshot.json;research/ptb-operator-review.json", "A privacy-scanned history-free local text-source snapshot is prepared. Sensitive original Git history is preserved and remains a publication blocker; automated rights review is not legal/regulatory approval; zero clinical activations."),
 "U-023": ("PARTIAL", "operations/proof.json", "Actual localhost hardened Linux containers, encrypted DB/uploads, authenticated backup, wrong-key/tamper refusals and independent restored backend on separate storage verified. Off-host disaster recovery remains untested."),
 "U-024": ("VERIFIED", "resources/resource-verification-summary.json;live/proof.json", "Publisher references, synthetic controls, reserved word-crop development, historical checkpoints and absent independent full-report clinical references remain explicitly separated."),
}


def read(path):
    raw = Path(path).read_bytes()
    return raw.decode("utf-16" if raw.startswith(b"\xff\xfe") else "utf-8-sig", errors="replace")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    original = DOC / "requirements-initial-2026-11-13.csv"
    if not original.exists():
        original.write_bytes((DOC / "requirements.csv").read_bytes())
    fields = ["id", "feature", "component", "priority", "owner", "status", "implementation_paths", "test_paths", "evidence_paths", "blocker"]
    rows = []
    for item in ROWS:
        row = list(item)
        row[8] = ";".join(p if p.startswith(("artifacts/", "docs/")) else f"artifacts/universal-2026-11-13/{p}" for p in row[8].split(";"))
        if row[0] in UPDATES:
            row[5], evidence, row[9] = UPDATES[row[0]]
            row[8] = ";".join(f"artifacts/completion-2026-11-13/{p}" for p in evidence.split(";"))
        rows.append(dict(zip(fields, row)))
    # The new modules supplement, rather than erase, the original implementation.
    additions = {
      "U-001": ("backend/app/services/universal_terminology.py", "backend/tests/test_completion_resources.py"),
      "U-003": ("backend/app/services/universal_spatial_io.py;backend/app/services/universal_registration.py", "backend/tests/test_spatial_completion.py;backend/tests/test_spatial_registration.py"),
      "U-007": ("src/components/ArenaDiagnostics.tsx", "backend/tests/test_completion_research.py"),
      "U-014": ("backend/app/services/upright_word_ocr.py;src/components/UprightWordReview.tsx", "backend/tests/test_upright_word_ocr.py"),
    }
    for row in rows:
        if row["id"] in additions:
            impl, tests = additions[row["id"]]
            row["implementation_paths"] += ";" + impl
            row["test_paths"] += ";" + tests
    with (DOC / "requirements.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    for row in rows:
        for column in ("implementation_paths", "test_paths", "evidence_paths"):
            for name in row[column].split(";"):
                if not (ROOT / name).is_file(): raise ValueError(f"Missing {row['id']} {column}: {name}")
    registry = hashlib.sha256((ROOT / "model_registry/models.json").read_bytes()).hexdigest()
    if registry != "b56979e0591788b1d588fa11c590e0378a1f98db1114612df702f816aa5b65b7": raise ValueError("Original registry identity changed")
    log = read(OUT / "backend-final.log")
    count = re.search(r"(?:(\d+) failed, )?(\d+) passed, (\d+) skipped", log)
    collected = re.search(r"(\d+) tests collected", read(OUT / "backend-collection.log"))
    if not count or not collected: raise ValueError("Actual completed full suite and collection required")
    verification = {"backend": {"complete": True, "failed": int(count[1] or 0), "passed": int(count[2]), "skipped": int(count[3]), "collected": int(collected[1])}}
    proofs = {"live": "live/proof.json", "imaging": "imaging/qa-proof.json", "imaging_browser": "imaging/browser/proof.json", "browser": "browser/proof.json", "word_api": "word-review/proof.json", "word_browser": "word-review/browser-proof.json", "operations": "operations/proof.json", "accessibility": "accessibility/report.json", "source_snapshot": "release/source-snapshot.json"}
    for key, name in proofs.items():
        proof = json.loads(read(OUT / name))
        verification[key] = {"file": name, "status": proof.get("status"), "checks": len(proof.get("checks", [])), "failure": proof.get("failure")}
    snapshot = json.loads(read(OUT / "release/source-snapshot.json"))
    source_manifest = json.loads(read(Path(snapshot["snapshot_directory"]) / "SOURCE_SNAPSHOT_MANIFEST.json"))
    sources = [ROOT / item["path"] for item in source_manifest["files"]]
    sources += [p for p in OUT.rglob("*") if p.is_file() and p.name not in {"run-manifest.json", "package-verification.json"}]
    for row in rows:
        sources += [ROOT / p for p in row["evidence_paths"].split(";")]
    manifest = {"schema_version": "medtwin.completion-run-manifest.v1", "recorded_at": datetime.now(timezone.utc).isoformat(), "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "uncommitted_source_included": True, "python": sys.version, "usage_profile": "commercial", "registry_sha256_preserved": registry, "baseline": "artifacts/completion-2026-11-13/baseline.json", "initial_requirements": str(original.relative_to(ROOT)).replace("\\", "/"), "requirement_count": len(rows), "statuses": {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})}, "verification": verification, "clinical_activation": False, "published": False, "scope": "BOUNDED_RESEARCH_ENGINEERING_WITH_UNRESOLVED_SCIENTIFIC_AND_RELEASE_REQUIREMENTS", "files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in sorted(set(sources))]}
    (OUT / "run-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"statuses": manifest["statuses"], "hashed_files": len(manifest["files"]), "backend": verification["backend"]}))


if __name__ == "__main__": main()
