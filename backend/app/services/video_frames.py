"""Endoscopy video: probing, frame sampling, per-frame quality measurements and per-frame research inference.

A GI endoscopy video (MP4 or AVI, decoded with OpenCV) is sampled at a fixed interval. Every sampled frame is
measured (brightness, dark share, sharpness as the variance of the Laplacian) and passed through the chosen still-
image research model exactly as an uploaded image would be: the model's own feature-space applicability check
first, then the model. Frames are scored independently; there is no temporal smoothing, tracking or video-level
decision, and no model here was trained or evaluated on video, so the timeline is research output only.
"""

from __future__ import annotations

import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.models.entities import EvidenceStatus, Finding, InferenceRun, RepresentationLevel, UploadedFile, User
from app.services import upload_store
from app.services.audit_service import log_audit_event

VIDEO_EXTENSIONS = (".mp4", ".avi")
MAX_SAMPLED_FRAMES = 240
MIN_INTERVAL_S = 0.2
MAX_INTERVAL_S = 30.0
MAX_FRAME_PIXELS = 4096 * 4096
DARK_LEVEL = 20  # grey level (0-255) below which a pixel counts as dark
SEMANTICS = ("Each sampled frame is scored independently by a still-image research model after that model's own applicability check; "
             "no temporal smoothing, tracking or video-level decision is made, and the model was not trained or evaluated on video. "
             "Quality values are measurements shown for review, not gates.")


class VideoError(ValueError):
    """A typed refusal; the message starts with its code."""


def is_video(filename: str) -> bool:
    return filename.lower().endswith(VIDEO_EXTENSIONS)


def probe(path: Path) -> dict[str, Any]:
    """Frame rate, frame count, size and codec, after decoding the first frame."""
    import cv2

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise VideoError("VIDEO_UNREADABLE: OpenCV cannot open the file as a video.")
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        code = int(capture.get(cv2.CAP_PROP_FOURCC) or 0)
        ok, _frame = capture.read()
    finally:
        capture.release()
    if not ok:
        raise VideoError("VIDEO_UNDECODABLE: the first frame cannot be decoded (codec not supported here).")
    if not (np.isfinite(fps) and fps > 0) or frames <= 0:
        raise VideoError("VIDEO_TIMING_UNKNOWN: the container states no frame rate or frame count.")
    if width * height <= 0 or width * height > MAX_FRAME_PIXELS:
        raise VideoError(f"VIDEO_FRAME_SIZE_UNSUPPORTED: {width} x {height} pixels.")
    codec = "".join(chr((code >> 8 * shift) & 0xFF) for shift in range(4)).strip("\x00 ") or "unknown"
    return {"fps": round(fps, 4), "frame_count": frames, "duration_s": round(frames / fps, 3), "width": width, "height": height, "codec": codec}


def sample_indices(meta: dict[str, Any], interval_s: float, max_frames: int) -> list[int]:
    """Every n-th frame (n = interval x stated frame rate); the range is sliced before it is materialised."""
    step = max(1, int(round(interval_s * meta["fps"])))
    return list(range(0, meta["frame_count"], step)[:max_frames])


def read_frames(path: Path, indices: list[int]) -> Iterator[tuple[int, np.ndarray, Optional[float]]]:
    """Frames at the given indices (RGB) with the decoder's presentation time in seconds (None when not reported),
    read sequentially; reading stops at the first frame that fails to decode."""
    import cv2

    wanted = sorted(set(indices))
    capture = cv2.VideoCapture(str(path))
    try:
        position = 0
        for index in wanted:
            while position < index:
                if not capture.grab():
                    return
                position += 1
            ok, frame = capture.read()
            position += 1
            if not ok:
                return
            milliseconds = float(capture.get(cv2.CAP_PROP_POS_MSEC) or 0.0)
            yield index, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (milliseconds / 1000.0 if milliseconds > 0 or index == 0 else None)
    finally:
        capture.release()


def read_frame(path: Path, index: int) -> np.ndarray:
    frames = list(read_frames(path, [index]))
    if not frames:
        raise VideoError(f"FRAME_NOT_DECODED: frame {index} could not be read.")
    return frames[0][1]


