"""Research-only inference with registered MedTwin models (ml_training pipelines).

A model may run only when its registry entry allows research inference and its
artifact bundle passes the research gate: licence verified, held-out evaluation
report present, checkpoint present with the registered SHA-256. Outputs are
returned in the uploaded image's own pixel coordinates and are labelled
MODEL_INFERENCE / RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED. Applicability is
declared by the requesting user (no out-of-distribution detector exists).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional
from weakref import WeakValueDictionary

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.models.entities import EvidenceStatus, Finding, InferenceRun, ModalityType, RepresentationLevel, UploadedFile, User
from app.services import ecg_inference, upload_store, volume_inference
from app.services.audit_service import log_audit_event
from app.services.model_registry import _load_registry, _resolve_artifact_path, _sha256

logger = logging.getLogger(__name__)
MODALITY_LABELS = {"ENDOSCOPY": "GI endoscopy image", "ANGIOGRAPHY": "X-ray coronary angiogram", "CT": "CT image or slice",
                   "MICROSCOPY": "single segmented blood-cell microscopy image",
                   "ECG": "resting 12-lead ECG recording (digital signal, not a photograph or printout)",
                   "MRI": "short-axis cardiac cine-MRI frame at end-diastole or end-systole"}
UPLOAD_INPUTS = {"image_2d", "ecg_12lead", "volume_nifti"}
_load_lock = threading.Lock()
# This workstation serves research requests on one GPU. Serialising model runs
# bounds activation memory and prevents concurrent requests loading several
# networks after the cache has evicted them.
_inference_lock = threading.Lock()
# Telemetry observes live networks without retaining another copy or extending
# their lifetime after cache eviction. Worker processes have separate telemetry.
_resident_lock = threading.Lock()
_resident_networks = WeakValueDictionary()


def resident_model_ids() -> list[str]:
    """Research networks alive in this process, including a request in progress."""
    with _resident_lock:
        return sorted({key[0] for key in _resident_networks.keys()})


class InferenceNotPermitted(Exception):
    """The model or input does not pass the research-inference gate."""


def research_gate(model: dict) -> dict:
    bundle = model.get("artifact_bundle") or {}
    blockers = []
    if not model.get("research_inference"):
        blockers.append("NOT_REGISTERED_FOR_RESEARCH_INFERENCE")
    if model.get("status") not in {"READY_UNVALIDATED", "VALIDATED"}:
        blockers.append(f"STATUS_{model.get('status')}")
    license_name = (bundle.get("dataset_license") or "").strip()
    if not license_name or license_name.upper() in {"UNKNOWN", "UNVERIFIED"}:
        blockers.append("DATASET_LICENSE_UNVERIFIED")
    report_path = bundle.get("evaluation_report_path")
    if not report_path or not _resolve_artifact_path(report_path).exists():
        blockers.append("EVALUATION_REPORT_MISSING")
    checkpoint = bundle.get("checkpoint_path")
    if not checkpoint or not _resolve_artifact_path(checkpoint).exists():
        blockers.append("CHECKPOINT_MISSING")
    elif _checkpoint_hash(_resolve_artifact_path(checkpoint)) != bundle.get("checkpoint_sha256"):
        blockers.append("CHECKPOINT_HASH_MISMATCH")
    return {"allowed": not blockers, "blockers": blockers}


def _checkpoint_hash(path: Path) -> str:
    stat = path.stat()
    return _cached_hash(str(path), stat.st_size, stat.st_mtime_ns)


@lru_cache(maxsize=16)
def _cached_hash(path: str, size: int, mtime_ns: int) -> str:
    return _sha256(Path(path))


def _report(model: dict) -> dict:
    path = _resolve_artifact_path(model["artifact_bundle"]["evaluation_report_path"])
    return json.loads(path.read_text(encoding="utf-8"))


def evaluation_summary(model: dict) -> dict:
    """Headline held-out metrics from the registered evaluation report."""
    report = _report(model)
    if model["task"] == "image_classification":
        metrics, ci = report["metrics"], report.get("confidence_intervals_95", {})
        return {"test_n": report["test_n"], "accuracy": metrics["accuracy"], "macro_f1": metrics["macro_f1"],
                "accuracy_95ci": [ci.get("accuracy", {}).get("low"), ci.get("accuracy", {}).get("high")],
                "ece_temperature_scaled": metrics.get("ece_temperature_scaled")}
    if model["task"] == "object_detection":
        test = report["test"]
        return {"test_n": test["n_images"], "map_50_95": test["metrics"].get("map_50_95"), "ap_50": test["metrics"].get("ap_50"),
                "operating_point": report["operating_point"]["test"]}
    if model["task"] == "multilabel_ecg_classification":
        metrics, ci = report["metrics"], report.get("confidence_intervals_95", {})
        return {"test_n": report["test_n"], "macro_auroc": metrics["macro_auroc"], "macro_auprc": metrics["macro_auprc"],
                "macro_auroc_95ci": [ci.get("macro_auroc", {}).get("low"), ci.get("macro_auroc", {}).get("high")],
                "macro_f1_at_validation_thresholds": metrics["macro_f1_at_validation_thresholds"]}
    if model["task"] == "survival_prediction":
        metrics, ci = report["metrics"], report.get("confidence_intervals_95", {})
        return {"test_n": report["test_n"], "harrell_c": metrics["harrell_c"],
                "harrell_c_95ci": [ci.get("harrell_c", {}).get("low"), ci.get("harrell_c", {}).get("high")],
                "integrated_brier": metrics["integrated_brier_model"], "integrated_brier_kaplan_meier": metrics["integrated_brier_kaplan_meier"],
                "integrated_brier_skill": metrics["integrated_brier_skill"]}
    if model["task"] == "semantic_segmentation":
        test = report["test"]
        return {"test_n": test["n_images"], "mean_foreground_dice": test["mean_foreground_dice_per_image"], "vessel_dice": test.get("vessel_dice")}
    if model["task"] == "volumetric_semantic_segmentation":
        metrics, structures = report["metrics"], report["metrics"]["per_structure"]
        return {"test_n": report["test_n"], "test_patients": report["test_patients"], "mean_case_macro_dice": metrics["mean_case_macro_dice"],
                "lv_cavity_dice": structures["left_ventricular_cavity"]["mean_dice"], "myocardium_dice": structures["myocardium"]["mean_dice"],
                "rv_cavity_dice": structures["right_ventricular_cavity"]["mean_dice"],
                "lv_ef_mean_absolute_error": report["clinical_indices"]["lv_ef_percent"]["mean_absolute_error"]}
    return {"status": "SUMMARY_NOT_DEFINED_FOR_TASK", "task": model["task"]}


def inference_models() -> list[dict]:
    """Registry models with research-inference metadata, gate state and headline metrics."""
    result = []
    for model in _load_registry()["models"]:
        if not model.get("research_inference"):
            continue
        gate = research_gate(model)
        entry = {
            "model_id": model["model_id"], "display_name": model["display_name"], "task": model["task"], "anatomy": model.get("anatomy"),
            "supported_modalities": model.get("supported_modalities", []), "supported_classes": model.get("supported_classes", []),
            "status": model["status"], "validated": model.get("validated", False), "gate": gate,
            "dataset_license": model["artifact_bundle"].get("dataset_license"), "model_card_path": model["artifact_bundle"].get("model_card_path"),
            "evaluation_report_path": model["artifact_bundle"].get("evaluation_report_path"), "checkpoint_sha256": model["artifact_bundle"].get("checkpoint_sha256"),
            "output_status": "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED",
            # Image and volume models run from Medical Imaging, ECG models from Multimodal; tabular survival models are evaluation evidence only.
            "inference_input": model.get("inference_input", "image_2d"),
            "run_scope": (model.get("validation_readiness") or {}).get("run_scope", "RESEARCH"),
        }
        if gate["allowed"]:
            entry["held_out_evaluation"] = evaluation_summary(model)
        result.append(entry)
    return result


def get_model(model_id: str) -> dict:
    model = next((m for m in _load_registry()["models"] if m["model_id"] == model_id), None)
    if model is None:
        raise InferenceNotPermitted(f"Unknown model {model_id}.")
    gate = research_gate(model)
    if not gate["allowed"]:
        raise InferenceNotPermitted(f"{model['display_name']} is not runnable: {', '.join(gate['blockers'])}.")
    return model


@lru_cache(maxsize=1)
def _load(model_id: str, checkpoint: str, sha256: str):
    import hashlib
    import io

    import torch

    data = Path(checkpoint).read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:  # the bytes deserialised are the bytes verified
        raise InferenceNotPermitted(f"Checkpoint for {model_id} does not match its registered SHA-256.")
    # weights_only stays on; NumPy scalars (e.g. a threshold saved as float64) are the
    # only extra types allowed, which reconstructs values and executes no code.
    numpy_scalars = [np._core.multiarray.scalar, np.dtype, np.dtypes.Float64DType, np.dtypes.Float32DType]
    with torch.serialization.safe_globals(numpy_scalars):
        payload = torch.load(io.BytesIO(data), map_location="cpu", weights_only=True)
    # Verification still covers exactly the bytes deserialised. They no longer
    # need to overlap network construction in memory once loading is complete.
    del data
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if payload["kind"] == "image_classifier":
        from torchvision import models
        from torch import nn

        constructor = {"resnet18": models.resnet18, "efficientnet_b0": models.efficientnet_b0}[payload["arch"]]
        network = constructor(weights=None)
        if payload["arch"].startswith("resnet"):
            network.fc = nn.Linear(network.fc.in_features, len(payload["classes"]))
        else:
            network.classifier[-1] = nn.Linear(network.classifier[-1].in_features, len(payload["classes"]))
    elif payload["kind"] == "object_detector":
        from torchvision.models.detection import fasterrcnn_resnet50_fpn_v2
        from torchvision.models.detection.faster_rcnn import FastRCNNPredictor

        network = fasterrcnn_resnet50_fpn_v2(weights=None, weights_backbone=None, min_size=payload["min_size"], max_size=payload["max_size"])
        network.roi_heads.box_predictor = FastRCNNPredictor(network.roi_heads.box_predictor.cls_score.in_features, 2)
    elif payload["kind"] == "semantic_segmenter":
        from monai.networks.nets import UNet

        params = payload["arch_params"]
        network = UNet(spatial_dims=params["spatial_dims"], in_channels=params["in_channels"], out_channels=params["out_channels"],
                       channels=tuple(params["channels"]), strides=tuple(params["strides"]), num_res_units=params["num_res_units"], norm=params["norm"])
    elif payload["kind"] == "ecg_classifier" and payload.get("arch") == "resnet1d_compact":
        network = ecg_inference.build_network(len(payload["classes"]), len(payload["leads"]))
    elif payload["kind"] == "volumetric_semantic_segmenter":
        try:
            network = volume_inference.build_network(payload)
        except volume_inference.VolumeInputError as exc:
            raise InferenceNotPermitted(str(exc)) from exc
        # Training resumption state is not needed for serving.
        payload.pop("best_state_dict", None)
        payload.pop("optimizer_state_dict", None)
    else:
        raise InferenceNotPermitted(f"Unsupported checkpoint kind {payload['kind']}.")
    # Serving needs the network weights and preprocessing metadata, not a
    # second CPU copy of every weight retained by the cached payload.
    network.load_state_dict(payload.pop("state_dict"))
    network.eval().to(device)
    with _resident_lock:
        _resident_networks[(model_id, checkpoint, sha256)] = network
    return network, payload, device


def load_model(model: dict):
    bundle = model["artifact_bundle"]
    with _load_lock:
        return _load(model["model_id"], str(_resolve_artifact_path(bundle["checkpoint_path"])), bundle["checkpoint_sha256"])


def evaluated_precision(device):
    """Numeric precision of the held-out evaluation, for the trainers that used autocast.

    ml_training.classify and ml_training.segment scored their test splits under bfloat16
    autocast on CUDA. Serving the same checkpoints in float32 changed predictions (84 of
    1,867 held-out C-NMC cells), so inference reproduces the evaluated configuration.
    Returns (context manager, description)."""
    import torch

    if device.type == "cuda":
        return torch.autocast("cuda", dtype=torch.bfloat16), "bfloat16 autocast on CUDA, as in the held-out evaluation"
    return torch.autocast("cpu", enabled=False), "float32 on CPU; differs from the evaluated bfloat16 CUDA configuration"


def classify(network, payload: dict, device, image: Image.Image) -> dict:
    import torch
    from torchvision import transforms

    size = payload["image_size"]
    transform = transforms.Compose([transforms.Resize(int(size * 1.14)), transforms.CenterCrop(size), transforms.ToTensor(),
                                    transforms.Normalize(payload["normalization"]["mean"], payload["normalization"]["std"])])
    precision, precision_note = evaluated_precision(device)
    with torch.no_grad(), precision:
        logits = network(transform(image.convert("RGB"))[None].to(device)).float().cpu().numpy()[0]
    scaled = logits / payload["temperature"]
    probabilities = np.exp(scaled - scaled.max())
    probabilities /= probabilities.sum()
    order = np.argsort(-probabilities)
    return {"type": "classification", "classes": [{"class": payload["classes"][i], "probability": float(probabilities[i])} for i in order],
            "top_class": payload["classes"][order[0]], "top_probability": float(probabilities[order[0]]), "numeric_precision": precision_note,
            "probability_semantics": "Softmax after temperature scaling fitted on the internal validation split; not a calibrated clinical probability."}


def detect(network, payload: dict, device, image: Image.Image) -> dict:
    import torch
    from torchvision.transforms import functional as F

    with torch.no_grad():
        result = network([F.to_tensor(image.convert("RGB")).to(device)])[0]
    width, height = image.size
    threshold = float(payload["score_threshold"])
    boxes = []
    for box, score in zip(result["boxes"].cpu().numpy(), result["scores"].cpu().numpy()):
        x1, y1, x2, y2 = (float(v) for v in box)
        boxes.append({"bbox_xyxy": [max(0.0, x1), max(0.0, y1), min(float(width), x2), min(float(height), y2)], "score": float(score),
                      "above_display_threshold": bool(score >= threshold)})
    return {"type": "detection", "class": payload["classes"][0], "coordinate_space": "source image pixels (x right, y down)",
            "image_size": [width, height], "display_score_threshold": threshold, "boxes": boxes,
            "score_semantics": "Detector confidence score; not a probability and not calibrated."}


def mask_to_source(mask: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Nearest-neighbour resize of a class-index mask back to the source (width, height)."""
    return np.asarray(Image.fromarray(mask.astype(np.uint8)).resize(size, Image.Resampling.NEAREST), dtype=np.uint8)


