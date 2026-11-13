"""Actual allowed native-volume inference on an explicitly isolated QA worker.

This is a reproducible one-input software check per model, not population accuracy.
Existing immutable checkpoints and frozen test inputs are never tuned here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from review_run_workflows import Runner, read_json, save_json

ROOT = Path(__file__).resolve().parents[1]


def run(state_path: Path, out: Path):
    runner = Runner(read_json(state_path), out)
    results = {"schema_version": "medtwin.universal-native-demo.v1", "scope": "ONE_PUBLIC_INPUT_PER_CHECKPOINT_NOT_NEW_POPULATION_ACCURACY", "workflows": {}}
    plans = [
        ("cardiac", 6, 11, "acdc_cardiac_mri_3d_unet", "MRI"),
    ]
    # Create a separate permitted research case for the actual 2-channel native
    # diffusion volume; it must not be substituted with an ordinary image.
    manifest = read_json(ROOT / "_derived/datasets/isles22-dwi-adc/manifest.json")
    sample = next(item for item in manifest["cases"] if item["split"] == "test")
    source = Path(manifest["dataset_root"]) / sample["image_path"]
    if hashlib.sha256(source.read_bytes()).hexdigest() != sample["image_sha256"]:
        raise ValueError("Frozen public input checksum mismatch")
    cases = runner.call("GET", "/cases")
    case = next((item for item in cases if item["pseudonymous_id"] == "UNIVERSAL-BRAIN-ISLES-QA"), None)
    if case is None:
        case = runner.call("POST", "/cases", json={"pseudonymous_id": "UNIVERSAL-BRAIN-ISLES-QA", "description": "One public ISLES research input; no private patient record. Not clinical validation."})
    uploads = runner.call("GET", f"/cases/{case['id']}/uploads")
    upload = next((item for item in uploads if item["file_hash"] == sample["image_sha256"]), None)
    if upload is None:
        upload = runner.upload(case["id"], "public-isles-dwi-adc.nii.gz", source.read_bytes(), "application/gzip")
    plans.append(("brain", case["id"], upload["id"], "brain_mri_stroke_lesion_segresnet", "BRAIN_MRI_DIFFUSION"))
    for name, case_id, upload_id, model_id, declared in plans:
        # Reuse the same idempotency key after process restart; no duplicate runs.
        queued = runner.call("POST", f"/uploads/{upload_id}/research-inference", json={"model_id": model_id, "declared_input_type": declared}, headers={"Idempotency-Key": f"universal-native-{case_id}-{upload_id}-{model_id}-v1"})
        job = runner.wait(queued)
        assert job["status"] == "SUCCEEDED", job
        runs = runner.call("GET", f"/uploads/{upload_id}/research-inference")["runs"]
        run = next(item for item in runs if item["id"] == job["result_ref"]["inference_run_id"])
        assert run["research_output"]["type"] == "volume_segmentation", run
        runner.review(run["finding_id"])
        metadata = runner.call("GET", f"/uploads/{upload_id}/spatial/metadata")
        surfaces = runner.call("GET", f"/research-inference/{run['id']}/surfaces")
        graph = runner.call("GET", f"/cases/{case_id}/evidence-graph")
        assert any(node["finding_id"] == run["finding_id"] for node in graph["nodes"])
        proof = {"case_id": case_id, "upload_id": upload_id, "run": run, "job": job, "spatial_metadata": metadata,
                 "surface_summary": {k: v for k, v in surfaces.items() if k != "surfaces"},
                 "surfaces": [{k: v for k, v in s.items() if k not in {"vertices_mm", "faces"}} for s in surfaces["surfaces"]],
                 "graph_snapshot": graph["data_version"], "graph_nodes": len(graph["nodes"]), "patient_to_atlas": "REGISTRATION_UNAVAILABLE"}
        save_json(out / f"{name}-native-evidence.json", proof)
        results["workflows"][name] = {"status": "VERIFIED_ONE_RESEARCH_INPUT", "case_id": case_id, "upload_id": upload_id, "run_id": run["id"], "model_id": model_id, "surface_count": len(surfaces["surfaces"]), "spatial_viewer_status": metadata["status"], "spatial_refusal": metadata.get("refusal"), "evidence": str(out / f"{name}-native-evidence.json")}
        print(name, json.dumps(results["workflows"][name]), flush=True)
        save_json(out / "native-workflows.json", results)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=ROOT / ".cache/review-20261113/stack.json")
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/universal-2026-11-13/native-workflows")
    args = parser.parse_args()
    try:
        run(args.state, args.out)
    except Exception as exc:
        save_json(args.out / "failure.json", {"status": "FAILED", "error": str(exc)})
        raise