def frame_quality(rgb: np.ndarray) -> dict[str, float]:
    import cv2

    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return {"brightness": round(float(grey.mean()) / 255.0, 4), "dark_fraction": round(float((grey < DARK_LEVEL).mean()), 4),
            "sharpness_laplacian_variance": round(float(cv2.Laplacian(grey, cv2.CV_64F).var()), 2)}


def _result_summary(output: dict[str, Any]) -> dict[str, Any]:
    kind = output["type"]
    if kind == "segmentation":
        width, height = output["image_size"]
        area = int(sum(segment["area_px"] for segment in output["segments"]))
        return {"kind": kind, "area_px": area, "area_fraction": round(area / float(width * height), 5), "segments": output["segments"],
                "foreground_label": output.get("foreground_label"), "image_size": output["image_size"]}
    if kind == "classification":
        ranked = sorted(output["classes"], key=lambda item: -item["probability"])
        return {"kind": kind, "top_class": ranked[0]["class"], "top_probability": ranked[0]["probability"], "top_classes": ranked[:3]}
    if kind == "detection":
        shown = [box for box in output["boxes"] if box["above_display_threshold"]]
        return {"kind": kind, "boxes_above_threshold": len(shown), "boxes": shown, "class": output.get("class"), "image_size": output["image_size"]}
    return {"kind": kind}


TRACKING_SEMANTICS = ("Regions linked between consecutive sampled frames by box overlap (IoU 0.2 or more), allowing one sampled frame without "
                      "a match (a frame the applicability check refused counts as one). A track says the model marked an overlapping region on successive frames; it does not establish that it is the same "
                      "lesion, and the linking has not been evaluated on video-labelled data.")


