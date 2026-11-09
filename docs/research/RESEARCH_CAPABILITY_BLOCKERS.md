# Research capability blockers (2026-10-30, updated 2026-11-06)

> Historical snapshot: current runtime, dependency migration, completed liver manifest, tests, image findings and remaining work are updated in [Priority execution, 9 November 2026](../development/PRIORITY_EXECUTION_2026-11-09.md). Earlier blockers and counts below must be read in their original dated context.

What the universal directive asks for that does **not** work today, and the exact prerequisite each needs.
Statuses: `NOT_IMPLEMENTED` (no code path), `BLOCKED` (code could run; data, licence, weights or a
decision is missing), `NOT_VALIDATED` (runs, but only internal or no evaluation). Facts come from
`dataset_registry/tasks.json` (licence and task audit), `model_registry/models.json`, and runs recorded in
`docs/implementation/REAL_IMAGE_FAILURE_MATRIX.md`.

## New specialty models (milestone M5)

Done since 2026-10-31:

- **MURA upper-limb radiograph abnormality** (`mura_study_baseline`): trained after the owner confirmed the Stanford AIMI
  agreement (2026-10-31). EfficientNet-B0 selected on validation; on the publisher's validation split as the held-out
  test (1,199 studies, 783 patients, none in training) study-level AUROC 0.898 (95% CI 0.880–0.917), Cohen's kappa 0.677
  (0.632–0.718). Runs on uploads behind its applicability gate, which lets 95% of coronary angiograms through.
- **CT organ segmentation** (`ct_totalsegmentator_v2`, third-party, Apache-2.0): TotalSegmentator v2 weights installed
  with the owner's approval. Local external check on 60 randomly sampled LUNA16 CTs (CC BY 4.0): lung Dice 0.974
  (95% CI 0.972–0.975) against LUNA16's published lung masks (agreement, not manual ground truth).

Remaining candidates:

