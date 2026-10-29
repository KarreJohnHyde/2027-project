"""Research chest-radiograph analysis with TorchXRayVision's pretrained models.

Third-party models, neither trained nor evaluated by MedTwin (registry status READY_UNVALIDATED,
output status RESEARCH_ONLY_THIRD_PARTY_PRETRAINED_NOT_EVALUATED_LOCALLY):

- classifier: DenseNet-121 "densenet121-res224-all" (Cohen et al., MIDL 2022), trained on public
  chest X-ray collections (NIH ChestX-ray14, PadChest, CheXpert, MIMIC-CXR, Google, OpenI,
  RSNA/Kaggle); 18 findings, each output scaled by the publisher so 0.5 is its operating point;
- anatomy: the ChestX-Det PSPNet segmenting 14 structures (lungs, heart, diaphragm, spine...);
- input similarity: a ResNet-101 autoencoder trained on chest radiographs, whose reconstruction
  error is reported (no reference distribution is registered to turn it into pass/fail).

The input must contain recognisable frontal chest anatomy: both lungs found, each on its own side
of the image; otherwise nothing is scored. Grad-CAM attention for the top findings is summarised
by lung zone (each lung's height in thirds): where a score depends on, not a lesion outline. The
report comparison lines each label up with what the case's reports state about it. Weights are
never downloaded while serving (scripts/fetch_cxr_weights.py fetches them once).
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.models.entities import (
    ClinicalReportStatement,
    EvidenceStatus,
    Finding,
    InferenceRun,
    ModalityType,
    RepresentationLevel,
    UploadedFile,
    User,
)
from app.services import upload_store
from app.services.audit_service import log_audit_event

MODEL_ID = "cxr_torchxrayvision_densenet121"
DISPLAY_NAME = "Chest radiograph findings, 18 labels (TorchXRayVision DenseNet-121, third-party)"
OUTPUT_STATUS = "RESEARCH_ONLY_THIRD_PARTY_PRETRAINED_NOT_EVALUATED_LOCALLY"
WEIGHTS_DIR = PROJECT_ROOT / "artifacts" / "third_party" / "torchxrayvision"
WEIGHT_FILES = {
    "classifier": "nih-pc-chex-mimic_ch-google-openi-kaggle-densenet121-d121-tw-lr001-rot45-tr15-sc15-seed0-best.pt",
    "anatomy": "pspnet_chestxray_best_model_4.pth",
    "autoencoder": "nihpcrsnamimic_ch-resnet101-2-ae-test2-elastic-e250.pt",
}
# SHA-256 of the files fetched from the publisher's release (github.com/mlmed/torchxrayvision, tag v1).
WEIGHT_SHA256 = {
    "classifier": "56524913dd16a906422e8d8b66a7a5c46be1d82eb7ac012d8103776f1aa68899",
    "anatomy": "019b167eac6b729fc1bb92bbbc185fc1730aaa65819f4e3fe718186cadc044fc",
    "autoencoder": "877ded430383a2bbce756737b316d76de42defed3079eebf2cce305f7be34df9",
}
PUBLISHER = {
    "library": "TorchXRayVision 1.5.7 (Apache-2.0)",
    "citation": "Cohen JP, Viviano JD, Bertin P, et al. TorchXRayVision: A library of chest X-ray datasets and models. MIDL 2022.",
    "training_data": "NIH ChestX-ray14, PadChest, CheXpert, MIMIC-CXR, Google, OpenI, RSNA/Kaggle (publisher's training; their terms apply)",
    "anatomy_model": "PSPNet trained on ChestX-Det (Lian et al., IEEE TMI 2021)",
    "local_evaluation": "None: MedTwin has no labelled chest radiographs to evaluate these models on.",
}
PREPROCESSING_VERSION = "torchxrayvision-1.5.7: grey levels to [-1024, 1024], centre square crop, 224 px classifier / 512 px anatomy"
# Each output is scaled so 0.5 is the publisher's operating point for that finding.
OPERATING_POINT = 0.5
# Display rule (not validated): a score within this distance of the operating point is weak.
WEAK_MARGIN = 0.1
# A lung must cover at least this share of the 512-pixel analysis frame to count as found.
MIN_LUNG_FRACTION = 0.03
ATTENTION_FINDINGS = 3
ATTENTION_GRID = 28
ZONES = ("upper", "middle", "lower")
# Report entities (app.services.terminology names) that state each label, and the organ system
# the statement must be about: "lesion" in a thyroid lobe is not a lung lesion.
LUNGS = ("lungs",)
REPORT_ENTITIES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "Fibrosis": (("pulmonary fibrosis", "fibrosis", "honeycombing", "interstitial lung disease"), LUNGS),
    "Effusion": (("pleural effusion",), LUNGS),
    "Consolidation": (("consolidation",), LUNGS),
    "Pneumothorax": (("pneumothorax",), LUNGS),
    "Emphysema": (("emphysema",), LUNGS),
    "Nodule": (("nodule", "pulmonary nodule"), LUNGS),
    "Mass": (("mass",), LUNGS),
    "Lung Lesion": (("lesion",), LUNGS),
    "Lung Opacity": (("opacity", "interstitial opacity", "ground-glass opacity"), LUNGS),
    "Infiltration": (("infiltrate", "interstitial opacity"), LUNGS),
    "Atelectasis": (("atelectasis",), LUNGS),
    "Edema": (("pulmonary edema", "edema"), LUNGS),
    "Pneumonia": (("pneumonia",), LUNGS),
    "Pleural_Thickening": (("pleural thickening",), LUNGS),
    "Cardiomegaly": (("cardiomegaly",), ("heart",)),
    "Enlarged Cardiomediastinum": (("cardiomegaly", "mediastinal widening"), ("heart", "lungs")),
    # The publisher's fracture label covers ribs and clavicles on a frontal film, not a vertebral deformity.
    "Fracture": (("fracture", "rib fracture"), ("skeletal",)),
    "Hernia": (("hiatal hernia", "hiatus hernia"), ("intestines", "lungs")),
}
# "To rule out" and other hypothetical statements state no finding.
STATED_CERTAINTIES = ("CERTAIN", "UNCERTAIN")

_lock = threading.Lock()


class CxrUnavailable(Exception):
    """The library or a weight file is missing."""


class CxrNotApplicable(Exception):
    """The image does not show recognisable frontal chest anatomy."""


def availability() -> dict[str, Any]:
    try:
        import torchxrayvision  # noqa: F401
    except ImportError:
        return {"available": False, "status": "DEPENDENCY_MISSING", "reason": "torchxrayvision is not installed."}
    missing = [name for name in WEIGHT_FILES.values() if not (WEIGHTS_DIR / name).is_file()]
    if missing:
        return {"available": False, "status": "WEIGHTS_MISSING", "reason": "Run scripts/fetch_cxr_weights.py to fetch the publisher's weights.", "missing": missing}
    return {"available": True, "status": "READY_UNVALIDATED"}


def model_card() -> dict[str, Any]:
    return {"model_id": MODEL_ID, "display_name": DISPLAY_NAME, "output_status": OUTPUT_STATUS, "publisher": PUBLISHER,
            "operating_point": OPERATING_POINT, "weak_margin": WEAK_MARGIN, "weights_sha256": WEIGHT_SHA256, **availability()}


@lru_cache(maxsize=1)
def _models():
    import torch
    import torchxrayvision as xrv

    state = availability()
    if not state["available"]:
        raise CxrUnavailable(state["reason"])
    for role, name in WEIGHT_FILES.items():
        digest = hashlib.sha256((WEIGHTS_DIR / name).read_bytes()).hexdigest()
        if digest != WEIGHT_SHA256[role]:
            raise CxrUnavailable(f"The {role} weights do not match their recorded SHA-256.")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    cache = str(WEIGHTS_DIR)
    classifier = xrv.models.DenseNet(weights="densenet121-res224-all", cache_dir=cache).eval().to(device)
    anatomy = xrv.baseline_models.chestx_det.PSPNet(cache_dir=cache).eval().to(device)
    autoencoder = xrv.autoencoders.ResNetAE(weights="101-elastic", cache_dir=cache).eval().to(device)
    return classifier, anatomy, autoencoder, device


def _square(gray: np.ndarray) -> tuple[int, int, int]:
    """The centre square the library's crop keeps: (left, top, side) in source pixels."""
    height, width = gray.shape
    side = min(height, width)
    return (width - side) // 2, (height - side) // 2, side