def _box_iou(a: list[float], b: list[float]) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _regions(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Boxes of one scored frame: detection boxes, or the connected components of the segmentation mask."""
    if result["kind"] == "detection":
        return [{"bbox_xyxy": box["bbox_xyxy"], "score": box["score"]} for box in result["boxes"]]
    if result["kind"] != "segmentation" or not result["segments"]:
        return []
    import cv2
    from app.services.reference_annotations import decode

    width, height = result["image_size"]
    mask = np.zeros((height, width), dtype=np.uint8)
    for segment in result["segments"]:
        mask |= decode(segment["rle"]).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    minimum = max(1, int(0.001 * width * height))
    return [{"bbox_xyxy": [float(x), float(y), float(x + w), float(y + h)], "area_px": int(area)}
            for x, y, w, h, area in stats[1:count].tolist() if area >= minimum]


def track_regions(frames: list[dict[str, Any]], min_iou: float = 0.2, max_gap: int = 1) -> dict[str, Any]:
    """Greedy frame-to-frame linking of marked regions across the scored frames, in time order."""
    tracks: list[dict[str, Any]] = []
    active: list[dict[str, Any]] = []
    # Positions count every sampled frame, refused ones included, so a gap means sampled frames without a match.
    for position, frame in enumerate(frames):
        regions = _regions(frame["result"]) if frame.get("status") == "SCORED" else []
        unmatched = list(range(len(regions)))
        for track in sorted(active, key=lambda item: -item["last_area"]):
            best = max(unmatched, key=lambda index: _box_iou(track["last_box"], regions[index]["bbox_xyxy"]), default=None)
            if best is not None and _box_iou(track["last_box"], regions[best]["bbox_xyxy"]) >= min_iou:
                region = regions[best]
                track["frames"].append({"frame_index": frame["frame_index"], "time_s": frame["time_s"], "bbox_xyxy": region["bbox_xyxy"]})
                track.update(last_box=region["bbox_xyxy"], last_position=position, last_area=region.get("area_px", 0))
                unmatched.remove(best)
        for index in unmatched:
            region = regions[index]
            track = {"track_id": len(tracks) + 1, "frames": [{"frame_index": frame["frame_index"], "time_s": frame["time_s"], "bbox_xyxy": region["bbox_xyxy"]}],
                     "last_box": region["bbox_xyxy"], "last_position": position, "last_area": region.get("area_px", 0)}
            tracks.append(track)
        active = [track for track in tracks if position - track["last_position"] <= max_gap]
    return {"method": f"greedy box-overlap linking (IoU >= {min_iou}, gaps of up to {max_gap} sampled frame)", "status": "NOT_EVALUATED_ON_VIDEO",
            "semantics": TRACKING_SEMANTICS,
            "tracks": [{"track_id": track["track_id"], "frames_marked": len(track["frames"]), "first_time_s": track["frames"][0]["time_s"],
                        "last_time_s": track["frames"][-1]["time_s"], "frames": track["frames"]} for track in tracks]}


def class_runs(frames: list[dict[str, Any]]) -> dict[str, Any]:
    """Consecutive scored frames with the same top class, and how often the top class changed."""
    runs: list[dict[str, Any]] = []
    for frame in (item for item in frames if item.get("status") == "SCORED"):
        top = frame["result"]["top_class"]
        if runs and runs[-1]["top_class"] == top:
            runs[-1].update(last_time_s=frame["time_s"], frames=runs[-1]["frames"] + 1)
        else:
            runs.append({"top_class": top, "first_time_s": frame["time_s"], "last_time_s": frame["time_s"], "frames": 1})
    return {"status": "NOT_EVALUATED_ON_VIDEO", "top_class_changes": max(0, len(runs) - 1), "runs": runs,
            "semantics": "Each frame is classified on its own; runs only show how stable the per-frame top class is. No smoothing is applied."}


@contextmanager
def _frame_file(rgb: np.ndarray) -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="medtwin-frame-") as folder:
        path = Path(folder) / "frame.png"
        Image.fromarray(rgb).save(path, format="PNG")
        yield path


def check_model(model: dict) -> None:
    from app.services.model_inference import InferenceNotPermitted

    if model.get("inference_input", "image_2d") != "image_2d" or "ENDOSCOPY" not in model.get("supported_modalities", []):
        raise InferenceNotPermitted(f"{model['display_name']} is not a still-image endoscopy model; video frames run only through those.")


def execute(db: Session, file_record: UploadedFile, model_id: str, interval_s: float, max_frames: int, actor: Optional[User],
            progress=None) -> InferenceRun:
    """Score sampled frames with a still-image endoscopy research model and record the timeline pending human review."""
    from app.services import model_inference

    model = model_inference.get_model(model_id)
    check_model(model)
    bundle = model["artifact_bundle"]
    started_at = datetime.now(timezone.utc)
    start = time.perf_counter()
    frames = []
    with upload_store.materialize(Path(file_record.file_path)) as plain:
        meta = probe(plain)
        indices = sample_indices(meta, interval_s, max_frames)
        for number, (index, rgb, presented) in enumerate(read_frames(plain, indices)):
            nominal = index / meta["fps"]
            record: dict[str, Any] = {"frame_index": index, "time_s": round(presented if presented is not None else nominal, 3),
                                      "time_source": "DECODER_PRESENTATION_TIME" if presented is not None else "FRAME_INDEX_OVER_STATED_FPS",
                                      "nominal_time_s": round(nominal, 3), "quality": frame_quality(rgb)}
            with _frame_file(rgb) as frame_path:
                try:
                    record["applicability"] = model_inference.check_distribution(model, frame_path)
                except model_inference.InferenceNotPermitted as exc:
                    record.update({"status": "REFUSED_BY_APPLICABILITY_CHECK", "reason": str(exc)})
                else:
                    record.update({"status": "SCORED", "result": _result_summary(model_inference.run_model(model, frame_path))})
            frames.append(record)
            if progress is not None and number % 10 == 0:
                progress(10 + int(80 * (number + 1) / max(1, len(indices))), f"Scored frame {number + 1} of {len(indices)}")
    scored = [frame for frame in frames if frame["status"] == "SCORED"]
    # Sampling is by frame count; with a variable frame rate the decoder's times drift from index / fps.
    variable = any(abs(frame["time_s"] - frame["nominal_time_s"]) > 1.5 / meta["fps"] for frame in frames
                   if frame["time_source"] == "DECODER_PRESENTATION_TIME")
    output = {
        "type": "video_frame_timeline", "video": meta, "model_id": model_id,
        "sampling": {"interval_s": interval_s, "max_frames": max_frames, "requested_frames": len(indices), "decoded_frames": len(frames),
                     "method": "every n-th frame, n = interval x stated frame rate; times are the decoder's presentation times where reported",
                     "variable_frame_rate_suspected": variable},
        "frames": frames, "scored_frames": len(scored), "refused_frames": len(frames) - len(scored),
        "coordinate_space": "frame pixels (each frame's own width and height)", "semantics": SEMANTICS,
    }
    if scored and scored[0]["result"]["kind"] == "segmentation":
        positive = [frame for frame in scored if frame["result"]["area_px"] > 0]
        output["summary"] = {"frames_with_mask": len(positive), "first_time_with_mask_s": positive[0]["time_s"] if positive else None,
                             "label": scored[0]["result"].get("foreground_label")}
    elif scored and scored[0]["result"]["kind"] == "classification":
        counts: dict[str, int] = {}
        for frame in scored:
            counts[frame["result"]["top_class"]] = counts.get(frame["result"]["top_class"], 0) + 1
        output["summary"] = {"top_class_counts": counts}
        output["class_runs"] = class_runs(frames)
    if scored and scored[0]["result"]["kind"] in ("segmentation", "detection"):
        output["tracking"] = track_regions(frames)
    exec_ms = round((time.perf_counter() - start) * 1000, 2)
    run = InferenceRun(case_id=file_record.case_id, file_id=file_record.id, modality=file_record.modality, model_name=model_id,
                       model_version=bundle["checkpoint_sha256"][:16], preprocessing_version=f"video-frames-v1+{bundle['preprocessing_version']}",
                       status=EvidenceStatus.COMPLETED, execution_time_ms=exec_ms, started_at=started_at, completed_at=datetime.now(timezone.utc))
    db.add(run)
    db.flush()
    label = (f"Research model on {len(scored)} of {len(frames)} sampled video frames"
             + (f"; mask in {output['summary']['frames_with_mask']}" if "frames_with_mask" in output.get("summary", {}) else ""))
    finding = Finding(
        inference_run_id=run.id, case_id=file_record.case_id, modality=file_record.modality,
        category="Research model output (endoscopy video frames)", label=label[:128], raw_confidence=None, calibration_status="UNCALIBRATED",
        representation_level=RepresentationLevel.L1_GENERIC, anatomical_region=None, mapping_status="NOT_MAPPABLE: RESEARCH_MODEL_OUTPUT_VIDEO_FRAMES",
        review_status=EvidenceStatus.PENDING_HUMAN_REVIEW, is_demo=False,
        evidence_provenance={
            "source": "MODEL_INFERENCE", "output_status": "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED", "model_id": model_id,
            "model_display_name": model["display_name"], "model_status": model["status"], "checkpoint_sha256": bundle["checkpoint_sha256"],
            "dataset_version": bundle["dataset_version"], "dataset_license": bundle["dataset_license"],
            "evaluation_report_path": bundle["evaluation_report_path"], "model_card_path": bundle["model_card_path"],
            "held_out_evaluation": model_inference.evaluation_summary(model), "declared_input_type": "ENDOSCOPY_VIDEO",
            "applicability": "Declared GI endoscopy video; every frame passed or failed the model's feature-space applicability reference on its own.",
            "anatomy_system_of_model": model.get("anatomy"), "source_file_sha256": file_record.file_hash, "output": output,
        },
    )
    db.add(finding)
    db.commit()
    log_audit_event(db=db, action="RESEARCH_VIDEO_FRAMES_COMPLETED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor,
                    details={"case_id": file_record.case_id, "file_id": file_record.id, "finding_id": finding.id, "model_id": model_id,
                             "frames": len(frames), "scored": len(scored), "exec_time_ms": exec_ms})
    db.refresh(run)
    return run
