"""Validate the requirement/evidence manifest without producing clinical claims."""
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/universal-2026-11-13"


def verify_legacy():
    manifest = json.loads((OUT / "run-manifest.json").read_text(encoding="utf-8"))
    checks = []
    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})
    check("No clinical activation or publication claimed", manifest["clinical_activation"] is False and manifest["published"] is False)
    with (ROOT / "docs/universal/requirements.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    check("All24 requirements present exactly once", sorted(r["id"] for r in rows) == [f"U-{n:03d}" for n in range(1, 25)])
    for row in rows:
        for column in ("implementation_paths", "test_paths", "evidence_paths"):
            check(f"{row['id']} {column} resolve", all((ROOT / name).exists() for name in row[column].split(";")))
        check(f"{row['id']} has explicit scope or blocker", bool(row["blocker"].strip()))
    for item in manifest["files"]:
        path = ROOT / item["path"]
        check(f"Current file hash: {item['path']}", path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"])
    backend = manifest["verification"]["backend"]
    check("Final full backend suite completed without failures", backend["complete"] and backend["failed"] == 0 and backend["passed"] == 1014 and backend["skipped"] == 5)
    for key in ("browser", "imaging_browser", "live_api"):
        result = manifest["verification"][key]
        check(f"{key} checks all passed", result["status"] == "VERIFIED" and result["passed"] == result["total"] and not result["failure"])
    actual = hashlib.sha256((ROOT / "model_registry/models.json").read_bytes()).hexdigest()
    check("Original model registry preserved", actual == manifest["registry_sha256_preserved"])
    report = {"schema_version": "medtwin.universal-package-verification.v1", "status": "VERIFIED" if all(c["passed"] for c in checks) else "FAILED", "scope": "EVIDENCE_MANIFEST_AND_ENGINEERING_RESULTS_NOT_CLINICAL_VALIDATION", "passed": sum(c["passed"] for c in checks), "total": len(checks), "checks": checks}
    (OUT / "package-verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}))
    if report["status"] != "VERIFIED":
        print(json.dumps([c for c in checks if not c["passed"]]))
        raise SystemExit(1)


def main():
    if (ROOT / "artifacts/completion-2026-11-13/run-manifest.json").exists():
        from verify_completion_package import main as verify_current
        verify_current()
    else:
        verify_legacy()


if __name__ == "__main__": main()
