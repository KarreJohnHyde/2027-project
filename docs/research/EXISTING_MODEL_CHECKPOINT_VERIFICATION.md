# Existing model checkpoint verification (2026-10-30)

Each registered checkpoint was hashed (SHA-256 over the file) and compared with `model_registry/models.json`;
the research gate (`model_inference.research_gate`) was evaluated for every research-runnable entry. Served
outputs were then compared with the predictions each trainer saved on its held-out test split
(`scripts/verify_upload_inference_parity.py`, results in `docs/validation/UPLOAD_INFERENCE_PARITY.json`).

| Model | Task | Checkpoint SHA-256 (prefix) | Hash | Gate | Upload path | Served vs saved held-out outputs |
| --- | --- | --- | --- | --- | --- | --- |
| gi_kvasir_v2_classifier | 8-class GI endoscopy classification | 6d7494d19e52 | match | allowed | 2-D image | 1,202/1,202 same top class; max probability difference 0.014 |
| gi_gastrovision_27class_classifier | 27-class GI endoscopy classification | 464986a86033 | match | allowed | 2-D image | 1,224/1,225 same top class |
| hematology_cnmc_all_classifier | ALL vs normal blood-cell image | f5ea1fafc826 | match | allowed | 2-D image | 1,867/1,867 same top class |
| angiography_stenosis_detector | Coronary stenosis boxes | d06224b406d7 | match | allowed | 2-D image | Operating point 147 TP / 537 FP / 239 FN vs saved 147 / 536 / 239 |
| kidney_stone_detector | Kidney-stone boxes on CT slices | e9267f9a6e9f | match | allowed | 2-D image | Operating point identical (221 / 77 / 181) |
| angiography_syntax_segmenter | Coronary segment masks | 3a3882071f72 | match | allowed | 2-D image | Pixel agreement ≥ 99.987 %; stored RLE decodes exactly 300/300 |
| gi_kvasir_seg_polyp_segmenter | Polyp masks | a5a2c88dc5af | match | allowed | 2-D image | Pixel agreement ≥ 99.954 %; RLE exact 120/120; source-pixel Dice 0.768 |
| ptbxl_ecg_baseline | 12-lead ECG superclasses | 687f69a2ff1c | match | allowed | WFDB / CSV | Recorded in the `ecg` section of the parity file |
| acdc_cardiac_mri_3d_unet | Cardiac cine-MRI 3-D segmentation | b18afcf66eff | match | allowed | NIfTI / DICOM series | 98/98 identical masks; 2 frames refused by the spacing envelope |
| heart_failure_survival_cox | Survival (tabular) | 0073a7eba793 | match | allowed | none (evaluation only) | — |
| pbc_mayo_survival_cox | Survival (tabular) | 3d86d29f2438 | match | allowed | none (evaluation only) | — |
| cxr_torchxrayvision_densenet121 (third party) | Chest radiograph scores, anatomy masks | 56524913dd16 | match | own endpoint | 2-D image with attestation | Not evaluated by MedTwin |

Registry entries without a checkpoint: `clinical_rules_v1`, `monai_runtime`, `scispacy_adapter` (framework or rules),
`mura_study_baseline`, `brain_imaging_adapter`, `lung_imaging_adapter`, `gi_endoscopy_adapter` (`WEIGHTS_MISSING`),
`medcat_adapter`, `radgraph_adapter` (`DEPENDENCY_MISSING`), `deepsa_angiography_adapter` (`UNSUPPORTED`).
A framework adapter is not a disease model.

None of these models has external validation or clinical authorisation; all outputs are research-only and
pending human review.
