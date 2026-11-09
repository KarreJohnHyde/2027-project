"""Endoscopy video uploads and per-frame research inference.

The video is a synthetic clip generated inside the test (a moving bright disc), and the model calls are replaced
by deterministic stand-ins, so the test covers the video pipeline, not any model; nothing here is patient evidence."""

import io

import numpy as np
import pytest
from PIL import Image

cv2 = pytest.importorskip("cv2")

from app.services import model_inference, video_frames  # noqa: E402
from tests.conftest import get_auth_headers  # noqa: E402


def _clip(path, frames=30, fps=10.0, size=(96, 64)):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    assert writer.isOpened()
    for index in range(frames):
        frame = np.full((size[1], size[0], 3), 40, dtype=np.uint8)
        cv2.circle(frame, (10 + 2 * index, 32), 8, (230, 230, 230), -1)
        writer.write(frame)
    writer.release()
    return path


def _upload(client, headers, name, body, mime):
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": f"CASE-VIDEO-{name}"}, headers=headers).json()["id"]
    return client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (name, body, mime)}, data={"deidentified": "true"}, headers=headers)


def test_sampling_and_quality_measurements(tmp_path):
    path = _clip(tmp_path / "clip.avi")
    meta = video_frames.probe(path)
    assert meta["frame_count"] == 30 and meta["fps"] == pytest.approx(10.0) and (meta["width"], meta["height"]) == (96, 64)
    indices = video_frames.sample_indices(meta, 0.5, 100)
    assert indices == list(range(0, 30, 5))
    frames = list(video_frames.read_frames(path, indices))
    assert [index for index, _, _ in frames] == indices and frames[0][1].shape == (64, 96, 3)
    times = [seconds for _, _, seconds in frames if seconds is not None]
    assert all(abs(seconds - index / 10.0) <= 0.15 for (index, _, seconds) in frames if seconds is not None) and times
    assert len(video_frames.sample_indices({"fps": 30.0, "frame_count": 10**12}, 0.2, 240)) == 240, "a huge stated frame count is never materialised"
    quality = video_frames.frame_quality(frames[0][1])
    assert 0 < quality["brightness"] < 1 and quality["sharpness_laplacian_variance"] > 0


def test_non_video_bytes_with_a_video_name_are_refused(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    response = _upload(client, headers, "fake.mp4", b"not a video at all" * 10, "video/mp4")
    assert response.status_code == 415


def test_a_queued_video_job_refuses_an_upload_withdrawn_before_it_runs(client, test_users, tmp_path, db_session):
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from app.models.entities import UploadedFile
    from app.services import job_handlers
    from app.services.analysis_runner import AnalysisNotPermitted

    headers = get_auth_headers(test_users["clinician_a"])
    created = _upload(client, headers, "withdrawn.avi", _clip(tmp_path / "clip.avi").read_bytes(), "video/x-msvideo")
    record = db_session.get(UploadedFile, created.json()["id"])
    record.withdrawn_at = datetime.now(timezone.utc)
    db_session.commit()
    job = SimpleNamespace(file_id=record.id, case_id=record.case_id, requested_by_id=None, payload={"model_id": "x", "interval_s": 1.0, "max_frames": 5})
    with pytest.raises(AnalysisNotPermitted):
        job_handlers.video_frame_analysis(db_session, job, SimpleNamespace(progress=lambda *args: None))


def test_video_frames_are_scored_one_by_one_after_each_applicability_check(client, test_users, tmp_path, monkeypatch):
    headers = get_auth_headers(test_users["clinician_a"])
    created = _upload(client, headers, "clip.avi", _clip(tmp_path / "clip.avi").read_bytes(), "video/x-msvideo")
    assert created.status_code == 201, created.text
    upload_id = created.json()["id"]

    meta = client.get(f"/api/v1/uploads/{upload_id}/video", headers=headers)
    assert meta.status_code == 200 and meta.json()["frame_count"] == 30
    frame = client.get(f"/api/v1/uploads/{upload_id}/video/frame", params={"index": 10}, headers=headers)
    assert frame.status_code == 200 and frame.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(frame.content)).size == (96, 64)
    assert client.get(f"/api/v1/uploads/{upload_id}/video/frame", params={"index": 99}, headers=headers).status_code == 400

    fixture = {"model_id": "fixture_polyp", "display_name": "fixture polyp segmenter", "status": "READY_UNVALIDATED", "task": "semantic_segmentation",
               "inference_input": "image_2d", "supported_modalities": ["ENDOSCOPY"], "anatomy": "intestines",
               "artifact_bundle": {"checkpoint_sha256": "0" * 64, "preprocessing_version": "fixture", "dataset_version": "fixture",
                                   "dataset_license": "CC0 (synthetic test fixture)", "evaluation_report_path": "fixture", "model_card_path": "fixture"}}
    calls = {"gate": 0}

    def gate(_model, path):
        calls["gate"] += 1
        if calls["gate"] == 2:  # the second sampled frame is refused, as a frame of the wrong kind would be
            raise model_inference.InferenceNotPermitted("IMAGE_OUTSIDE_MODEL_DISTRIBUTION: fixture refusal")
        return {"status": "IN_DISTRIBUTION"}

    def segment(_model, path):
        from app.services.reference_annotations import encode

        grey = np.asarray(Image.open(path).convert("L"))
        mask = grey > 150
        return {"type": "segmentation", "image_size": [grey.shape[1], grey.shape[0]], "foreground_label": "polyp",
                "segments": [{"class_index": 1, "segment": "polyp", "area_px": int(mask.sum()), "rle": encode(mask)}]}

    monkeypatch.setattr(model_inference, "get_model", lambda model_id: fixture if model_id == "fixture_polyp" else (_ for _ in ()).throw(model_inference.InferenceNotPermitted("unknown")))
    monkeypatch.setattr(model_inference, "check_distribution", gate)
    monkeypatch.setattr(model_inference, "run_model", segment)
    monkeypatch.setattr(model_inference, "evaluation_summary", lambda model: {"fixture": True})

    body = {"model_id": "fixture_polyp", "interval_s": 1.0, "max_frames": 10, "attest_gi_endoscopy_video": True}
    assert client.post(f"/api/v1/uploads/{upload_id}/video-frame-analysis", json={**body, "attest_gi_endoscopy_video": False}, headers=headers).status_code == 422
    run = client.post(f"/api/v1/uploads/{upload_id}/video-frame-analysis", json=body, headers=headers)
    assert run.status_code == 201, run.text
    output = run.json()["research_output"]
    assert output["type"] == "video_frame_timeline" and output["sampling"]["decoded_frames"] == 3, "0, 1 and 2 s of a 3-s clip"
    assert [frame["frame_index"] for frame in output["frames"]] == [0, 10, 20]
    assert [frame["status"] for frame in output["frames"]] == ["SCORED", "REFUSED_BY_APPLICABILITY_CHECK", "SCORED"]
    assert output["scored_frames"] == 2 and output["summary"]["frames_with_mask"] == 2
    assert all(frame["result"]["area_px"] > 0 for frame in output["frames"] if frame["status"] == "SCORED")
    assert run.json()["research_provenance"]["output_status"] == "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED"

    stored = client.get(f"/api/v1/research-inference/{run.json()['id']}", headers=headers)
    assert stored.status_code == 200 and stored.json()["research_output"]["frames"] == output["frames"]