def _contours(mask: np.ndarray, square: tuple[int, int, int], frame: int) -> list[list[list[float]]]:
    from skimage import measure

    left, top, side = square
    scale = side / frame
    result = []
    for contour in measure.find_contours(mask.astype(float), 0.5):
        if len(contour) < 20:
            continue
        step = max(1, len(contour) // 160)
        result.append([[round(left + x * scale, 1), round(top + y * scale, 1)] for y, x in contour[::step]])
    return result


def _zone_masks(lung: np.ndarray) -> dict[str, np.ndarray]:
    rows = np.where(lung.any(axis=1))[0]
    if rows.size == 0:
        return {}
    bounds = np.linspace(rows.min(), rows.max() + 1, len(ZONES) + 1)
    zones = {}
    for name, low, high in zip(ZONES, bounds[:-1], bounds[1:]):
        band = np.zeros_like(lung)
        band[int(low):int(high)] = True
        zones[name] = lung & band
    return zones


def analyse(image: Image.Image, statements: list[ClinicalReportStatement]) -> dict[str, Any]:
    """Scores, attention by lung zone, anatomy outlines, input checks and the report comparison."""
    import torch
    import torch.nn.functional as functional
    import torchvision
    import torchxrayvision as xrv

    classifier, anatomy, autoencoder, device = _models()
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    normalised = xrv.datasets.normalize(gray, 255)[None, ...]
    square = _square(gray)
    crop = xrv.datasets.XRayCenterCrop()
    small = torchvision.transforms.Compose([crop, xrv.datasets.XRayResizer(224)])(normalised)
    large = torchvision.transforms.Compose([crop, xrv.datasets.XRayResizer(512)])(normalised)

    with _lock:
        with torch.no_grad():
            masks = (torch.sigmoid(anatomy(torch.from_numpy(large)[None].to(device)))[0] > 0.5).cpu().numpy()
            x = torch.from_numpy(small)[None].to(device)
            reconstruction_error = float((autoencoder.decode(autoencoder.encode(x)) - x).abs().mean() / 1024)
        structures = {name: masks[index] for index, name in enumerate(anatomy.targets)}
        right, left = structures["Right Lung"], structures["Left Lung"]
        right_fraction, left_fraction = float(right.mean()), float(left.mean())
        found = right_fraction >= MIN_LUNG_FRACTION and left_fraction >= MIN_LUNG_FRACTION
        # Patient's right lung on the image's left in a frontal (PA or AP) radiograph.
        sides = found and np.where(right)[1].mean() < np.where(left)[1].mean()
        checks = {
            "status": "APPLICABLE" if found and sides else "NOT_APPLICABLE",
            "right_lung_fraction": round(right_fraction, 4), "left_lung_fraction": round(left_fraction, 4),
            "heart_fraction": round(float(structures["Heart"].mean()), 4),
            "lungs_on_expected_sides": bool(sides),
            "autoencoder_reconstruction_error": round(reconstruction_error, 4),
            "autoencoder_note": "Mean absolute reconstruction error (fraction of the input range) of an autoencoder trained on chest radiographs; "
                                "no reference distribution is registered, so it is reported, not used as a gate.",
            "rule": f"Both lungs must each cover at least {MIN_LUNG_FRACTION:.0%} of the analysis frame, the right lung on the image's left.",
        }
        if checks["status"] != "APPLICABLE":
            raise CxrNotApplicable("No frontal chest anatomy was recognised (both lungs, each on its own side); nothing was scored. "
                                   f"Right lung {right_fraction:.1%}, left lung {left_fraction:.1%} of the frame.")

        features: dict[str, torch.Tensor] = {}
        handle = classifier.features.register_forward_hook(lambda _module, _inputs, output: features.update(value=output))
        try:
            x = torch.from_numpy(small)[None].to(device).requires_grad_(False)
            outputs = classifier(x)[0]
            scores = {name: float(value) for name, value in zip(classifier.pathologies, outputs.detach().cpu().numpy()) if name}
            ranked = sorted(scores, key=lambda name: -scores[name])
            lungs = right | left
            zone_masks = {f"right_{zone}": mask for zone, mask in _zone_masks(right).items()}
            zone_masks |= {f"left_{zone}": mask for zone, mask in _zone_masks(left).items()}
            attention = []
            for name in ranked[:ATTENTION_FINDINGS]:
                activation = features["value"]
                gradient = torch.autograd.grad(outputs[classifier.pathologies.index(name)], activation, retain_graph=True)[0]
                cam = torch.relu((gradient.mean(dim=(2, 3), keepdim=True) * activation).sum(dim=1, keepdim=True))
                full = functional.interpolate(cam, size=(512, 512), mode="bilinear", align_corners=False)[0, 0].detach().cpu().numpy()
                total = float(full.sum()) or 1.0
                shares = {zone: round(float(full[mask].sum()) / total, 3) for zone, mask in zone_masks.items()}
                grid = functional.interpolate(cam, size=(ATTENTION_GRID, ATTENTION_GRID), mode="bilinear", align_corners=False)[0, 0].detach().cpu().numpy()
                peak = float(grid.max()) or 1.0
                attention.append({
                    "finding": name, "zones": shares, "outside_lungs": round(1.0 - float(full[lungs].sum()) / total, 3),
                    "top_zone": max(shares, key=shares.get) if shares else None,
                    "grid": [[round(float(value) / peak, 2) for value in row] for row in grid],
                })
        finally:
            handle.remove()

    findings = [{"finding": name, "score": round(scores[name], 3), "above_operating_point": scores[name] > OPERATING_POINT,
                 "weak": abs(scores[name] - OPERATING_POINT) < WEAK_MARGIN} for name in ranked]
    return {
        "type": "chest_radiograph_findings",
        "coordinate_space": "SOURCE_IMAGE_PIXELS",
        "image_size": [int(gray.shape[1]), int(gray.shape[0])],
        "analysis_square": list(square),
        "operating_point": OPERATING_POINT, "weak_margin": WEAK_MARGIN,
        "findings": findings,
        "attention": attention,
        "anatomy": [{"name": name, "fraction": round(float(mask.mean()), 4), "contours": _contours(mask, square, 512)}
                    for name, mask in structures.items() if name in ("Right Lung", "Left Lung", "Heart", "Facies Diaphragmatica") and mask.any()],
        "input_checks": checks,
        "report_comparison": report_comparison(findings, statements),
        "summary": summarise(findings),
    }


def summarise(findings: list[dict[str, Any]]) -> str:
    strong = [item for item in findings if item["above_operating_point"] and not item["weak"]]
    if strong:
        return "Above the operating point: " + ", ".join(f"{item['finding']} {item['score']:.2f}" for item in strong[:4])
    top = max(findings, key=lambda item: item["score"])
    return (f"No finding clearly above its operating point; highest {top['finding']} {top['score']:.2f} "
            f"(weak band {OPERATING_POINT - WEAK_MARGIN:.2f}-{OPERATING_POINT + WEAK_MARGIN:.2f})")


def report_comparison(findings: list[dict[str, Any]], statements: list[ClinicalReportStatement]) -> list[dict[str, Any]]:
    """What the case's reports state about each label, beside the model's score. Agreement is not
    proof of correctness, and a report covers what its examination covered (a CT is not a radiograph)."""
    rows = []
    for item in findings:
        terms, systems = REPORT_ENTITIES.get(item["finding"], ((), ()))
        stated = [statement for statement in statements
                  if statement.experiencer == "PATIENT" and statement.entity.lower() in terms
                  and statement.anatomy_system in systems and statement.certainty in STATED_CERTAINTIES]
        if not stated:
            continue
        affirmed = [statement for statement in stated if statement.negation == "AFFIRMED"]
        reported = "AFFIRMED" if affirmed else "NEGATED"
        if item["weak"]:
            status = "MODEL_INDETERMINATE"
        elif item["above_operating_point"] == (reported == "AFFIRMED"):
            status = "AGREES"
        else:
            status = "DIFFERS"
        example = (affirmed or stated)[0]
        rows.append({"finding": item["finding"], "score": item["score"], "report_status": reported, "status": status,
                     "report_entities": sorted({statement.entity for statement in stated}),
                     "report_quote": example.source_span[:200], "report_statement_ids": [statement.id for statement in stated]})
    return rows


def execute(db: Session, file_record: UploadedFile, actor: Optional[User], content_check: Optional[dict] = None) -> InferenceRun:
    """Run on one image upload and record the output as a finding pending human review."""
    statements = db.query(ClinicalReportStatement).filter(ClinicalReportStatement.case_id == file_record.case_id).all()
    started_at = datetime.now(timezone.utc)
    start = time.perf_counter()
    with upload_store.materialize(Path(file_record.file_path)) as plain:
        with Image.open(plain) as image:
            output = analyse(image, statements)
    output["input_checks"]["printed_document"] = content_check
    exec_ms = round((time.perf_counter() - start) * 1000, 2)
    run = InferenceRun(case_id=file_record.case_id, file_id=file_record.id, modality=file_record.modality, model_name=MODEL_ID,
                       model_version=WEIGHT_SHA256["classifier"][:16], preprocessing_version=PREPROCESSING_VERSION,
                       status=EvidenceStatus.COMPLETED, execution_time_ms=exec_ms, started_at=started_at, completed_at=datetime.now(timezone.utc))
    db.add(run)
    db.flush()
    finding = Finding(
        inference_run_id=run.id, case_id=file_record.case_id, modality=ModalityType.IMAGE,
        category="Research model output (chest radiograph findings, third-party)", label=output["summary"][:255],
        raw_confidence=None, calibration_status="PUBLISHER_OPERATING_POINT_SCALING_NOT_CALIBRATED_LOCALLY",
        representation_level=RepresentationLevel.L1_GENERIC, anatomical_region=None,
        mapping_status="L1_GENERIC: attention summarised by lung zone on the source image; not registered to 3D anatomy.",
        review_status=EvidenceStatus.PENDING_HUMAN_REVIEW, is_demo=False,
        evidence_provenance={
            "source": "MODEL_INFERENCE", "output_status": OUTPUT_STATUS, "model_id": MODEL_ID, "model_display_name": DISPLAY_NAME,
            "model_status": "READY_UNVALIDATED", "checkpoint_sha256": WEIGHT_SHA256["classifier"], "weights_sha256": WEIGHT_SHA256,
            "publisher": PUBLISHER, "held_out_evaluation": None, "declared_input_type": "CHEST_RADIOGRAPH",
            "applicability": "Declared a frontal chest radiograph by the requesting user; both lungs were found on their expected sides "
                             "(input_checks). A photograph of a printed film is outside the publisher's digital-radiograph training data.",
            "anatomy_system_of_model": "lungs", "source_file_sha256": file_record.file_hash, "output": output,
        },
    )
    db.add(finding)
    db.commit()
    log_audit_event(db=db, action="RESEARCH_INFERENCE_COMPLETED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor,
                    details={"case_id": file_record.case_id, "file_id": file_record.id, "finding_id": finding.id, "model_id": MODEL_ID,
                             "declared_input_type": "CHEST_RADIOGRAPH", "exec_time_ms": exec_ms})
    db.refresh(run)
    return run
