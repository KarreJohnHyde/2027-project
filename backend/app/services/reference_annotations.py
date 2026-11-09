"""Reference masks attached to image uploads, and per-image comparison with a model's mask.

A reference annotation is stored apart from model output and from reviews: the uploader
declares where it comes from (a dataset publisher's mask for a public test image, or an
independent expert's annotation), and that declaration is shown with every comparison.
Comparing one model mask with one reference gives per-image agreement (Dice, IoU, pixel
precision/recall, surface distances in source pixels) and the disagreement regions for
display. It is not a performance estimate; the model's held-out evaluation is.
"""

from __future__ import annotations

import hashlib
import io
from typing import Any, Optional

import numpy as np
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app.models.entities import ReferenceAnnotation, UploadedFile, User
from app.services.audit_service import log_audit_event
from app.services.evaluation_metrics import _overlap, _surface_distances

SOURCES = {
    "DATASET_PUBLISHER_ANNOTATION": "Mask published with the dataset this image comes from",
    "INDEPENDENT_EXPERT_ANNOTATION": "Mask drawn by an expert independently of the model output",
    "REVIEWER_CORRECTION_OF_MODEL_OUTPUT": "The model's mask as edited by a reviewer (brush and eraser), starting from the run it corrects",
}
CORRECTION = "REVIEWER_CORRECTION_OF_MODEL_OUTPUT"
# Uploaded reference masks must be independent of model output; corrections are made only from a run.
UPLOADABLE_SOURCES = {key for key in SOURCES if key != CORRECTION}
CORRECTION_SEMANTICS = ("Agreement between this run's mask and a reviewer's correction of it, in source image pixels: it measures how much "
                        "the reviewer changed the model output. A correction starts from the model's mask, so it is not independent ground "
                        "truth and not a performance estimate.")
MASK_FORMATS = {"PNG", "JPEG", "BMP"}
MAX_MASK_BYTES = 20 * 1024 * 1024
SEMANTICS = ("Per-image agreement between this run's mask and the attached reference annotation, in source image pixels. "
             "One image is not a performance estimate; the model's internal held-out evaluation is the performance evidence.")


class ReferenceAnnotationError(ValueError):
    """A typed refusal; the message starts with its code."""


def encode(mask: np.ndarray) -> dict:
    from pycocotools import mask as coco_mask

    rle = coco_mask.encode(np.asfortranarray(mask.astype(np.uint8)))
    return {"size": [int(v) for v in rle["size"]], "counts": rle["counts"].decode("ascii")}


def decode(rle: dict) -> np.ndarray:
    from pycocotools import mask as coco_mask

    return coco_mask.decode({"size": rle["size"], "counts": rle["counts"].encode("ascii")}) > 0


def read_mask(content: bytes, threshold: int) -> tuple[np.ndarray, int]:
    """Binary mask from a PNG/JPEG/BMP and the threshold used: pixels brighter than the threshold
    are the class (publisher masks saved as JPEG carry compression noise at the edge); a label
    image holding only 0 and 1 counts every non-zero pixel."""
    if not content or len(content) > MAX_MASK_BYTES:
        raise ReferenceAnnotationError("MASK_SIZE_INVALID: the mask file is empty or larger than 20 MB.")
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in MASK_FORMATS:
                raise ReferenceAnnotationError("MASK_FORMAT_UNSUPPORTED: masks must be PNG, JPEG or BMP images.")
            image.load()
            upright = ImageOps.exif_transpose(image)
            grey = np.asarray(upright.convert("L"))
    except ReferenceAnnotationError:
        raise
    except Exception as exc:  # undecodable bytes
        raise ReferenceAnnotationError(f"MASK_UNREADABLE: {type(exc).__name__}") from exc
    if int(grey.max()) <= 1:
        return grey > 0, 0
    return grey > threshold, threshold


