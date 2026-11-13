"""Reproducible local QA of a permitted native ACDC input; no inference or training.

Credentials stay in memory. This creates/reuses only its named case on the selected QA server.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

import requests
from PIL import Image


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8018/api/v1")
    parser.add_argument("--credentials", type=Path, default=Path(".cache/review-20261113/qa-credentials.json"))
    parser.add_argument("--source", type=Path, default=Path("database/testing/patient101/patient101_frame01.nii"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/universal-2026-11-13/imaging-native-proof"))
    args = parser.parse_args()
    credentials = json.loads(args.credentials.read_text(encoding="utf-8-sig"))
    session = requests.Session()
    login = session.post(args.base + "/auth/login", json={"username": credentials["username"], "password": credentials["password"]}, timeout=30)
    login.raise_for_status()
    # Use the canonical authenticated API, never direct database writes.
    session.headers["Authorization"] = "Bearer " + login.json()["access_token"]
    cases = session.get(args.base + "/cases", timeout=30); cases.raise_for_status()
    case = next((case for case in cases.json() if case["pseudonymous_id"] == "UNIVERSAL-NATIVE-ACDC-QA"), None)
    if case is None:
        created = session.post(args.base + "/cases", json={"pseudonymous_id": "UNIVERSAL-NATIVE-ACDC-QA", "description": "Public ACDC test input for source geometry research QA. No clinical use or training."}, timeout=30)
        created.raise_for_status(); case = created.json()
    uploads = session.get(args.base + f"/cases/{case['id']}/uploads", timeout=30); uploads.raise_for_status()
    sha = hashlib.sha256(args.source.read_bytes()).hexdigest()
    record = next((upload for upload in uploads.json() if upload["file_hash"] == sha and upload["is_associated"] and not upload.get("withdrawn_at")), None)
    if record is None:
        with args.source.open("rb") as source:
            uploaded = session.post(args.base + f"/cases/{case['id']}/uploads", files={"file": (args.source.name, source, "application/octet-stream")}, data={"deidentified": "true"}, timeout=60)
        uploaded.raise_for_status(); record = uploaded.json()
    metadata = session.get(args.base + f"/uploads/{record['id']}/spatial/metadata", timeout=30); metadata.raise_for_status()
    proof = {"case_id": case["id"], "upload_id": record["id"], "source": args.source.as_posix(), "sha256": sha, "spatial": metadata.json(), "renders": []}
    assert proof["spatial"]["status"] == "AVAILABLE", proof["spatial"]
    args.output.mkdir(parents=True, exist_ok=True)
    dims = proof["spatial"]["dimensions_xyz"]
    for axis, dimension in [("axial", 2), ("coronal", 1), ("sagittal", 0)]:
        index = dims[dimension] // 2
        rendered = session.get(args.base + f"/uploads/{record['id']}/imaging/render", params={"axis": axis, "index": index}, timeout=60)
        rendered.raise_for_status()
        assert rendered.headers["content-type"] == "image/png"
        image = Image.open(io.BytesIO(rendered.content)); image.load()
        target = args.output / f"{axis}.png"; target.write_bytes(rendered.content)
        proof["renders"].append({"axis": axis, "index": index, "dimensions": list(image.size), "png_sha256": hashlib.sha256(rendered.content).hexdigest(), "render_metadata": json.loads(rendered.headers["X-MedTwin-Render"]), "artifact": target.as_posix()})
    (args.output / "proof.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
    print(json.dumps({"case_id": case["id"], "upload_id": record["id"], "status": proof["spatial"]["status"], "coordinate_frame": proof["spatial"]["coordinate_frame"], "display_frame": proof["spatial"]["display_frame"], "dimensions": dims, "verified_planes": [r["axis"] for r in proof["renders"]], "proof": str(args.output / "proof.json")}))


if __name__ == "__main__":
    main()
