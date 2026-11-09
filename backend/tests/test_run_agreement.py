"""Model-versus-model agreement on one upload (synthetic outputs; neither is ground truth)."""
import io

import numpy as np
import pytest
from PIL import Image

from app.models.entities import EvidenceStatus, Finding, InferenceRun, ModalityType
from app.services import run_agreement
from app.services.reference_annotations import encode
from tests.conftest import get_auth_headers


def segmentation(region):
    mask = np.zeros((20, 20), dtype=bool)
    mask[region] = True
    return {"type": "segmentation", "image_size": [20, 20], "segments": [{"segment": "polyp", "rle": encode(mask)}]}


def test_segmentation_agreement_is_dice_between_the_two_masks():
    result = run_agreement.agreement(segmentation(np.s_[0:10, 0:10]), segmentation(np.s_[0:10, 5:15]))
    assert result["kind"] == "segmentation" and result["foreground_dice"] == pytest.approx(0.5)
    assert result["shared_classes"]["polyp"]["iou"] == pytest.approx(1 / 3, abs=1e-4)
    assert "Neither output is ground truth" in result["semantics"]


def test_detection_agreement_matches_boxes_one_to_one():
    def detection(boxes):
        return {"type": "detection", "class": "stone", "image_size": [100, 100],
                "boxes": [{"bbox_xyxy": box, "score": 0.9, "above_display_threshold": True} for box in boxes]}
    result = run_agreement.agreement(detection([[10, 10, 40, 40], [60, 60, 80, 80]]), detection([[11, 11, 40, 40]]))
    assert (result["matched"], result["only_first"], result["only_second"]) == (1, 1, 0)


def test_different_kinds_and_abstentions_are_not_compared():
    with pytest.raises(run_agreement.NotComparable, match="NOT_COMPARABLE"):
        run_agreement.agreement(segmentation(np.s_[0:5, 0:5]), {"type": "classification", "classes": [], "top_class": "x"})
    with pytest.raises(run_agreement.NotComparable, match="NO_MODEL_OUTPUT"):
        run_agreement.agreement(None, segmentation(np.s_[0:5, 0:5]))


def test_agreement_endpoint_requires_the_same_upload_and_case_access(client, db_session, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-AGREEMENT"}).json()["id"]
    image = io.BytesIO()
    Image.new("RGB", (20, 20), "grey").save(image, "PNG")
    uploads = [client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"},
                           files={"file": (f"frame{index}.png", image.getvalue() + bytes([index]), "image/png")}).json()["id"] for index in range(2)]
    runs = []
    for upload_id, region in ((uploads[0], np.s_[0:10, 0:10]), (uploads[0], np.s_[0:10, 0:10]), (uploads[1], np.s_[0:10, 0:10])):
        run = InferenceRun(case_id=case_id, file_id=upload_id, modality=ModalityType.IMAGE, model_name="fixture", model_version="fixture",
                           preprocessing_version="fixture", status=EvidenceStatus.COMPLETED)
        db_session.add(run)
        db_session.flush()
        db_session.add(Finding(case_id=case_id, inference_run_id=run.id, modality=ModalityType.IMAGE, category="Research model output", label="fixture",
                               mapping_status="L1", is_demo=False, evidence_provenance={"source": "MODEL_INFERENCE", "output": segmentation(region)}))
        runs.append(run.id)
    db_session.commit()
    same = client.get(f"/api/v1/research-inference/{runs[0]}/agreement/{runs[1]}", headers=headers)
    assert same.status_code == 200 and same.json()["foreground_dice"] == 1.0
    assert client.get(f"/api/v1/research-inference/{runs[0]}/agreement/{runs[2]}", headers=headers).status_code == 400
    assert client.get(f"/api/v1/research-inference/{runs[0]}/agreement/{runs[1]}", headers=get_auth_headers(test_users["clinician_b"])).status_code == 403
