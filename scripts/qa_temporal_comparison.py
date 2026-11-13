"""Original synthetic temporal-control API proof; no inference or clinical progression claim."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import nibabel as nib
import numpy as np
from PIL import Image
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/expansion-2026-11-13/imaging"
BASE = "http://127.0.0.1:8018/api/v1"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    credentials = json.loads((ROOT/".cache/review-20261113/qa-credentials.json").read_text(encoding="utf-8-sig"))
    session = requests.Session()
    login = session.post(BASE+"/auth/login", json={"username": credentials["username"], "password": credentials["password"]}, timeout=30); login.raise_for_status()
    session.headers["Authorization"] = "Bearer "+login.json()["access_token"]
    def get(path):
        result = session.get(BASE+path, timeout=60); result.raise_for_status(); return result.json()
    def post(path, **kwargs):
        result = session.post(BASE+path, timeout=60, **kwargs); result.raise_for_status(); return result
    def render(case, token, mode, name, index=10):
        result = post(f"/cases/{case}/temporal-comparisons/{token}/render", json={"axis": "axial", "index": index, "mode": mode})
        image = Image.open(io.BytesIO(result.content)); image.load()
        target = OUT/name; target.write_bytes(result.content)
        return {"path": target.relative_to(ROOT).as_posix(), "png_sha256": hashlib.sha256(result.content).hexdigest(), "dimensions": list(image.size), "metadata": json.loads(result.headers["X-MedTwin-Comparison"])}
    cases = get("/cases")
    case = next((item for item in cases if item["pseudonymous_id"] == "EXPANSION-ORIGINAL-TEMPORAL-CONTROL"), None)
    if case is None:
        case = post("/cases", json={"pseudonymous_id": "EXPANSION-ORIGINAL-TEMPORAL-CONTROL", "description": "Original synthetic matched intensity phantom with known local numeric change. No patient or clinical progression data."}).json()
    x, y, z = np.indices((32, 36, 24))
    previous = (5+100*np.exp(-((x-16)**2+(y-18)**2+(z-12)**2)/120)+x*.02).astype(np.float32)
    current = previous.copy(); current[12:18, 14:20, 8:13] += 7
    uploads = get(f"/cases/{case['id']}/uploads"); records = []
    with tempfile.TemporaryDirectory(prefix="medtwin-temporal-control-") as temporary:
        for label, array in [("previous", previous), ("current", current)]:
            path = Path(temporary)/f"original-{label}.nii.gz"
            affine = np.eye(4); affine[:3, 3] = [-16, -18, -12]
            image = nib.Nifti1Image(array, affine); image.header.set_xyzt_units("mm")
            image.header["intent_name"] = b"MT_SYNTHETIC"; image.header["descrip"] = b"MedTwin original synthetic control;unit=matched_arbitrary"
            nib.save(image, path); sha = hashlib.sha256(path.read_bytes()).hexdigest()
            record = next((item for item in uploads if item["file_hash"] == sha and item["is_associated"] and not item.get("withdrawn_at")), None)
            if record is None:
                with path.open("rb") as stream:
                    record = post(f"/cases/{case['id']}/uploads", files={"file": (path.name, stream, "application/octet-stream")}, data={"deidentified": "true"}).json()
            records.append(record)
    source = lambda record: {"upload_id": record["id"], "sha256": record["file_hash"]}
    body = {"previous": source(records[0]), "current": source(records[1]), "previous_region": "synthetic phantom", "current_region": "synthetic phantom", "same_subject_attested": True, "same_region_attested": True, "comparable_intensity_attested": True, "alignment": "shared_physical_space", "shared_physical_space_attested": True}
    comparison = post(f"/cases/{case['id']}/temporal-comparisons", json=body).json()
    assert comparison["status"] == "CANDIDATE_UNVALIDATED" and comparison["intensity"]["difference_allowed"] and not comparison["clinical_progression_claim"]
    renders = [render(case["id"], comparison["comparison_id"], mode, mode+".png") for mode in ["previous", "current", "checkerboard", "blend", "difference"]]
    actual = renders[-1]["metadata"]["statistics"]; expected = float((current[:, :, 10]-previous[:, :, 10]).mean())
    assert actual["valid_fraction"] == 1 and abs(actual["mean_current_minus_previous"]-expected) < 1e-6
    proof = {"schema_version": "medtwin.temporal-qa.v1", "case_id": case["id"], "upload_ids": [record["id"] for record in records], "source_kind": "ORIGINAL_PROGRAMMATIC_SYNTHETIC_CONTROL", "request": body, "comparison": comparison, "renders": renders, "expected_mean_change": expected, "clinical_progression_claim": False}
    existing = get("/cases/10/uploads")
    old, new = [next(item for item in existing if item["id"] == i) for i in [18, 19]]
    geometry_body = {**body, "previous": source(old), "current": source(new), "alignment": "compute_rigid"}
    geometry = post("/cases/10/temporal-comparisons", json=geometry_body).json()
    assert not geometry["intensity"]["difference_allowed"]
    proof["uncalibrated_geometric_comparison"] = {"case_id": 10, "comparison": geometry, "render": render(10, geometry["comparison_id"], "checkerboard", "uncalibrated-checkerboard.png", index=20)}
    (OUT/"qa-proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps({"case_id": case["id"], "uploads": proof["upload_ids"], "modes_verified": len(renders), "actual_mean_change": actual["mean_current_minus_previous"], "expected_mean_change": expected, "uncalibrated_difference_refused": True, "proof": str(OUT/"qa-proof.json")}))


if __name__ == "__main__": main()