def segment(network, payload: dict, device, image: Image.Image) -> dict:
    import torch
    from pycocotools import mask as coco_mask
    from torchvision.transforms import InterpolationMode
    from torchvision.transforms import functional as TF

    size = payload["input_size"]
    arch_params = payload.get("arch_params") or {}
    rgb = payload.get("color") == "rgb" or arch_params.get("in_channels", 1) == 3
    tensor = TF.to_tensor(TF.resize(image.convert("RGB" if rgb else "L"), [size, size], interpolation=InterpolationMode.BILINEAR))
    if rgb:  # per-channel standardisation, as in ml_training.segment
        tensor = (tensor - tensor.mean(dim=(1, 2), keepdim=True)) / (tensor.std(dim=(1, 2), keepdim=True) + 1e-6)
    else:
        tensor = (tensor - tensor.mean()) / (tensor.std() + 1e-6)
    precision, precision_note = evaluated_precision(device)
    with torch.no_grad(), precision:
        prediction = network(tensor[None].to(device)).float().argmax(1).cpu().numpy()[0].astype(np.uint8)
    source = mask_to_source(prediction, image.size)
    segments = []
    for index, name in enumerate(payload["classes"], start=1):
        binary = np.asfortranarray((source == index).astype(np.uint8))
        area = int(binary.sum())
        if area == 0:
            continue
        rle = coco_mask.encode(binary)
        segments.append({"class_index": index, "segment": name, "area_px": area, "rle": {"size": rle["size"], "counts": rle["counts"].decode("ascii")}})
    return {"type": "segmentation", "coordinate_space": "source image pixels", "image_size": list(image.size),
            "segments": segments, "vessel_area_px": int((source > 0).sum()), "foreground_label": payload.get("foreground_label", "vessel"),
            "numeric_precision": precision_note, "encoding": "COCO RLE per segment (column-major)"}


