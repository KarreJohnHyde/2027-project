"""Synthetic acceptance tests; no patient files or clinical accuracy claims."""
import hashlib
import io
from datetime import datetime, timedelta

import numpy as np
import pytest
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, text

from app.models.entities import (Case, ClinicalReportStatement, EvidenceStatus, Finding, ForecastRecord,
                                HumanReview, InferenceRun, MedicalMeasurement, ModalityType, UploadedFile)
from app.services import film_processing, image_ood, model_inference
from app.services.evidence_synthesis import synthesize
from app.services.research_baselines import evaluate
from tests.conftest import get_auth_headers


def montage(columns=5, rows=2):
    image = Image.new("RGB", (columns * 200, rows * 240), "black")
    draw = ImageDraw.Draw(image)
    for row in range(rows):
        for col in range(columns):
            x, y = col * 200 + 15, row * 240 + 10
            draw.ellipse((x, y, x + 170, y + 215), fill=(55, 95, 110), outline="white", width=12)
            draw.ellipse((x + 22, y + 90, x + 45, y + 115), fill=(230, 65, 55))
    data = io.BytesIO()
    image.save(data, "PNG")
    return data.getvalue()


@pytest.mark.parametrize("columns,rows", [(5, 2), (1, 1)])
def test_film_panels_preserve_source_geometry_and_marks(tmp_path, columns, rows):
    path = tmp_path / "film.png"
    path.write_bytes(montage(columns, rows))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = film_processing.assess_raster(path)
    assert len(result["panels"]) == columns * rows
    assert result["source_type"] == ("FILM_MONTAGE_CANDIDATE" if columns * rows > 1 else "FILM_SLICE_CANDIDATE")
    assert result["spatial_metadata_available"] is False
    assert result["source_annotations"]["coloured_marks_suspected"]
    assert not result["source_annotations"]["is_ai_mask"]
    assert [(p["row"], p["column"]) for p in result["panels"]] == [(r, c) for r in range(rows) for c in range(columns)]
    assert Image.open(io.BytesIO(film_processing.render_panel(path, result, 0))).size[0] > 100
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    with pytest.raises(model_inference.InferenceNotPermitted, match="PHOTOGRAPHED_FILM"):
        model_inference.check_document_photograph(path)


def test_ambiguous_raster_is_never_claimed_native_dicom(tmp_path):
    path = tmp_path / "unknown.png"
    Image.new("RGB", (240, 240), "grey").save(path)
    result = film_processing.assess_raster(path)
    assert result["source_type"] == "AMBIGUOUS_RASTER"
    assert result["modality"] == "UNKNOWN"
    assert result["panels"] == []


def test_monochrome_digital_slice_is_not_assumed_to_be_photographed(tmp_path):
    path = tmp_path / "digital-slice.png"
    Image.open(io.BytesIO(montage(1, 1))).convert("L").save(path)
    assert film_processing.assess_raster(path)["inference_eligibility"] == "MODEL_SPECIFIC_CHECKS_REQUIRED"


def test_header_date_reread_preserves_raw_text_and_source_box(tmp_path, monkeypatch):
    from app.services import ocr
    from app.services.nlp_processor import _append_header_dates, extract_documented_attributes
    path = tmp_path / "header.png"
    Image.new("RGB", (1000, 1000), "white").save(path)
    monkeypatch.setattr(ocr, "ocr_image", lambda image: ocr.OcrPage(text="Date:MARO7TH 2023", engine="synthetic",
                        line_count=1, mean_confidence=.9, image_width=480, image_height=180,
                        lines=[{"text": "Date:MARO7TH 2023", "box": [1, 2, 100, 20], "confidence": .9}]))
    pages, meta = ["Original extraction"], {"lines": []}
    _append_header_dates(path, 0, pages, meta)
    assert pages[0].startswith("Original extraction\n")
    result = extract_documented_attributes(pages[0])[0]
    assert result["value_text"] == "2023-03-07"
    assert result["parse_status"] == "OCR_DAY_ZERO_REQUIRES_REVIEW"
    assert result["raw_text"] == "MARO7TH 2023"
    assert meta["lines"][0]["bbox_xyxy"] == [481, 122, 580, 140]