def _seg_frame(index, box):
    import numpy as np
    from app.services.reference_annotations import encode

    mask = np.zeros((60, 80), dtype=bool)
    if box:
        x1, y1, x2, y2 = box
        mask[y1:y2, x1:x2] = True
    return {"frame_index": index, "time_s": index / 10, "status": "SCORED",
            "result": {"kind": "segmentation", "image_size": [80, 60], "segments": [{"segment": "polyp", "rle": encode(mask)}] if box else []}}


def test_a_moving_region_is_one_track_and_a_long_gap_starts_another():
    from app.services.video_frames import track_regions

    frames = [_seg_frame(0, (10, 10, 30, 30)), _seg_frame(1, (14, 12, 34, 32)), _seg_frame(2, None), _seg_frame(3, (18, 14, 38, 34)),
              _seg_frame(4, None), _seg_frame(5, None), _seg_frame(6, (20, 15, 40, 35))]
    result = track_regions(frames)
    assert result["status"] == "NOT_EVALUATED_ON_VIDEO"
    assert [track["frames_marked"] for track in result["tracks"]] == [3, 1], "one missed frame is bridged, two are not"
    assert result["tracks"][0]["first_time_s"] == 0.0 and result["tracks"][0]["last_time_s"] == 0.3


def test_class_runs_count_top_class_changes():
    from app.services.video_frames import class_runs

    frames = [{"frame_index": i, "time_s": float(i), "status": "SCORED", "result": {"kind": "classification", "top_class": label}}
              for i, label in enumerate(["normal", "normal", "polyp", "polyp", "normal"])]
    result = class_runs(frames)
    assert result["top_class_changes"] == 2 and [run["frames"] for run in result["runs"]] == [2, 2, 1]


def test_refused_frames_count_towards_the_tracking_gap():
    from app.services.video_frames import track_regions

    refused = {"frame_index": 0, "time_s": 0.0, "status": "REFUSED_BY_APPLICABILITY_CHECK"}
    frames = [_seg_frame(0, (10, 10, 30, 30))] + [{**refused, "frame_index": i, "time_s": i / 10} for i in range(1, 11)] + [_seg_frame(11, (10, 10, 30, 30))]
    assert [track["frames_marked"] for track in track_regions(frames)["tracks"]] == [1, 1]
