"""Verify actual current evidence, source hashes and retained refusal boundaries."""
from pathlib import Path
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/completion-2026-11-13"


def main():
    manifest = json.loads((OUT / "run-manifest.json").read_text(encoding="utf-8"))
    checks = []
    def check(name, passed): checks.append({"name": name, "passed": bool(passed)})
    def proof(name): return json.loads((OUT / name).read_text(encoding="utf-8-sig"))
    check("Commercial purpose, no clinical activation or publication", manifest["usage_profile"] == "commercial" and not manifest["clinical_activation"] and not manifest["published"])
    with (ROOT / "docs/universal/requirements.csv").open(encoding="utf-8", newline="") as handle: rows = list(csv.DictReader(handle))
    check("All24 original requirements reconciled exactly once", sorted(r["id"] for r in rows) == [f"U-{n:03d}" for n in range(1, 25)])
    check("Initial assessment preserved separately", (ROOT / manifest["initial_requirements"]).is_file())
    for row in rows:
        for key in ("implementation_paths", "test_paths", "evidence_paths"):
            check(f"{row['id']} {key} resolve", all((ROOT / p).is_file() for p in row[key].split(";")))
        check(f"{row['id']} explicitly scoped", bool(row["blocker"].strip()))
    check("Scientific requirements remain blocked rather than fabricated", all(next(r for r in rows if r["id"] == key)["status"] == "BLOCKED" for key in ("U-014", "U-016")))
    backend = manifest["verification"]["backend"]
    check("Full current suite passed and accounts for every collected test", backend["complete"] and backend["failed"] == 0 and backend["passed"] > 0 and backend["passed"] + backend["skipped"] == backend["collected"])
    for name in ("live/proof.json", "word-review/proof.json", "operations/proof.json", "imaging/browser/proof.json", "browser/proof.json", "word-review/browser-proof.json"):
        item = proof(name)
        outcomes = [c["passed"] is True if "passed" in c else c.get("status") == "PASSED" for c in item["checks"]]
        check(f"Actual controls passed: {name}", len(outcomes) > 0 and all(outcomes) and not item.get("failure") and not item.get("page_errors") and not item.get("server_errors"))
    spatial = proof("imaging/qa-proof.json")
    check("Actual selected source channels rendered without flattening", len(spatial["brain"]["renders"]) == 6 and spatial["brain"]["renders"][0]["sha256"] != spatial["brain"]["renders"][3]["sha256"])
    registration = spatial["synthetic_registration"]["result"]
    check("Synthetic registration is explicitly unvalidated", registration["status"] == "CANDIDATE_UNVALIDATED" and not registration["clinical_activation"] and not registration["atlas_registration"] and registration["landmark_evaluation"]["after_mean_mm"] < 1)
    accessibility = proof("accessibility/report.json")
    check("All eight audited page/viewports have zero detected violations", accessibility["status"] == "VERIFIED_AUTOMATED_SCOPE" and len(accessibility["pages"]) == 8 and all(not p["violations"] and p["layout"]["document"] <= p["layout"]["viewport"] + 1 for p in accessibility["pages"]))
    release = proof("release/source-snapshot.json")
    check("Local source snapshot excludes Git and privacy findings", release["status"] == "VERIFIED_HISTORY_FREE_LOCAL_SOURCE" and not release["git_metadata_present"] and not release["privacy_findings"] and not release["published"] and not release["original_history_changed"])
    for item in manifest["files"]:
        relative = Path(item["path"])
        path = ROOT / relative
        check(f"Current file hash: {item['path']}", not relative.is_absolute() and ".." not in relative.parts and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"])
    actual = hashlib.sha256((ROOT / "model_registry/models.json").read_bytes()).hexdigest()
    check("Original user model registry preserved", actual == manifest["registry_sha256_preserved"] == "b56979e0591788b1d588fa11c590e0378a1f98db1114612df702f816aa5b65b7")
    report = {"schema_version": "medtwin.completion-package-verification.v1", "status": "VERIFIED" if all(c["passed"] for c in checks) else "FAILED", "scope": "CURRENT_SOURCE_AND_BOUNDED_ENGINEERING_EVIDENCE_NOT_CLINICAL_CLEARANCE", "passed": sum(c["passed"] for c in checks), "total": len(checks), "checks": checks}
    (OUT / "package-verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}))
    if report["status"] != "VERIFIED":
        print(json.dumps([c for c in checks if not c["passed"]])); raise SystemExit(1)


if __name__ == "__main__": main()
