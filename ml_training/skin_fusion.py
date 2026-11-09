"""Patient-separated PAD-UFES-20 image and image/tabular research baselines.

Frozen ImageNet ResNet18 features + train-only standardized linear heads. Select
regularization and fit temperature on validation only; freeze before test. No
patient identifier, biopsy indicator or diagnosis is an input feature.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from torch import nn
from torchvision import models

from ml_training.common import ROOT, bootstrap_ci, register_model, relative, set_seed, sha256_file
from ml_training.classify import balanced_accuracy, expected_calibration_error, fit_temperature, macro_f1, softmax, transforms_for

sys.path.insert(0, str(ROOT / "backend"))
from app.services import skin_metadata

SOURCE = ROOT / "_derived/datasets/multimodal/pad-ufes-20/samples.jsonl"
OUT = ROOT / "_derived/datasets/pad-clinical-image"
CACHE = ROOT / "artifacts/research_skin"
CLASS_NAMES = {"ACK": "actinic_keratosis", "BCC": "basal_cell_carcinoma", "MEL": "melanoma",
               "NEV": "nevus", "SCC": "squamous_cell_carcinoma", "SEK": "seborrheic_keratosis"}
PREPROCESSING = "rgb-resize114-centercrop-imagenetnorm-v1"
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def load_rows():
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 2298 or any(row["label"] not in CLASS_NAMES for row in rows):
        raise ValueError("Unexpected PAD cohort or labels")
    for key in ("patient_id", "image_sha256"):
        assignments = {}
        for row in rows:
            assignments.setdefault(row[key], set()).add(row["split"])
        if any(len(splits) != 1 for splits in assignments.values()):
            raise ValueError(f"Cross-split leakage in {key}")
    return rows


def extract_features(rows, encoder, device, transform, cache_key):
    path = CACHE / "features.npz"
    if path.exists():
        with np.load(path, allow_pickle=False) as stored:
            if str(stored["cache_key"]) == cache_key:
                values = stored["features"]
                if values.shape == (len(rows), 512) and np.isfinite(values).all():
                    return values
    output = []
    for start in range(0, len(rows), 32):
        images = []
        for row in rows[start:start + 32]:
            source = Path(row["image_path"])
            if sha256_file(source) != row["image_sha256"]:
                raise ValueError("Source image no longer matches prepared manifest")
            with Image.open(source) as image:
                images.append(transform(image.convert("RGB")))
        with torch.inference_mode(), torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
            features = encoder(torch.stack(images).to(device)).float().cpu().numpy()
        output.append(features)
        if start % 320 == 0:
            print(f"Frozen image features {min(start + 32, len(rows))}/{len(rows)}", flush=True)
    values = np.concatenate(output)
    if values.shape != (len(rows), 512) or not np.isfinite(values).all():
        raise ValueError("Invalid image feature matrix")
    np.savez_compressed(path, features=values, cache_key=np.array(cache_key))
    return values


def fit_head(matrix, labels, split):
    train, val = split["train"], split["val"]
    scaler = StandardScaler().fit(matrix[train])
    scaled = scaler.transform(matrix)
    candidates = []
    for regularization in (0.01, 0.1, 1.0):
        model = LogisticRegression(C=regularization, class_weight="balanced", max_iter=2000, random_state=20261109)
        model.fit(scaled[train], labels[train])
        score = macro_f1(labels[val], model.predict(scaled[val]), len(model.classes_))
        candidates.append((score, regularization, model))
    score, regularization, model = max(candidates, key=lambda candidate: candidate[0])
    # Absorb train-only standardization into the linear head; no pickle required.
    weights = model.coef_ / scaler.scale_[None]
    bias = model.intercept_ - weights @ scaler.mean_
    logits = matrix @ weights.T + bias
    temperature = fit_temperature(logits[val].astype(np.float32), labels[val])
    return weights.astype(np.float32), bias.astype(np.float32), float(temperature), {
        "criterion": "validation macro F1", "C": regularization, "val_macro_f1": score,
        "candidates": [{"C": c, "val_macro_f1": f1} for f1, c, _ in candidates],
        "standardization_fitted_on": "train", "class_weight": "balanced from training labels only"}


def main():
    set_seed(20261109)
    torch.set_num_threads(4)
    started = time.perf_counter()
    CACHE.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    version = sha256_file(SOURCE)
    classes = sorted(CLASS_NAMES.values())
    labels = np.array([classes.index(CLASS_NAMES[row["label"]]) for row in rows], dtype=np.int64)
    split = {name: np.array([index for index, row in enumerate(rows) if row["split"] == name]) for name in ("train", "val", "test")}
    with (OUT / "samples.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["entry", "path", "label", "group_id", "split"])
        writer.writeheader()
        writer.writerows({"entry": Path(row["image_path"]).name, "path": row["image_path"], "label": CLASS_NAMES[row["label"]],
                          "group_id": row["patient_id"], "split": row["split"]} for row in rows)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    encoder = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    encoder.fc = nn.Identity()
    encoder.eval().to(device)
    encoder_file = CACHE / "frozen_encoder.pt"
    if not encoder_file.exists():
        torch.save({name: value.cpu() for name, value in encoder.state_dict().items()}, encoder_file)
    _, transform = transforms_for(224)
    features = extract_features(rows, encoder, device, transform, version + ":" + sha256_file(encoder_file) + ":" + PREPROCESSING)
    schema = skin_metadata.fit_encoder([rows[index]["features"] for index in split["train"]])
    metadata = np.stack([skin_metadata.encode({field: row["features"].get(field) for field in skin_metadata.FIELDS}, schema) for row in rows])
    groups = np.array([row["patient_id"] for row in rows])
    common_limitations = ["Internal patient-separated holdout from PAD-UFES-20, not independent external or clinical validation.",
                          "Six clinical skin-lesion categories; not all skin diseases, dermoscopy, histopathology or whole-slide interpretation.",
                          "Training source has variable diagnostic confirmation; a predicted class is not a confirmed diagnosis.",
                          "Only five melanoma images are present in the frozen test split; rare-class estimates are unstable.",
                          "Frozen ImageNet ResNet18 features; regularization and temperature selected on validation only.",
                          "Source age/gender/region can encode cohort bias; no clinical fairness or safety claim.",
                          "Research-only; no treatment, exclusion of malignancy or clinical activation."]
    summaries = {}
    for arm in ("image_only", "image_tabular"):
        model_id = "skin_padufes_image_classifier" if arm == "image_only" else "skin_padufes_image_tabular_classifier"
        matrix = features if arm == "image_only" else np.concatenate([features, metadata], axis=1)
        weights, bias, temperature, selection = fit_head(matrix, labels, split)
        indices = split["test"]
        logits = matrix[indices] @ weights.T + bias
        probabilities = softmax(logits, temperature)
        truth, prediction = labels[indices], probabilities.argmax(axis=1)
        metrics = {"accuracy": float(np.mean(prediction == truth)), "macro_f1": macro_f1(truth, prediction, len(classes)),
                   "balanced_accuracy": balanced_accuracy(truth, prediction, len(classes)),
                   "ece_temperature_scaled": expected_calibration_error(probabilities, truth),
                   "ece_uncalibrated": expected_calibration_error(softmax(logits), truth)}
        interval = bootstrap_ci(lambda ix: macro_f1(truth[ix], prediction[ix], len(classes)), len(indices), groups[indices], rounds=300, unit="patient")
        run = ROOT / "artifacts/training" / f"{model_id}-20261109"
        run.mkdir(parents=True, exist_ok=True)
        state = {name: value.detach().cpu() for name, value in encoder.state_dict().items()}
        state.update({"fc.weight": torch.from_numpy(weights[:, :512].copy()), "fc.bias": torch.from_numpy(bias.copy())})
        payload = {"kind": "image_classifier", "arch": "resnet18", "state_dict": state, "image_size": 224,
                   "classes": classes, "normalization": {"mean": MEAN, "std": STD}, "temperature": temperature,
                   "dataset_version": version, "arm": arm, "frozen_linear_head": True}
        if arm == "image_tabular":
            payload.update(clinical_metadata_encoder=schema, clinical_metadata_weights=torch.from_numpy(weights[:, 512:].copy()))
        checkpoint = run / "model.pt"
        torch.save(payload, checkpoint)
        predictions_path = run / "test_predictions.csv"
        with predictions_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["entry", "group_id", "y_true", "y_pred"] + [f"p_{name}" for name in classes])
            for index, actual, guessed, probability in zip(indices, truth, prediction, probabilities):
                writer.writerow([Path(rows[index]["image_path"]).name, rows[index]["patient_id"], classes[actual], classes[guessed], *probability.tolist()])
        report_path = ROOT / "docs/validation/models" / f"{model_id}.json"
        report = {"model_id": model_id, "dataset": "PAD-UFES-20", "dataset_version": version, "arm": arm,
                  "test_n": len(indices), "test_patients": len(set(groups[indices])), "classes": classes,
                  "split_counts": {name: len(value) for name, value in split.items()}, "group_unit": "patient",
                  "source_manifest": relative(SOURCE), "encoder": "torchvision ResNet18 IMAGENET1K_V1, frozen",
                  "clinical_features": ["age", "gender", "region"] if arm == "image_tabular" else [],
                  "metadata_preprocessing": schema if arm == "image_tabular" else None,
                  "selection": selection, "metrics": metrics, "macro_f1_ci95": interval,
                  "per_class": {name: {"test_n": int(np.sum(truth == k)),
                                       "sensitivity": float(np.mean(prediction[truth == k] == k)) if np.any(truth == k) else None}
                                for k, name in enumerate(classes)},
                  "calibration": {"method": "temperature_scaling", "fitted_on": "validation", "temperature": temperature},
                  "checkpoint_sha256": sha256_file(checkpoint), "limitations": common_limitations,
                  "clinical_validated": False, "elapsed_seconds": time.perf_counter() - started}
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        card = ROOT / "docs/models" / f"{model_id}.md"
        card.write_text(f"# {model_id}\n\nResearch-only {arm} classifier on PAD-UFES-20.\n\n"
                        f"Patient-separated test: {len(indices)} images; accuracy {metrics['accuracy']:.4f}, macro F1 {metrics['macro_f1']:.4f}.\n\n"
                        + "\n".join(f"- {text}" for text in common_limitations)
                        + "\n\nData: CC BY 4.0, https://data.mendeley.com/datasets/zr7vgbcyr2/1. "
                        "Encoder: torchvision/ImageNet pretrained ResNet18; separate weight/data commercial review required.\n", encoding="utf-8")
        entry = {"model_id": model_id, "display_name": "Clinical skin image + documented attributes (research)" if arm == "image_tabular" else "Clinical skin-image classifier (research)",
                 "domain": "dermatology", "task": "image_classification", "anatomy": "skin", "framework": "torchvision resnet18 frozen + regularized linear head",
                 "adapter": "app.services.model_inference", "source_repository": "medtwin/ml_training/skin_fusion.py",
                 "dependency_environment": ".venv", "weights_path": relative(checkpoint), "device": "cuda_or_cpu",
                 "supported_inputs": ["image/png", "image/jpeg"], "supported_modalities": ["DERMATOLOGY"], "supported_classes": classes,
                 "status": "READY_UNVALIDATED", "validated": False, "research_inference": True,
                 "requires_clinical_features": arm == "image_tabular", "clinical_metadata_contract": schema if arm == "image_tabular" else None,
                 "input_quality": {"min_dimension": 64, "min_intensity_std": 2.0}, "limitations": common_limitations,
                 "artifact_bundle": {"dataset_version": version, "dataset_license": "CC BY 4.0 (PAD-UFES-20); pretrained encoder terms require separate review",
                                     "split_manifest_path": relative(OUT / "samples.csv"), "task_definition": "Six labelled clinical skin-lesion categories",
                                     "label_definition": {"classes": classes, "source": "publisher diagnostic column; confirmation varies"},
                                     "preprocessing_version": PREPROCESSING + ("+" + skin_metadata.VERSION if arm == "image_tabular" else ""),
                                     "checkpoint_path": relative(checkpoint), "checkpoint_sha256": report["checkpoint_sha256"],
                                     "calibration": report["calibration"], "decision_thresholds": {"rule": "argmax after temperature scaling"},
                                     "abstention_thresholds": None, "held_out_predictions_path": relative(predictions_path),
                                     "evaluation_report_path": relative(report_path), "model_card_path": relative(card)}}
        register_model(entry)
        summaries[arm] = metrics
        print(model_id, json.dumps(metrics), flush=True)
    (CACHE / "paired_arm_comparison.json").write_text(json.dumps({"same_test_patients": True, "arms": summaries,
        "fusion_minus_image_macro_f1": summaries["image_tabular"]["macro_f1"] - summaries["image_only"]["macro_f1"],
        "clinical_validation": False, "notice": "Descriptive paired-cohort difference; no external validation or statistical superiority claim."}, indent=2) + "\n")


if __name__ == "__main__":
    main()
