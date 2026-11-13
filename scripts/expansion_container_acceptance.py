"""Live Linux acceptance with original phantoms and one permitted public ECG."""
from pathlib import Path
import csv
import hashlib
import io
import json
import sys
import tempfile
import time
import nibabel as nib
import numpy as np
from review_run_workflows import Runner, read_json, save_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/expansion-2026-11-13/container-acceptance"


def main():
    runner = Runner(read_json(ROOT / ".cache/completion-container/stack.json"), OUT)
    report = {"scope": "LOCAL_LINUX_ORIGINAL_SYNTHETIC_CONTROLS_AND_PERMITTED_PUBLIC_ECG_NOT_CLINICAL_VALIDATION", "checks": []}
    def check(name, passed, **details):
        report["checks"].append({"name": name, "passed": bool(passed), **details}); save_json(OUT / "proof.json", report)
        if not passed: raise AssertionError(name)
    structure = runner.call("GET", "/universal/structures/systems")
    check("Linux serves source-backed hierarchy for all25 families", len(structure["systems"]) == 25)
    for mode in ["global", "same_run"]:
        records = runner.call("POST", "/universal/research/matched-records/query", json={"mode": mode, "label": "MI", "limit": 2})
        check("Linux verifies same-input saved records: " + mode, records["status"] == "MATCHED_RECORDS_AVAILABLE" and records["cohort"]["records"] == 2163 and len(records["rows"]) == 2, records=records["cohort"]["records"], patients=records["cohort"]["patients"])
    cases = runner.call("GET", "/cases")
    case = next((c for c in cases if c["pseudonymous_id"] == "EXPANSION-CONTAINER-SYNTHETIC"), None)
    if case is None: case = runner.call("POST", "/cases", json={"pseudonymous_id": "EXPANSION-CONTAINER-SYNTHETIC", "description": "Original programmatic phantom comparison; no patient data or disease progression reference."})
    x, y, z = np.indices((32, 36, 24))
    previous = (5 + 100*np.exp(-((x-16)**2+(y-18)**2+(z-12)**2)/120) + x*.02).astype(np.float32)
    current = previous.copy(); current[12:18, 14:20, 8:13] += 7
    uploads = runner.call("GET", f"/cases/{case['id']}/uploads"); records = []
    with tempfile.TemporaryDirectory(prefix="medtwin-original-control-") as temporary:
        for label, array in [("previous", previous), ("current", current)]:
            path = Path(temporary) / f"original-{label}.nii.gz"
            affine = np.eye(4); affine[:3, 3] = [-16, -18, -12]
            image = nib.Nifti1Image(array, affine); image.header.set_xyzt_units("mm")
            image.header["intent_name"] = b"MT_SYNTHETIC"; image.header["descrip"] = b"MedTwin original synthetic control;unit=matched_arbitrary"
            nib.save(image, path); raw = path.read_bytes(); sha = hashlib.sha256(raw).hexdigest()
            record = next((u for u in uploads if u["file_hash"] == sha), None)
            if record is None: record = runner.upload(case["id"], path.name, raw, "application/octet-stream")
            records.append(record)
    body = {"previous": {"upload_id": records[0]["id"], "sha256": records[0]["file_hash"]}, "current": {"upload_id": records[1]["id"], "sha256": records[1]["file_hash"]}, "previous_region": "synthetic phantom", "current_region": "synthetic phantom", "same_subject_attested": True, "same_region_attested": True, "comparable_intensity_attested": True, "alignment": "shared_physical_space", "shared_physical_space_attested": True}
    comparison = runner.call("POST", f"/cases/{case['id']}/temporal-comparisons", json=body)
    check("Linux creates explicitly unvalidated source-bound comparison", comparison["status"] == "CANDIDATE_UNVALIDATED" and not comparison["clinical_progression_claim"], case_id=case["id"], upload_ids=[u["id"] for u in records])
    response = runner.client.post(f"/cases/{case['id']}/temporal-comparisons/{comparison['comparison_id']}/render", json={"axis": "axial", "index": 10, "mode": "difference"}); response.raise_for_status()
    metadata = json.loads(response.headers["X-MedTwin-Comparison"])
    expected = float((current[:, :, 10]-previous[:, :, 10]).mean())
    check("Linux actual difference equals known original synthetic change", metadata["statistics"]["valid_fraction"] == 1 and abs(metadata["statistics"]["mean_current_minus_previous"]-expected) < 1e-6, expected_mean=expected, measured_mean=metadata["statistics"]["mean_current_minus_previous"])
    refused = runner.client.post(f"/cases/{case['id']}/temporal-comparisons", json={**body, "same_subject_attested": False})
    check("Linux missing correspondence attestation refuses", refused.status_code == 422)
    sys.path.insert(0, str(ROOT)); from ml_training import ptbxl
    with (ROOT / "artifacts/training/ptbxl_ecg_baseline-20261025T072058Z/predictions_test.csv").open(newline="") as handle: frozen = next(csv.DictReader(handle))
    public = next(r for r in ptbxl.load_metadata()[0] if r["ecg_id"] == int(frozen["ecg_id"]))
    base = ptbxl.DATASET_DIR / public["file"]
    ptbxl.verify_files([public["file"] + extension for extension in [".hea", ".dat"]], ptbxl.publisher_checksums())
    ecg_case = runner.call("POST", "/cases", json={"pseudonymous_id": "EXPANSION-LINUX-PUBLIC-ECG-" + str(time.time_ns()), "description": "One permitted public input through the Linux commercial-gated worker; not a population evaluation."})
    header = runner.upload(ecg_case["id"], base.name + ".hea", base.with_suffix(".hea").read_bytes(), "application/octet-stream")
    signal = runner.upload(ecg_case["id"], base.name + ".dat", base.with_suffix(".dat").read_bytes(), "application/octet-stream")
    job = runner.wait(runner.call("POST", f"/uploads/{header['id']}/research-inference", json={"model_id": "ptbxl_ecg_baseline", "declared_input_type": "ECG", "companion_upload_id": signal["id"]}, headers={"Idempotency-Key": f"expansion-linux-ecg-{header['id']}"}))
    check("Linux commercial-gated ECG worker performs actual inference", job["status"] == "SUCCEEDED", case_id=ecg_case["id"], header_id=header["id"], signal_id=signal["id"])
    report["status"] = "VERIFIED_EXPANSION_LINUX_SCOPE"; save_json(OUT / "proof.json", report)
    print(json.dumps({"status": report["status"], "checks": len(report["checks"])}))


if __name__ == "__main__": main()