def test_ood_controls_and_nonfinite_fail_closed():
    rng = np.random.default_rng(18)
    fit = rng.normal(size=(160, 10))
    calibration = rng.normal(size=(80, 10))
    reference = image_ood.fit_reference([fit], [calibration])
    threshold = reference["threshold"]
    assert np.median(image_ood.score(reference, [calibration])) < threshold
    assert image_ood.score(reference, [np.full((1, 10), 50.)])[0] > threshold
    for value in (np.nan, np.inf, 1e308):
        with pytest.raises(image_ood.OodReferenceError, match="NONFINITE"):
            image_ood.score(reference, [np.full((1, 10), value)])
    with pytest.raises(image_ood.OodReferenceError, match="MISMATCH"):
        image_ood.score(reference, [np.zeros((1, 9))])
    assert reference["threshold"] == threshold


def case_and_upload(db, user, tmp_path, name="evidence.txt", data=b"Synthetic evidence"):
    case = Case(pseudonymous_id="SYNTHETIC-HETEROGENEOUS", created_by_id=user.id)
    db.add(case); db.flush()
    path = tmp_path / name
    path.write_bytes(data)
    upload = UploadedFile(case_id=case.id, filename=name, stored_filename=name, file_path=str(path),
                          file_hash=hashlib.sha256(data).hexdigest(), file_size_bytes=len(data), mime_type="text/plain",
                          modality=ModalityType.REPORT, is_associated=True)
    db.add(upload); db.flush()
    run = InferenceRun(case_id=case.id, file_id=upload.id, modality=ModalityType.REPORT,
                       model_name="rules", model_version="test", preprocessing_version="test", status=EvidenceStatus.COMPLETED)
    db.add(run); db.flush()
    finding = Finding(case_id=case.id, inference_run_id=run.id, modality=ModalityType.REPORT,
                      category="Report", label="Extracted statements", mapping_status="L1", is_demo=False)
    db.add(finding); db.flush()
    return case, upload, finding


def test_synthesis_deduplicates_and_preserves_abstention(db_session, test_users, tmp_path):
    case, upload, finding = case_and_upload(db_session, test_users["clinician_a"], tmp_path)
    for page in (4, 5):
        db_session.add(ClinicalReportStatement(case_id=case.id, finding_id=finding.id, entity="Cerebral contusion",
                       negation="AFFIRMED", laterality="RIGHT", temporality="CURRENT", anatomical_site="Right parietal lobe",
                       certainty="CERTAIN", source_span="Right high parietal lobe hemorrhagic contusion.", source_page=page,
                       atlas_structure_id="nervous.parietal_lobe"))
    db_session.add(InferenceRun(case_id=case.id, file_id=upload.id, modality=ModalityType.IMAGE,
                   model_name="rsna", model_version="NOT_RUN", preprocessing_version="PREFLIGHT",
                   status=EvidenceStatus.ABSTAIN, error_message="MODEL_INPUT_OUT_OF_DISTRIBUTION"))
    db_session.commit()
    result = synthesize(case.id, db_session)
    assert len(result["report_findings"]) == 1
    item = result["report_findings"][0]
    assert [s["page"] for s in item["sources"]] == [4, 5]
    assert item["review_status"] == "PENDING_HUMAN_REVIEW"
    assert not item["patient_registered"]
    assert item["independent_image_confirmation"] == "NOT_ESTABLISHED"
    assert result["abstentions"][0]["status"] == "ABSTAIN"
    assert result["overall_disease_probability"] is None
    upload.is_associated = False; db_session.commit()
    assert synthesize(case.id, db_session)["report_findings"] == []