def run_model(model: dict, image_path: Path) -> dict:
    with _inference_lock:
        network, payload, device = load_model(model)
        with Image.open(image_path) as image:
            image.load()
            if payload["kind"] == "image_classifier":
                output = classify(network, payload, device, image)
            elif payload["kind"] == "object_detector":
                output = detect(network, payload, device, image)
            else:
                output = segment(network, payload, device, image)
        return output


RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


def summary_label(output: dict) -> str:
    if output["type"] == "classification":
        return f"Research model top class: {output['top_class']}"[:128]
    if output["type"] == "detection":
        shown = sum(1 for box in output["boxes"] if box["above_display_threshold"])
        return f"Research model: {shown} {output['class']} box(es) above threshold"[:128]
    if output["type"] == "ecg_multilabel":
        positive = ", ".join(output["positive_classes"]) or "none"
        return f"Research ECG model, classes at/above threshold: {positive}"[:128]
    if output["type"] == "volume_segmentation":
        present = sum(1 for item in output["structures"] if item["voxels"])
        return f"Research model: {present} cardiac structure(s) segmented"[:128]
    return f"Research model: {len(output['segments'])} segment class(es) predicted"[:128]


def _suffix(name: str) -> str:
    lower = name.lower()
    return ".nii.gz" if lower.endswith(".nii.gz") else Path(lower).suffix


