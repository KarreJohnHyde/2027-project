"""Run real API/worker review controls on an explicitly isolated QA stack.

Synthetic reports test software, not clinical extraction accuracy. The public
Kvasir sample tests one existing checkpoint, not a new population evaluation.
Credentials are read locally and never copied into the evidence artifact.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "gi_kvasir_seg_polyp_segmenter"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")


def pdf_fixture(text: str, scanned: bool = False) -> bytes:
    if scanned:
        image = Image.new("RGB", (1654, 2339), "white")
        font_path = Path("C:/Windows/Fonts/arial.ttf")
        if not font_path.exists():
            font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        font = ImageFont.truetype(str(font_path), 28)
        draw = ImageDraw.Draw(image)
        for index, line in enumerate(text.splitlines()):
            draw.text((85, 100 + index * 50), line, font=font, fill="black")
        buffer = io.BytesIO()
        image.save(buffer, format="PDF", resolution=200)
        return buffer.getvalue()
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    page = writer.add_blank_page(width=595, height=842)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    lines = ["BT /F1 10 Tf 40 790 Td 17 TL"]
    for line in text.splitlines():
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        lines.append(f"({escaped}) Tj T*")
    lines.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(lines).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class Runner:
    def __init__(self, state, out):
        self.state, self.out = state, out
        if state.get("mode") != "qa" or state.get("job_execution") != "worker":
            raise ValueError("An isolated worker-mode QA stack is required; refusing a development/patient database.")
        self.client = httpx.Client(base_url=state["backend_url"] + "/api/v1", timeout=180,
                                   headers={"X-MedTwin-Client": "web"})
        credentials = read_json(state["credentials_file"])
        token = self.call("POST", "/auth/login", json={"username": credentials["username"], "password": credentials["password"]})
        if token.get("access_token"):
            self.client.headers["Authorization"] = "Bearer " + token["access_token"]
        # The web-client header deliberately uses HttpOnly cookie sessions.
        # httpx retains that cookie; never export it in the evidence artifact.

    def call(self, method, endpoint, expected=(200, 201, 202), **kwargs):
        response = self.client.request(method, endpoint, **kwargs)
        if response.status_code not in expected:
            raise RuntimeError(f"{method} {endpoint}: HTTP {response.status_code}: {response.text[:700]}")
        return response.json()

    def upload(self, case_id, name, content, mime, examination_id=None):
        data = {"deidentified": "true", "is_associated": "true", "association_notes": "Isolated review fixture; no private patient input"}
        if examination_id:
            data["examination_id"] = str(examination_id)
        return self.call("POST", f"/cases/{case_id}/uploads", data=data, files={"file": (name, content, mime)})

    def wait(self, response):
        if "queued_job" not in response:
            return response
        job_id = response["queued_job"]["id"]
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            job = self.call("GET", f"/jobs/{job_id}")
            if job["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                return job
            time.sleep(0.5)
        raise TimeoutError(f"Worker job {job_id} did not finish in 240 seconds")

    def review(self, finding):
        return self.call("POST", f"/reviews/{finding}", json={"review_status": "CONFIRMED",
                         "reviewer_comments": "Synthetic/public research software verification only; not clinical validation."})

    def document(self):
        case = self.call("POST", "/cases", json={"pseudonymous_id": "REVIEW-DOC-" + str(time.time_ns()),
                                                 "description": "Fictional synthetic report workflow"})
        cid = case["id"]
        reports = [ROOT / "backend/app/data/demo/demo_lab_report_march.txt", ROOT / "backend/app/data/demo/demo_lab_report_june.txt"]
        jobs, uploads = [], []
        for index, report in enumerate(reports):
            exam = self.call("POST", f"/cases/{cid}/examinations", json={"modality": "REPORT",
                             "exam_date": ("2026-03-14T08:30:00Z" if index == 0 else "2026-06-18T08:45:00Z"),
                             "clinical_indication": "Fictional software demonstration"})
            source = report.read_text(encoding="utf-8")
            # This is an invented report, so its explicitly printed method is
            # also invented and labelled; never fill missing real-report context.
            source = source.replace("Specimen: whole blood (EDTA)", "Specimen: whole blood (EDTA)\nMethod: SYNTHETIC")
            source = source.replace("Specimen: serum", "Specimen: serum\nMethod: SYNTHETIC")
            content = pdf_fixture(source, scanned=index == 1)
            (self.out / f"synthetic-report-{index + 1}.pdf").write_bytes(content)
            upload = self.upload(cid, f"synthetic-report-{index + 1}.pdf", content, "application/pdf", exam["id"])
            uploads.append(upload)
            job = self.wait(self.call("POST", f"/uploads/{upload['id']}/analysis-jobs",
                            headers={"Idempotency-Key": f"review-doc-{cid}-{index}"}))
            if job.get("status") != "SUCCEEDED":
                raise RuntimeError(f"Report worker did not succeed: {job}")
            jobs.append(job)
            run = self.call("GET", f"/analysis-jobs/{job['result_ref']['inference_run_id']}")
            for finding in run["findings"]:
                self.review(finding["id"])
        measurements = self.call("GET", f"/cases/{cid}/measurements")
        statements = self.call("GET", f"/cases/{cid}/statements")
        save_json(self.out / "document-observed-fields.json", {"case_id": cid, "uploads": uploads, "measurements": measurements})
        assert len(measurements) == 18, f"Expected 9 explicitly printed fields per report; extracted {len(measurements)}"
        names = ["hemoglobin", "white_blood_cell_count", "platelet_count", "glucose", "creatinine", "urea", "sodium", "potassium", "hba1c"]
        expected = [[10.8, 7.2, 210, 132, 1.4, 48, 138, 4.6, 7.4], [11.9, 6.8, 225, 112, 1.2, 38, 139, 4.4, 6.8]]
        checked = 0
        for index, upload in enumerate(uploads):
            rows = {row["name"]: row for row in measurements if row["source_file_id"] == upload["id"]}
            assert set(rows) == set(names), f"Unexpected field association for synthetic page {index + 1}"
            for name, value in zip(names, expected[index]):
                assert rows[name]["value"] == value, f"Incorrect synthetic field {name}"
                expected_specimen = "Whole blood (EDTA)" if name in names[:3] else "Serum"
                assert rows[name]["specimen"] == expected_specimen, f"Wrong panel specimen for {name}: {rows[name]['specimen']}"
                assert rows[name]["laboratory_method"] == "SYNTHETIC", f"Wrong printed method for {name}"
                assert rows[name]["source_page"] == 1
                if index == 1:
                    assert rows[name].get("source_bbox"), f"OCR field {name} lost source geometry"
                checked += 1
        comparison = self.call("POST", f"/cases/{cid}/compare", json={"same_patient_confirmed": True})
        assert comparison.get("numeric_deltas"), f"No context-compatible numeric comparison: {comparison.get('numeric_comparison_blockers')}"
        trends = self.call("GET", f"/cases/{cid}/biomarker-trends")
        synthesis = self.call("GET", f"/cases/{cid}/evidence-synthesis")
        forecast = self.call("POST", f"/cases/{cid}/forecast", json={"case_id": cid, "target_metric": "Hemoglobin", "unit": "g/dL", "horizon_days": 30})
        assert forecast["predicted_value"] is None, "Two synthetic observations cannot establish a disease forecast"
        effective = self.call("GET", f"/cases/{cid}/effective-evidence")
        provenance = self.call("GET", f"/cases/{cid}/provenance")
        export = {"schema_version": "medtwin-review-api-evidence-1", "scope": "SYNTHETIC_SOFTWARE_CONTROL_NOT_CLINICAL_GOLD",
                  "case": case, "uploads": uploads, "jobs": jobs, "measurements": measurements, "statements": statements,
                  "effective_evidence": effective, "comparison": comparison, "trends": trends, "synthesis": synthesis,
                  "forecast": forecast, "provenance": provenance}
        save_json(self.out / "document-evidence.json", export)
        # A new connection proves results are stored, independent of client state.
        with httpx.Client(base_url=self.client.base_url, headers=dict(self.client.headers), cookies=self.client.cookies) as reloaded:
            restored = reloaded.get(f"/cases/{cid}/measurements").json()
        assert restored == measurements
        return {"status": "VERIFIED", "case_id": cid, "input_scope": "2 SYNTHETIC PDF pages, one embedded-text and one rendered scan",
                "worker_jobs": [{"id": j["id"], "status": j["status"]} for j in jobs], "measurement_count": len(measurements),
                "statement_count": len(statements), "trend_series": len(trends.get("series", [])),
                "numeric_delta_count": len(comparison.get("numeric_deltas", [])), "forecast_status": forecast["eligibility_status"],
                "independent_human_annotated_pages": 0, "reload_equal": True,
                "synthetic_values_checked": checked, "synthetic_value_matches": checked,
                "synthetic_specimens_checked": checked, "synthetic_specimen_matches": checked,
                "synthetic_methods_checked": checked, "synthetic_method_matches": checked,
                "export_sha256": hashlib.sha256((self.out / "document-evidence.json").read_bytes()).hexdigest()}

    def imaging(self):
        case = self.call("POST", "/cases", json={"pseudonymous_id": "REVIEW-IMAGE-" + str(time.time_ns()),
                                                 "description": "Public Kvasir research sample; no private patient"})
        cid = case["id"]
        with (ROOT / "_derived/datasets/kvasir-seg-polyp-segmentation/samples.csv").open(newline="", encoding="utf-8-sig") as handle:
            sample = next(row for row in csv.DictReader(handle) if row["split"] == "test")
        image_path, mask_path = Path(sample["path"]), Path(sample["mask_file"])
        upload = self.upload(cid, "public-kvasir-research.jpg", image_path.read_bytes(), "image/jpeg")
        selection = self.call("POST", f"/uploads/{upload['id']}/model-selection",
                              json={"declared_input_type": "ENDOSCOPY", "task": "segmentation"})
        assert selection["selected_model_id"] == MODEL_ID, selection
        job = self.wait(self.call("POST", f"/uploads/{upload['id']}/research-inference",
                                 json={"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"},
                                 headers={"Idempotency-Key": f"review-image-{cid}"}))
        assert job.get("status") == "SUCCEEDED", job
        runs = self.call("GET", f"/uploads/{upload['id']}/research-inference")["runs"]
        run = next(row for row in runs if row["id"] == job["result_ref"]["inference_run_id"])
        annotation = self.call("POST", f"/uploads/{upload['id']}/reference-annotations",
                    data={"source": "DATASET_PUBLISHER_ANNOTATION", "source_detail": "Public Kvasir-SEG publisher mask for the same frozen test image", "class_name": "polyp"},
                    files={"mask": ("publisher-mask.jpg", mask_path.read_bytes(), "image/jpeg")})
        comparison = self.call("GET", f"/research-inference/{run['id']}/reference-comparison/{annotation['id']}")
        self.review(run["finding_id"])
        reloaded = self.call("GET", f"/uploads/{upload['id']}/research-inference")["runs"]
        assert reloaded[0]["research_output"] == run["research_output"]
        assert reloaded[0]["latest_review"]["review_status"] == "CONFIRMED"
        save_json(self.out / "image-evidence.json", {"scope": "ONE_PUBLIC_RESEARCH_TEST_IMAGE_NOT_NEW_POPULATION_ACCURACY",
                  "case": case, "upload": upload, "selection": selection, "job": job, "run": reloaded[0],
                  "reference": annotation, "comparison": comparison,
                  "source_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                  "reference_sha256": hashlib.sha256(mask_path.read_bytes()).hexdigest()})
        # Compare the served source-grid mask with a fresh direct path, with identical checkpoint/precision.
        sys.path.insert(0, str(ROOT / "backend"))
        from app.services import model_inference, reference_annotations
        model = model_inference.get_model(MODEL_ID)
        net, payload, device = model_inference.load_model(model)
        from app.services.imaging_readers import open_raster
        upright, _ = open_raster(image_path)
        direct = model_inference.segment(net, payload, device, upright)
        served_mask, _ = reference_annotations.predicted_mask(run["research_output"], "polyp")
        direct_mask, _ = reference_annotations.predicted_mask(direct, "polyp")
        assert served_mask.shape == direct_mask.shape
        differing = int(np.count_nonzero(served_mask != direct_mask))
        overlay = upright.convert("RGBA")
        shade = Image.new("RGBA", overlay.size, (34, 211, 238, 0))
        shade.putalpha(Image.fromarray(served_mask.astype(np.uint8) * 100))
        Image.alpha_composite(overlay, shade).convert("RGB").save(self.out / "public-image-model-overlay.png")
        save_json(self.out / "parity.json", {"model_id": MODEL_ID, "checkpoint_sha256": model["artifact_bundle"]["checkpoint_sha256"],
                  "comparison": "API worker output vs fresh direct serving adapter, same original bytes; not independent trainer parity",
                  "input_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(), "source_grid_shape": list(served_mask.shape),
                  "mask_differing_pixels": differing, "exact": differing == 0, "device": str(device),
                  "precision": direct.get("numeric_precision"), "tolerance": "0 differing source-grid pixels",
                  "preprocessing_version": model["artifact_bundle"]["preprocessing_version"]})
        assert differing == 0
        # Blank and a report photograph are controls with explicit non-clinical provenance.
        refusals = []
        for label, image in [("blank", Image.new("RGB", (512, 512), "white")),
                             ("report_photo", Image.open(io.BytesIO(pdf_page_image_bytes())) )]:
            buf = io.BytesIO(); image.save(buf, format="PNG")
            bad = self.upload(cid, f"synthetic-{label}.png", buf.getvalue(), "image/png")
            request = self.client.post(f"/uploads/{bad['id']}/research-inference", json={"model_id": MODEL_ID, "declared_input_type": "ENDOSCOPY"})
            if request.status_code == 202:
                outcome = self.wait(request.json())
                assert outcome["status"] == "FAILED", outcome
                reason = outcome.get("last_error")
            else:
                assert request.status_code == 400, request.text
                reason = request.json().get("detail")
            listed = self.call("GET", f"/uploads/{bad['id']}/research-inference")["runs"]
            assert not any(row.get("research_output") for row in listed)
            refusals.append({"input": label, "status": "REFUSED", "reason": reason, "prediction_produced": False})
        save_json(self.out / "refusals.json", refusals)
        return {"status": "VERIFIED", "case_id": cid, "upload_id": upload["id"], "run_id": run["id"],
                "model_id": MODEL_ID, "reference_comparison": comparison, "parity_exact": differing == 0,
                "reload_output_equal": True, "refusals": refusals, "source_path": str(image_path)}

    def persistence(self):
        checks = {}
        document = read_json(self.out / "document-evidence.json")
        cid = document["case"]["id"]
        checks["document_measurements_equal"] = self.call("GET", f"/cases/{cid}/measurements") == document["measurements"]
        image = read_json(self.out / "image-evidence.json")
        runs = self.call("GET", f"/uploads/{image['upload']['id']}/research-inference")["runs"]
        run = next(row for row in runs if row["id"] == image["run"]["id"])
        checks["image_output_equal"] = run["research_output"] == image["run"]["research_output"]
        checks["image_review_equal"] = run["latest_review"] == image["run"]["latest_review"]
        result = {"status": "VERIFIED" if all(checks.values()) else "BLOCKED", "checks": checks,
                  "document_case_id": cid, "image_case_id": image["case"]["id"], "image_run_id": run["id"],
                  "scope": "Stored evidence compared after operator restart of isolated QA API/worker", "private_database_used": False}
        save_json(self.out / "persistence.json", result)
        assert all(checks.values()), result
        return result


def pdf_page_image_bytes():
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 35)
    for i in range(16):
        draw.text((60, 60 + i * 75), f"SYNTHETIC LAB REPORT   Hemoglobin 12.4 g/dL   row {i}", font=font, fill="black")
    output = io.BytesIO(); image.save(output, format="PNG")
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/review-2026-11-13/workflows")
    parser.add_argument("--only", choices=["document", "imaging", "persistence"])
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    # The direct-path comparison must not bind even a read-only import to a
    # development/patient database. API/worker state comes solely from QA.
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DATABASE_URL"] = f"sqlite:///{(args.out.resolve() / 'direct-control.db').as_posix()}"
    os.environ["UPLOAD_DIR"] = str(args.out.resolve() / "direct-control-uploads")
    os.environ["MEDTWIN_USAGE_PROFILE"] = "research"
    runner = Runner(read_json(args.state / "stack.json"), args.out)
    result = read_json(args.out / "workflow-results.json") if args.only and (args.out / "workflow-results.json").exists() else {"scope": "ISOLATED_RESEARCH_SOFTWARE_DEMONSTRATION", "workflows": {}}
    result["recorded_at"] = datetime.now(timezone.utc).isoformat()
    for name, task in [("document", runner.document), ("imaging", runner.imaging), ("persistence", runner.persistence)]:
        if not args.only and name == "persistence":
            continue
        if args.only and name != args.only:
            continue
        print(f"Running {name} workflow", flush=True)
        try:
            result["workflows"][name] = task()
        except Exception as exc:
            result["workflows"][name] = {"status": "BLOCKED", "exception": type(exc).__name__, "reason": str(exc)}
        save_json(args.out / "workflow-results.json", result)
        print(f"{name}: {result['workflows'][name]['status']}", flush=True)
    return 0 if all(item["status"] == "VERIFIED" for item in result["workflows"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