def test_synthesis_groups_ocr_variants_without_merging_distinct_assertions(db_session, test_users, tmp_path):
    case, upload, finding = case_and_upload(db_session, test_users["clinician_a"], tmp_path)
    for entity, site, side, assertion, span in [
        ("Cerebral contusion", "Right high parietal lobe", "right", "AFFIRMED", "Right high parietal lobe hemorrhagic contusion"),
        ("Cerebral contusion", "RIGHT HIGH PARIETAL LOBE", "RIGHT", "AFFIRMED", "RIGHT HIGH PARIETAL LOBE HEMORRHAGIC CONTUSION"),
        ("Cerebral contusion", "Right high parietalobe", "right", "AFFIRMED", "Right high parietalobe hemorrhagic contusion"),
        ("Cerebral contusion", "Left high parietal lobe", "left", "AFFIRMED", "Left high parietal lobe hemorrhagic contusion"),
        ("Cerebral contusion", "Right high parietal lobe", "right", "NEGATED", "No right high parietal lobe contusion"),
        ("Cerebral oedema", "Right high parietal lobe", "right", "AFFIRMED", "Mild cerebral oedema"),
        ("Edema", "Right high parietalobe", "right", "AFFIRMED", "Mild perilesional edema"),
        ("Lesion", None, None, "NEGATED", "No obvious pituitary lesions"),
        ("Lesion", None, None, "NEGATED", "No obvious focal lesion is seen"),
        ("Edema", "right ankle", "right", "AFFIRMED", "Right ankle edema"),
    ]:
        db_session.add(ClinicalReportStatement(case_id=case.id, finding_id=finding.id, entity=entity,
            anatomical_site=site, laterality=side, negation=assertion, temporality="CURRENT", certainty="CERTAIN",
            source_span=span, source_page=4))
    for _ in range(3):
        db_session.add(InferenceRun(case_id=case.id, file_id=upload.id, modality=ModalityType.IMAGE,
            model_name="rsna", model_version="NOT_RUN", preprocessing_version="PREFLIGHT",
            status=EvidenceStatus.ABSTAIN, error_message="MODEL_INPUT_PHOTOGRAPHED_FILM: suspected montage"))
    db_session.commit()
    result = synthesize(case.id, db_session)
    assert len(result["report_findings"]) == 7
    contusions = [r for r in result["report_findings"] if r["entity"] == "Cerebral contusion"]
    assert sorted(len(r["sources"]) for r in contusions) == [1, 1, 3]
    assert len([r for r in result["report_findings"] if r["entity"] == "Lesion"]) == 2
    oedema = next(r for r in result["report_findings"] if r["entity"] == "Cerebral oedema")
    assert len(oedema["sources"]) == 2
    assert sum(len(r["sources"]) for r in result["report_findings"]) == 10
    assert len(result["contradictions"]) == 1
    assert len(result["abstentions"]) == 1
    assert result["abstentions"][0]["attempt_count"] == 3
    assert len(result["abstentions"][0]["run_ids"]) == 3
    assert result["evidence_mask"]["REPORT"] == 1
    assert result["model_output_mask"]["REPORT"] == 0
    assert result["abstentions"][0]["status"] == "ABSTAIN"


REPORT = (b"CT BRAIN REPORT\nStudy date: 2023-03-07\nFINDINGS:\n"
          b"RighthighparietallobeHemorrhagiccontusionwithmildperilesionaledema.\n"
          b"No midline shift.\nNo fractures noted.\nRight parietal region scalp soft tissue swelling.\n"
          b"IMPRESSION:\nRight high parietal lobe hemorrhagic contusion.\n")