def create(db: Session, file_record: UploadedFile, image_size: list[int], content: bytes, filename: str, source: str,
           source_detail: str, class_name: str, threshold: int, actor: Optional[User], derived_from_run_id: Optional[int] = None) -> ReferenceAnnotation:
    if source not in SOURCES:
        raise ReferenceAnnotationError(f"SOURCE_UNSUPPORTED: declare one of {', '.join(sorted(UPLOADABLE_SOURCES))}.")
    if (source == CORRECTION) != (derived_from_run_id is not None):
        raise ReferenceAnnotationError("CORRECTION_NEEDS_ITS_RUN: a reviewer correction is made from one research run, and only a correction names one.")
    mask, threshold = read_mask(content, threshold)
    if [mask.shape[1], mask.shape[0]] != list(image_size):
        raise ReferenceAnnotationError(
            f"MASK_SIZE_MISMATCH: the mask is {mask.shape[1]}x{mask.shape[0]} px but the image is {image_size[0]}x{image_size[1]} px; "
            "a reference must be drawn on this exact image."
        )
    annotation = ReferenceAnnotation(
        case_id=file_record.case_id, file_id=file_record.id, kind="SEGMENTATION_MASK", source=source, source_detail=source_detail,
        class_name=class_name, mask_filename=filename[:256], mask_sha256=hashlib.sha256(content).hexdigest(), binarize_threshold=threshold,
        image_size=list(image_size), rle=encode(mask), area_px=int(mask.sum()), created_by_id=actor.id if actor else None,
        derived_from_run_id=derived_from_run_id,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    log_audit_event(db=db, action="MODEL_MASK_CORRECTED" if source == CORRECTION else "REFERENCE_ANNOTATION_ADDED", resource_type="UPLOADED_FILE",
                    resource_id=str(file_record.id), user=actor,
                    details={"case_id": file_record.case_id, "annotation_id": annotation.id, "source": source, "mask_sha256": annotation.mask_sha256,
                             "derived_from_run_id": derived_from_run_id})
    return annotation


BOXES = "BOUNDING_BOXES"
MAX_BOXES = 500
BOX_SEMANTICS = ("Per-image agreement between this run's boxes above its display threshold and the attached reference boxes, matched "
                 "one-to-one at IoU 0.5 or more (greedy, highest score first). One image is not a performance estimate; the model's "
                 "internal held-out evaluation is the performance evidence.")


def read_boxes(content: bytes, image_size: list[int], yolo_class: Optional[int] = None) -> list[list[float]]:
    """Reference boxes from JSON ({"boxes": [[x1, y1, x2, y2], ...]}, a list of such boxes, or COCO-style
    [{"bbox": [x, y, w, h]}]) or YOLO text ("class cx cy w h" normalised, or a polygon), in source pixels. A YOLO file
    with several class ids must name the one to use (``yolo_class``); one reference holds one class."""
    if not content or len(content) > MAX_MASK_BYTES:
        raise ReferenceAnnotationError("BOXES_SIZE_INVALID: the box file is empty or larger than 20 MB.")
    width, height = image_size
    text = content.decode("utf-8", errors="replace").strip()
    boxes: list[list[float]] = []
    try:
        if text.startswith("{") or text.startswith("["):
            import json

            data = json.loads(text)
            items = data.get("boxes", data.get("annotations", [])) if isinstance(data, dict) else data
            for item in items:
                if isinstance(item, dict) and "bbox" in item:
                    x, y, w, h = (float(v) for v in item["bbox"])
                    boxes.append([x, y, x + w, y + h])
                elif isinstance(item, dict) and "bbox_xyxy" in item:
                    boxes.append([float(v) for v in item["bbox_xyxy"]])
                else:
                    boxes.append([float(v) for v in item])
        else:
            ids = {int(float(line.split()[0])) for line in text.splitlines() if line.split()}
            if yolo_class is None and len(ids) > 1:
                raise ReferenceAnnotationError(f"MULTICLASS_YOLO_REFERENCE: the file has class ids {sorted(ids)}; name the one this reference holds.")
            for line in text.splitlines():
                parts = line.split()
                if parts and yolo_class is not None and int(float(parts[0])) != yolo_class:
                    continue
                if len(parts) == 5:
                    _, cx, cy, w, h = (float(v) for v in parts)
                    boxes.append([(cx - w / 2) * width, (cy - h / 2) * height, (cx + w / 2) * width, (cy + h / 2) * height])
                elif len(parts) >= 7 and len(parts) % 2 == 1:
                    xs, ys = [float(v) for v in parts[1::2]], [float(v) for v in parts[2::2]]
                    boxes.append([min(xs) * width, min(ys) * height, max(xs) * width, max(ys) * height])
                elif parts:
                    raise ValueError("unrecognised line")
    except ReferenceAnnotationError:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise ReferenceAnnotationError(f"BOXES_UNREADABLE: expected JSON boxes or YOLO lines ({type(exc).__name__}).") from exc
    if len(boxes) > MAX_BOXES:
        raise ReferenceAnnotationError(f"TOO_MANY_BOXES: at most {MAX_BOXES} reference boxes per image.")
    for box in boxes:
        if len(box) != 4 or not all(np.isfinite(box)) or box[2] <= box[0] or box[3] <= box[1]:
            raise ReferenceAnnotationError("BOX_INVALID: every box needs x1 < x2 and y1 < y2.")
        if box[0] < -1 or box[1] < -1 or box[2] > width + 1 or box[3] > height + 1:
            raise ReferenceAnnotationError(f"BOX_OUTSIDE_IMAGE: a box extends beyond the {width}x{height} px image; references must be drawn on this exact image.")
    return [[round(max(0.0, x1), 2), round(max(0.0, y1), 2), round(min(float(width), x2), 2), round(min(float(height), y2), 2)] for x1, y1, x2, y2 in boxes]


def create_boxes(db: Session, file_record: UploadedFile, image_size: list[int], content: bytes, filename: str, source: str,
                 source_detail: str, class_name: str, actor: Optional[User], yolo_class: Optional[int] = None) -> ReferenceAnnotation:
    if source not in UPLOADABLE_SOURCES:
        raise ReferenceAnnotationError(f"SOURCE_UNSUPPORTED: declare one of {', '.join(sorted(UPLOADABLE_SOURCES))}.")
    boxes = read_boxes(content, image_size, yolo_class)
    width, height = image_size
    union = np.zeros((height, width), dtype=bool)
    for x1, y1, x2, y2 in boxes:
        union[int(y1):int(np.ceil(y2)), int(x1):int(np.ceil(x2))] = True
    annotation = ReferenceAnnotation(
        case_id=file_record.case_id, file_id=file_record.id, kind=BOXES, source=source, source_detail=source_detail, class_name=class_name,
        mask_filename=filename[:256], mask_sha256=hashlib.sha256(content).hexdigest(), binarize_threshold=0, image_size=list(image_size),
        rle=encode(union), area_px=int(union.sum()), created_by_id=actor.id if actor else None, boxes=boxes,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    log_audit_event(db=db, action="REFERENCE_ANNOTATION_ADDED", resource_type="UPLOADED_FILE", resource_id=str(file_record.id), user=actor,
                    details={"case_id": file_record.case_id, "annotation_id": annotation.id, "source": source, "kind": BOXES,
                             "boxes": len(boxes), "file_sha256": annotation.mask_sha256})
    return annotation


def _class_key(name: Optional[str]) -> str:
    return "".join(character for character in str(name or "").lower() if character.isalnum())


def _iou(a: list[float], b: list[float]) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def compare_boxes(output: Optional[dict], annotation: ReferenceAnnotation) -> dict[str, Any]:
    if not output or output.get("type") != "detection":
        raise ReferenceAnnotationError("DETECTION_RUN_REQUIRED: reference boxes are compared with detection runs only.")
    if _class_key(output.get("class")) != _class_key(annotation.class_name):
        raise ReferenceAnnotationError(f"CLASS_MISMATCH: the run detects '{output.get('class')}' but the reference boxes are '{annotation.class_name}'.")
    if list(output["image_size"]) != list(annotation.image_size):
        raise ReferenceAnnotationError("IMAGE_SIZE_MISMATCH: the run and the reference were made on different pixel grids.")
    predicted = sorted((box for box in output["boxes"] if box["above_display_threshold"]), key=lambda box: -box["score"])
    reference = list(annotation.boxes or [])
    unmatched = list(range(len(reference)))
    pairs, model_only = [], []
    for box in predicted:
        best = max(unmatched, key=lambda index: _iou(box["bbox_xyxy"], reference[index]), default=None)
        overlap = _iou(box["bbox_xyxy"], reference[best]) if best is not None else 0.0
        if best is not None and overlap >= 0.5:
            pairs.append({"model_box": box["bbox_xyxy"], "score": round(box["score"], 4), "reference_box": reference[best], "iou": round(overlap, 4)})
            unmatched.remove(best)
        else:
            model_only.append({"model_box": box["bbox_xyxy"], "score": round(box["score"], 4), "best_iou": round(overlap, 4)})
    tp, fp, fn = len(pairs), len(model_only), len(unmatched)
    return {
        "comparison": "PER_IMAGE_BOX_AGREEMENT", "semantics": BOX_SEMANTICS + (" The reference has no boxes: every model box is unmatched." if not reference else ""),
        "reference": {"annotation_id": annotation.id, "source": annotation.source, "source_detail": annotation.source_detail, "class_name": annotation.class_name},
        "display_score_threshold": output.get("display_score_threshold"), "matched": tp, "model_only": fp, "reference_only": fn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None, "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "mean_matched_iou": round(float(np.mean([pair["iou"] for pair in pairs])), 4) if pairs else None,
        "pairs": pairs, "model_only_boxes": model_only, "reference_only_boxes": [reference[index] for index in unmatched],
    }


VOLUME_SLICE = "VOLUME_SLICE_CORRECTION"
VOLUME_SEMANTICS = ("Reviewer corrections of this run's volume mask, one axial index plane at a time. The run is unchanged; the corrected volume "
                    "is the model's voxels plus those added and minus those removed on the corrected slices, times the header voxel volume. "
                    "Corrections start from the model's mask, so they are not independent ground truth.")


def _slice_mask(output: dict, slice_index: int, class_index: int) -> np.ndarray:
    """The run's mask for one class on axial plane k, (j, i) like the stored output (labels[:, :, k].T)."""
    ni, nj, _ = output["volume_shape_ijk"]
    mask = np.zeros((nj, ni), dtype=bool)
    plane = next((item for item in output["slices"] if item["slice_index"] == slice_index), None)
    for segment in (plane or {}).get("segments", []):
        if segment["class_index"] == class_index:
            mask |= decode(segment["rle"])
    return mask


def create_volume_slice_correction(db: Session, file_record: UploadedFile, run_id: int, output: dict, slice_index: int, class_name: str,
                                   content: bytes, source_detail: str, actor: Optional[User]) -> ReferenceAnnotation:
    if not output or output.get("type") != "volume_segmentation":
        raise ReferenceAnnotationError("VOLUME_RUN_REQUIRED: slice corrections are made on volumetric segmentation runs.")
    ni, nj, nk = output["volume_shape_ijk"]
    if not 0 <= slice_index < nk:
        raise ReferenceAnnotationError(f"SLICE_OUTSIDE_VOLUME: axial planes are 0-{nk - 1}.")
    structures = {item["structure"]: item["class_index"] for item in output["structures"]}
    if class_name not in structures:
        raise ReferenceAnnotationError(f"CLASS_NOT_IN_RUN: choose one of {', '.join(sorted(structures))}.")
    mask, _ = read_mask(content, 127)
    if mask.shape != (nj, ni):
        raise ReferenceAnnotationError(f"MASK_SIZE_MISMATCH: the slice is {ni}x{nj} px but the mask is {mask.shape[1]}x{mask.shape[0]} px.")
    annotation = ReferenceAnnotation(
        case_id=file_record.case_id, file_id=file_record.id, kind=VOLUME_SLICE, source=CORRECTION, source_detail=source_detail[:256],
        class_name=class_name, mask_filename=f"slice-{slice_index}.png", mask_sha256=hashlib.sha256(content).hexdigest(), binarize_threshold=127,
        image_size=[ni, nj], rle=encode(mask), area_px=int(mask.sum()), created_by_id=actor.id if actor else None,
        derived_from_run_id=run_id, slice_index=slice_index,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    log_audit_event(db=db, action="MODEL_MASK_CORRECTED", resource_type="UPLOADED_FILE", resource_id=str(file_record.id), user=actor,
                    details={"case_id": file_record.case_id, "annotation_id": annotation.id, "derived_from_run_id": run_id,
                             "slice_index": slice_index, "class_name": class_name, "kind": VOLUME_SLICE})
    return annotation


def volume_corrections_summary(output: dict, annotations: list[ReferenceAnnotation]) -> dict[str, Any]:
    """Per structure: model and corrected voxels and volumes; per corrected slice: what changed. The newest correction of a
    (slice, structure) replaces earlier ones."""
    latest: dict[tuple[int, str], ReferenceAnnotation] = {}
    for annotation in sorted(annotations, key=lambda item: item.id):
        latest[(int(annotation.slice_index), annotation.class_name)] = annotation
    structures = {item["structure"]: item for item in output["structures"]}
    voxel_ml = float(output["voxel_volume_ml"])
    added = {name: 0 for name in structures}
    removed = {name: 0 for name in structures}
    slices = []
    for (slice_index, name), annotation in sorted(latest.items()):
        model = _slice_mask(output, slice_index, structures[name]["class_index"])
        corrected = decode(annotation.rle)
        plus, minus = int((corrected & ~model).sum()), int((model & ~corrected).sum())
        added[name] += plus
        removed[name] += minus
        dice, _ = _overlap(corrected, model)
        slices.append({"slice_index": slice_index, "structure": name, "annotation_id": annotation.id, "voxels_added": plus, "voxels_removed": minus,
                       "dice_with_model": round(dice, 4), "source_detail": annotation.source_detail,
                       "created_at": annotation.created_at.isoformat() if annotation.created_at else None})
    rows = []
    for name, item in structures.items():
        corrected_voxels = int(item["voxels"]) + added[name] - removed[name]
        rows.append({"structure": name, "model_voxels": int(item["voxels"]), "corrected_voxels": corrected_voxels,
                     "model_volume_ml": round(int(item["voxels"]) * voxel_ml, 3), "corrected_volume_ml": round(corrected_voxels * voxel_ml, 3),
                     "slices_corrected": sum(1 for row in slices if row["structure"] == name)})
    return {"semantics": VOLUME_SEMANTICS, "structures": rows, "corrected_slices": slices}


def serialize(annotation: ReferenceAnnotation) -> dict[str, Any]:
    return {
        "id": annotation.id, "file_id": annotation.file_id, "kind": annotation.kind, "boxes": annotation.boxes, "slice_index": annotation.slice_index,
        "layer": "REVIEWER_CORRECTION" if annotation.source == CORRECTION else "GROUND_TRUTH", "source": annotation.source,
        "derived_from_run_id": annotation.derived_from_run_id,
        "source_label": SOURCES.get(annotation.source, annotation.source), "source_detail": annotation.source_detail,
        "class_name": annotation.class_name, "mask_filename": annotation.mask_filename, "mask_sha256": annotation.mask_sha256,
        "binarize_threshold": annotation.binarize_threshold, "image_size": annotation.image_size, "rle": annotation.rle,
        "area_px": annotation.area_px, "empty": annotation.area_px == 0, "created_by_id": annotation.created_by_id,
        "created_at": annotation.created_at.isoformat() if annotation.created_at else None,
    }


def predicted_mask(output: dict, class_name: str, strict: bool = False) -> tuple[np.ndarray, str]:
    """The run's mask for the reference's class: the segment of that name, else every foreground segment.

    strict (reviewer corrections): a class the run did not predict has an empty mask, because the reviewer
    painted that class itself rather than a mask published under another name."""
    width, height = output["image_size"]
    mask = np.zeros((height, width), dtype=bool)
    named = [segment for segment in output["segments"] if segment["segment"] == class_name]
    if strict and not named:
        return mask, f"segment '{class_name}' (not predicted by the run, so its mask is empty)"
    for segment in named or output["segments"]:
        mask |= decode(segment["rle"])
    return mask, (f"segment '{class_name}'" if named else "all foreground segments")


def compare(output: Optional[dict], annotation: ReferenceAnnotation, run_id: Optional[int] = None) -> dict[str, Any]:
    if annotation.kind == BOXES:
        return compare_boxes(output, annotation)
    if not output or output.get("type") != "segmentation":
        raise ReferenceAnnotationError("SEGMENTATION_RUN_REQUIRED: reference masks are compared with segmentation runs only.")
    if list(output["image_size"]) != list(annotation.image_size):
        raise ReferenceAnnotationError("IMAGE_SIZE_MISMATCH: the run and the reference were made on different pixel grids.")
    predicted, compared = predicted_mask(output, annotation.class_name, strict=annotation.source == CORRECTION)
    reference = decode(annotation.rle)
    dice, iou = _overlap(reference, predicted)
    tp = int((reference & predicted).sum())
    fp = int((predicted & ~reference).sum())
    fn = int((reference & ~predicted).sum())
    distances = _surface_distances(reference, predicted, (1.0, 1.0))
    correction = annotation.source == CORRECTION
    of_this_run = correction and run_id is not None and annotation.derived_from_run_id == run_id
    if of_this_run:
        semantics = CORRECTION_SEMANTICS + f" The correction was made from this run ({run_id})."
    elif correction:
        semantics = (f"Agreement between this run's mask and a reviewer's correction of another run ({annotation.derived_from_run_id}), in source "
                     "image pixels. The differences are not edits of this run, and a correction is not independent ground truth.")
    else:
        semantics = SEMANTICS
    if not reference.any():
        semantics += " The reference is empty (no class pixels): Dice is 1 only if the model also predicts nothing."
    return {
        "comparison": "PER_IMAGE_AGREEMENT", "semantics": semantics, "compared": compared, "reference_empty": not reference.any(),
        "correction_of_this_run": bool(of_this_run),
        "reference": {"annotation_id": annotation.id, "source": annotation.source, "source_detail": annotation.source_detail, "class_name": annotation.class_name},
        "dice": round(dice, 4), "iou": round(iou, 4),
        "pixel_precision": round(tp / (tp + fp), 4) if tp + fp else None, "pixel_recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "reference_area_px": int(reference.sum()), "predicted_area_px": int(predicted.sum()),
        "hd95_px": round(distances["hausdorff_95"], 2) if distances else None,
        "assd_px": round(distances["average_symmetric_surface_distance"], 2) if distances else None,
        "regions": {"agreement": encode(reference & predicted), "model_only": encode(predicted & ~reference), "reference_only": encode(reference & ~predicted)},
    }
