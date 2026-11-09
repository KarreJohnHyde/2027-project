# Model card: Brain MRI ischaemic stroke lesion segmenter, DWI + ADC, 3-D (research)

- **Model id:** `brain_mri_stroke_lesion_segresnet` (registry status `READY_UNVALIDATED`; research-only; upload inference on 4-D NIfTI inside the development input envelope)
- **Task:** Patient-split segmentation of ischaemic stroke lesions on skull-stripped DWI (b=1000) and ADC.
- **Data:** CC BY 4.0 (ISLES 2022, multi-centre stroke MRI); dataset version `577bbf290a101762`; patients split {'train': 174, 'val': 38, 'test': 38} (train/val/test) by `sha256(seed:patient_id)`. Citation: Hernandez Petzsche MR, de la Rosa E, Hanning U, et al. ISLES 2022. Scientific Data 9:762 (2022).
- **Input:** channels DWI, ADC; in-plane spacing 0.875-2 mm, slice spacing 2-4.8 mm; voxel axes LAS; non-zero voxel share 14.0%-100.0% (1 of 212 development cases have more than half their voxels non-zero, i.e. are probably not skull-stripped, so this range does not separate heads with skull from skull-stripped brains). Held-out cases accepted by the gate: 37 of 38 (refused: SLICE_SPACING_OUTSIDE_DEVELOPMENT_RANGE x1).
- **Preprocessing:** crop to the non-zero box, per-channel z-score, resampling to 2 x 2 x 2 mm and back (trilinear); sliding window [96, 96, 64] with overlap 0.5 (gaussian).
- **Architecture:** MONAI SegResNet (init filters 16, blocks [1, 2, 2, 4]/[1, 1, 1]), trained from scratch; best validation epoch 90 of 150 (validation mean case Dice 0.755).
- **Checkpoint:** `artifacts/training/brain_mri_stroke_lesion_segresnet-20261105T092121Z/best.pt`, SHA-256 `058be494f9b04b603fa47bfc7425707bb6802408eac37d5ce8daa910a86d14ca`.

## Held-out test results (38 patients, evaluated once through the serving function)

- Mean case macro Dice 0.752 (95% CI 0.666-0.822).
- ischaemic stroke lesion: Dice 0.752 (95% CI 0.666-0.822) over 38 cases (0 with neither reference nor prediction excluded).
- Lesion detection: 161 of 295 reference lesions touched (sensitivity 0.546); component precision 0.853; 0.76 false-positive components per case.
- Dice by reference lesion volume: smallest third (13 cases) 0.641; middle third (12 cases) 0.796; largest third (13 cases) 0.823.
- ischaemic stroke lesion volume ml vs reference: bias -3.87 mL, limits of agreement -38.69 to 30.96 mL, MAE 4.82 (n = 38).

## Limitations

- Internal held-out test on ISLES 2022 patients from the same centres as training; no external or clinical validation.
- Input: DWI and ADC on one grid, stacked in one 4-D NIfTI with DWI first, skull-stripped like the development data; FLAIR is not used. One development case was not skull-stripped, so the non-zero-share check cannot refuse a head with skull for this model.
- A predicted lesion is a research segmentation of diffusion restriction, not an infarct-core estimate for treatment selection.
- Small lesions are segmented less reliably (Dice by reference lesion volume is reported); false-positive components per case are reported.
- Trained on ischaemic stroke only: haemorrhage, tumour, infection and other causes of diffusion restriction are out of scope.
- Research-only output; not clinically validated and not for diagnosis or treatment decisions.
- Evaluation and serving use float16 autocast on CUDA with cuDNN autotuning; a rerun of training can differ slightly.

Full report: `docs/validation/models/brain_mri_stroke_lesion_segresnet.json`; input envelope: `docs/validation/models/brain_mri_stroke_lesion_segresnet_input_envelope.json`.