def test_complete_report_film_link_synthesis_workflow(client, db_session, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-CT-WORKFLOW"}).json()["id"]
    uploads = []
    for name, data, mime in (("report.txt", REPORT, "text/plain"), ("montage.png", montage(), "image/png")):
        response = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers,
                               files={"file": (name, data, mime)}, data={"deidentified": "true"})
        assert response.status_code == 201, response.text
        uploads.append(response.json())
    report, film = uploads
    response = client.post(f"/api/v1/uploads/{report['id']}/analysis-jobs", headers=headers)
    assert response.status_code == 201, response.text
    metadata = client.get(f"/api/v1/uploads/{film['id']}/imaging/metadata", headers=headers).json()
    assert len(metadata["input_assessment"]["panels"]) == 10
    assert metadata["inference"]["status"] == "ABSTAIN"
    assert "Photographed film" in metadata["inference"]["reason"]
    preview = client.get(f"/api/v1/uploads/{film['id']}/imaging/film-panels/0", headers=headers)
    assert preview.status_code == 200 and preview.headers["x-source-sha256"] == film["file_hash"]
    exam = client.post(f"/api/v1/cases/{case_id}/examinations", headers=headers,
                       json={"exam_date": "2023-03-07T00:00:00", "modality": "IMAGE"}).json()
    for upload in uploads:
        url = f"/api/v1/uploads/{upload['id']}/examination"
        assert client.patch(url, headers=headers, json={"examination_id": exam["id"], "same_patient_confirmed": False}).status_code == 400
        assert client.patch(url, headers=headers, json={"examination_id": exam["id"], "same_patient_confirmed": True}).status_code == 200
    response = client.post(f"/api/v1/cases/{case_id}/fusion", headers=headers)
    assert response.status_code == 200, response.text
    synthesis = response.json()["evidence_synthesis"]
    entities = {f["entity"]: f for f in synthesis["report_findings"]}
    assert {"Cerebral contusion", "Cerebral oedema", "Midline shift", "Fracture", "Scalp soft-tissue swelling"} <= entities.keys()
    assert entities["Midline shift"]["assertion"] == entities["Fracture"]["assertion"] == "NEGATED"
    assert entities["Cerebral contusion"]["laterality"] == "right"
    assert all(source["page"] == 1 for item in entities.values() for source in item["sources"])
    assert synthesis["overall_disease_probability"] is None
    stored = client.get(f"/api/v1/cases/{case_id}/fusion/results/{response.json()['id']}", headers=headers)
    assert stored.json()["evidence_synthesis"] == synthesis
    other = get_auth_headers(test_users["clinician_b"])
    for url in (f"/api/v1/cases/{case_id}/evidence-synthesis", f"/api/v1/uploads/{film['id']}/imaging/film-panels/0"):
        assert client.get(url, headers=other).status_code == 403


def test_multimodel_records_unavailable_models_without_predictions(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-MULTIMODEL"}).json()["id"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"},
                         files={"file": ("film.png", montage(), "image/png")}).json()
    url = f"/api/v1/uploads/{upload['id']}/multimodel"
    request = {"model_ids": ["unavailable-fixture-a", "unavailable-fixture-b"], "declared_input_type": "HEAD_CT"}
    response = client.post(url, headers=headers, json=request)
    assert response.status_code == 202, response.text
    job = response.json()["queued_job"]
    assert job["status"] == "SUCCEEDED", job
    assert [r["status"] for r in job["result_ref"]["results"]] == ["ABSTAIN", "ABSTAIN"]
    assert job["result_ref"]["analysis_status"] == "ABSTAIN"
    assert job["result_ref"]["models_with_outputs"] == 0
    assert "all selected models abstained" in job["message"]
    assert response.json()["probability_combination"] == "NOT_ESTABLISHED"
    assert client.post(url, headers=headers, json={**request, "model_ids": ["same", "same"]}).status_code == 400
    other = get_auth_headers(test_users["clinician_b"])
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=other).status_code == 403
    result = client.get(f"/api/v1/cases/{case_id}/evidence-synthesis", headers=headers).json()
    assert len(result["abstentions"]) == 2
    assert result["model_findings"] == []


def test_pdf_panel_previews_are_source_linked_and_authorized(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-PDF-PANELS"}).json()["id"]
    output = io.BytesIO()
    Image.open(io.BytesIO(montage())).save(output, "PDF")
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"},
                         files={"file": ("film.pdf", output.getvalue(), "application/pdf")}).json()
    url = f"/api/v1/uploads/{upload['id']}/pages/1"
    assessment = client.get(url + "/film-assessment", headers=headers)
    assert assessment.status_code == 200, assessment.text
    assert len(assessment.json()["panels"]) == 10
    panel = client.get(url + "/film-panels/0", headers=headers)
    assert panel.status_code == 200 and panel.headers["x-source-page"] == "1"
    assert client.get(url + "/film-panels/0", headers=get_auth_headers(test_users["clinician_b"])).status_code == 403