def _usable(record: UploadedFile) -> bool:
    return bool(record.is_associated) and record.withdrawn_at is None


def check_input(model: dict, file_record: UploadedFile, declared_input_type: str, options: Optional[dict] = None,
                db: Optional[Session] = None) -> Optional[UploadedFile]:
    """Applicability gate on the upload's metadata: modality, container and declared type.

    Returns the companion upload (the WFDB signal file) when the input needs one."""
    kind = model.get("inference_input", "image_2d")
    options = options or {}
    if kind not in UPLOAD_INPUTS:
        raise InferenceNotPermitted(f"{model['display_name']} has no upload inference path; its held-out evaluation is evidence only.")
    if not _usable(file_record):
        raise InferenceNotPermitted("Unassociated uploads cannot enter case-level processing.")
    suffix = _suffix(file_record.stored_filename)
    companion = None
    if kind == "image_2d":
        if file_record.modality != ModalityType.IMAGE:
            raise InferenceNotPermitted("Research image models accept image uploads only.")
        if suffix not in RASTER_SUFFIXES:
            raise InferenceNotPermitted("These 2D models accept PNG, JPEG or BMP images only; DICOM/NIfTI are not supported by them.")
    elif kind == "volume_nifti":
        if file_record.modality != ModalityType.IMAGE or suffix not in {".nii", ".nii.gz"}:
            raise InferenceNotPermitted("This volumetric model accepts one NIfTI frame (.nii or .nii.gz).")
    else:
        if file_record.modality != ModalityType.ECG or suffix not in {".hea", ".csv"}:
            raise InferenceNotPermitted("The ECG model runs on a WFDB header (.hea) with its signal file, or on a CSV record.")
        if suffix == ".hea":
            companion_id = options.get("companion_upload_id")
            companion = db.get(UploadedFile, companion_id) if db is not None and companion_id is not None else None
            if companion is None or companion.case_id != file_record.case_id:
                raise InferenceNotPermitted("WFDB_SIGNAL_FILE_REQUIRED: select the record's .dat signal upload from the same case.")
            if not _usable(companion) or _suffix(companion.stored_filename) != ".dat":
                raise InferenceNotPermitted("WFDB_SIGNAL_FILE_REQUIRED: the signal upload must be a current, case-bound .dat file.")
        elif not options.get("amplitude_unit"):
            raise InferenceNotPermitted("AMPLITUDE_UNIT_NOT_DECLARED: declare the CSV amplitude unit (mV or uV).")
    if declared_input_type not in model.get("supported_modalities", []):
        supported = ", ".join(MODALITY_LABELS.get(m, m) for m in model.get("supported_modalities", []))
        raise InferenceNotPermitted(f"{model['display_name']} was trained only on: {supported}.")
    if not Path(file_record.file_path).exists() or (companion is not None and not Path(companion.file_path).exists()):
        raise InferenceNotPermitted("Stored file missing from disk store.")
    return companion


