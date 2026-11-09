"""Publish a finished volumetric training run (brain MRI; abdominal CT since 2026-11-06): input envelope, evaluation
report, model card and registry entry.

Every number in the model card is read from the run's held-out evaluation (execution.json); nothing is typed
by hand. Registry entries are research-only; a measured zero-Dice declared target
is marked FAILED and blocked from upload inference.

    python scripts/publish_brain_mri_models.py --profile stroke --run-dir artifacts/training/<run>
    python scripts/publish_brain_mri_models.py --profile glioma --run-dir artifacts/training/<run>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_training import volumetric_multichannel as trainer  # noqa: E402
from ml_training.common import MODEL_CARDS, REPORTS, register_model, relative  # noqa: E402

COMMON_LIMITATIONS = [
    "Research-only output; not clinically validated and not for diagnosis or treatment decisions.",
    "Evaluation and serving use float16 autocast on CUDA with cuDNN autotuning; a rerun of training can differ slightly.",
]
PROFILES = {
    "kidney": {
        "model_id": "ct_kidney_tumour_segresnet",
        "display_name": "CT kidney and renal-tumour segmenter, 3-D (research)",
        "task_id": "kits19-kidney-tumour-segmentation", "anatomy": "kidneys",
        "dataset_preparation": "python scripts/prepare_kits19_dataset.py",
        "modalities": ["CT_ABDOMEN_VOLUME"],
        "dataset_license": "CC BY-NC-SA 4.0 (KiTS19 data); local non-commercial research only",
        "task_definition": "Patient-separated kidney and renal-tumour segmentation on the 210 labelled KiTS19 contrast CT volumes.",
        "label_source": "KiTS19 original kidney/tumour masks paired with checksum-verified publisher CT volumes",
        "citation": "Heller N et al. The KiTS19 Challenge Data: 300 Kidney Tumor Cases with Clinical Context, CT Semantic Segmentations, and Surgical Outcomes. arXiv:1904.00445.",
        "limitations": [
            "Internal held-out patients only; no independent external or clinical validation.",
            "Renal-surgery cohort; healthy kidneys and incidental lesions in general populations are not established use cases.",
            "Tumour masks do not determine histology, malignancy, stage or treatment.",
            "One contrast abdominal CT volume in Hounsfield units within the recorded development geometry and intensity envelope.",
            "Initial bounded training experiment; measured results must be assessed before proposing further research use.",
        ],
    },
    "stroke": {
        "model_id": "brain_mri_stroke_lesion_segresnet",
        "display_name": "Brain MRI ischaemic stroke lesion segmenter, DWI + ADC, 3-D (research)",
        "task_id": "isles22-stroke-lesion-segmentation",
        "modalities": ["BRAIN_MRI_DIFFUSION"],
        "dataset_license": "CC BY 4.0 (ISLES 2022, multi-centre stroke MRI)",
        "task_definition": "Patient-split segmentation of ischaemic stroke lesions on skull-stripped DWI (b=1000) and ADC.",
        "label_source": "ISLES 2022 binary lesion masks on the DWI grid (publisher's annotation)",
        "citation": "Hernandez Petzsche MR, de la Rosa E, Hanning U, et al. ISLES 2022. Scientific Data 9:762 (2022).",
        "limitations": [
            "Internal held-out test on ISLES 2022 patients from the same centres as training; no external or clinical validation.",
            "Input: DWI and ADC on one grid, stacked in one 4-D NIfTI with DWI first, skull-stripped like the development data; FLAIR is not used. "
            "One development case was not skull-stripped, so the non-zero-share check cannot refuse a head with skull for this model.",
            "A predicted lesion is a research segmentation of diffusion restriction, not an infarct-core estimate for treatment selection.",
            "Small lesions are segmented less reliably (Dice by reference lesion volume is reported); false-positive components per case are reported.",
            "Trained on ischaemic stroke only: haemorrhage, tumour, infection and other causes of diffusion restriction are out of scope.",
        ],
    },
    "glioma": {
        "model_id": "brain_mri_glioma_segresnet",
        "display_name": "Brain MRI glioma sub-region segmenter, FLAIR/T1/T1c/T2, 3-D (research)",
        "task_id": "msd-brain-tumour-segmentation",
        "modalities": ["BRAIN_MRI_MULTISEQUENCE"],
        "dataset_license": "CC BY-SA 4.0 (Medical Segmentation Decathlon Task01, BraTS 2016/2017)",
        "task_definition": "Patient-split segmentation of glioma sub-regions (oedema, necrotic/non-enhancing core, enhancing tumour) on co-registered FLAIR, T1, T1c and T2.",
        "label_source": "Medical Segmentation Decathlon Task01 labels (BraTS expert annotations)",
        "citation": "Antonelli M, Reinke A, Bakas S, et al. The Medical Segmentation Decathlon. Nat Commun 13:4128 (2022); Menze BH et al. IEEE TMI 34:1993 (2015).",
        "limitations": [
            "Internal held-out test on Medical Segmentation Decathlon cases; no external or clinical validation.",
            "Gliomas only (BraTS): metastases, meningiomas, abscesses, stroke and other lesions are out of scope.",
            "Input must be skull-stripped FLAIR, T1, post-contrast T1 and T2, co-registered on a 1 mm grid like the SRI24 atlas, stacked in that order in one 4-D NIfTI.",
            "BraTS 2016 and 2017 cases are combined; a subject present in both releases cannot be excluded from the case numbers, so split leakage is possible.",
            "Label 2 combines necrosis and non-enhancing tumour (MSD convention); volumes are research estimates, not RANO measurements.",
        ],
    },
    # CT models (approved MSD downloads, 2026-11-06): the same trainer with the Hounsfield intensity mode.
    "pancreas": {
        "model_id": "ct_pancreas_tumour_segresnet",
        "display_name": "CT pancreas and pancreatic tumour segmenter, 3-D (research)",
        "task_id": "msd-pancreas-tumour-segmentation", "anatomy": "pancreas",
        "modalities": ["CT_ABDOMEN_VOLUME"],
        "dataset_license": "CC BY-SA 4.0 (Medical Segmentation Decathlon Task07 Pancreas)",
        "task_definition": "Patient-split segmentation of the pancreas and pancreatic tumour (cyst or mass) on portal-venous abdominal CT.",
        "label_source": "Medical Segmentation Decathlon Task07 labels (pancreas and tumour, Memorial Sloan Kettering)",
        "citation": "Antonelli M, Reinke A, Bakas S, et al. The Medical Segmentation Decathlon. Nat Commun 13:4128 (2022); Simpson AL et al. arXiv:1902.09063 (2019).",
        "limitations": [
            "Internal held-out test on Medical Segmentation Decathlon cases from one centre; no external or clinical validation.",
            "Cases are patients undergoing resection of pancreatic masses (cysts and tumours); a pancreas without a mass is under-represented.",
            "Input: one abdominal CT volume in Hounsfield units (NIfTI, NRRD or MetaImage, or a DICOM series permuted and flipped into the development "
            "orientation without resampling), inside the development spacing and intensity ranges.",
            "The tumour label covers cystic and solid lesions alike; a segmentation is not a diagnosis of malignancy.",
        ],
    },
    "liver": {
        "model_id": "ct_liver_tumour_segresnet",
        "display_name": "CT liver and liver tumour segmenter, 3-D (research)",
        "task_id": "msd-liver-tumour-segmentation", "anatomy": "liver",
        "modalities": ["CT_ABDOMEN_VOLUME"],
        "dataset_license": "CC BY-SA 4.0 (Medical Segmentation Decathlon Task03 Liver, LiTS)",
        "task_definition": "Patient-split segmentation of the liver and liver tumours on contrast-enhanced abdominal CT.",
        "label_source": "Medical Segmentation Decathlon Task03 labels (LiTS liver and tumour annotations)",
        "citation": "Antonelli M, Reinke A, Bakas S, et al. The Medical Segmentation Decathlon. Nat Commun 13:4128 (2022); Bilic P et al. Medical Image Analysis 84:102680 (2023).",
        "limitations": [
            "Internal held-out test on Medical Segmentation Decathlon (LiTS) cases; no external or clinical validation.",
            "Primary and secondary liver tumours share one label; a segmentation is not a tumour type or a diagnosis.",
            "Input: one abdominal CT volume in Hounsfield units (NIfTI, NRRD or MetaImage, or a DICOM series permuted and flipped into the development "
            "orientation without resampling), inside the development spacing and intensity ranges.",
            "Small lesions are segmented less reliably (lesion detection and Dice by reference volume are reported).",
        ],
    },
    # LIDC-IDRI subset (approved 300-patient download, 2026-11-06; TCIA CC BY 3.0).
    "lidc": {
        "model_id": "ct_lung_nodule_segresnet",
        "display_name": "CT lung nodule segmenter, 3-D (LIDC-IDRI subset, research)",
        "task_id": "lidc-nodule-segmentation", "anatomy": "lungs",
        "modalities": ["CT_CHEST_VOLUME"],
        "dataset_license": "CC BY 3.0 (TCIA Data Usage Policy; LIDC-IDRI)",
        "task_definition": "Patient-split segmentation of lung nodules of 3 mm or more on thoracic CT (voxels outlined by at least two of the four LIDC readers).",
        "label_source": "LIDC-IDRI reader XML (unblinded reads), 50 % consensus of the outlined nodules",
        "citation": ("Armato SG III, McLennan G, Bidaut L, et al. The Lung Image Database Consortium (LIDC) and Image Database Resource Initiative (IDRI). "
                     "Med Phys 38(2):915-931 (2011); Data From LIDC-IDRI, TCIA, doi:10.7937/K9/TCIA.2015.LO9QL9SX."),
        "limitations": [
            "Trained on a 300-patient subset of LIDC-IDRI (the first 300 patients by ID with reader XML); internal held-out test only.",
            "The reference is a reader consensus (two of four readers); nodules under 3 mm and non-nodules are not outlined, so they count as background.",
            "Segmenting a nodule says nothing about malignancy; LIDC malignancy ratings were not used.",
            "Input: one thoracic CT volume in Hounsfield units (NIfTI, NRRD or MetaImage, or a DICOM series permuted and flipped into the development "
            "orientation without resampling), inside the development spacing and intensity ranges.",
        ],
    },
}


def _pct(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _ci(block) -> str:
    return f" (95% CI {block['low']:.3f}-{block['high']:.3f})" if isinstance(block, dict) and block.get("status") == "COMPUTED" else ""


def research_quality_assessment(metrics: dict) -> dict:
    failed = [name for name, values in metrics.get("per_structure", {}).items()
              if values.get("reference_positive_cases", 0) > 0 and values.get("mean_dice") == 0]
    return {"status": "FAILED_DECLARED_TARGET" if failed else "METRICS_RECORDED_NOT_CLINICALLY_VALIDATED",
            "failed_targets": failed,
            "rule": "A declared target with zero mean Dice despite positive held-out references blocks upload use. This is not a clinical acceptance threshold."}


def card(profile: dict, report: dict, envelope: dict) -> str:
    metrics = report["metrics"]
    config = report["config"]
    quality = report.get("research_quality_assessment", {})
    status = "FAILED" if quality.get("status") == "FAILED_DECLARED_TARGET" else "READY_UNVALIDATED"
    lines = [
        f"# Model card: {profile['display_name']}", "",
        f"- **Model id:** `{profile['model_id']}` (registry status `{status}`; research evidence only when FAILED; no clinical authorization)",
        f"- **Task:** {profile['task_definition']}",
        f"- **Data:** {profile['dataset_license']}; dataset version `{report['dataset_version'][:16]}`; patients split {report['split_counts']} "
        f"(train/val/test) by `sha256(seed:patient_id)`. Citation: {profile['citation']}",
        f"- **Input:** channels {', '.join(envelope['channels'])}; in-plane spacing {envelope['in_plane_spacing_mm']['min']:g}-{envelope['in_plane_spacing_mm']['max']:g} mm, "
        f"slice spacing {envelope['slice_spacing_mm']['min']:g}-{envelope['slice_spacing_mm']['max']:g} mm; voxel axes {', '.join(envelope['orientations'])}; "
        + (f"1st/99th intensity percentiles {envelope['hu_percentiles']['p01']['min']:g} to {envelope['hu_percentiles']['p01']['max']:g} and "
           f"{envelope['hu_percentiles']['p99']['min']:g} to {envelope['hu_percentiles']['p99']['max']:g} HU (margin {envelope['hu_percentiles']['margin_hu']:g} HU)"
           if "hu_percentiles" in envelope else
           f"non-zero voxel share {envelope['nonzero_fraction']['min']:.1%}-{envelope['nonzero_fraction']['max']:.1%}"
           + (f" ({envelope['nonzero_fraction']['development_cases_above_half']} of {envelope['development_cases']} development cases have more than half "
              "their voxels non-zero, i.e. are probably not skull-stripped, so this range does not separate heads with skull from skull-stripped brains)"
              if envelope["nonzero_fraction"].get("development_cases_above_half") else " (all development cases skull-stripped)"))
        + f". Held-out cases accepted by the gate: {envelope['held_out_test_cases']['accepted_by_gate']} of {envelope['held_out_test_cases']['total']}"
        + (f" (refused: {', '.join(f'{code} x{count}' for code, count in envelope['held_out_test_cases']['refusal_reasons'].items())})"
           if envelope["held_out_test_cases"]["refusal_reasons"] else "") + ".",
        (f"- **Preprocessing:** clip to {config['preprocessing']['ct_clip_hu'][0]:g} to {config['preprocessing']['ct_clip_hu'][1]:g} HU (0.5-99.5 percentiles of "
         f"training foreground voxels), z-score with mean {config['preprocessing']['ct_mean']:g} and SD {config['preprocessing']['ct_std']:g} HU (training foreground), "
         if config["preprocessing"].get("intensity") == "ct_hu_window" else "- **Preprocessing:** crop to the non-zero box, per-channel z-score, ")
        + f""
        f"{'resampling to ' + ' x '.join(f'{v:g}' for v in config['preprocessing']['target_spacing_mm']) + ' mm and back (trilinear)' if config['preprocessing']['target_spacing_mm'] else 'native grid'}; "
        f"sliding window {config['patch_size']} with overlap {config['preprocessing']['sliding_window_overlap']} ({config['preprocessing']['sliding_window_mode']}).",
        f"- **Architecture:** MONAI SegResNet (init filters {config['init_filters']}, blocks {config['blocks_down']}/{config['blocks_up']}), trained from scratch; "
        f"best validation epoch {report['selection']['best_epoch']} of {report['epochs_run']} (validation mean case Dice {report['selection']['best_score']:.3f}).",
        f"- **Checkpoint:** `{relative(Path(report['checkpoint']['path']))}`, SHA-256 `{report['checkpoint']['sha256']}`.", "",
        f"## Held-out test results ({report['test_patients']} patients, evaluated once through the serving function)", "",
        f"- Mean case macro Dice {_pct(metrics['mean_case_macro_dice'])}{_ci(metrics['mean_case_macro_dice_95ci'])}.",
    ]
    for name, values in metrics["per_structure"].items():
        lines.append(f"- {name.replace('_', ' ')}: Dice {_pct(values['mean_dice'])}{_ci(values['mean_dice_95ci'])} over {values['scored_cases']} cases "
                     f"({values['both_empty_cases_excluded']} with neither reference nor prediction excluded).")
    for name, values in (metrics.get("regions") or {}).items():
        lines.append(f"- {name.replace('_', ' ')} (labels {values['labels']}): Dice {_pct(values['mean_dice'])}{_ci(values['mean_dice_95ci'])}.")
    detection = metrics.get("lesion_detection")
    if detection:
        lines.append(f"- Lesion detection: {detection['detected_lesions']} of {detection['reference_lesions']} reference lesions touched "
                     f"(sensitivity {_pct(detection['lesion_sensitivity'])}); component precision {_pct(detection['component_precision'])}; "
                     f"{detection['false_positive_components_per_case']:.2f} false-positive components per case.")
    bands = (metrics.get("dice_by_reference_volume") or {}).get("bands")
    if bands:
        lines.append("- Dice by reference lesion volume: " + "; ".join(
            f"{band.replace('_', ' ')} ({values['cases']} cases) {_pct(values['mean_dice'])}" for band, values in bands.items()) + ".")
    for name, values in report["clinical_indices"].items():
        if values.get("bias") is not None:
            lines.append(f"- {name.replace('_', ' ')} vs reference: bias {values['bias']:+.2f} mL, limits of agreement {values['limits_of_agreement'][0]:.2f} to "
                         f"{values['limits_of_agreement'][1]:.2f} mL, MAE {values['mean_absolute_error']:.2f} (n = {values['n_patients']}).")
    lines += ["", "## Limitations", "", *[f"- {item}" for item in profile["limitations"] + COMMON_LIMITATIONS], "",
              f"Full report: `docs/validation/models/{profile['model_id']}.json`; input envelope: `docs/validation/models/{profile['model_id']}_input_envelope.json`.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", choices=sorted(PROFILES), required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    profile = PROFILES[args.profile]
    run_dir = args.run_dir.resolve()
    execution = json.loads((run_dir / "execution.json").read_text(encoding="utf-8"))
    if execution.get("execution_status") != "COMPLETE" or execution.get("model_id") != profile["model_id"]:
        raise SystemExit("The run is not a completed run of this profile's model.")
    quality = research_quality_assessment(execution["held_out_test"]["metrics"])
    if quality["status"] == "FAILED_DECLARED_TARGET":
        profile = {**profile, "limitations": profile["limitations"] + [
            "FAILED TARGET: zero held-out Dice for " + ", ".join(quality["failed_targets"]) + ". Upload inference is blocked; a zero mask must not imply absence of disease."]}
    envelope_path = REPORTS / f"{profile['model_id']}_input_envelope.json"
    report_path = REPORTS / f"{profile['model_id']}.json"
    card_path = MODEL_CARDS / f"{profile['model_id']}.md"
    envelope = trainer.build_envelope(run_dir, envelope_path)
    report = trainer.build_report(run_dir, report_path, {"task_id": profile["task_id"], "dataset_license": profile["dataset_license"],
                                                         "limitations": profile["limitations"] + COMMON_LIMITATIONS, "citation": profile["citation"],
                                                         "research_quality_assessment": quality,
                                                         "input_envelope": relative(envelope_path)})
    card_path.write_text(card(profile, report, envelope), encoding="utf-8")
    manifest = json.loads(Path(execution["manifest_path"]).read_text(encoding="utf-8"))
    checkpoint = Path(execution["checkpoint"]["path"])
    entry = {
        "model_id": profile["model_id"], "display_name": profile["display_name"], "domain": "medical_imaging",
        "task": "volumetric_semantic_segmentation", "anatomy": profile.get("anatomy", "brain"), "framework": "MONAI SegResNet (PyTorch), 3-D",
        "adapter": "ml_training.volumetric_multichannel", "source_repository": "medtwin/ml_training", "dependency_environment": ".venv",
        "weights_path": relative(checkpoint), "device": "cuda_or_cpu", "supported_inputs": ["application/x-nifti", "application/gzip"],
        "supported_modalities": profile["modalities"], "supported_classes": [label["name"] for label in manifest["labels"]],
        "status": "FAILED" if quality["status"] == "FAILED_DECLARED_TARGET" else "READY_UNVALIDATED",
        "validated": False, "research_inference": True, "research_quality_assessment": quality,
        "limitations": profile["limitations"] + COMMON_LIMITATIONS,
        "pipeline": {"dataset_preparation": profile.get("dataset_preparation", "python scripts/prepare_brain_mri_datasets.py"), "manifest_builder": "python -m ml_training.volumetric_manifest pairs",
                     "trainer": "python -m ml_training.volumetric_multichannel train", "synthetic_smoke": "python -m ml_training.volumetric_multichannel smoke",
                     "publisher": "python scripts/publish_brain_mri_models.py", "run_id": run_dir.name, "real_data_training_executed": True,
                     "manifest_dataset_version": manifest["dataset_version"]},
        "artifact_bundle": {
            "dataset_version": manifest["dataset_version"], "dataset_license": profile["dataset_license"],
            "split_manifest_path": relative(Path(execution["manifest_path"])), "task_definition": profile["task_definition"],
            "label_definition": {"source": profile["label_source"], "classes": {str(label["id"]): label["name"] for label in manifest["labels"]}},
            "preprocessing_version": trainer.PREPROCESSING_VERSION, "checkpoint_path": relative(checkpoint),
            "checkpoint_sha256": execution["checkpoint"]["sha256"], "calibration": None,
            "decision_thresholds": {"rule": "argmax over softmax per voxel"}, "abstention_thresholds": None,
            "held_out_predictions_path": relative(Path(execution["held_out_predictions"])), "evaluation_report_path": relative(report_path),
            "model_card_path": relative(card_path), "input_envelope_path": relative(envelope_path),
        },
        "source_display_name": profile["display_name"], "inference_input": "volume_nifti",
        "validation_readiness": {"validation_ready": False,
                                 "readiness": "FAILED_DECLARED_TARGET" if quality["status"] == "FAILED_DECLARED_TARGET" else "INTERNAL_HELD_OUT_ONLY", "run_scope": "RESEARCH"},
    }
    register_model(entry)
    print(json.dumps({"model_id": profile["model_id"], "report": relative(report_path), "card": relative(card_path),
                      "envelope_accepted": envelope["held_out_test_cases"]["accepted_by_gate"], "envelope_total": envelope["held_out_test_cases"]["total"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
