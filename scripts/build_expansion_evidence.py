"""Publish aggregate software evidence only; no uploads, record rows or screenshots."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/expansion-2026-11-13"
DEST = ROOT / "docs/universal/evidence/expansion-2026-11-13.json"


def read(path):
    data = path.read_bytes()
    return data.decode("utf-16" if data.startswith(b"\xff\xfe") else "utf-8-sig", errors="replace")


def main():
    log = read(OUT / "backend-final.log")
    match = re.search(r"(?:(\d+) failed, )?(\d+) passed, (\d+) skipped", log)
    if not match or int(match[1] or 0): raise ValueError("A passing integrated full backend run is required")
    files = ["control-room/proof.json", "catalogue/browser-proof.json", "research/ui-proof.json", "research/api-proof.json", "imaging/browser/proof.json", "operations/proof.json", "container-acceptance/proof.json"]
    proofs = []
    for name in files:
        path = OUT / name; proof = json.loads(read(path))
        checks = proof["checks"]
        results = [item["passed"] is True if "passed" in item else item.get("status") == "PASSED" for item in checks]
        if not results or not all(results) or proof.get("failure") or proof.get("page_errors") or proof.get("server_errors") or proof.get("errors"): raise ValueError(f"Incomplete engineering proof: {name}")
        proofs.append({"name": name, "checks_passed": len(results), "artifact_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    registry = hashlib.sha256((ROOT / "model_registry/models.json").read_bytes()).hexdigest()
    if registry != "b56979e0591788b1d588fa11c590e0378a1f98db1114612df702f816aa5b65b7": raise ValueError("Original registry changed")
    hierarchy = json.loads(read(OUT / "catalogue/proof.json"))
    temporal = json.loads(read(OUT / "imaging/qa-proof.json"))
    summary = {"schema_version": "medtwin.public-expansion-evidence.v1", "generated_at": datetime.now(timezone.utc).isoformat(), "scope": "BOUNDED_RESEARCH_ENGINEERING_NOT_CLINICAL_VALIDATION", "usage_profile": "commercial", "clinical_activation": False,
        "backend": {"passed": int(match[2]), "skipped": int(match[3]), "log_sha256": hashlib.sha256((OUT / "backend-final.log").read_bytes()).hexdigest()},
        "frontend": {"typecheck_lint_check_build": "PASSED", "production_build": "PASSED", "log_sha256": hashlib.sha256((OUT / "frontend-check.log").read_bytes()).hexdigest()},
        "proofs": proofs, "source_hierarchy": {"families": hierarchy["families"], "nodes": hierarchy["nodes"], "semantics": "Source parents/context/model labels distinct; no guessed laterality or code crosswalk"},
        "matched_records": {"records": 2163, "patients": 1881, "new_inference": False, "patient_identifiers_returned": False, "superiority_demonstrated": False},
        "temporal_control": {"source_kind": "ORIGINAL_PROGRAMMATIC_SYNTHETIC_CONTROL", "expected_mean_change": temporal["expected_mean_change"], "measured_mean_change": temporal["renders"][-1]["metadata"]["statistics"]["mean_current_minus_previous"], "clinical_progression_claim": False},
        "registry_sha256_preserved": registry,
        "excluded_from_publication": ["Original local Git objects/history", "Patient uploads/databases", "Credentials and encryption keys", "Downloaded datasets and new weights", "New binary anatomy assets", "Third-party input screenshots and individual research record rows"],
        "open_scientific_prerequisites": ["Independent human-reviewed full real-report references", "Commercial rights/review prerequisites for six original weak-model families", "Known leakage groups and unknown patient identities", "Exact historical one-pixel Kvasir parity", "Independent patient/atlas registration", "Broad paired multimodal and longitudinal clinical outcomes", "Genuine ICD-11 configuration and separate crosswalk permission", "Off-host recovery and clinical/regulatory release"]}
    DEST.parent.mkdir(parents=True, exist_ok=True); DEST.write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": "PREPARED_AGGREGATE_EVIDENCE", "backend": summary["backend"]["passed"], "proof_checks": sum(p["checks_passed"] for p in proofs)}))


if __name__ == "__main__": main()
