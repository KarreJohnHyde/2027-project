# Model card: Brain MRI glioma sub-region segmenter, FLAIR/T1/T1c/T2, 3-D (research)

- **Model id:** `brain_mri_glioma_segresnet` (registry status `READY_UNVALIDATED`; research-only; upload inference on 4-D NIfTI inside the development input envelope)
- **Task:** Patient-split segmentation of glioma sub-regions (oedema, necrotic/non-enhancing core, enhancing tumour) on co-registered FLAIR, T1, T1c and T2.
- **Data:** CC BY-SA 4.0 (Medical Segmentation Decathlon Task01, BraTS 2016/2017); dataset version `d3b2c312fdb06107`; patients split {'train': 338, 'val': 73, 'test': 73} (train/val/test) by `sha256(seed:patient_id)`. Citation: Antonelli M, Reinke A, Bakas S, et al. The Medical Segmentation Decathlon. Nat Commun 13:4128 (2022); Menze BH et al. IEEE TMI 34:1993 (2015).
- **Input:** channels FLAIR, T1w, T1gd, T2w; in-plane spacing 1-1 mm, slice spacing 1-1 mm; voxel axes RAS; non-zero voxel share 12.6%-20.7% (all development cases skull-stripped). Held-out cases accepted by the gate: 73 of 73.
- **Preprocessing:** crop to the non-zero box, per-channel z-score, native grid; sliding window [112, 112, 96] with overlap 0.5 (gaussian).
- **Architecture:** MONAI SegResNet (init filters 16, blocks [1, 2, 2, 4]/[1, 1, 1]), trained from scratch; best validation epoch 80 of 80 (validation mean case Dice 0.694).
- **Checkpoint:** `artifacts/training/brain_mri_glioma_segresnet-20261105T182742Z/best.pt`, SHA-256 `2f2836466ff27cdb06f0807dcd2dc97cb6b8498bcf25692ff23cf8e0481c7c42`.

## Held-out test results (73 patients, evaluated once through the serving function)

- Mean case macro Dice 0.752 (95% CI 0.728-0.775).
- peritumoural oedema: Dice 0.809 (95% CI 0.776-0.838) over 73 cases (0 with neither reference nor prediction excluded).
- necrotic or non enhancing tumour core: Dice 0.644 (95% CI 0.598-0.689) over 73 cases (0 with neither reference nor prediction excluded).
- enhancing tumour: Dice 0.802 (95% CI 0.759-0.838) over 73 cases (0 with neither reference nor prediction excluded).
- whole tumour (labels [1, 2, 3]): Dice 0.908 (95% CI 0.890-0.923).
- tumour core (labels [2, 3]): Dice 0.856 (95% CI 0.831-0.879).
- enhancing tumour (labels [3]): Dice 0.802 (95% CI 0.759-0.838).
- peritumoural oedema volume ml vs reference: bias -2.62 mL, limits of agreement -24.91 to 19.67 mL, MAE 7.99 (n = 73).
- necrotic or non enhancing tumour core volume ml vs reference: bias -2.27 mL, limits of agreement -16.66 to 12.11 mL, MAE 4.87 (n = 73).
- enhancing tumour volume ml vs reference: bias +0.17 mL, limits of agreement -8.55 to 8.88 mL, MAE 2.72 (n = 73).
- whole tumour volume ml vs reference: bias -4.72 mL, limits of agreement -25.30 to 15.85 mL, MAE 8.06 (n = 73).
- tumour core volume ml vs reference: bias -2.11 mL, limits of agreement -15.54 to 11.33 mL, MAE 4.90 (n = 73).

## Limitations

- Internal held-out test on Medical Segmentation Decathlon cases; no external or clinical validation.
- Gliomas only (BraTS): metastases, meningiomas, abscesses, stroke and other lesions are out of scope.
- Input must be skull-stripped FLAIR, T1, post-contrast T1 and T2, co-registered on a 1 mm grid like the SRI24 atlas, stacked in that order in one 4-D NIfTI.
- BraTS 2016 and 2017 cases are combined; a subject present in both releases cannot be excluded from the case numbers, so split leakage is possible.
- Label 2 combines necrosis and non-enhancing tumour (MSD convention); volumes are research estimates, not RANO measurements.
- Research-only output; not clinically validated and not for diagnosis or treatment decisions.
- Evaluation and serving use float16 autocast on CUDA with cuDNN autotuning; a rerun of training can differ slightly.

Full report: `docs/validation/models/brain_mri_glioma_segresnet.json`; input envelope: `docs/validation/models/brain_mri_glioma_segresnet_input_envelope.json`.