| Candidate | Local data | Blocker | To unblock |
| --- | --- | --- | --- |
| Brain MRI tumour (BraTS-type) | Now `MedTwin_Datasets/Brain_Tumour_MSD` (see "Brain tumour" below); the older `brain-mri-tumor-4class-a/b`, `brain-tumor-ct-mri` stay unlicensed | Superseded by the MSD release | — |
| Brain CT haemorrhage | `RSNA_PNG/rsna-ich-png.zip` (RSNA ICH training set as PNG; the owner confirmed it is the licensed download, 2026-11-04) | Done: `brain_ct_rsna_ich_classifier`, held-out AUROC 0.969–0.992 per subtype, study-level 0.980; slice-level only, epidural weak at its F1 threshold | Neighbouring-slice context, external validation |
| Brain ischaemic stroke (MRI) | `MedTwin_Datasets/Stroke_ISLES2022` (ISLES 2022, CC BY 4.0, found 2026-11-05) | Done: `brain_mri_stroke_lesion_segresnet`, held-out Dice 0.752 (95% CI 0.666-0.822) on 38 patients, lesion sensitivity 0.55; small lesions weaker; same centres as training | External validation; stroke on CT (the local stroke CT sets have no stated licence) |
| Brain tumour (glioma, MRI) | `MedTwin_Datasets/Brain_Tumour_MSD` (MSD Task01, CC BY-SA 4.0, found 2026-11-05) | `brain_mri_glioma_segresnet` published 2026-11-06: 73 held-out patients, whole tumour Dice 0.908 (0.890-0.923), tumour core 0.856, enhancing tumour 0.802; serving parity 73 of 73 accepted, 418 voxels differ in total (0.005 % of foreground); gliomas only | Metastases and other tumour types need their own licensed labels |
| Brain infection; chest infection beyond the third-party CXR scores | `MedTwin_Datasets/Tuberculosis/NLM_data_server` (NLM Shenzhen 662 + Montgomery 138 radiographs, downloaded 2026-11-06 from data.lhncbc.nlm.nih.gov with per-file MD5 checks; the Open-i links were down for maintenance) | No brain-infection data at all. TB: terms read from the publisher's read-me files (research group use, no redistribution, citation); `scripts/register_nlm_tb_dataset.py` registers the task with near-duplicate-aware splits; classifier `cxr_tuberculosis_nlm_classifier` queued for training (GPU queue 4) | Held-out results when training ends; the local pneumonia copy still carries no licence text |
| Coronary angiography vessels (DeepSA) | Unused source/checkpoints moved out of the project on 2026-11-06; see `docs/data/PUBLIC_DATA_ACQUISITION_2026-11-06.md` | No published licence; no model enabled | An appropriately licensed implementation and weights would be needed to revisit this candidate |
| Lung nodules (CT) | LIDC-IDRI subset: 300 patients (one annotated CT series each, 28 GB, CC BY 3.0) downloading from the TCIA NBIA API since 2026-11-06 to `C:/MedTwin_Datasets/LIDC`; reader XML (`LIDC-XML-only.zip`) downloaded | `scripts/prepare_lidc_dataset.py` writes NIfTI volumes and 50 % reader-consensus nodule masks (checked on two patients: solid nodule median -33 HU inside against -835 HU around; ground-glass nodule -681 against -802); segmenter `ct_lung_nodule_segresnet` queued after the download (GPU queue 4) | Held-out results when training ends |
| Liver / pancreas CT | MSD Task03 Liver and Task07 Pancreas (CC BY-SA 4.0), download approved by the owner on 2026-11-06 and in progress; the older `liver-ct-volumes` stays unlicensed | CT pipeline ready (`--intensity ct`: Hounsfield window from training foreground, HU-percentile input gate; tested on synthetic CT); training waits for the archives | Finish the downloads, register the archives, train |
| Kidney tumour (KiTS19) | 210 original masks plus all 210 official CTs acquired and hash-verified by 2026-11-07 (`dataset_registry/public_acquisition.json`, 20.02 GB CT; CC BY-NC-SA 4.0). All paired shapes/affines match (`artifacts/audits/kits19-pairing-2026-11-07.json`) | A usable single-root paired-volume manifest and label/protocol checks are still required | Stage paired masks/volumes and prepare the patient-grouped volumetric manifest before training; the downloader does not train or activate a model |
| Fractures (radiographs) | `bone-fracture-roboflow-v4` (CC BY 4.0, verified) | Owner decision 2026-11-06: one 'fracture' class, the 'humerus' anatomy class excluded, one archive copy; YOLO polygons are read as their boxes (they had been dropped). Training (`bone_fracture_detector`) | Held-out results when training ends; no patient IDs, so independence is near-duplicate grouping only |
| EchoNet-Dynamic | present locally | Owner confirmed the Stanford AIMI agreement on 2026-11-06. Ejection-fraction model (`echonet_ef_r2plus1d`, R(2+1)-D from random initialisation) queued for training; serving path, input gate and applicability reference built and tested | Held-out results when training ends |
| Otoscopy, fetal ultrasound, lymphoma histology | Moved out of the project on 2026-11-06 (`docs/research/DATASETS_MOVED_OUT_2026-11-06.md`; restorable) | Licence `UNVERIFIED` | Original source and licence |

## Capabilities by area