def _input_envelope(model: dict) -> dict:
    bundle = model["artifact_bundle"]
    path = bundle.get("input_envelope_path")
    if not path or not _resolve_artifact_path(path).exists():
        raise InferenceNotPermitted("INPUT_ENVELOPE_MISSING: no recorded input envelope; upload inference is refused.")
    try:
        return volume_inference.load_envelope(_resolve_artifact_path(path), bundle["dataset_version"])
    except volume_inference.VolumeInputError as exc:
        raise InferenceNotPermitted(str(exc)) from exc


def prepare_input(model: dict, file_record: UploadedFile, companion: Optional[UploadedFile], options: Optional[dict] = None):
    """Read the upload and check its content against the model's input contract.

    Runs in the API before a job is queued (so refusals are typed) and again at execution.
    Returns the prepared ECG record or volume; images are prepared by run_model."""
    kind = model.get("inference_input", "image_2d")
    options = options or {}
    try:
        if kind == "ecg_12lead":
            contract = ecg_inference.CONTRACTS.get(model["artifact_bundle"].get("preprocessing_version"))
            if contract is None:
                raise InferenceNotPermitted("No input contract is registered for this ECG preprocessing version.")
            with ExitStack() as stack:
                primary = stack.enter_context(upload_store.materialize(Path(file_record.file_path)))
                signal = stack.enter_context(upload_store.materialize(Path(companion.file_path))) if companion is not None else None
                record = ecg_inference.read_upload(primary, signal, options.get("amplitude_unit"))
            return ecg_inference.check_record(record, contract)
        if kind == "volume_nifti":
            envelope = _input_envelope(model)
            with upload_store.materialize(Path(file_record.file_path)) as plain:
                return volume_inference.read_volume(plain, envelope)
    except (ecg_inference.EcgInputError, volume_inference.VolumeInputError) as exc:
        raise InferenceNotPermitted(f"MODEL_INPUT_INCOMPATIBLE: {exc}") from exc
    return None


