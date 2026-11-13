"""Authorized isolated-QA proof: existing public brain channels + original synthetic registration.

No new inference/training. No third-party data download or external transmission.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tempfile

import nibabel as nib
import numpy as np
from PIL import Image
import requests

from benchmark_spatial_registration import synthetic_case


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8018/api/v1")
    parser.add_argument("--credentials", type=Path, default=Path(".cache/review-20261113/qa-credentials.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/completion-2026-11-13/imaging"))
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    credentials = json.loads(args.credentials.read_text(encoding="utf-8-sig"))
    session = requests.Session()
    login = session.post(args.base + "/auth/login", json={"username": credentials["username"], "password": credentials["password"]}, timeout=30); login.raise_for_status()
    session.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    def get(path, **kwargs):
        response = session.get(args.base + path, timeout=60, **kwargs); response.raise_for_status(); return response
    def post(path, **kwargs):
        response = session.post(args.base + path, timeout=60, **kwargs); response.raise_for_status(); return response
    def png(path, name, **kwargs):
        response = get(path, **kwargs); assert response.headers["content-type"] == "image/png"
        image = Image.open(io.BytesIO(response.content)); image.load()
        target = args.output / name; target.write_bytes(response.content)
        return {"artifact": target.as_posix(), "sha256": hashlib.sha256(response.content).hexdigest(), "dimensions": list(image.size), "render_metadata": json.loads(response.headers["X-MedTwin-Render"])}
    proof = {"schema_version": "medtwin.spatial-completion-qa.v1", "clinical_validation": False, "brain": {"case_id": 7, "upload_id": 12, "run_id": 12, "data_use_scope": "PREEXISTING_AUTHORIZED_RESEARCH_QA_NOT_COMMERCIAL_DATA_CLEARANCE", "model_semantics": "Existing full multichannel run; frame selection does not create an independent channel-specific prediction."}, "synthetic_registration": {}}
    endpoint = "/uploads/12/spatial"
    baseline = get(endpoint + "/metadata").json()
    assert baseline["refusal"]["code"] == "FRAME_SELECTION_REQUIRED", "QA backend must be restarted with completion imaging routes."
    proof["brain"]["before_selection"] = baseline
    renders = []
    for frame in (0, 1):
        selectors = {"frame_kind": "channel", "frame_index": frame}
        metadata = get(endpoint + "/metadata", params=selectors).json()
        assert metadata["status"] == "AVAILABLE" and metadata["frame_selection"]["index"] == frame
        proof["brain"][f"channel_{frame}_metadata"] = metadata
        for axis, dimension in [("axial", 2), ("coronal", 1), ("sagittal", 0)]:
            rendered = png(endpoint + "/render", f"brain-channel-{frame}-{axis}.png", params={**selectors, "axis": axis, "index": metadata["dimensions_xyz"][dimension]//2})
            assert rendered["render_metadata"]["frame_selection"]["index"] == frame
            renders.append(rendered)
    assert any(renders[i]["sha256"] != renders[i+3]["sha256"] for i in range(3)), "Channels must not be flattened to the same source frame."
    proof["brain"]["renders"] = renders
    anatomical = get(endpoint + "/metadata", params={"frame_kind": "channel", "frame_index": 0, "view_space": "anatomical"}).json()
    proof["brain"]["anatomical_metadata"] = anatomical
    if anatomical["status"] == "AVAILABLE":
        proof["brain"]["anatomical_renders"] = [png(endpoint + "/render", f"brain-anatomical-{axis}.png", params={"frame_kind": "channel", "frame_index": 0, "view_space": "anatomical", "axis": axis, "index": anatomical["dimensions_xyz"][dim]//2}) for axis, dim in [("axial", 2), ("coronal", 1), ("sagittal", 0)]]
    run = get("/research-inference/12").json()
    volume = run["research_output"]
    mask_slice = max(volume["slices"], key=lambda plane: sum(segment["area_px"] for segment in plane["segments"]))["slice_index"]
    proof["brain"]["prediction_source_mask"] = png(endpoint + "/render", "brain-source-prediction.png", params={"frame_kind": "channel", "frame_index": 0, "axis": "axial", "index": mask_slice, "layer": "prediction", "run_id": 12})
    # Original generated data have known spatial units/transform; no publisher or patient labels are invented.
    fixed, moving, contract, landmarks, known = synthetic_case(.06, np.asarray([2., -1.5, 1.]), .2)
    cases = get("/cases").json()
    case = next((case for case in cases if case["pseudonymous_id"] == "COMPLETION-SYNTHETIC-REGISTRATION"), None)
    if case is None:
        case = post("/cases", json={"pseudonymous_id": "COMPLETION-SYNTHETIC-REGISTRATION", "description": "Original programmatic Gaussian phantom pair with known physical transform. Engineering control, no patient data or clinical validation."}).json()
    uploads = get(f"/cases/{case['id']}/uploads").json(); records = []
    with tempfile.TemporaryDirectory(prefix="medtwin-original-registration-") as temporary:
        for name, array in [("fixed", fixed), ("moving", moving)]:
            path = Path(temporary) / f"synthetic-{name}.nii.gz"
            image = nib.Nifti1Image(array, np.asarray(contract["affine_voxel_to_world"])); image.header.set_xyzt_units("mm"); nib.save(image, path)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            record = next((record for record in uploads if record["file_hash"] == sha and record["is_associated"] and not record.get("withdrawn_at")), None)
            if record is None:
                with path.open("rb") as source:
                    record = post(f"/cases/{case['id']}/uploads", files={"file": (path.name, source, "application/octet-stream")}, data={"deidentified": "true"}).json()
            records.append(record)
    body = {"fixed": {"upload_id": records[0]["id"]}, "moving": {"upload_id": records[1]["id"]}, "same_subject_attested": True, "same_anatomical_region_attested": True, "metric": "mean_squares", "landmarks": landmarks, "landmark_source": "SYNTHETIC_KNOWN_TRANSFORM"}
    result = post(f"/cases/{case['id']}/spatial/registration", json=body).json()
    assert result["status"] == "CANDIDATE_UNVALIDATED" and not result["clinical_activation"] and not result["atlas_registration"]
    assert result["landmark_evaluation"]["after_mean_mm"] < 1.
    proof["synthetic_registration"] = {"case_id": case["id"], "fixed_upload_id": records[0]["id"], "moving_upload_id": records[1]["id"], "known_moving_to_fixed_ras_mm": known.tolist(), "request": body, "result": result}
    synthetic_anatomical = get(f"/uploads/{records[0]['id']}/spatial/metadata", params={"view_space": "anatomical"}).json()
    assert synthetic_anatomical["status"] == "AVAILABLE"
    proof["synthetic_registration"]["anatomical_metadata"] = synthetic_anatomical
    proof["synthetic_registration"]["anatomical_renders"] = [png(f"/uploads/{records[0]['id']}/spatial/render", f"synthetic-anatomical-{axis}.png", params={"view_space": "anatomical", "axis": axis, "index": synthetic_anatomical["dimensions_xyz"][dim]//2}) for axis, dim in [("axial", 2), ("coronal", 1), ("sagittal", 0)]]
    (args.output / "qa-proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": (args.output / "qa-proof.json").as_posix(), "brain_channel_planes": len(renders), "brain_anatomical_status": anatomical["status"], "synthetic_case_id": case["id"], "synthetic_uploads": [record["id"] for record in records], "synthetic_registration_mean_TRE_mm": result["landmark_evaluation"]["after_mean_mm"], "clinical_activation": False}))


if __name__ == "__main__":
    main()
