"""Research-only inference with registered MedTwin models (ml_training pipelines).

A model may run only when its registry entry allows research inference and its
artifact bundle passes the research gate: licence verified, held-out evaluation
report present, checkpoint present with the registered SHA-256. Outputs are
returned in the uploaded image's own pixel coordinates and are labelled
MODEL_INFERENCE / RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED. Before a 2-D image model
runs, the upload must pass the printed-document check and the model's own feature-space
reference (app/services/image_ood.py), whatever modality the user declared.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import threading
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional
from weakref import WeakValueDictionary

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.models.entities import (EvidenceStatus, Finding, InferenceRun, ModalityType, RepresentationLevel, ReviewedDemographics,
                                 UploadedFile, User)
from app.services import dicom_raster, echo_inference, ecg_inference, image_ood, upload_store, volume_inference
from app.services.audit_service import log_audit_event
from app.services.imaging_readers import open_raster
from app.services.model_registry import _load_registry, _resolve_artifact_path, _sha256

logger = logging.getLogger(__name__)
MODALITY_LABELS = {"ENDOSCOPY": "GI endoscopy image", "ANGIOGRAPHY": "X-ray coronary angiogram", "CT": "CT image or slice",
                   "MICROSCOPY": "single segmented blood-cell microscopy image",
                   "ECG": "resting 12-lead ECG recording (digital signal, not a photograph or printout)",
                   "MRI": "short-axis cardiac cine-MRI frame at end-diastole or end-systole",
                   "XRAY": "upper-limb musculoskeletal radiograph (shoulder, humerus, elbow, forearm, wrist, hand or finger)",
                   "HEAD_CT": "non-contrast axial head CT slice in a brain window (PNG or JPEG)",
                   "BRAIN_MRI_DIFFUSION": "skull-stripped brain diffusion MRI: DWI (b=1000) and ADC on one grid, stacked in one 4-D NIfTI, DWI first",
                   "BRAIN_MRI_MULTISEQUENCE": "skull-stripped brain MRI on a 1 mm grid: FLAIR, T1, post-contrast T1 and T2, co-registered and stacked in one 4-D NIfTI in that order",
                   "ECHO": "apical-4-chamber echocardiography video in EchoNet format (112 x 112 pixels, sector cropped and masked; MP4 or AVI)",
                   "CT_ABDOMEN_VOLUME": "contrast-enhanced abdominal CT volume in Hounsfield units, one NIfTI file",
                   "HEAD_CT_SERIES": "non-contrast axial head CT series in Hounsfield units (every slice of one DICOM series)",
                   "CHEST_XRAY": "frontal (PA or AP) chest radiograph",
                   "CT_CHEST_VOLUME": "thoracic CT volume in Hounsfield units",
                   "DERMATOLOGY": "clinical photograph of one skin lesion (PAD-UFES-20 research scope; not dermoscopy or pathology)"}
UPLOAD_INPUTS = {"image_2d", "ecg_12lead", "volume_nifti", "echo_video"}
# Models that run only on an assembled multi-file DICOM series.
SERIES_INPUTS = {"head_ct_series"}
# Inputs whose models never run without a feature-space applicability reference.
REFERENCE_GATED_INPUTS = {"image_2d", "echo_video", "head_ct_series"}
# Axial head CT is acquired with a gantry tilt of up to about 30 degrees.
HEAD_CT_MAX_TILT_DEG = 35.0
# A series is refused when more than this share of its slices lies outside the model's applicability reference.
HEAD_CT_MAX_REFUSED_SLICE_FRACTION = 0.5
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


def record_abstention(db: Session, upload: UploadedFile, model_id: str, reason: str, actor: Optional[User]) -> InferenceRun:
    """A preflight refusal is evidence of an abstention, never a disease finding."""
    run = InferenceRun(case_id=upload.case_id, file_id=upload.id, modality=upload.modality,
                       model_name=model_id, model_version="NOT_RUN", preprocessing_version="PREFLIGHT_ONLY",
                       status=EvidenceStatus.ABSTAIN, error_message=reason, completed_at=datetime.now(timezone.utc))
    db.add(run)
    db.commit()
    db.refresh(run)
    log_audit_event(db=db, action="RESEARCH_INFERENCE_ABSTAINED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor,
                    details={"case_id": upload.case_id, "file_id": upload.id, "model_id": model_id, "status": "ABSTAIN"})
    return run


def research_gate(model: dict) -> dict:
    from app.services.model_usage_policy import usage_gate
    bundle = model.get("artifact_bundle") or {}
    blockers = list(usage_gate(model)["blockers"])
    if not model.get("research_inference"):
        blockers.append("NOT_REGISTERED_FOR_RESEARCH_INFERENCE")
    if model.get("status") not in {"READY_UNVALIDATED", "VALIDATED"}:
        blockers.append(f"STATUS_{model.get('status')}")
    if (model.get("research_quality_assessment") or {}).get("status") == "FAILED_DECLARED_TARGET":
        blockers.append("DECLARED_TARGET_FAILED_EVALUATION")
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
    if model.get("research_inference") and model.get("inference_input", "image_2d") in REFERENCE_GATED_INPUTS:
        # A 2-D image or echo video model never runs without its feature-space applicability reference.
        reference = bundle.get("ood_reference_path")
        if not reference or not _resolve_artifact_path(reference).exists():
            blockers.append("OOD_REFERENCE_MISSING")
        elif _checkpoint_hash(_resolve_artifact_path(reference)) != bundle.get("ood_reference_sha256"):
            blockers.append("OOD_REFERENCE_HASH_MISMATCH")
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
        summary = {"test_n": report["test_n"], "macro_auroc": metrics["macro_auroc"], "macro_auprc": metrics["macro_auprc"],
                   "macro_auroc_95ci": [ci.get("macro_auroc", {}).get("low"), ci.get("macro_auroc", {}).get("high")],
                   "macro_f1_at_validation_thresholds": metrics["macro_f1_at_validation_thresholds"]}
        paired = report.get("paired_difference")
        if paired:
            interval = paired.get("macro_auroc_95ci") or {}
            summary.update({"ecg_only_macro_auroc_same_test_records": report["arms"]["ecg_only"]["macro_auroc"],
                            "fusion_minus_ecg_only_macro_auroc": paired["macro_auroc"],
                            "fusion_minus_ecg_only_95ci": [interval.get("low"), interval.get("high")], "fusion_conclusion": paired["conclusion"]})
        return summary
    if model["task"] == "survival_prediction":
        metrics, ci = report["metrics"], report.get("confidence_intervals_95", {})
        return {"test_n": report["test_n"], "harrell_c": metrics["harrell_c"],
                "harrell_c_95ci": [ci.get("harrell_c", {}).get("low"), ci.get("harrell_c", {}).get("high")],
                "integrated_brier": metrics["integrated_brier_model"], "integrated_brier_kaplan_meier": metrics["integrated_brier_kaplan_meier"],
                "integrated_brier_skill": metrics["integrated_brier_skill"]}
    if model["task"] == "multilabel_image_classification":
        # Slice-level per-label AUROC on the held-out patients, plus the study-level "any" AUROC when reported.
        labels = report.get("per_label") or {}
        summary = {"test_n": report.get("test_n"), "test_patients": report.get("test_patients"), "mean_auroc": report.get("mean_auroc")}
        for values in labels.values():
            if isinstance(values, dict) and values.get("name") and values.get("auroc") is not None:
                summary[f"{values['name']}_auroc"] = values["auroc"]
        study = report.get("study_level_any") or {}
        if study.get("auroc") is not None:
            summary["study_level_any_auroc"] = study["auroc"]
        return summary
    if model["task"] == "semantic_segmentation":
        test = report["test"]
        return {"test_n": test["n_images"], "mean_foreground_dice": test["mean_foreground_dice_per_image"], "vessel_dice": test.get("vessel_dice")}
    if model["task"] == "volumetric_semantic_segmentation":
        metrics, structures = report["metrics"], report["metrics"]["per_structure"]
        summary = {"test_n": report["test_n"], "test_patients": report["test_patients"], "mean_case_macro_dice": metrics["mean_case_macro_dice"]}
        if "left_ventricular_cavity" in structures:
            return {**summary, "lv_cavity_dice": structures["left_ventricular_cavity"]["mean_dice"], "myocardium_dice": structures["myocardium"]["mean_dice"],
                    "rv_cavity_dice": structures["right_ventricular_cavity"]["mean_dice"],
                    "lv_ef_mean_absolute_error": report["clinical_indices"]["lv_ef_percent"]["mean_absolute_error"]}
        for name, values in structures.items():
            summary[f"{name}_dice"] = values["mean_dice"]
        for name, values in (metrics.get("regions") or {}).items():
            summary[f"{name}_dice"] = values["mean_dice"]
        detection = metrics.get("lesion_detection")
        if detection:
            summary.update({"lesion_sensitivity": detection["lesion_sensitivity"], "lesion_f1": detection["lesion_f1"],
                            "false_positive_components_per_case": detection["false_positive_components_per_case"]})
        return summary
    if model["task"] == "video_regression":
        test = report["test"]
        served = report.get("test_serving_gate")
        if served:  # the population the whole serving pipeline (format gate and applicability reference) accepts
            metrics, ci = served["metrics"], served["metrics_95ci"]
            return {"test_n": served["accepted_by_both_gates"], "test_videos": test["videos"], "mae": metrics["mae"], "rmse": metrics["rmse"],
                    "r2": metrics["r2"], "bias": metrics["bias"], "mae_95ci": [ci["mae"].get("low"), ci["mae"].get("high")],
                    "reduced_ef_auroc": served["reduced_ef_auroc"], "population": "accepted by the format gate and the applicability reference"}
        metrics, ci = test["metrics"], test["metrics_95ci"]
        return {"test_n": test["accepted_by_gate"], "test_videos": test["videos"], "mae": metrics["mae"], "rmse": metrics["rmse"], "r2": metrics["r2"],
                "bias": metrics["bias"], "mae_95ci": [ci["mae"].get("low"), ci["mae"].get("high")],
                "reduced_ef_auroc": test["reduced_ef_discrimination"]["auroc_of_negative_estimate"], "population": "accepted by the format gate"}
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
            "demographic_inputs": model.get("demographic_inputs", []),
            "requires_clinical_features": model.get("requires_clinical_features", False),
            "clinical_metadata_contract": model.get("clinical_metadata_contract"),
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
    if payload["kind"] in ("image_classifier", "image_multilabel_classifier"):
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
    elif payload["kind"] == "ecg_classifier" and payload.get("arch") in ("resnet1d_compact", ecg_inference.FUSION_ARCH):
        network = ecg_inference.build_network(len(payload["classes"]), len(payload["leads"]), demographic_fusion=payload["arch"] == ecg_inference.FUSION_ARCH)
    elif payload["kind"] == "volumetric_semantic_segmenter":
        try:
            network = volume_inference.build_network(payload)
        except volume_inference.VolumeInputError as exc:
            raise InferenceNotPermitted(str(exc)) from exc
        # Training resumption state is not needed for serving.
        payload.pop("best_state_dict", None)
        payload.pop("optimizer_state_dict", None)
    elif payload["kind"] == "echo_ef_regressor" and payload.get("arch") == echo_inference.ARCH:
        network = echo_inference.build_network()
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


def classifier_tensor(payload: dict, image: Image.Image):
    from torchvision import transforms

    size = payload["image_size"]
    transform = transforms.Compose([transforms.Resize(int(size * 1.14)), transforms.CenterCrop(size), transforms.ToTensor(),
                                    transforms.Normalize(payload["normalization"]["mean"], payload["normalization"]["std"])])
    return transform(image.convert("RGB"))[None]


def multilabel_tensor(payload: dict, image: Image.Image):
    """As ml_training.rsna_ich evaluated: short side to the input size, centre crop, ImageNet normalisation."""
    from torchvision import transforms

    size = payload["image_size"]
    transform = transforms.Compose([transforms.Resize(size), transforms.CenterCrop(size), transforms.ToTensor(),
                                    transforms.Normalize(payload["normalization"]["mean"], payload["normalization"]["std"])])
    return transform(image.convert("RGB"))[None]


def multilabel_precision(device):
    """ml_training.rsna_ich scored its test patients under float16 autocast on CUDA."""
    import torch

    if device.type == "cuda":
        return torch.autocast("cuda", dtype=torch.float16), "float16 autocast on CUDA, as in the held-out evaluation"
    return torch.autocast("cpu", enabled=False), "float32 on CPU; differs from the evaluated float16 CUDA configuration"


def segmenter_tensor(payload: dict, image: Image.Image):
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
    return tensor[None]


def _unet_encoder(network) -> list:
    """The encoder blocks of a MONAI UNet, outermost first, ending with the bottleneck."""
    import torch
    from monai.networks.layers.simplelayers import SkipConnection

    blocks = []
    node = network.model
    while isinstance(node, torch.nn.Sequential) and len(node) == 3 and isinstance(node[1], SkipConnection):
        blocks.append(node[0])
        node = node[1].submodule
    return blocks + [node]


def _feature_stages(network, payload: dict) -> list:
    if payload["kind"] in ("image_classifier", "image_multilabel_classifier"):
        if payload["arch"].startswith("resnet"):
            return [network.layer1, network.layer2, network.layer3, network.layer4]
        return list(network.features)[1:]
    if payload["kind"] == "object_detector":
        body = network.backbone.body
        return [body.layer1, body.layer2, body.layer3, body.layer4]
    return _unet_encoder(network)


# Recorded in each applicability reference; a reference built from other features is refused.
FEATURE_VERSION = "input-statistics+network-stages-v1"


def _input_statistics(tensor) -> np.ndarray:
    """Summary of the image as the model receives it (after its own preprocessing): per-channel
    mean and spread, intensity quantiles and, for colour input, the spread of channel differences,
    which is zero for a greyscale image whatever the normalisation."""
    import torch

    x = tensor.float()[0] if tensor.dim() == 4 else tensor.float()
    flat = x.reshape(x.shape[0], -1)
    grey = flat.mean(dim=0)
    parts = [flat.mean(dim=1), flat.std(dim=1), torch.quantile(grey, torch.tensor([0.05, 0.25, 0.5, 0.75, 0.95], device=grey.device))]
    if x.shape[0] == 3:
        differences = torch.stack([flat[0] - flat[1], flat[1] - flat[2]])
        parts += [differences.std(dim=1), differences.abs().mean(dim=1)]
    return torch.cat(parts).cpu().numpy().astype(np.float64)


def image_features(network, payload: dict, device, image: Image.Image) -> list[np.ndarray]:
    """The features the applicability reference is fitted on: statistics of the model's input
    tensor, then every stage of the network (ResNet layers, EfficientNet stages, U-Net encoder
    levels, the detector's ResNet stages) averaged over space, computed with the model's own
    preprocessing and numeric precision."""
    import torch
    from torchvision.transforms import functional as F

    captured: list = []
    hooks = [stage.register_forward_hook(lambda module, inputs, output: captured.append(output.float().mean(dim=(2, 3))))
             for stage in _feature_stages(network, payload)]
    try:
        with torch.no_grad():
            if payload["kind"] == "image_classifier":
                tensor = classifier_tensor(payload, image).to(device)
                precision, _ = evaluated_precision(device)
                with precision:
                    network(tensor)
            elif payload["kind"] == "image_multilabel_classifier":
                tensor = multilabel_tensor(payload, image).to(device)
                precision, _ = multilabel_precision(device)
                with precision:
                    network(tensor)
            elif payload["kind"] == "object_detector":
                tensor = F.to_tensor(image.convert("RGB")).to(device)
                images, _ = network.transform([tensor])
                network.backbone.body(images.tensors)
            else:
                tensor = segmenter_tensor(payload, image).to(device)
                precision, _ = evaluated_precision(device)
                with precision:
                    network(tensor)
            inputs = _input_statistics(tensor)
    finally:
        for hook in hooks:
            hook.remove()
    return [inputs] + [values.cpu().numpy()[0].astype(np.float64) for values in captured]


def classify(network, payload: dict, device, image: Image.Image, clinical_features: Optional[dict] = None) -> dict:
    import torch

    precision, precision_note = evaluated_precision(device)
    captured = []
    hook = network.avgpool.register_forward_hook(lambda _module, _inputs, output: captured.append(output.detach().float().flatten(1))) if payload.get("frozen_linear_head") else None
    try:
        with torch.no_grad(), precision:
            logits = network(classifier_tensor(payload, image).to(device)).float().cpu().numpy()[0]
    finally:
        if hook is not None:
            hook.remove()
    if hook is not None:
        # The frozen-feature experiment fitted/evaluated its linear head in
        # float32 after a bfloat16 encoder. Reproduce that precision boundary.
        logits = captured[0].cpu().numpy()[0] @ network.fc.weight.detach().float().cpu().numpy().T + network.fc.bias.detach().float().cpu().numpy()
        precision_note += "; frozen linear head evaluated in float32"
    schema = payload.get("clinical_metadata_encoder")
    metadata_note = None
    if schema:
        from app.services.skin_metadata import check_serving_features
        try:
            attributes = check_serving_features(clinical_features, schema)
        except ValueError as exc:
            raise InferenceNotPermitted(str(exc)) from exc
        coefficients = payload["clinical_metadata_weights"].cpu().numpy()
        if coefficients.shape != (len(payload["classes"]), len(attributes)):
            raise InferenceNotPermitted("Clinical metadata weights do not match their declared input contract")
        logits = logits + coefficients @ attributes
        metadata_note = {"fields": sorted(clinical_features), "values": clinical_features,
                         "source": "explicit user-provided research attributes; pending human review",
                         "preprocessing_version": schema["version"], "imputed_fields": [key for key in ("gender",) if not clinical_features.get(key)]}
    scaled = logits / payload["temperature"]
    probabilities = np.exp(scaled - scaled.max())
    probabilities /= probabilities.sum()
    order = np.argsort(-probabilities)
    return {"type": "classification", "classes": [{"class": payload["classes"][i], "probability": float(probabilities[i])} for i in order],
            "top_class": payload["classes"][order[0]], "top_probability": float(probabilities[order[0]]), "numeric_precision": precision_note,
            "probability_semantics": "Softmax after temperature scaling fitted on the internal validation split; not a calibrated clinical probability.",
            **({"clinical_metadata": metadata_note} if metadata_note else {})}


def classify_multilabel(network, payload: dict, device, image: Image.Image) -> dict:
    """Independent sigmoid per label; each compared with its threshold chosen on validation patients."""
    import torch

    precision, precision_note = multilabel_precision(device)
    with torch.no_grad(), precision:
        logits = network(multilabel_tensor(payload, image).to(device)).float().cpu().numpy()[0]
    probabilities = 1.0 / (1.0 + np.exp(-logits))
    labels = []
    for key, name, probability in zip(payload["label_keys"], payload["classes"], probabilities):
        threshold = float(payload["thresholds"][key])
        labels.append({"label": name, "probability": float(probability), "threshold": threshold, "at_or_above_threshold": bool(probability >= threshold)})
    return {"type": "multilabel_classification", "labels": labels, "positive_labels": [item["label"] for item in labels if item["at_or_above_threshold"]],
            "numeric_precision": precision_note,
            "probability_semantics": "Independent sigmoid outputs of a slice-level model; not calibrated clinical probabilities.",
            "threshold_semantics": f"Each label's threshold: {payload.get('threshold_rule', 'maximum of Youden’s J on the validation patients')}; "
                                   "it is not a clinical decision threshold."}


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

    precision, precision_note = evaluated_precision(device)
    with torch.no_grad(), precision:
        prediction = network(segmenter_tensor(payload, image).to(device)).float().argmax(1).cpu().numpy()[0].astype(np.uint8)
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


def run_model(model: dict, image_path: Path, options: Optional[dict] = None) -> dict:
    with _inference_lock:
        network, payload, device = load_model(model)
        image, orientation = open_raster(image_path)
        if payload["kind"] == "image_classifier":
            output = classify(network, payload, device, image, (options or {}).get("clinical_features"))
        elif payload["kind"] == "image_multilabel_classifier":
            output = classify_multilabel(network, payload, device, image)
        elif payload["kind"] == "object_detector":
            output = detect(network, payload, device, image)
        else:
            output = segment(network, payload, device, image)
        output["exif_orientation_applied"] = orientation
        return output


RASTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}
IMAGE_2D_SUFFIXES = RASTER_SUFFIXES | {".dcm"}


@contextmanager
def raster_input(model: dict, file_record: UploadedFile, declared_input_type: str,
                 options: Optional[dict] = None) -> Iterator[tuple[Path, Optional[dict]]]:
    """The raster a 2-D model and its gates read, with the DICOM conversion record (None for PNG/JPEG/BMP).

    A DICOM frame is converted by app.services.dicom_raster (the model's declared DICOM window if any, else the
    frame's VOI) into a lossless PNG in a private work directory that is removed afterwards."""
    with upload_store.materialize(Path(file_record.file_path)) as plain:
        if _suffix(file_record.stored_filename) != ".dcm":
            yield plain, None
            return
        try:
            frame = dicom_raster.read_frame(plain, declared_input_type, (options or {}).get("frame_index"), model.get("dicom_window"))
        except dicom_raster.DicomRasterError as exc:
            # A missing or invalid frame choice is a request error, not a property of the image.
            request_error = str(exc).startswith(("FRAME_INDEX_", "DICOM_INPUT_TYPE_NOT_MAPPED"))
            raise InferenceNotPermitted(str(exc) if request_error else f"MODEL_INPUT_INCOMPATIBLE: {exc}") from exc
        work = upload_store.work_dir()
        work.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=work) as private:
            target = Path(private) / "frame.png"
            frame.image.save(target, format="PNG")
            yield target, frame.provenance


def summary_label(output: dict) -> str:
    if output["type"] == "classification":
        return f"Research model top class: {output['top_class']}"[:128]
    if output["type"] == "multilabel_classification":
        return f"Research model, labels at/above threshold: {', '.join(output['positive_labels']) or 'none'}"[:128]
    if output["type"] == "detection":
        shown = sum(1 for box in output["boxes"] if box["above_display_threshold"])
        return f"Research model: {shown} {output['class']} box(es) above threshold"[:128]
    if output["type"] == "ecg_multilabel":
        positive = ", ".join(output["positive_classes"]) or "none"
        return f"Research ECG model, classes at/above threshold: {positive}"[:128]
    if output["type"] == "volume_segmentation":
        present = [item for item in output["structures"] if item["voxels"]]
        if not present:
            return "Research model: no structure segmented"
        named = ", ".join(f"{item['structure'].replace('_', ' ')} {item['volume_ml']:.1f} mL" for item in present)
        return f"Research model segmented: {named}"[:128]
    if output["type"] == "regression":
        return f"Research model: estimated LVEF {output['ef_percent']:.1f}% ({len(output['clip_ef_percent'])} clips)"[:128]
    if output["type"] == "series_slice_multilabel":
        series = output["series_level"]
        state = "at/above" if series["at_or_above_threshold"] else "below"
        partial = "" if series["complete_coverage"] else " (partial)"
        return (f"Research model: {series['label']} {state} threshold on {series['coverage']}{partial}; "
                f"{len(output['slices_with_positive_labels'])} slices with labels")[:128]
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
    if model.get("requires_clinical_features"):
        from app.services.skin_metadata import check_serving_features
        try:
            check_serving_features(options.get("clinical_features"), model.get("clinical_metadata_contract") or {})
        except ValueError as exc:
            raise InferenceNotPermitted(str(exc)) from exc
    if kind in SERIES_INPUTS:
        raise InferenceNotPermitted(f"{model['display_name']} reads neighbouring slices: it runs on an assembled DICOM series of the case's "
                                    "slice uploads (Medical Imaging, DICOM series), not on one file.")
    if kind not in UPLOAD_INPUTS:
        raise InferenceNotPermitted(f"{model['display_name']} has no upload inference path; its held-out evaluation is evidence only.")
    if not _usable(file_record):
        raise InferenceNotPermitted("Unassociated uploads cannot enter case-level processing.")
    suffix = _suffix(file_record.stored_filename)
    companion = None
    if kind == "image_2d":
        if file_record.modality != ModalityType.IMAGE:
            raise InferenceNotPermitted("Research image models accept image uploads only.")
        if suffix not in IMAGE_2D_SUFFIXES:
            raise InferenceNotPermitted("These 2-D models accept PNG, JPEG or BMP images, or one DICOM frame (.dcm); volumes go to the "
                                        "volumetric models.")
    elif kind == "volume_nifti":
        if file_record.modality != ModalityType.IMAGE or suffix not in {".nii", ".nii.gz", *volume_inference.ITK_SUFFIXES}:
            raise InferenceNotPermitted("This volumetric model accepts one volume file: NIfTI (.nii, .nii.gz), NRRD (.nrrd) or "
                                        "single-file MetaImage (.mha); a DICOM series is assembled from its slice uploads.")
    elif kind == "echo_video":
        if file_record.modality != ModalityType.IMAGE or suffix not in echo_inference.VIDEO_SUFFIXES:
            raise InferenceNotPermitted("This echocardiography model accepts one video upload (MP4 or AVI).")
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
    if not upload_store.available(Path(file_record.file_path)) or (companion is not None and not upload_store.available(Path(companion.file_path))):
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


@dataclass
class FusedEcgInput:
    """An ECG record plus the age and sex a demographic-fusion model takes, with where they came from."""

    record: Any
    demographics: dict


def resolve_demographics(file_record: UploadedFile, options: dict, db: Optional[Session]) -> dict:
    """Age and sex for a fusion model: declared in the request, else the case's latest reviewed demographics.

    Nothing is read from OCR or extracted text; without both values the run is refused."""
    age, sex = options.get("age_years"), options.get("sex")
    sources, warnings = [], []
    if age is not None or sex is not None:
        sources.append("DECLARED_IN_REQUEST")
    if (age is None or sex is None) and db is not None:
        latest = (db.query(ReviewedDemographics).filter(ReviewedDemographics.case_id == file_record.case_id)
                  .order_by(ReviewedDemographics.revision.desc()).first())
        if latest is not None and (latest.source_kind == "FILE" or latest.source_reference_id or latest.source_file_id):
            # A revision drawn from a document is used only while that document is still a current, case-bound upload.
            source = db.get(UploadedFile, latest.source_file_id) if latest.source_file_id else None
            if not (source is not None and source.case_id == file_record.case_id and source.is_associated
                    and source.withdrawn_at is None and source.superseded_by_file_id is None):
                warnings.append(f"REVIEWED_DEMOGRAPHICS_REVISION_{latest.revision}_NOT_USED: its source document was withdrawn, superseded, "
                                "deleted or unassociated")
                latest = None
        if latest is not None:
            used = False
            if sex is None and latest.sex in ("M", "F"):
                sex, used = latest.sex, True
            if age is None and latest.date_of_birth is not None:
                reference = (file_record.created_at or datetime.now(timezone.utc)).date()
                birth = latest.date_of_birth
                age = reference.year - birth.year - ((reference.month, reference.day) < (birth.month, birth.day))
                warnings.append("AGE_FROM_REVIEWED_DATE_OF_BIRTH_AT_THE_UPLOAD_DATE (the recording date is not known)")
                used = True
            if used:
                sources.append(f"REVIEWED_DEMOGRAPHICS_REVISION_{latest.revision}")
    if age is None or sex not in ("M", "F"):
        raise InferenceNotPermitted("DEMOGRAPHICS_REQUIRED: this fusion model takes the patient's age and sex with the ECG; declare both with "
                                    "the request or record reviewed demographics (sex and date of birth) for the case."
                                    + (f" {'; '.join(warnings)}." if warnings else ""))
    if not 0 <= float(age) <= 120:
        raise InferenceNotPermitted(f"DEMOGRAPHICS_OUT_OF_RANGE: age {age} years.")
    return {"vector": ecg_inference.demographic_vector(float(age), sex), "age_years": float(age), "sex": sex,
            "sources": sources, "warnings": warnings, "encoding": "app.services.ecg_inference.demographic_vector v1"}


def prepare_input(model: dict, file_record: UploadedFile, companion: Optional[UploadedFile], options: Optional[dict] = None,
                  db: Optional[Session] = None, declared_input_type: str = ""):
    """Read the upload and check its content against the model's input contract.

    Runs in the API before a job is queued (so refusals are typed) and again at execution.
    Returns the prepared ECG record (with demographics for a fusion model) or volume; images are prepared by run_model."""
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
            record = ecg_inference.check_record(record, contract)
            if model.get("demographic_inputs"):
                return FusedEcgInput(record, resolve_demographics(file_record, options, db))
            return record
        if kind == "volume_nifti":
            envelope = _input_envelope(model)
            reader = (volume_inference.read_itk_volume if _suffix(file_record.stored_filename) in volume_inference.ITK_SUFFIXES
                      else volume_inference.read_volume)
            with upload_store.materialize(Path(file_record.file_path)) as plain:
                return reader(plain, envelope)
        if kind == "echo_video":
            with upload_store.materialize(Path(file_record.file_path)) as plain:
                video = echo_inference.read_video(plain)
            echo_inference.check_video(video, model["artifact_bundle"].get("input_envelope") or {})
            return video
    except (ecg_inference.EcgInputError, volume_inference.VolumeInputError) as exc:
        raise InferenceNotPermitted(f"MODEL_INPUT_INCOMPATIBLE: {exc}") from exc
    except echo_inference.EchoInputError as exc:
        raise InferenceNotPermitted(str(exc)) from exc
    if kind == "image_2d":
        from app.services import job_queue

        # The image gates need OCR and the network. With inline execution the network runs in
        # this process anyway, so refusals come back before a job is queued; a worker runs them
        # at execution (execute_research_inference), keeping model memory out of the API.
        if job_queue.execution_mode() == "inline":
            with raster_input(model, file_record, declared_input_type, options) as (plain, _conversion):
                check_document_photograph(plain)
                check_distribution(model, plain)
        elif _suffix(file_record.stored_filename) == ".dcm":
            # The DICOM conversion needs no network: its refusals (modality tag, frame choice, codec) come back before queueing.
            with raster_input(model, file_record, declared_input_type, options):
                pass
    return None


CARDIAC_SERIES_INPUT = "MRI"


def prepare_series(model: dict, report: dict, declared_input_type: str, options: Optional[dict] = None):
    """An assembled DICOM series as input for a volumetric model: the same checks as a NIfTI frame, and for the
    cardiac model the short-axis plausibility checks and the requester's attestation of view and phase."""
    kind = model.get("inference_input", "image_2d")
    if kind != "volume_nifti" and kind not in SERIES_INPUTS:
        raise InferenceNotPermitted(f"{model['display_name']} does not take volumes; only volumetric and series models run on an assembled DICOM series.")
    if declared_input_type not in model.get("supported_modalities", []):
        supported = ", ".join(MODALITY_LABELS.get(m, m) for m in model.get("supported_modalities", []))
        raise InferenceNotPermitted(f"{model['display_name']} was trained only on: {supported}.")
    if report.get("status") != "ASSEMBLED":
        phases = f" ({report['cardiac_phases']} phases; trigger times {report.get('phase_trigger_times_ms')} ms)" if report.get("cardiac_phases") else ""
        raise InferenceNotPermitted(f"SERIES_NOT_ASSEMBLED: {', '.join(report.get('issues') or ['unknown'])}{phases}.")
    if kind == "head_ct_series":
        return prepare_head_ct_series(model, report)
    envelope = _input_envelope(model)
    try:
        if declared_input_type == CARDIAC_SERIES_INPUT:
            if not (options or {}).get("short_axis_attested"):
                raise InferenceNotPermitted("SHORT_AXIS_ATTESTATION_REQUIRED: confirm that the series is a short-axis cine stack at end-diastole "
                                            "or end-systole; DICOM tags cannot show the view or the phase.")
            volume_inference.short_axis_plausibility(report)
            if (envelope.get("axis_convention") or {}).get("rv_direction_deg") is None:
                raise InferenceNotPermitted("AXIS_CONVENTION_NOT_CALIBRATED: the development frames carry no patient orientation and no "
                                            "calibrated rule for choosing a scanner series' axis convention is recorded; scanner series are refused.")
        return volume_inference.from_series(report["volume"], report["spacing_mm"], envelope, np.asarray(report["affine_lps_mm"], dtype=float))
    except volume_inference.VolumeInputError as exc:
        raise InferenceNotPermitted(f"MODEL_INPUT_INCOMPATIBLE: {exc}") from exc


@dataclass
class HeadCtSeries:
    """An ordered head CT series in Hounsfield units (slices, rows, columns) for a neighbouring-slice model."""

    hounsfield: np.ndarray
    ordered_upload_ids: list[int]
    checks: dict


def prepare_head_ct_series(model: dict, report: dict) -> HeadCtSeries:
    """Geometry checks for an axial head CT series; pixels are checked slice by slice at execution."""
    issues = []
    tags = list(report.get("modality_tags") or [])
    if tags and tags != ["CT"]:
        issues.append(f"SERIES_MODALITY_NOT_CT ({', '.join(tags)})")
    normal = np.asarray(report["slice_normal_lps"], dtype=float)
    tilt = float(np.degrees(np.arccos(min(1.0, abs(float(normal[2])) / float(np.linalg.norm(normal))))))
    if tilt > HEAD_CT_MAX_TILT_DEG:
        issues.append(f"NOT_AN_AXIAL_STACK (slice normal {tilt:.0f} degrees from the head-foot axis; at most {HEAD_CT_MAX_TILT_DEG:.0f} for gantry tilt)")
    slices = int(report["shape_slices_rows_columns"][0])
    if slices < 3:
        issues.append(f"TOO_FEW_SLICES ({slices}; the model reads a slice with both neighbours)")
    if model.get("dicom_window") is None:
        issues.append("NO_DECLARED_DICOM_WINDOW")
    if issues:
        raise InferenceNotPermitted(f"MODEL_INPUT_INCOMPATIBLE: {'; '.join(issues)}.")
    hounsfield = np.asarray(report["volume"], dtype=np.float32)
    uploads = list(report.get("ordered_upload_ids") or [])
    # Training stacked neighbours in ascending patient z (ImagePositionPatient z); the series is ordered along its own
    # slice normal, which points down the body when the normal's z component is negative.
    descending = float(normal[2]) < 0
    if descending:
        hounsfield, uploads = hounsfield[::-1].copy(), uploads[::-1]
    return HeadCtSeries(hounsfield, uploads,
                        {"status": "PASSED", "gantry_tilt_deg": round(tilt, 1), "slices": slices, "modality_tags": tags,
                         "slice_order": "ascending patient z (head-foot axis), as the training neighbours" + (" (series order reversed)" if descending else ""),
                         "checks": f"CT modality, slice normal within {HEAD_CT_MAX_TILT_DEG:.0f} degrees of the head-foot axis, at least 3 slices."})


def series_slice_images(hounsfield: np.ndarray, window: dict) -> list[Image.Image]:
    """Every slice with its neighbours (below, slice, above) as one RGB image, each windowed as the training PNGs were."""
    centre, width = float(window["center"]), float(window["width"])
    scaled = dicom_raster.window_linear(hounsfield.astype(np.float64), centre, width, str(window.get("function") or "LINEAR_EXACT").upper())
    grey = (np.floor(scaled * 255.0) if window.get("rounding") == "floor" else np.round(scaled * 255.0)).clip(0, 255).astype(np.uint8)
    count = grey.shape[0]
    return [Image.fromarray(np.stack([grey[max(0, k - 1)], grey[k], grey[min(count - 1, k + 1)]], axis=-1), mode="RGB") for k in range(count)]


def run_head_ct_series(model: dict, prepared: HeadCtSeries) -> dict:
    """Per-slice haemorrhage labels for every slice of the series that passes the applicability reference."""
    reference = ood_reference(model)
    window = model["dicom_window"]
    slices = []
    with _inference_lock:
        network, payload, device = load_model(model)
        for index, image in enumerate(series_slice_images(prepared.hounsfield, window)):
            features = image_features(network, payload, device, image)
            try:
                value = _combined_score(reference, image_ood.stage_scores(reference, [stage[None] for stage in features])[0])
            except image_ood.OodReferenceError as exc:
                raise InferenceNotPermitted(f"{exc}: the applicability reference does not match this network's feature stages.") from exc
            entry = {"slice_index": index, "upload_id": prepared.ordered_upload_ids[index] if index < len(prepared.ordered_upload_ids) else None,
                     "applicability_score": round(value, 3)}
            if value > reference["threshold"]:
                entry["status"] = "REFUSED_OUT_OF_DISTRIBUTION"
            else:
                result = classify_multilabel(network, payload, device, image)
                entry.update(status="ANALYSED", labels=result["labels"], positive_labels=result["positive_labels"])
                precision = result["numeric_precision"]
            slices.append(entry)
    analysed = [item for item in slices if item["status"] == "ANALYSED"]
    refused = len(slices) - len(analysed)
    meta = reference["metadata"]
    if refused > HEAD_CT_MAX_REFUSED_SLICE_FRACTION * len(slices):
        raise InferenceNotPermitted(
            f"MODEL_INPUT_OUT_OF_DISTRIBUTION: {refused} of {len(slices)} slices are unlike the slices {model['display_name']} was trained on "
            f"(limit {reference['threshold']:.2f}, the {meta['calibration_quantile']:.3g} quantile of its validation slices). The series was "
            "windowed as the training images were; check that it is a non-contrast head CT in Hounsfield units. The model was not run.")
    any_label = model["supported_classes"][-1]
    scores = [(next(label["probability"] for label in item["labels"] if label["label"] == any_label), item["slice_index"], item) for item in analysed]
    top_probability, top_index, top = max(scores, key=lambda value: value[0])
    threshold = next(label["threshold"] for label in top["labels"] if label["label"] == any_label)
    complete = refused == 0
    return {"type": "series_slice_multilabel", "slices": slices, "slices_analysed": len(analysed), "slices_refused": refused,
            "series_level": {"label": any_label, "probability": top_probability, "threshold": threshold, "at_or_above_threshold": top_probability >= threshold,
                             "slice_index": top_index, "coverage": f"{len(analysed)} of {len(slices)} slices", "complete_coverage": complete,
                             "rule": ("highest probability among the analysed slices of this one series. The held-out evaluation took the highest "
                                      "over every slice of a study; " + ("every slice of this series was analysed." if complete else
                                      "here some slices were refused, so a haemorrhage on them cannot raise this value (partial aggregate)."))},
            "slices_with_positive_labels": [item["slice_index"] for item in analysed if item["positive_labels"]],
            "window": window, "context": model.get("context"), "numeric_precision": precision,
            "applicability": {"limit": round(reference["threshold"], 3), "score_version": meta["score_version"],
                              "calibration": f"{meta['calibration_quantile']:.3g} quantile of {meta['calibration_n']} validation slices",
                              "rule": f"slices above the limit are not analysed; more than {HEAD_CT_MAX_REFUSED_SLICE_FRACTION:.0%} refuses the series"},
            "probability_semantics": "Independent sigmoid outputs per slice; not calibrated clinical probabilities.",
            "coordinate_space": "slice index in ascending patient z; each slice names its upload"}


def run_cardiac_series(model: dict, prepared, report: dict) -> tuple[dict, dict]:
    """The cardiac segmenter on a scanner series whose axis convention relative to the development frames is unknown.

    The convention is chosen from the image content with the rule calibrated on the development frames
    (volume_inference.choose_convention), and the chosen result must put the right ventricle anterior-right of the left
    ventricle in the series' own patient coordinates. Either check failing refuses the series."""
    prior = _input_envelope(model)["axis_convention"]
    with _inference_lock:
        network, payload, device = load_model(model)
        try:
            affine = np.asarray(report["affine_lps_mm"], dtype=float)
            mask, convention = volume_inference.choose_convention(network, payload, device, prepared, prior, affine)
            convention["patient_space_check"] = volume_inference.right_ventricle_is_right_anterior(
                mask, affine, int(prior["rv_label"]), int(prior["lv_label"]))
        except volume_inference.VolumeInputError as exc:
            raise InferenceNotPermitted(f"MODEL_INPUT_INCOMPATIBLE: {exc}") from exc
        output = volume_inference.segmentation_output(mask, payload, prepared, volume_inference.held_out_agreement(_report(model)), device)
    convention["status"] = "PASSED"
    return output, convention


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
            fused = isinstance(prepared, FusedEcgInput)
            if fused != (payload.get("arch") == ecg_inference.FUSION_ARCH):
                raise InferenceNotPermitted("DEMOGRAPHIC_INPUT_CONTRACT_MISMATCH: the registry entry and the checkpoint disagree on age/sex inputs.")
            if fused:
                return ecg_inference.classify(network, payload, device, prepared.record, evaluated_precision(device), demographics=prepared.demographics)
            return ecg_inference.classify(network, payload, device, prepared, evaluated_precision(device))
        if payload["kind"] == "echo_ef_regressor":
            mean, std = echo_inference.statistics(payload)
            result = echo_inference.predict(network, prepared, mean, std, device)
            return {"type": "regression", "target": "left_ventricular_ejection_fraction", "unit": "%", **result,
                    "band": echo_inference.interpretation(result["ef_percent"]),
                    "numeric_precision": "float16 autocast on CUDA, as in the held-out evaluation" if device.type == "cuda" else
                                         "float32 on CPU; differs from the evaluated float16 CUDA configuration",
                    "estimate_semantics": "Mean of the clip estimates; a research regression output with the held-out error stated, not a measured EF."}
        mask, on_grid = volume_inference.to_series_grid(volume_inference.predict(network, payload, device, prepared), prepared)
        output = volume_inference.segmentation_output(mask, payload, on_grid, volume_inference.held_out_agreement(_report(model)), device)
        if prepared.reorientation is not None:
            output["series_reorientation"] = {key: prepared.reorientation[key] for key in ("from", "to")}
        return output


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
    page = ocr.ocr_image(open_raster(image_path)[0])
    return sum(1 for line in page.lines if _WORD_LIKE.search(line["text"]))


def check_document_photograph(image_path: Path) -> dict:
    """Content gate, independent of the user's declared modality: a photograph of a printed
    document is refused before any image model sees it."""
    from app.services.film_processing import assess_raster

    assessment = assess_raster(image_path)
    if assessment["inference_eligibility"] == "ABSTAIN_FILM_INPUT":
        raise InferenceNotPermitted(
            "MODEL_INPUT_PHOTOGRAPHED_FILM: suspected photographed CT film or montage. "
            "Native-image model inference abstained. Use linked film-panel previews and report evidence; "
            "no patient-space geometry or AI lesion mask is available. Source assessment requires review."
        )
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


def ood_reference(model: dict, feature_version: Optional[str] = None) -> dict:
    bundle = model["artifact_bundle"]
    path = bundle.get("ood_reference_path")
    try:
        if not path:
            raise image_ood.OodReferenceError("OOD_REFERENCE_MISSING")
        reference = image_ood.load_reference(_resolve_artifact_path(path), bundle.get("ood_reference_sha256"), bundle.get("checkpoint_sha256"))
        if reference["metadata"].get("feature_version") != (feature_version or FEATURE_VERSION):
            raise image_ood.OodReferenceError("OOD_REFERENCE_FEATURES_MISMATCH")
        return reference
    except image_ood.OodReferenceError as exc:
        raise InferenceNotPermitted(f"{exc}: the model's applicability reference is unavailable; upload inference is refused.") from exc


def check_distribution(model: dict, image_path: Path) -> dict:
    """Refuse an image whose features lie outside the model's training distribution, whatever
    modality the user declared (e.g. a phone photograph of an X-ray film sent to an endoscopy model)."""
    reference = ood_reference(model)
    image = open_raster(image_path)[0]
    quality = model.get("input_quality")
    if quality:
        if min(image.size) < quality["min_dimension"]:
            raise InferenceNotPermitted("IMAGE_QUALITY_INSUFFICIENT_DIMENSIONS: skin-lesion input is too small")
        intensity_std = float(np.asarray(image.convert("L").resize((128, 128)), dtype=float).std())
        if not np.isfinite(intensity_std) or intensity_std < quality["min_intensity_std"]:
            raise InferenceNotPermitted("IMAGE_QUALITY_INSUFFICIENT_CONTRAST: near-uniform skin-lesion input")
        if quality.get("min_chroma") is not None:
            pixels = np.asarray(image.convert("RGB").resize((128, 128)), dtype=np.float32)
            chroma = float((np.abs(pixels[..., 0] - pixels[..., 1]) + np.abs(pixels[..., 1] - pixels[..., 2])).mean() / 2)
            if chroma < quality["min_chroma"]:
                raise InferenceNotPermitted("IMAGE_QUALITY_ACHROMATIC_INPUT: this research model requires a colour clinical skin photograph")
    with _inference_lock:
        network, payload, device = load_model(model)
        features = image_features(network, payload, device, image)
        try:
            stages = image_ood.stage_scores(reference, [values[None] for values in features])[0]
        except image_ood.OodReferenceError as exc:
            raise InferenceNotPermitted(f"{exc}: the applicability reference does not match this network's feature stages.") from exc
        value = _combined_score(reference, stages)
        explanation = refusal_explanation(reference, stages, image, network, payload, device) if value > reference["threshold"] else ""
    meta = reference["metadata"]
    result = {"applicability_score": round(value, 3), "applicability_limit": round(reference["threshold"], 3),
              "score_version": meta["score_version"],
              "calibration": f"{meta['calibration_quantile']:.3g} quantile of {meta['calibration_n']} validation images",
              "status": "PASSED"}
    if value > reference["threshold"]:
        raise InferenceNotPermitted(
            f"MODEL_INPUT_OUT_OF_DISTRIBUTION: this image is unlike the images {model['display_name']} was trained on "
            f"(applicability score {value:,.2f}; limit {reference['threshold']:.2f}, the {meta['calibration_quantile']:.3g} quantile of its "
            f"validation images). {explanation}The model was not run. Check the modality and upload a native frame of the kind the model was trained on."
        )
    return result


def _combined_score(reference: dict, stages: np.ndarray) -> float:
    return float(stages.max() if reference.get("combine") == "max" else stages.mean())


# A pixel is coloured when its channels differ by more than this (8-bit levels); JPEG noise on greyscale stays below it.
COLOUR_LEVELS = 12


def refusal_explanation(reference: dict, stages: np.ndarray, image: Image.Image, network, payload: dict, device) -> str:
    """Where an out-of-distribution score comes from, in one or two sentences.

    Stage 0 holds the input's colour and intensity statistics; the other stages are the network's features.
    A colour image whose distance lies mostly in stage 0 is scored again as a greyscale copy, which tells
    "colour alone" apart from "the content differs too". The copy is never analysed by the model."""
    share = float(stages[0] / stages.sum()) if stages.sum() > 0 else 0.0
    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
    coloured = float(np.mean(rgb.max(axis=2) - rgb.min(axis=2) > COLOUR_LEVELS))
    if share > .5 and coloured > .01:
        grey = image.convert("L").convert("RGB")
        grey_stages = image_ood.stage_scores(reference, [values[None] for values in image_features(network, payload, device, grey)])[0]
        grey_value = _combined_score(reference, grey_stages)
        if grey_value <= reference["threshold"]:
            return (f"Colour accounts for the refusal: {coloured:.0%} of pixels are coloured, and a greyscale copy scores "
                    f"{grey_value:.2f}, within the limit (the copy was not analysed). ")
        return (f"Most of the score comes from colour ({coloured:.0%} of pixels are coloured), but a greyscale copy is also outside "
                f"the training images (score {grey_value:,.2f}): the content itself differs (for example photographed film: glare, "
                "grain, perspective, film borders or burnt-in marks). ")
    if share > .5:
        return "Most of the score comes from the image's overall intensity statistics (brightness and contrast). "
    return "The distance is spread across the network's feature stages: the image content differs from the training images. "


def check_echo_distribution(model: dict, video) -> dict:
    """Feature-space applicability of an echo video (centre clip): the image reference machinery on the video network's stages."""
    reference = ood_reference(model, echo_inference.FEATURE_VERSION)
    with _inference_lock:
        network, payload, device = load_model(model)
        mean, std = echo_inference.statistics(payload)
        features = echo_inference.clip_features(network, video, mean, std, device)
    try:
        stages = image_ood.stage_scores(reference, [values[None] for values in features])[0]
    except image_ood.OodReferenceError as exc:
        raise InferenceNotPermitted(f"{exc}: the applicability reference does not match this network's feature stages.") from exc
    value = _combined_score(reference, stages)
    meta = reference["metadata"]
    if value > reference["threshold"]:
        share = float(stages[0] / stages.sum()) if stages.sum() > 0 else 0.0
        where = ("Most of the distance is in the clip's intensity statistics." if share > .5 else
                 "The distance is spread across the network's feature stages: the video content differs from the development videos.")
        raise InferenceNotPermitted(
            f"MODEL_INPUT_OUT_OF_DISTRIBUTION: this video is unlike the EchoNet-Dynamic videos the model was trained on (applicability score "
            f"{value:,.2f}; limit {reference['threshold']:.2f}, the {meta['calibration_quantile']:.3g} quantile of its validation videos). {where} "
            "The model was not run.")
    return {"applicability_score": round(value, 3), "applicability_limit": round(reference["threshold"], 3), "score_version": meta["score_version"],
            "calibration": f"{meta['calibration_quantile']:.3g} quantile of {meta['calibration_n']} validation videos", "status": "PASSED"}


CONTENT_CHECKS = {
    "head_ct_series": ("Series geometry checked (CT, axial within the gantry-tilt limit, at least 3 slices); every slice windowed as the "
                       "training images were (the model's declared DICOM window), stacked with its neighbours and checked against the "
                       "model's feature-space applicability reference; only slices inside it are analysed."),
    "echo_video": ("Video decoded and checked against the development videos: EchoNet format (112 x 112 pixels), frame count, frame rate "
                   "range and coloured-pixel share; then the model's feature-space applicability reference on the centre clip."),
    "ecg_12lead": "Signal read exactly (WFDB checksums or CSV time column) and checked against the trained contract: sampling rate, duration, lead set, amplitude and flatline limits.",
    "volume_nifti": ("Header and voxels checked against the recorded development envelope: channel count, voxel spacing and matrix, and for "
                     "skull-stripped brain models the share of non-zero voxels; cardiac frames also need square pixels and the slice axis last."),
}
MAPPING_STATUS = {"image_2d": "NOT_MAPPABLE: RESEARCH_MODEL_OUTPUT_2D_SOURCE_COORDINATES",
                  "head_ct_series": "NOT_MAPPABLE: RESEARCH_MODEL_OUTPUT_PER_SLICE_OF_A_SERIES",
                  "ecg_12lead": "NOT_MAPPABLE: RESEARCH_MODEL_OUTPUT_WHOLE_RECORDING",
                  "volume_nifti": "NOT_MAPPABLE: RESEARCH_MODEL_OUTPUT_NATIVE_VOXEL_GRID",
                  "echo_video": "NOT_MAPPABLE: RESEARCH_MODEL_OUTPUT_WHOLE_VIDEO"}


def execute_research_inference(db: Session, file_record: UploadedFile, model_id: str, declared_input_type: str,
                               actor: Optional[User], options: Optional[dict] = None, series: Optional[dict] = None) -> InferenceRun:
    """Run a research model on one upload, or (``series``: the assembled report and its ordered
    upload records) on a multi-file DICOM series, and record the output pending review."""
    with ExitStack() as stack:
        return _execute_research_inference(db, file_record, model_id, declared_input_type, actor, options, series, stack)


def _execute_research_inference(db: Session, file_record: UploadedFile, model_id: str, declared_input_type: str,
                                actor: Optional[User], options: Optional[dict], series: Optional[dict], stack: ExitStack) -> InferenceRun:
    model = get_model(model_id)
    bundle = model["artifact_bundle"]
    kind = model.get("inference_input", "image_2d")
    prepared = None
    companion = None
    series_provenance = None
    raster: Optional[Path] = None
    dicom_conversion: Optional[dict] = None
    # Series outputs whose checks need the network (convention choice, per-slice applicability) are computed before the run is recorded.
    precomputed_output: Optional[dict] = None
    if series is not None:
        prepared = prepare_series(model, series["report"], declared_input_type, options)
        report = series["report"]
        series_provenance = {
            "series_reference": report["series_reference"], "ordered_upload_ids": report["ordered_upload_ids"],
            "file_sha256": [record.file_hash for record in series["records"]], "shape_slices_rows_columns": report["shape_slices_rows_columns"],
            "spacing_mm": report["spacing_mm"], "assembly_warnings": report["warnings"], "input_warnings": getattr(prepared, "warnings", []),
            **({"cardiac_phase": report["phase"], "phase_trigger_times_ms": report["phase_trigger_times_ms"]} if "phase" in report else {}),
        }
        content_check = {"status": "PASSED", "checks": CONTENT_CHECKS[kind], "dicom_series": series_provenance}
        if kind == "head_ct_series":
            content_check["series_geometry"] = prepared.checks
            precomputed_output = run_head_ct_series(model, prepared)
            content_check["distribution"] = {"status": "PASSED", **precomputed_output["applicability"],
                                             "slices_refused": precomputed_output["slices_refused"]}
        elif declared_input_type == CARDIAC_SERIES_INPUT:
            content_check["short_axis_plausibility"] = volume_inference.short_axis_plausibility(report)
            content_check["short_axis_attested_by_requester"] = True
            precomputed_output, content_check["axis_convention"] = run_cardiac_series(model, prepared, report)
    elif kind == "image_2d":
        check_input(model, file_record, declared_input_type, options, db)
        # One raster (a DICOM frame converted once) for both gates and the model, removed when the run is recorded.
        raster, dicom_conversion = stack.enter_context(raster_input(model, file_record, declared_input_type, options))
        content_check = check_document_photograph(raster)
        content_check["distribution"] = check_distribution(model, raster)
        if dicom_conversion is not None:
            content_check["dicom_frame"] = dicom_conversion
    else:
        companion = check_input(model, file_record, declared_input_type, options, db)
        prepared = prepare_input(model, file_record, companion, options, db)
        content_check = {"status": "PASSED", "checks": CONTENT_CHECKS[kind]}
        if kind == "echo_video":
            content_check["video"] = echo_inference.check_video(prepared, bundle.get("input_envelope") or {})
            content_check["distribution"] = check_echo_distribution(model, prepared)
    started_at = datetime.now(timezone.utc)
    start = time.perf_counter()
    try:
        if precomputed_output is not None:
            output = precomputed_output  # computed with the series checks above
        elif prepared is None:
            output = run_model(model, raster, options) if model.get("requires_clinical_features") else run_model(model, raster)
            if dicom_conversion is not None:
                output["dicom_frame"] = dicom_conversion
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
    applicability = ("Input type declared by the requesting user; the image passed the printed-document check and the model's "
                     "feature-space applicability reference (input_content_check.distribution).")
    if dicom_conversion is not None:
        window = dicom_conversion.get("window") or {}
        applicability += (f" DICOM frame {dicom_conversion['frame_index']} converted to 8 bits ({window.get('source', 'colour, unchanged')}); "
                          "the converted frame, not the stored values, passed those checks (input_content_check.dicom_frame).")
    if kind in ("echo_video", "head_ct_series"):
        applicability = f"Input type declared by the requesting user. {CONTENT_CHECKS[kind]} (input_content_check.distribution)."
    elif kind != "image_2d":
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
            **({"dicom_series": series_provenance} if series_provenance is not None else {}),
        },
    )
    db.add(finding)
    db.commit()
    log_audit_event(db=db, action="RESEARCH_INFERENCE_COMPLETED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor,
                    details={"case_id": file_record.case_id, "file_id": file_record.id, "finding_id": finding.id, "model_id": model_id,
                             "declared_input_type": declared_input_type, "exec_time_ms": exec_ms})
    db.refresh(run)
    return run