| Area | Status | Missing prerequisite |
| --- | --- | --- |
| Endoscopy other than GI stills (bronchoscopy, cystoscopy, ureteroscopy, laparoscopy, arthroscopy, hysteroscopy, laryngoscopy, colposcopy, EUS, thoracoscopy) | NOT_IMPLEMENTED | Licensed, labelled datasets per scope; no model registered |
| Endoscopy and surgical video (frame timeline, tracking) | NOT_VALIDATED (since 2026-11-05) | MP4/AVI uploads are decoded with OpenCV; frames sampled at an interval are measured (brightness, dark share, sharpness) and each is scored by a still-image endoscopy model after that model's own applicability check, shown as a timeline with the frame and its mask. Since 2026-11-06 marked regions are linked between sampled frames (box overlap, one-frame gaps) and classification gets runs of the same top class; no smoothing. None of it is evaluated: procedure-separated video labels are needed |
| Capsule endoscopy | NOT_IMPLEMENTED | Labelled capsule dataset |
| GI stills | NOT_VALIDATED | Internal held-out results only (Kvasir v2, GastroVision, Kvasir-SEG); polyp segmenter coverage limited by its applicability gate |
| Chest radiograph lesion boxes | Attention marks measured, no detector (since 2026-11-05) | The third-party classifier's Grad-CAM peak and attention region are drawn and were measured on the 984 NIH ChestX-ray14 radiologist boxes: the peak fell inside the box 26.4% of the time (95% CI 23.6-29.3%; a random point 7.5%), from 69% for cardiomegaly to 2% for pneumothorax (below chance). A trained lesion detector needs a larger box-labelled set (e.g. VinDr-CXR, credentialed) |
| Coronary angiography | NOT_VALIDATED | Stenosis detector AP50 0.203; SYNTAX segment Dice 0.307; no automatic SYNTAX score |
| Kidney-stone CT slices | NOT_VALIDATED | Internal AP50 0.629 only |
| Cardiac cine MRI | NOT_VALIDATED | Internal ACDC test only. Scanner series: see "Cardiac MRI from scanner series" below |
| Whole-body CT organ masks (TotalSegmentator) | NOT_VALIDATED | Installed (fast 3 mm and full 1.5 mm); local check covers lungs only (LUNA16); other organs carry the publisher's evaluation only |
| Musculoskeletal radiographs (MURA) | NOT_VALIDATED | Internal held-out test only (publisher's validation split); upper limb only; single views less reliable than whole studies |
| Brain MRI lesions | NOT_VALIDATED (since 2026-11-05) | Ischaemic stroke lesions (ISLES 2022) and glioma sub-regions (MSD BrainTumour): internal held-out tests only, masks per slice and patient-derived 3-D surfaces, organ-level link to the brain atlas after review. Brain haemorrhage is the RSNA slice classifier (no location) |
| Lung, liver, pancreas, prostate, breast, thyroid, dermatology, ophthalmology (fundus, OCT), dental, ENT, nuclear medicine models | NOT_IMPLEMENTED | Licensed labelled data per task (see M5) |
| Digital pathology whole-slide images | Viewing only (since 2026-11-06) | SVS, NDPI and tiled TIFF uploads read tile by tile (pyramid, microns per pixel, full-resolution regions, a colour-rule tissue grid). No model: slide-level labels with a licence are needed |
| EEG | NOT_IMPLEMENTED | EDF reader and a labelled seizure set with licence |
| ECG from photographs or printed tracings | BLOCKED by design | The PTB-XL model takes digital signals only |
| Clinical NLP accuracy | NOT_VALIDATED | An expert-annotated, de-identified report corpus. Secondary tools now run beside the rules: scispaCy (WSL, on by default where installed), medSpaCy ConText (agreement with the rules recorded per report), RadGraph-XL (imaging-report observations with anatomy), MedCAT (integration only) |
| MedCAT concept linking | BLOCKED | Installed (MedCAT 2.3.0, WSL); the only model pack present is the 2-concept example. Needs a UMLS or SNOMED CT model pack (licensed vocabularies) via `MEDTWIN_MEDCAT_MODEL_PACK` |
| Lab-report extraction accuracy | NOT_VALIDATED | A gold-standard annotated lab-report set with adjudication |
| Image-to-atlas registration (L2 spatial, L3 on the atlas) | BLOCKED | Patient CT/MRI with landmarks and a validated transform; today findings link to organs schematically (L1) |
| Patient-derived 3-D surfaces | Research view only | Available for volumetric runs (cardiac MRI and now CT organs) in the scan's own voxel frame; not registered to the atlas |
| Multimodal fusion | NOT_VALIDATED (since 2026-11-05) | One fusion model runs: 12-lead ECG + age and sex (PTB-XL, intermediate fusion), age/sex from the request or the case's reviewed demographics. On 2,163 held-out records it did not beat the same ECG network alone (macro AUROC 0.920 vs 0.918, paired difference +0.001, 95% CI -0.001 to +0.004). Image + report + laboratory fusion still needs paired data with shared outcomes (e.g. MIMIC-IV + MIMIC-CXR, credentialed) |
| Forecasting and treatment effects | BLOCKED | Longitudinal outcome data and a defined estimand; Prognosis Studio shows the missing inputs. No local dataset has repeated measurements with later outcomes |
| Reviewer mask editing (brush, polygon) | IMPLEMENTED (2-D since 2026-11-05; polygons and volumes since 2026-11-06) | Brush, eraser and polygon fill/cut on a 2-D run's mask; volumetric runs are corrected one axial plane at a time with the corrected volume per structure. Corrections are separate REVIEWER_CORRECTION layers linked to the run (the run is unchanged) |
| Reference boxes for detection runs | IMPLEMENTED (since 2026-11-06) | JSON or YOLO boxes attached as a GROUND_TRUTH layer with a declared origin; per-image one-to-one matching at IoU 0.5 against the run's boxes above its threshold |
| Two models on the same image | IMPLEMENTED (since 2026-11-06) | Agreement between two stored runs (mask Dice, box matching, class or label agreement, volume differences) with side-by-side views; neither run is treated as ground truth |
| Neighbouring-slice haemorrhage model (RSNA 2.5-D) | Trainer and serving implemented; training queued (GPU queue 3) | `ml_training/rsna_ich_25d.py` stacks the slice below, the slice and the slice above (ordered by z; 99.9 % of these neighbours are also adjacent in the archive's own numbering), same patient split as the single-slice model, paired comparison on the same test slices. The PNG export window was measured: width exactly 80 HU with truncation (79 reachable grey levels); level 40 HU estimated from tissue peaks (`docs/validation/RSNA_PNG_WINDOW_ESTIMATE.md`). Serving runs on an assembled head CT DICOM series, windowed the same way, with per-slice applicability checks. External test: CQ500 (490 head CT DICOM scans with three radiologists' reads, CC BY-NC-SA 4.0, evaluation only) approved and downloading on 2026-11-06; `scripts/evaluate_head_ct_cq500.py` runs both models through the serving path and scores scans against the majority read (on the first 5 scans every slice passed the applicability gate) |
| Cardiac MRI from scanner series | NOT_VALIDATED (since 2026-11-06) | Runs on an assembled cine stack (a phase is chosen when the series holds several). Checks: MR, double-oblique slice normal, at least 6 slices, the requester's attestation of view and phase. The development frames carry no orientation, so the model runs under all 16 axis conventions; the chosen one must put the right ventricle anterior-right of the left ventricle in the series' patient coordinates, with a shrinking left-ventricle area along the slices and the development ventricle layout. On 98 held-out ACDC frames with simulated scanner geometry: 91 accepted, mean macro Dice 0.750 against 0.753 with the publisher's convention (`docs/validation/CARDIAC_SCANNER_SERIES.md`). No real scanner series has been evaluated |
| Credentialed data (MIMIC-IV, MIMIC-CXR, VinDr-CXR) | BLOCKED (personal credentialing) | PhysioNet credentials the person: CITI training, a reference and signed agreements. A research summary is drafted in `docs/access/PHYSIONET_RESEARCH_SUMMARY_DRAFT.md`; nothing was submitted |
| Scan formats for the research models | IMPLEMENTED (since 2026-11-06) | 2-D models take DICOM frames (VOI or the model's declared window, MONOCHROME1 inverted, colour decoded, frame choice for multi-frame files, Modality tag checked); volume models take NIfTI, NRRD and single-file MetaImage, and CT models take DICOM series reoriented exactly into the development orientation. NRRD/MetaImage headers that point at another file are refused (they would have let an upload read any local file) |
| Independent Codex review | Available again from 2026-11-04 16:21 | Codex reported its usage limit on 2026-10-30 |

## Third-party model setup

- TotalSegmentator, nnU-Net, RadGraph: `scripts/setup_third_party_models.ps1` (main `.venv`, existing packages held at
  their versions; `backend/requirements-third-party.txt`). Weights: `artifacts/third_party/totalsegmentator/weights`
  (v2.0.0 'total' parts 291–295, fast 297 and the 6 mm crop model 298 that TotalSegmentator fetched itself, 1.49 GB) and
  `artifacts/third_party/radgraph` (radgraph-xl, MIT, 416 MB download). TotalSegmentator's usage statistics are off.
- medSpaCy and MedCAT: `scripts/setup_clinical_nlp_wsl.sh` (WSL `~/.medtwin/venv-clinical`); scispaCy:
  `scripts/setup_nlp_wsl.sh` (`~/.medtwin/venv-nlp`). Switches: `MEDTWIN_SCISPACY`, `MEDTWIN_CLINICAL_NLP`,
  `MEDTWIN_RADGRAPH` (`auto` by default; `off` in tests and wherever the tools are not installed, such as Vercel).
