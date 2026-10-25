# Dataset training results

Every number below comes from a run executed on 2026-10-24 or 2026-10-25 on the local RTX 5060 Laptop
GPU (8 GB), evaluated **once** on a frozen held-out test split after model and operating-
point selection on the validation split; classifier temperature scaling also used only
the validation split. Reports: `docs/validation/models/<model_id>.json`;
model cards: `docs/models/<model_id>.md`; run directories (config, log, checkpoint,
test predictions): `artifacts/training/<run_id>/` (not committed: checkpoints are large
binaries; the registry stores their SHA-256 and the research gate re-hashes them).

All models are **research-only** (`READY_UNVALIDATED`): internal held-out evaluation on
the same public source distribution, no external or clinical validation, no patient-level
separation guarantee unless stated. None is clinically activatable.

## Current registered runs

| Model | Frozen held-out set | Headline result | Evidence status |
| --- | ---: | --- | --- |
| Kvasir v2 8-class classifier | 1,202 images | Accuracy 0.926; macro-F1 0.926 | Internal held-out only |
| GastroVision 27-class classifier | 1,225 images | Accuracy 0.737; macro-F1 0.553 | `EXPLORATORY_ONLY`; rare classes below the declared minimum |
| ARCADE stenosis detector | 300 images | COCO mAP@[.50:.95] 0.062; AP50 0.203 | Internal held-out only |
| TEZ kidney-stone detector | 196 images | COCO mAP@[.50:.95] 0.231; AP50 0.629 | Internal held-out only |
| ARCADE SYNTAX segmenter | 300 images | Mean foreground Dice/image 0.307; whole-vessel Dice 0.683 | Internal held-out only |
| Kvasir-SEG polyp segmenter (2026-10-25) | 120 images (publisher test list) | Polyp Dice 0.768 (0.725–0.809); IoU 0.670 | Internal held-out only |
| C-NMC ALL-vs-normal cell classifier (2026-10-25) | 1,867 images / 28 subject clusters | Accuracy 0.807 (0.659–0.894); macro-F1 0.790 (0.626–0.877) | Internal held-out only |
| PTB-XL ECG superclass classifier (2026-10-25) | 2,163 ECGs / 1,881 patients | Macro AUROC 0.917 (0.909–0.925); macro AUPRC 0.805 | Internal held-out only; patient-disjoint folds |
| ACDC cardiac cine-MRI segmenter, 3-D (2026-10-25) | 100 ED/ES volumes / 50 patients | Macro Dice 0.750 (0.719–0.778); LV EF mean absolute error 9.1 points vs reference masks | Internal held-out only; evaluation evidence, no upload path |
| PBC survival, Mayo covariates (2026-10-25) | 104 patients (cohort hold-out) | Harrell's C 0.786 (0.709–0.854); integrated Brier 0.105 vs 0.146 Kaplan–Meier | Internal hold-out cohort only |
| Heart-failure survival (2026-10-25) | 90 patients | Harrell's C 0.671 (0.569–0.774); no Brier skill over Kaplan–Meier | `EXPLORATORY_ONLY` |

The first five rows are the image runs registered on 2026-10-24. The later Kvasir-SEG and
C-NMC image models were trained on 2026-10-25 and have research-only upload inference;
the ECG, survival and cardiac MRI models are listed in Validation Center as evaluation
evidence, with no upload inference path. The application shows all of them under medical
names; the source dataset names used here are credited on its Data sources and licences
page. The superseded Kvasir run described below is retained only as
methodological history and is not a registered model.

## Protocol (`ml_training/`)

1. Task gate and manifests: `scripts/dataset_task_audit.py` (licence verified from the
   official source; labels validated; exact cross-archive duplicates removed;
   near-duplicate groups = dHash candidate pools confirmed by 64×64 normalised pixel
   correlation ≥ 0.95, endoscopy frame/text masked). Splits: group-aware stratified
   70/15/15 (seed 20261024) unless the publisher split is kept; publisher splits are
   audited for cross-split duplicates, and those test images are also reported
   separately.
2. Training one job at a time, bf16 autocast, deterministic seeds, no anatomically
   invalid augmentation (no left-right flips for angiography or CT).
3. Selection and thresholds on validation only (macro-F1, AP50, mean Dice); temperature
   scaling on validation for classifiers.