def test_multimodel_continues_after_adapter_failure(client, test_users, monkeypatch):
    from app.services import job_handlers
    attempted = []

    def execute(db, upload, model_id, *args):
        attempted.append(model_id)
        if model_id == "broken-adapter":
            raise RuntimeError("synthetic adapter failure")
        raise model_inference.InferenceNotPermitted("MODEL_INPUT_PHOTOGRAPHED_FILM: synthetic film")

    monkeypatch.setattr(job_handlers, "execute_research_inference", execute)
    headers = get_auth_headers(test_users["clinician_a"])
    case = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-BATCH-FAILURE"}).json()
    upload = client.post(f"/api/v1/cases/{case['id']}/uploads", headers=headers, data={"deidentified": "true"},
        files={"file": ("film.png", montage(), "image/png")}).json()
    result = client.post(f"/api/v1/uploads/{upload['id']}/multimodel", headers=headers,
        json={"model_ids": ["broken-adapter", "second-adapter"], "declared_input_type": "HEAD_CT"})
    assert result.status_code == 202, result.text
    outcome = result.json()["queued_job"]["result_ref"]
    assert attempted == ["broken-adapter", "second-adapter"]
    assert [item["status"] for item in outcome["results"]] == ["ERROR", "ABSTAIN"]
    assert outcome["analysis_status"] == "ERROR"
    assert outcome["models_with_outputs"] == 0


def add_measurements(db, case, upload, finding, user, count):
    db.add(HumanReview(finding_id=finding.id, reviewer_id=user.id, review_status="CONFIRMED", original_output_preserved=True))
    for i in range(count):
        db.add(MedicalMeasurement(case_id=case.id, source_file_id=upload.id, finding_id=finding.id,
                                 name="synthetic_metric", display_name="Synthetic metric", value=10. + i * 2,
                                 raw_value=str(10 + i * 2), raw_unit="mm", unit="mm", source_span=f"Synthetic metric {10 + i * 2} mm",
                                 source_span_start=0, source_span_end=20, documented_date=(datetime(2024, 1, 1) + timedelta(days=i * 30)).date().isoformat(),
                                 specimen="SYNTHETIC", laboratory_method="SYNTHETIC"))
    db.commit()


@pytest.mark.parametrize("count,method,available", [(1, "persistence", False), (2, "linear", False), (3, "persistence", True), (5, "linear", True)])
def test_research_baselines_use_real_dated_values(db_session, test_users, tmp_path, count, method, available):
    user = test_users["clinician_a"]
    case, upload, finding = case_and_upload(db_session, user, tmp_path)
    add_measurements(db_session, case, upload, finding, user, count)
    result = evaluate(case.id, db_session, "synthetic_metric", "mm", 30, method)
    assert (result["predicted_value"] is not None) == available
    assert result["baseline_analysis"]["prediction_interval"] is None
    if available:
        assert len(result["baseline_analysis"]["backtest"]["folds"]) >= 2
        expected = 10 + (count - 1) * 2 if method == "persistence" else 10 + count * 2
        assert result["predicted_value"] == pytest.approx(expected)
    evaluate(case.id, db_session, "synthetic_metric", "mm", 30, method)
    assert db_session.query(ForecastRecord).filter_by(case_id=case.id).count() == 2


def test_new_migrations_preserve_existing_records(tmp_path):
    from app.migrations import run_migrations
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE clinical_report_statements (id INTEGER PRIMARY KEY, source_span TEXT)"))
        connection.execute(text("CREATE TABLE multimodal_fusion_records (id INTEGER PRIMARY KEY, fused_prediction JSON)"))
        connection.execute(text("CREATE TABLE forecast_records (id INTEGER PRIMARY KEY, predicted_value FLOAT)"))
        connection.execute(text("INSERT INTO clinical_report_statements VALUES (1, 'Original evidence')"))
        connection.execute(text("INSERT INTO forecast_records VALUES (1, 12.5)"))
    run_migrations(engine)
    assert run_migrations(engine) == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT source_span, source_page FROM clinical_report_statements")).one() == ("Original evidence", None)
        assert connection.execute(text("SELECT predicted_value, baseline_analysis FROM forecast_records")).one() == (12.5, None)
    engine.dispose()


def test_guest_cannot_read_real_cases_even_when_shared_mode_is_enabled(client, test_users, monkeypatch):
    from app import config
    monkeypatch.setattr(config, "SHARED_WORKSPACE", True)
    owner = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=owner, json={"pseudonymous_id": "PRIVATE-FROM-DEMO"}).json()["id"]
    session = client.post("/api/v1/auth/guest").json()
    guest = {"Authorization": f"Bearer {session['access_token']}"}
    assert case_id not in {case["id"] for case in client.get("/api/v1/cases", headers=guest).json()}
    assert client.get(f"/api/v1/cases/{case_id}/evidence-synthesis", headers=guest).status_code == 403
