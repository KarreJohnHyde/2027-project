"""Execute a fictional scanned-source crop through the canonical authorized API."""
from pathlib import Path
import json
from datetime import datetime, timezone
from review_run_workflows import Runner, read_json, save_json, pdf_fixture

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/completion-2026-11-13/word-review"


def main():
    runner = Runner(read_json(ROOT / ".cache/review-20261113/stack.json"), OUT)
    report = {"scope": "FICTIONAL_SCANNED_WORD_SOURCE_SOFTWARE_CONTROL_NOT_ACCURACY_VALIDATION", "recorded_at": datetime.now(timezone.utc).isoformat(), "checks": []}
    def check(name, passed, **details):
        report["checks"].append({"name": name, "passed": bool(passed), **details})
        save_json(OUT / "proof.json", report)
        if not passed: raise AssertionError(name)
    cap = runner.call("GET", "/universal/ocr/upright-word/capability")
    check("Pinned evaluated commercial-permissive OCR runtime available", cap["available"])
    cases = runner.call("GET", "/cases")
    case = next((c for c in cases if c["pseudonymous_id"] == "COMPLETION-SCANNED-WORD"), None)
    if case is None:
        case = runner.call("POST", "/cases", json={"pseudonymous_id": "COMPLETION-SCANNED-WORD", "description": "Fictional single-word scanned PDF software control. No real patient."})
    uploads = runner.call("GET", f"/cases/{case['id']}/uploads")
    upload = next((u for u in uploads if u["filename"] == "fictional-word-control.pdf"), None)
    if upload is None:
        upload = runner.upload(case["id"], "fictional-word-control.pdf", pdf_fixture("Hemoglobin\nFICTIONAL SOFTWARE CONTROL - NO PATIENT", scanned=True), "application/pdf")
    job = runner.wait(runner.call("POST", f"/uploads/{upload['id']}/analysis-jobs", headers={"Idempotency-Key": f"completion-word-{upload['id']}"}))
    check("Existing whole-document worker prepares scanned-source masking metadata", job["status"] in {"SUCCEEDED", "COMPLETED"})
    run_id = job["result_ref"]["inference_run_id"] if "result_ref" in job else job["id"]
    before = runner.call("GET", f"/analysis-jobs/{run_id}")
    preview = runner.client.get(f"/uploads/{upload['id']}/pages/1/image")
    preview.raise_for_status()
    metadata = json.loads(preview.headers["X-MedTwin-Page"])
    from PIL import Image
    import io
    image = Image.open(io.BytesIO(preview.content))
    box = [42, 48, 160, 86]
    body = {"page": 1, "bbox_xyxy": box, "expected_image_size": list(image.size), "source_file_sha256": upload["file_hash"], "coordinate_space": "REPORT_PAGE_PREVIEW_110_DPI", "upright_attested": True, "single_word_attested": True, "latin_text_attested": True}
    result = runner.call("POST", f"/uploads/{upload['id']}/ocr/upright-word", json=body)
    save_json(OUT / "proposal.json", result)
    check("Actual selected word yields review-only proposal", result["status"] == "AVAILABLE" and result["text_proposal"].lower() == "hemoglobin" and result["review_required"] and not result["persisted_finding_or_correction"], case_id=case["id"], upload_id=upload["id"], preview_size=list(image.size), bbox_xyxy=box, masking=metadata["masking"])
    missing = runner.call("POST", f"/uploads/{upload['id']}/ocr/upright-word", json={**body, "upright_attested": False})
    check("Missing upright attestation refuses", missing["status"] == "REFUSED")
    wrong = runner.client.post(f"/uploads/{upload['id']}/ocr/upright-word", json={**body, "source_file_sha256": "0" * 64})
    check("Stale source hash refuses", wrong.status_code == 409)
    after = runner.call("GET", f"/analysis-jobs/{run_id}")
    check("Original extracted findings and review state remain unchanged", before == after)
    report["status"] = "VERIFIED_DECLARED_SOFTWARE_SCOPE"
    save_json(OUT / "proof.json", report)
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "case_id": case["id"], "upload_id": upload["id"]}))


if __name__ == "__main__": main()