4. Single frozen-test evaluation. Classifier CIs and the reported segmentation CIs use
   1,000 group-bootstrap resamples. Detector COCO metrics currently have no uncertainty
   intervals and must not be interpreted as precise population estimates.
5. Registration: checkpoint SHA-256, dataset version, split counts, report, card and
   held-out predictions in `model_registry/models.json`.

## GI endoscopy — Kvasir v2, 8 classes (`gi_kvasir_v2_classifier`)

- Data: `archive (16).zip` (Kvasir v2, 8 × 1,000 images; `archive (18).zip` is a 7,988-file
  duplicate and was not used). Licence: Kvasir terms of use — research and educational
  use only, commercial use requires permission (<https://datasets.simula.no/kvasir/>).
- Split: 5,599 / 1,199 / 1,202 images; 1,202 test images in 1,194 near-duplicate groups.
  29 pixel-confirmed near-duplicate pairs, one with conflicting publisher labels (the same
  file in `dyed-lifted-polyps` and `dyed-resection-margins`), kept in one split.
- Candidates: ResNet-18 (val macro-F1 0.943) and EfficientNet-B0 (0.940), ImageNet
  weights, 8 epochs, AdamW + one-cycle, batch 48, 224 px. Selected: ResNet-18.
  Temperature T = 1.078. Training 704 s for both candidates.
- **Test (n = 1,202): accuracy 0.926 (95% CI 0.911–0.940); macro-F1 0.926 (0.911–0.940);
  balanced accuracy 0.926 (0.912–0.940); macro one-vs-rest AUROC 0.995; ECE 0.020 → 0.019
  after temperature scaling; multiclass Brier 0.110.**
- Per class F1: dyed-lifted-polyps 0.963, dyed-resection-margins 0.963, esophagitis 0.807,
  normal-cecum 0.970, normal-pylorus 0.980, normal-z-line 0.825, polyps 0.960,
  ulcerative-colitis 0.939. The main confusion is esophagitis ↔ normal z-line.
- The manuscript's > 95 % accuracy objective is **not met** (CI upper bound 0.940).
- Checkpoint `artifacts/training/gi_kvasir_v2_classifier-20261024T151359Z/model.pt`,
  SHA-256 `6d7494d19e52c0b5462f90637e35f474d9db1950217e5a40e95cda4bec27a8e4`.
- Inference parity: the backend adapter reproduced the training-time test predictions
  (21/21 sampled images, same top class; max probability difference 0.005, bf16 vs fp32).

**Superseded run** `gi_kvasir_v2_classifier-20261024T145606Z` (reported for transparency):
its split used unconfirmed dHash chains, which merged look-alike frames into one
255-image mixed-class group in the test split. Test accuracy 0.902 (95% CI 0.864–0.945),
macro-F1 0.907. The grouping was corrected for a methodological reason (the groups were
not near-duplicates), not to change the result, and the model was retrained once.

## Coronary angiography — ARCADE stenosis detection (`angiography_stenosis_detector`)

- Data: ARCADE (X-ray coronary angiography, expert COCO annotations), stenosis subset,
  CC0 1.0 (<https://zenodo.org/records/10390295>). Publisher splits kept: 1,000 / 200 / 300
  images. Leakage audit: 11 pixel-confirmed cross-split components contain 54 images,
  including 10 test images. The older direct-endpoint count (41 images, 4 test images)
  was superseded by this conservative transitive-component definition. No patient
  identifiers are distributed, so patient-level separation cannot be verified.
- Model: Faster R-CNN ResNet-50 FPN v2 (COCO-pretrained torchvision weights), 1 class,
  20 epochs, SGD lr 0.01, batch 4, min/max size 512/1024, no flips. Selected on
  validation AP50: epoch 4 (val AP50 0.226); later epochs overfit. Training 2,951 s.
- **Test (300 images, 386 reference boxes): COCO mAP@[.50:.95] 0.062; AP50 0.203;
  AP75 0.015; AR@100 0.359.** The conservative post-hoc sensitivity analysis excludes
  all 10 test images in transitive components spanning publisher splits (n = 290): mAP
  0.061, AP50 0.198. The official publisher-test result remains the primary result.
- Operating point chosen on validation (max F1 at IoU 0.5): score ≥ 0.75. On test:
  precision 0.215, recall 0.381, F1 0.275 (TP 147, FP 536, FN 239). Detector scores are
  not probabilities and are not calibrated.
- **Independent re-score with `MedTwin_2_Validation_Kit`** against the publisher's own
  `test.json` (image ids matched by file name, publisher category `stenosis`): mAP
  0.0618, AP50 0.2029, AP75 0.0149 — identical to the trainer
  (`docs/validation/models/angiography_stenosis_detector.kit_crosscheck.json`).
- Checkpoint SHA-256 `d06224b406d7e9104f25c03921fcbe78c2aedae0752ce74e9bcbfefae49c05b8`.
- Interpretation: low localisation accuracy (AP75 0.015) and many false positives at
  the chosen threshold; suitable only for research exploration of the pipeline.

## CT — TEZ kidney stone detection (`kidney_stone_detector`)

- Data: `archive (11).zip`, TEZ_ROI_AUG Roboflow v3 ROI crops with YOLO boxes for the
  single publisher class `Tas_Var`, mapped to `kidney_stone`; CC BY 4.0. The publisher
  image-level split put 88 publisher-test images in inferred acquisition sessions also
  represented in train or validation. The executed split therefore joined timestamp-
  inferred acquisition sessions (within 30 minutes) with confirmed pixel-near-duplicate
  groups before a 909 / 195 / 196 stratified re-split. No confirmed near-duplicate group
  crosses that executed split. Patient identifiers are unavailable, so the session rule
  is a leakage-control heuristic, not verified patient-level separation.
- Model: Faster R-CNN ResNet-50 FPN v2 (COCO-pretrained torchvision weights), one class,
  20 epochs, batch 4, min/max size 512/1024, no flips. Selected on validation AP50:
  epoch 1 (val AP50 0.779). Training 2,953 s.
- **Test (196 images, 402 reference boxes): COCO mAP@[.50:.95] 0.231; AP50 0.629;
  AP75 0.089; AR@100 0.360.** AP for large objects is undefined because this test set
  has no evaluable large-object stratum.
- Operating point chosen on validation (max F1 at IoU 0.5): score ≥ 0.85. On test:
  precision 0.742, recall 0.550, F1 0.631 (TP 221, FP 77, FN 181). Detector scores are
  not probabilities and are not calibrated.
- Checkpoint `artifacts/training/kidney_stone_detector-20261024T161540Z/model.pt`,
  SHA-256 `e9267f9a6e9fb36cc08fd27a888096209febf023ce2f140c5f7d38f6839b9fcb`.
- Limitations: augmented ROI slices from one public source, no external validation,
  no verified patient identifiers, no metric confidence intervals, and only slice/box
  detection—not patient diagnosis, stone burden, composition, or prognosis.

## Coronary angiography — ARCADE SYNTAX segmentation (`angiography_syntax_segmenter`)

- Data: ARCADE SYNTAX subset with 25 coronary-segment polygon classes, CC0 1.0
  (<https://zenodo.org/records/10390295>). Publisher splits kept: 1,000 / 200 / 300.
  Two pixel-confirmed transitive components cross publisher splits (6 images, including
  2 test images). Patient-level separation cannot be verified because identifiers are
  unavailable.
- Model: MONAI 2D U-Net (25 segment classes plus background), trained from scratch at
  512 × 512 for 40 epochs, batch 8. Selected on validation mean foreground Dice per
  image: epoch 18 (0.358). Training 1,166 s.
- **Test (300 images): mean foreground Dice per image 0.307 (95% CI 0.291–0.322);
  macro segment Dice 0.201; whole-vessel Dice 0.683 (0.665–0.699), IoU 0.535, and
  HD95 80.5 pixels at the model's 512 × 512 working resolution.** After excluding the
  2 cross-split-component test images (post-hoc n = 298), mean foreground Dice is 0.308
  and whole-vessel Dice is 0.683.
- Segment `10a` has no held-out reference mask, so its Dice is undefined. Segment `10`
  has only 14 supported test images and Dice 0.000; several other rare segments also
  have near-zero Dice. Aggregate vessel overlap must not be read as reliable 25-segment
  labelling.
- Checkpoint `artifacts/training/angiography_syntax_segmenter-20261024T170738Z/model.pt`,
  SHA-256 `3a3882071f72192edaec39a3cfd2449faf6d93f367d11dccf3455ba8824ab0a0`.
- Limitations: internal source only, no external or clinical validation, pixel distances
  are not millimetres, patient independence is unverified, and the duplicate-exclusion
  result is a post-hoc sensitivity analysis rather than a replacement test set.

## GI endoscopy — GastroVision, 27 classes (`gi_gastrovision_27class_classifier`)

- Data: `archive (17).zip`, GastroVision 27 publisher class folders (8,000 images),
  CC BY 4.0 (<https://api.osf.io/v2/nodes/84e7f/>). Group-aware stratified split:
  5,587 / 1,188 / 1,225 images; the test set contains 1,223 near-duplicate groups.
  Nineteen confirmed near-duplicate groups were kept within one split. No patient ids
  are supplied, so patient-level independence cannot be verified.
- This dataset is **not validation-ready** under the declared minimum of 20 samples per
  class. The run required explicit exploratory opt-in and used inverse-frequency class
  weights computed from the training split. Four classes are below the minimum:
  Angiectasia 17 total (4 test), Erythema 15 (3 test), Esophageal varices 7 (2 test),
  and Ulcer 6 (1 test).
- Candidates: ResNet-18 (val macro-F1 0.410) and EfficientNet-B0 (0.555), ImageNet
  weights, 8 epochs, AdamW + one-cycle, batch 48, 224 px. Selected: EfficientNet-B0.
  Temperature T = 1.117. Training 329 s for both candidates.
- **Exploratory test (n = 1,225): accuracy 0.737 (95% CI 0.713–0.761); macro-F1 0.553
  (0.507–0.589); balanced accuracy 0.622 (0.574–0.693); macro one-vs-rest AUROC 0.979;
  ECE 0.047 → 0.035 after temperature scaling; multiclass Brier 0.375.** Angiectasia
  and Ulcer each have test F1 0.000. The high macro AUROC does not override the tiny
  rare-class supports or failed rare-class operating performance.
- Checkpoint `artifacts/training/gi_gastrovision_27class_classifier-20261024T173442Z/model.pt`,
  SHA-256 `464986a86033a6415af2870ac26a75d06c787e86caf3b9f74b865e4f5ba757f9`.
- Limitations: `EXPLORATORY_ONLY`, severe class imbalance and unstable rare-class
  estimates, internal source only, no external validation, no verified patient-level
  split, and temperature scaling is not calibration for a clinical population.

## GI endoscopy — Kvasir-SEG polyp segmentation (`gi_kvasir_seg_polyp_segmenter`)

- Data: `archive (25).zip`, Kvasir-SEG: 1,000 polyp images with publisher binary masks;
  research and educational use only, no commercial use without written permission,
  citation required (<https://datasets.simula.no/kvasir-seg/>). The publisher's lists are
  kept: `train.txt` (880 images) is split group-aware into 748 training and 132 validation
  images (seed 20261024), and `val.txt` (120 images) is the frozen test set, evaluated
  once. The audit found 3 pixel-confirmed near-duplicate pairs, all inside the training
  list and kept within one split; no near-duplicate crosses splits. Patient identifiers
  are unavailable, so patient-level independence cannot be verified.
- Masks: the publisher's JPEG masks thresholded at 127 (compression noise along the edges).
- Model: MONAI 2D U-Net (32–512 channels, residual units), trained from scratch on RGB
  input with per-channel standardisation at 352 × 352; 80 epochs (fixed before training),
  batch 8, Dice + cross-entropy loss, AdamW with one-cycle 1e-3. Selected on validation
  mean Dice: epoch 54 (0.810). Training 1,131 s.
- **Test (120 images): polyp Dice 0.768 (95% CI 0.725–0.809), IoU 0.670, HD95 73.6 pixels
  at the model's 352 × 352 working resolution.** Every test image has a polyp, so no
  empty-mask convention applies.
- Independent re-score: the validation kit reproduced Dice 0.7679 and IoU 0.6696 from the
  saved masks (`docs/validation/models/gi_kvasir_seg_polyp_segmenter.kit_crosscheck.json`).
  Inference parity: the backend adapter reproduced the trainer's test masks on 20 sampled
  images (pixel agreement ≥ 0.9996, adapter-vs-trainer Dice ≥ 0.998 once the adapter used
  the evaluated bf16 autocast; ≥ 0.995 / 0.988 in fp32 before that correction).
- Context only (not identical conditions): Jha et al. 2021 (IEEE Access,
  doi:10.1109/ACCESS.2021.3063716, Table V) used the same 880/120 lists at 512 × 512 and
  report Dice 0.597 for a plain U-Net, 0.714 for ResUNet++, 0.821 for ColonSegNet and 0.876
  for a U-Net with an ImageNet ResNet34 encoder. Their 120 images served as validation;
  resolution, metric aggregation and training budgets differ.
- Relationship to Kvasir v2: the publisher states the images come from Kvasir v2, whose
  polyp class is part of the `gi_kvasir_v2_classifier` data. With the audit's
  near-duplicate rule (not crop-invariant, so a lower bound), 14 Kvasir-SEG test images
  match Kvasir v2 polyp images, 9 of them in the classifier's training split. Results of
  the two models are not independent evidence, and the classifier must not be evaluated on
  Kvasir-SEG images.
- Checkpoint `artifacts/training/gi_kvasir_seg_polyp_segmenter-20261025T080312Z/model.pt`,
  SHA-256 `a5a2c88dc5af67a8993210ca8a3d40ea79b9cd5e0a7cd5f422c1356828115c36`.
- Limitations: internal source only, no external or clinical validation, pixel distances
  are not millimetres, and patient independence is unverified.

## Haematology microscopy — C-NMC ALL vs normal (`hematology_cnmc_all_classifier`)

- Data: `archive (47).zip`, C-NMC 2019 cell images from TCIA, CC BY 3.0 with citation
  required. Dataset version `6d29f9139eccdb722b2b625f87c8d81360923eef0fb91e6ce7246055e8c1ba16`.
- Split: subject identifiers parsed from publisher filenames; subjects sharing a
  pixel-identical image were joined into clusters. Training/validation used an 85/15
  per-class split, and the publisher's labelled preliminary-phase set was frozen for
  test. Training subjects linked to that test set were removed. Counts were 8,157 / 1,430
  / 1,867 images; the test set contains 28 subject clusters.
- Candidates: ResNet-18 and EfficientNet-B0 with ImageNet initialization, selected only
  by validation macro-F1. EfficientNet-B0 was selected (0.821 vs 0.783). Training used
  inverse-frequency cross-entropy computed from training counts. Temperature scaling
  used only the validation split (T = 3.191).
- **Test (n = 1,867): accuracy 0.807 (95% subject-cluster bootstrap CI 0.659–0.894),
  macro-F1 0.790 (0.626–0.877), balanced accuracy 0.794 (0.657–0.871), macro AUROC
  0.867, and ECE 0.138 → 0.020 after temperature scaling.**
- Checkpoint `artifacts/training/hematology_cnmc_all_classifier-20261025T082713Z/model.pt`,
  SHA-256 `f5ea1fafc826ae524c8d335a5e32019243c58dcd0bda19ef0e9722823ca82736`.
- **Numeric-precision correction (2026-10-25).** The test split was scored under bfloat16
  autocast, but the backend adapter served the checkpoint in float32. Re-scoring the same
  frozen checkpoint and test images in float32 changed 84 of 1,867 predictions (accuracy
  0.787, macro-F1 0.771, AUROC 0.842); bfloat16 reproduced the reported metrics exactly.
  The adapter now runs classifiers and segmenters under the evaluated bfloat16 autocast on
  CUDA, and every output states its precision. Parity after the fix: 21/21 sampled images
  with the same top class, maximum probability difference 0.0008 (it was 0.135). CPU
  inference stays float32 and is labelled as differing from the evaluated configuration.
- Limitations: filename subjects are not independently verified patient identities;
  only 28 clusters contribute to uncertainty, producing wide intervals. This is an
  internal same-source cell-image result with no external or clinical validation, and
  the temperature-scaled score is not a probability calibrated for a clinical population.

## Cardiac cine-MRI — ACDC ventricular segmentation (`acdc_cardiac_mri_3d_unet`)

- Data: `archive (23).zip`, ACDC (CREATIS): 150 patients with end-diastolic (ED) and
  end-systolic (ES) volumes and reference masks for the RV cavity, myocardium and LV
  cavity. No licence text exists; the publisher states the data and ground truth remain
  publicly available and requires its citation for any use (Bernard et al., IEEE TMI 2018).
  **Local, non-commercial research training was authorized by the repository owner on
  2026-10-25** and recorded with that evidence in the dataset registry; the images and
  masks are not committed or redistributed.
- Split (manifest `c0fa24d113128f2d`): the publisher's 50 test patients are frozen;
  development patient055 is excluded because both of its images duplicate test patient118
  while the masks differ; the remaining development patients are split by patient into 84
  training and 15 validation patients (168 / 30 / 100 volumes). No patient or identical
  image or mask crosses splits.
- Model: 3-D U-Net (channels 32-256, residual units) trained from scratch on the native
  acquisition grid with non-zero z-score normalisation; 128 × 128 × 16 patches, batch 4,
  4 foreground-biased patches per volume, Dice + cross-entropy, float16 autocast; 60
  epochs (fixed before training), selected on validation mean case macro Dice: epoch 41
  (0.776). CUDA cross-entropy has no deterministic kernel, so the run used warn-only
  determinism (a rerun can differ slightly). The first attempt stopped at its first step
  under strict determinism and is kept, marked `FAILED`.
- **Test (50 patients, 100 volumes, evaluated once): mean case macro Dice 0.750 (95%
  patient-bootstrap CI 0.719–0.778); LV cavity 0.812 (0.771–0.848; ED 0.873, ES 0.751),
  myocardium 0.731 (0.698–0.758), RV cavity 0.707 (0.672–0.742; ED 0.784, ES 0.631).**
  Mean 3-D HD95: LV 53.7 mm, myocardium 58.6 mm, RV 81.6 mm.
- Cardiac indices from predicted vs reference masks (per patient, n = 50; voxel volume from
  the NIfTI header pixdim because the files' sform affine is unit-scaled):

  | Index | Reference mean | Bias (predicted − reference) | 95% limits of agreement | Mean absolute error | Pearson r |
  | --- | ---: | ---: | --- | ---: | ---: |
  | LV end-diastolic volume (mL) | 176.6 | +21.7 | −57.2 to +100.6 | 30.3 | 0.900 |
  | LV end-systolic volume (mL) | 98.6 | +24.6 | −56.8 to +105.9 | 30.4 | 0.901 |
  | LV ejection fraction (points) | 50.7 | −5.8 | −29.6 to +17.9 | 9.1 (6.5–11.9) | 0.852 |
  | RV end-diastolic volume (mL) | 171.5 | +40.4 | −85.4 to +166.1 | 52.0 | 0.756 |
  | RV end-systolic volume (mL) | 94.2 | +55.9 | −84.2 to +196.1 | 64.4 | 0.693 |
  | RV ejection fraction (points) | 46.6 | −13.2 | −42.6 to +16.2 | 16.6 | 0.602 |
  | LV myocardial mass (g) | 133.7 | +27.2 | −50.4 to +104.8 | 38.1 | 0.716 |

- Interpretation: every volume is overestimated and HD95 is large because predicted
  regions away from the heart are kept (no connected-component post-processing was
  prespecified; adding it now would be tuned on the test set). The limits of agreement are
  far too wide for any measurement use. Leading entries of the publisher's challenge
  reported substantially higher overlap and ejection-fraction agreement; this from-scratch
  baseline is not competitive with them.
- Checkpoint `artifacts/training/acdc_cardiac_mri_3d_unet-20261025T132755Z/best.pt`,
  SHA-256 `b18afcf66effbfd8c8db515958e798cb7b03f322b4a1da354d41edb5edc2d60e`; report
  `docs/validation/models/acdc_cardiac_mri_3d_unet.json` (`python -m ml_training.volumetric_report`).
  Registered `READY_UNVALIDATED` with `inference_input = volume_nifti`: evaluation evidence
  only, no upload inference path.

## ECG — PTB-XL 1.0.1, 5 diagnostic superclasses (`ptbxl_ecg_baseline`)

- Data: `archive (30).zip` (87,354/87,354 files verified on disk), CC BY 4.0 (`LICENSE.txt`
  in the dataset; PhysioNet). Trainer `ml_training/ecg.py` with the shared reader
  `ml_training/ptbxl.py`: all 42,862 files used were verified against the publisher's
  `SHA256SUMS.txt`, and every lead of every record against its WFDB header checksum and
  first sample (no `wfdb` package; reader tested on synthetic corrupt records).
- Labels: multi-label NORM, MI, STTC, CD, HYP aggregated from the 44 SCP statements with
  `diagnostic == 1`; 407 records without a superclass excluded (21,430 kept).
- Split: publisher folds 1–8 / 9 / 10 = 17,111 / 2,156 / 2,163 records from 14,834 /
  1,922 / 1,881 patients; **patient overlap asserted to be 0**.
- Model: compact 1D ResNet from scratch on 10 s, 100 Hz, per-lead standardised signals;
  40 epochs, AdamW + one-cycle, amplitude-scaling and noise augmentation; best
  validation epoch 11 (val macro AUROC 0.923) — later epochs overfit and were not used.
  Per-class Platt scaling and per-class max-F1 thresholds from fold 9 only. 92 s total.
- **Test (fold 10, n = 2,163 ECGs, 1,881 patients): macro AUROC 0.917 (95% patient-
  bootstrap CI 0.909–0.925); macro AUPRC 0.805; macro F1 at validation thresholds 0.734
  (0.717–0.750); mean ECE 0.027 → 0.015 after Platt scaling.**
- Per class (AUROC / AUPRC / sensitivity / specificity): NORM 0.938 / 0.913 / 0.93 / 0.79;
  MI 0.908 / 0.796 / 0.75 / 0.88; STTC 0.931 / 0.822 / 0.75 / 0.93; CD 0.908 / 0.822 /
  0.65 / 0.95; HYP 0.903 / 0.669 / 0.67 / 0.94.
- Context only (not identical conditions): Strodthoff et al. 2020 report macro AUROC
  about 0.93 for 1D CNNs on this task.
- Checkpoint SHA-256 `687f69a2ff1cb50dcd0c5a26759f2d2154090c71746518db150c7638d9efb067`.
  Registered as `ptbxl_ecg_baseline` (replacing the former `WEIGHTS_MISSING` placeholder),
  `inference_input = ecg_12lead`: evaluation evidence only — the ECG upload path does not
  run this model.

## Survival — Mayo PBC and heart failure (`pbc_mayo_survival_cox`, `heart_failure_survival_cox`)

Full design, metrics, calibration tables and limitations: `docs/forecast/PROGNOSTIC_VALIDATION.md`.
Both from UCI (CC BY 4.0): PBC cohort hold-out (312 trial patients develop, 104
non-randomized evaluate) gives Harrell's C 0.786 (0.709–0.854) and integrated Brier
0.105 vs 0.146 for Kaplan–Meier; heart failure (209 / 90 stratified split) gives C 0.671
(0.569–0.774) but no Brier skill (0.168 vs 0.158), so it is registered `EXPLORATORY_ONLY`.
Re-running either command reproduces the identical checkpoint hash.

## Not trained (with reasons)

| Task family | Reason |
| --- | --- |
| Brain MRI tumour (4 classes), brain CT haemorrhage | `LICENSE_BLOCKED`: source and terms not verifiable from the archives |
| Chest X-ray / lung CT | `LICENSE_BLOCKED` |
| Liver, kidney CT normal/tumour, other folders | `LICENSE_BLOCKED` or labels insufficient (`docs/data/DATA_READINESS_MATRIX.md`) |
| DICOM study ST000001 (archive 5) | `PRIVACY_REVIEW_REQUIRED` (real-looking birth date in headers) |
| MURA v1.1 (archive 60), EchoNet-Dynamic (archive 56) | `LICENSE_BLOCKED` (`PERMISSION_UNVERIFIED`): Stanford AIMI Research Use Agreement requires the user's own registration; the copies arrived as third-party downloads |
| KiTS19 (archive 24), LIDC-IDRI XML (archive 59) | `MISSING_IMAGES`: masks / annotations without the CT volumes |
| Bone fracture v4 (archive 58) | `NEEDS_REVIEW`: CC BY 4.0, but the 7-class label set mixes fracture labels with a non-fracture `humerus` class |
| Other supplementary tables and image sets (archives 26–57) | catalogued only; no licence verified from an official source (`docs/import/ARCHIVE_REPORT.md`) |
| Longitudinal trajectory / treatment-effect models | no repeated-measurement or causal dataset (`docs/forecast/PROGNOSTIC_VALIDATION.md`) |