def run_prepared(model: dict, prepared) -> dict:
    """Run an ECG or volumetric model on input returned by prepare_input."""
    with _inference_lock:
        network, payload, device = load_model(model)
        if payload["kind"] == "ecg_classifier":
            contract = ecg_inference.CONTRACTS[model["artifact_bundle"]["preprocessing_version"]]
            try:
                ecg_inference.verify_contract(payload, contract)
            except ecg_inference.EcgInputError as exc:
                raise InferenceNotPermitted(str(exc)) from exc
            return ecg_inference.classify(network, payload, device, prepared, evaluated_precision(device))
        mask = volume_inference.predict(network, payload, device, prepared)
        return volume_inference.segmentation_output(mask, payload, prepared, volume_inference.held_out_agreement(_report(model)), device)


# A native image frame carries at most a few burned-in annotations; a photograph or scan
# of a printed report page carries many lines of text. Measured on held-out in-domain
# frames of every upload model (docs/validation/DOCUMENT_PHOTO_GATE.md).
DOCUMENT_TEXT_LINE_LIMIT = 8
_WORD_LIKE = re.compile(r"[A-Za-z]{3,}")


def printed_text_lines(image_path: Path) -> Optional[int]:
    """Lines of printed text that local OCR reads in the image (None if OCR is unavailable)."""
    from app.services import ocr

    if not ocr.ocr_available():
        return None
    with Image.open(image_path) as image:
        image.load()
        page = ocr.ocr_image(image)
    return sum(1 for line in page.lines if _WORD_LIKE.search(line["text"]))


