"""Reviewer corrections of a volumetric run, one axial plane at a time (synthetic volume output)."""
import io

import numpy as np
from PIL import Image

from app.models.entities import EvidenceStatus, Finding, InferenceRun, ModalityType
from app.services.reference_annotations import encode
from tests.conftest import get_auth_headers

NI, NJ, NK = 20, 16, 4


def volume_output():
    """Class 1 'lesion' as a 4 x 4 square on planes 1 and 2; stored as labels[:, :, k].T, i.e. (j, i)."""
    slices = []
    for k in range(NK):
        mask = np.zeros((NJ, NI), dtype=bool)
        if k in (1, 2):
            mask[4:8, 4:8] = True
        slices.append({"slice_index": k, "segments": [{"class_index": 1, "area_px": int(mask.sum()), "rle": encode(mask)}] if mask.any() else []})
    return {"type": "volume_segmentation", "structures": [{"class_index": 1, "structure": "lesion", "voxels": 32, "volume_ml": 0.032}],
            "slices": slices, "volume_shape_ijk": [NI, NJ, NK], "voxel_spacing_mm": [1.0, 1.0, 1.0], "voxel_volume_ml": 0.001}


def png(mask: np.ndarray) -> bytes:
    data = io.BytesIO()
    Image.fromarray((mask * 255).astype(np.uint8)).save(data, "PNG")
    return data.getvalue()


def test_slice_corrections_change_the_corrected_volume_not_the_run(client, db_session, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "SYNTHETIC-VOLUME-EDIT"}).json()["id"]
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "grey").save(image, "PNG")
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"},
                         files={"file": ("frame.png", image.getvalue(), "image/png")}).json()
    run = InferenceRun(case_id=case_id, file_id=upload["id"], modality=ModalityType.IMAGE, model_name="fixture-volume", model_version="fixture",
                       preprocessing_version="fixture", status=EvidenceStatus.COMPLETED)
    db_session.add(run)
    db_session.flush()
    output = volume_output()
    db_session.add(Finding(case_id=case_id, inference_run_id=run.id, modality=ModalityType.IMAGE, category="Research model output", label="fixture",
                           mapping_status="L1", is_demo=False, evidence_provenance={"source": "MODEL_INFERENCE", "output": output}))
    db_session.commit()
    url = f"/api/v1/research-inference/{run.id}/volume-slice-corrections"
    bigger = np.zeros((NJ, NI), dtype=np.uint8)
    bigger[4:8, 4:12] = 1  # plane 1: 16 voxels added
    response = client.post(url, headers=headers, data={"slice_index": "1", "class_name": "lesion", "note": "extend"},
                           files={"mask": ("slice.png", png(bigger), "image/png")})
    assert response.status_code == 201, response.text
    summary = response.json()["summary"]
    lesion = summary["structures"][0]
    assert (lesion["model_voxels"], lesion["corrected_voxels"], lesion["slices_corrected"]) == (32, 48, 1)
    assert summary["corrected_slices"][0]["voxels_added"] == 16 and response.json()["layer"] == "REVIEWER_CORRECTION"
    # A newer correction of the same plane replaces the earlier one; an empty plane removes the model's voxels there.
    client.post(url, headers=headers, data={"slice_index": "1", "class_name": "lesion"}, files={"mask": ("slice.png", png(np.zeros((NJ, NI), np.uint8)), "image/png")})
    listed = client.get(url, headers=headers).json()
    assert listed["structures"][0]["corrected_voxels"] == 16 and len(listed["corrected_slices"]) == 1
    assert db_session.get(Finding, run.findings[0].id).evidence_provenance["output"]["structures"][0]["voxels"] == 32, "the run is unchanged"
    for data, code in (({"slice_index": "9", "class_name": "lesion"}, "SLICE_OUTSIDE_VOLUME"), ({"slice_index": "0", "class_name": "liver"}, "CLASS_NOT_IN_RUN")):
        refused = client.post(url, headers=headers, data=data, files={"mask": ("slice.png", png(bigger), "image/png")})
        assert refused.status_code == 400 and code in refused.text
    wrong = client.post(url, headers=headers, data={"slice_index": "0", "class_name": "lesion"}, files={"mask": ("slice.png", png(np.zeros((NI, NJ), np.uint8)), "image/png")})
    assert wrong.status_code == 400 and "MASK_SIZE_MISMATCH" in wrong.text
    assert client.get(url, headers=get_auth_headers(test_users["clinician_b"])).status_code == 403
