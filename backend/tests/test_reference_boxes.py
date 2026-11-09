"""Reference boxes as a GROUND_TRUTH layer and per-image agreement with a detection run (synthetic data)."""
import io
import json

import pytest
from PIL import Image

from app.models.entities import EvidenceStatus, Finding, InferenceRun, ModalityType, ReferenceAnnotation
from app.services import reference_annotations as ra
from tests.conftest import get_auth_headers


@pytest.mark.parametrize("content", [
    json.dumps({"boxes": [[10, 10, 50, 60]]}).encode(),
    json.dumps([[10, 10, 50, 60]]).encode(),
    json.dumps([{"bbox": [10, 10, 40, 50]}]).encode(),
    b"0 0.3 0.35 0.4 0.5\n",               # YOLO box on a 100 x 100 image
    b"0 0.1 0.1 0.5 0.1 0.5 0.6 0.1 0.6\n",  # YOLO polygon
])
def test_box_formats_read_to_source_pixels(content):
    assert ra.read_boxes(content, [100, 100]) == [[10.0, 10.0, 50.0, 60.0]]


@pytest.mark.parametrize("content,code", [
    (b"[[50, 10, 10, 60]]", "BOX_INVALID"),
    (b"[[10, 10, 150, 60]]", "BOX_OUTSIDE_IMAGE"),
    (b"not boxes at all", "BOXES_UNREADABLE"),
])
def test_invalid_boxes_are_refused(content, code):
    with pytest.raises(ra.ReferenceAnnotationError, match=code):
        ra.read_boxes(content, [100, 100])


def detection(boxes):
    return {"type": "detection", "class": "target", "image_size": [100, 100], "display_score_threshold": 0.5,
            "boxes": [{"bbox_xyxy": box, "score": score, "above_display_threshold": score >= 0.5} for box, score in boxes]}


def test_matching_is_one_to_one_above_the_display_threshold():
    annotation = ReferenceAnnotation(id=1, kind=ra.BOXES, source="DATASET_PUBLISHER_ANNOTATION", source_detail="fixture", class_name="target",
                                     image_size=[100, 100], boxes=[[10, 10, 50, 50], [60, 60, 90, 90]])
    result = ra.compare(detection([([12, 12, 50, 50], 0.9), ([11, 11, 49, 51], 0.8), ([60, 60, 90, 90], 0.3), ([0, 0, 5, 5], 0.7)]), annotation)
    assert (result["matched"], result["model_only"], result["reference_only"]) == (1, 2, 1)
    assert result["precision"] == pytest.approx(1 / 3, abs=1e-4) and result["recall"] == 0.5
    assert result["reference_only_boxes"] == [[60, 60, 90, 90]], "a box below the display threshold does not count"


def test_reference_boxes_attach_and_compare_through_the_api(client, db_session, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-BOXES"}).json()["id"]
    image = io.BytesIO()
    Image.new("RGB", (100, 100), "grey").save(image, "PNG")
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"},
                         files={"file": ("frame.png", image.getvalue(), "image/png")}).json()
    response = client.post(f"/api/v1/uploads/{upload['id']}/reference-boxes", headers=headers,
                           data={"source": "DATASET_PUBLISHER_ANNOTATION", "source_detail": "Synthetic fixture boxes", "class_name": "target"},
                           files={"boxes": ("boxes.json", json.dumps({"boxes": [[10, 10, 50, 50]]}).encode(), "application/json")})
    assert response.status_code == 201, response.text
    reference = response.json()
    assert reference["kind"] == ra.BOXES and reference["layer"] == "GROUND_TRUTH" and reference["boxes"] == [[10.0, 10.0, 50.0, 50.0]]
    run = InferenceRun(case_id=case_id, file_id=upload["id"], modality=ModalityType.IMAGE, model_name="fixture-detector", model_version="fixture",
                       preprocessing_version="fixture", status=EvidenceStatus.COMPLETED)
    db_session.add(run)
    db_session.flush()
    output = {**detection([([11, 11, 50, 50], 0.9)]), "exif_orientation_applied": 1}
    db_session.add(Finding(case_id=case_id, inference_run_id=run.id, modality=ModalityType.IMAGE, category="Research model output", label="fixture",
                           mapping_status="L1", is_demo=False, evidence_provenance={"source": "MODEL_INFERENCE", "output": output}))
    db_session.commit()
    comparison = client.get(f"/api/v1/research-inference/{run.id}/reference-comparison/{reference['id']}", headers=headers)
    assert comparison.status_code == 200, comparison.text
    assert comparison.json()["matched"] == 1 and comparison.json()["precision"] == 1.0
    other = get_auth_headers(test_users["clinician_b"])
    assert client.get(f"/api/v1/research-inference/{run.id}/reference-comparison/{reference['id']}", headers=other).status_code == 403


def test_box_references_must_name_the_runs_class_and_one_yolo_class():
    annotation = ReferenceAnnotation(id=2, kind=ra.BOXES, source="DATASET_PUBLISHER_ANNOTATION", source_detail="fixture", class_name="humerus",
                                     image_size=[100, 100], boxes=[[10, 10, 50, 50]])
    run = {**detection([([10, 10, 50, 50], 0.9)]), "class": "fracture"}
    with pytest.raises(ra.ReferenceAnnotationError, match="CLASS_MISMATCH"):
        ra.compare(run, annotation)
    two_classes = b"0 0.3 0.35 0.4 0.5\n4 0.7 0.7 0.1 0.1\n"
    with pytest.raises(ra.ReferenceAnnotationError, match="MULTICLASS_YOLO_REFERENCE"):
        ra.read_boxes(two_classes, [100, 100])
    assert ra.read_boxes(two_classes, [100, 100], yolo_class=0) == [[10.0, 10.0, 50.0, 60.0]]