def check_document_photograph(image_path: Path) -> dict:
    """Content gate, independent of the user's declared modality: a photograph of a printed
    document is refused before any image model sees it."""
    lines = printed_text_lines(image_path)
    if lines is not None and lines >= DOCUMENT_TEXT_LINE_LIMIT:
        raise InferenceNotPermitted(
            f"MODEL_INPUT_INCOMPATIBLE: this image looks like a photograph or scan of a printed document "
            f"({lines} lines of printed text were read). Research image models accept native image frames only; "
            "upload the page as a report for text extraction, and provide the original DICOM/PACS export or native "
            "frames if image analysis is needed."
        )
    return {"printed_text_lines": lines, "document_text_line_limit": DOCUMENT_TEXT_LINE_LIMIT,
            "status": "NOT_CHECKED_OCR_UNAVAILABLE" if lines is None else "PASSED"}


CONTENT_CHECKS = {
    "ecg_12lead": "Signal read exactly (WFDB checksums or CSV time column) and checked against the trained contract: sampling rate, duration, lead set, amplitude and flatline limits.",
    "volume_nifti": "Header and voxels checked against the recorded development envelope: one 3-D frame, square in-plane pixels, slice axis last, voxel spacing range.",
}
MAPPING_STATUS = {"image_2d": "NOT_MAPPABLE: RESEARCH_MODEL_OUTPUT_2D_SOURCE_COORDINATES",
                  "ecg_12lead": "NOT_MAPPABLE: RESEARCH_MODEL_OUTPUT_WHOLE_RECORDING",
                  "volume_nifti": "NOT_MAPPABLE: RESEARCH_MODEL_OUTPUT_NATIVE_VOXEL_GRID"}


def execute_research_inference(db: Session, file_record: UploadedFile, model_id: str, declared_input_type: str,
                               actor: Optional[User], options: Optional[dict] = None) -> InferenceRun:
    model = get_model(model_id)
    companion = check_input(model, file_record, declared_input_type, options, db)
    bundle = model["artifact_bundle"]
    kind = model.get("inference_input", "image_2d")
    prepared = None
    if kind == "image_2d":
        with upload_store.materialize(Path(file_record.file_path)) as plain:
            content_check = check_document_photograph(plain)
    else:
        prepared = prepare_input(model, file_record, companion, options)
        content_check = {"status": "PASSED", "checks": CONTENT_CHECKS[kind]}
    started_at = datetime.now(timezone.utc)
    start = time.perf_counter()
    try:
        if prepared is None:
            with upload_store.materialize(Path(file_record.file_path)) as plain:
                output = run_model(model, plain)
        else:
            output = run_prepared(model, prepared)
        output["input_content_check"] = content_check
    except Exception as exc:
        logger.exception("Research model %s failed for upload %s", model_id, file_record.id)
        db.rollback()
        run = InferenceRun(case_id=file_record.case_id, file_id=file_record.id, modality=file_record.modality, model_name=model_id,
                           model_version=bundle["checkpoint_sha256"][:16], preprocessing_version=bundle["preprocessing_version"],
                           status=EvidenceStatus.ERROR, error_message=f"Research model failed: {type(exc).__name__}",
                           execution_time_ms=round((time.perf_counter() - start) * 1000, 2), started_at=started_at,
                           completed_at=datetime.now(timezone.utc))
        db.add(run)
        db.commit()
        log_audit_event(db=db, action="RESEARCH_INFERENCE_FAILED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor,
                        details={"case_id": file_record.case_id, "file_id": file_record.id, "model_id": model_id, "error_type": type(exc).__name__})
        raise
    exec_ms = round((time.perf_counter() - start) * 1000, 2)
    run = InferenceRun(case_id=file_record.case_id, file_id=file_record.id, modality=file_record.modality, model_name=model_id,
                       model_version=bundle["checkpoint_sha256"][:16], preprocessing_version=bundle["preprocessing_version"],
                       status=EvidenceStatus.COMPLETED, execution_time_ms=exec_ms, started_at=started_at, completed_at=datetime.now(timezone.utc))
    db.add(run)
    db.flush()
    classification = output["type"] == "classification"
    calibration = {"classification": "TEMPERATURE_SCALED_ON_INTERNAL_VALIDATION_SPLIT", "ecg_multilabel": "PLATT_SCALED_PER_CLASS_ON_INTERNAL_VALIDATION_FOLD"}
    applicability = "Input type declared by the requesting user; no out-of-distribution detection is performed."
    if kind != "image_2d":
        applicability = f"Input type declared by the requesting user. {CONTENT_CHECKS[kind]} No out-of-distribution detector is used."
    finding = Finding(
        inference_run_id=run.id, case_id=file_record.case_id, modality=file_record.modality,
        category=f"Research model output ({model['task'].replace('_', ' ')})"[:128], label=summary_label(output),
        raw_confidence=output["top_probability"] if classification else None,
        calibration_status=calibration.get(output["type"], "UNCALIBRATED"),
        representation_level=RepresentationLevel.L1_GENERIC, anatomical_region=None,
        mapping_status=MAPPING_STATUS[kind],
        review_status=EvidenceStatus.PENDING_HUMAN_REVIEW, is_demo=False,
        evidence_provenance={
            "source": "MODEL_INFERENCE", "output_status": "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED", "model_id": model_id,
            "model_display_name": model["display_name"], "model_status": model["status"], "checkpoint_sha256": bundle["checkpoint_sha256"],
            "dataset_version": bundle["dataset_version"], "dataset_license": bundle["dataset_license"],
            "evaluation_report_path": bundle["evaluation_report_path"], "model_card_path": bundle["model_card_path"],
            "held_out_evaluation": evaluation_summary(model), "declared_input_type": declared_input_type,
            "applicability": applicability,
            "anatomy_system_of_model": model.get("anatomy"), "source_file_sha256": file_record.file_hash, "output": output,
            **({"companion_file_id": companion.id, "companion_file_sha256": companion.file_hash} if companion is not None else {}),
            **({"declared_amplitude_unit": options["amplitude_unit"]} if options and options.get("amplitude_unit") else {}),
        },
    )
    db.add(finding)
    db.commit()
    log_audit_event(db=db, action="RESEARCH_INFERENCE_COMPLETED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor,
                    details={"case_id": file_record.case_id, "file_id": file_record.id, "finding_id": finding.id, "model_id": model_id,
                             "declared_input_type": declared_input_type, "exec_time_ms": exec_ms})
    db.refresh(run)
    return run
