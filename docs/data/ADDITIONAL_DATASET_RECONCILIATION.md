# Additional dataset recommendation reconciliation

Date: 2026-10-25

This note reconciles the two additional dataset recommendation lists with the local
archive inventory, dataset task registry and model registry. It is a metadata and
provenance review, not a clinical validation or a new authorization to use data.

## Evidence reviewed

- All 108 ZIP files in `C:\Users\johnn\Downloads` had readable central directories.
- The numbered archive series is complete from `archive.zip` through
  `archive (60).zip`; archives 23-60 are the 38-file supplementary batch.
- `dataset_registry/imported.json` records 58 archives as
  `ALREADY_PRESENT_VERIFIED`, one as `EXTRACTED_VERIFIED` and three as
  `PARTIALLY_PRESENT`. For archives 24-26, partial presence concerns overwritten
  root-level files; the medical payload described below was inspected separately.
- `dataset_registry/tasks.json` is the current task-level evidence. The older
  path-level `dataset_registry/datasets.json` pre-dates the supplementary batch, so
  its MURA/PTB-XL presence flags were reconciled without changing its conservative
  training-readiness conclusion.

`NO_IDENTIFIERS_FOUND_IN_SAMPLED_METADATA` is a bounded scan result. It is not proof
of de-identification, consent, lawful processing or suitability for clinical use.

## Reconciliation

| Recommendation | Local evidence and actual labels | Rights and privacy | Current action |
| --- | --- | --- | --- |
| ACDC | Present in `archive_23`: 150 cine-MRI patient folders, 150 4-D volumes, 300 ED/ES phase volumes and 300 ground-truth volumes. Labels cover LV cavity, myocardium and RV cavity. The 3-D pipeline is implemented; only a blocked `WEIGHTS_MISSING` placeholder is registered. The publisher test cohort stays frozen, and one development patient is excluded because both phase images duplicate a test patient while their masks differ. | Public source and mandatory citation are recorded, but no explicit licence grant was found. Bounded metadata scan only. | Do not reacquire or train yet. Resolve explicit authorization, pre-register the ACDC-specific protocol, then execute and independently re-score a real run. |
| BraTS | No identifiable BraTS data. The sole BraTS-named ZIP member is a MONAI documentation image. Local brain MRI folders are 2-D glioma/meningioma/no-tumour/pituitary classification and are not BraTS segmentation data. | Local substitutes have unverified licences and no patient grouping. | Official acquisition is required only after a 3-D trainer is working on ACDC. |
| KiTS19 | `archive_24` contains 210 `segmentation.nii` masks and clinical JSON, but no paired `imaging.nii` volumes. Labels are kidney and tumour. | CC BY-NC-SA 4.0 is recorded; pseudonymous case IDs; bounded metadata scan only. | Acquire the exact official CT volumes matching the existing cases. This is the highest-value next imaging acquisition. |
| Kvasir-SEG | Present in `archive_25`: 1,000 image/mask pairs with binary polyp masks. A research-only MONAI U-Net checkpoint and held-out report are registered. | Research/education use; commercial use needs written permission; patient IDs unavailable. | Do not reacquire. Its images originate in Kvasir v2, so Kvasir-SEG and Kvasir-v2 results are not independent evidence. |
| Pancreas CT | No verified pancreas CT segmentation set. `archive_09` contains 1,411 JPEGs under `normal` and `pancreatic_tumor`, but modality, provenance and patient grouping are unverified and there are no masks. The TotalSegmentator repository contributes only a test-reference pancreas mask. | Archive 09 has no verified licence or full privacy review. | Keep the raster set blocked. Acquire an official paired CT/mask release if pancreas segmentation remains required. |
| TotalSegmentator / BTCV | `archive_26` is TotalSegmentator software plus test references, not its training data. BTCV appears only in a MONAI documentation image. | The software licence does not grant rights to absent training data or weights. | Defer acquisition until the common volumetric trainer is proven on ACDC. |
| LIDC-IDRI | `archive_59` contains 1,319 radiologist XML files and no CT images. The XML supplies nodule ROIs/coordinates, inclusion and nodule characteristics, not pixels. | Local licence is unverified; identifiers in technical metadata require governance review. | Acquire the matched official CT series and verify terms before building the annotation-to-volume join. |
| LUNA / NIH chest X-ray | No identifiable LUNA or NIH ChestX-ray dataset was found in the 108 ZIPs or current task registry. Existing lung folders are different, licence-blocked collections. | Not applicable locally. | Do not infer localization labels from an image-level classification release. Select one pulmonary task and obtain its official release and label definition. |
| MURA | Present in `archive_60`: 40,009 upper-extremity radiographs in 14,863 studies with study-level normal/abnormal labels. MURA does not supply fracture boxes or masks. | Individual Stanford registration/agreement is not demonstrated by the third-party ZIP; `PERMISSION_UNVERIFIED`. | Do not reacquire or train until the user documents their own permission. Reconcile the stale model placeholder before any run. |
| Bone fractures | `archive_58` contains two identical copies of 4,148 X-rays with YOLO boxes. The seven classes mix fracture labels with a non-fracture `humerus` class. | CC BY 4.0 is recorded; patient grouping is unavailable. | Deduplicate, clinically approve the taxonomy and audit split leakage before training. |
| PTB-XL | Present in `archive_30` and already evaluated with a registered research checkpoint. Labels are five diagnostic superclasses: NORM, MI, STTC, CD and HYP. Publisher folds are patient-disjoint as recorded. | CC BY 4.0; publisher hashes checked; research-only, single-source evidence. | Do not reacquire. External validation and an input adapter are separate gaps. |
| Annotated clinical reports | `nbme_train.csv` has 14,300 feature-span rows over 1,000 note histories and 143 features, with annotation text and character locations populated. This supports feature-span extraction only. MTSamples is unannotated. RadGraph repository test files contain report inputs and saved model-generated regression outputs, not independently adjudicated gold labels. | NBME competition terms, derivative provenance and a full privacy review are unresolved. The RadGraph software licence does not establish report-text rights. | Keep NBME blocked until those checks pass. Acquire a lawful independently adjudicated report corpus for assertion, relation, radiology-graph or laboratory extraction evaluation. |

## Acquisition order

1. Obtain the official KiTS19 CT volumes matching the 210 local masks. The common
   volumetric software path is now operational on a generated fixture; acquisition and
   any training still require dataset-specific rights, pairing and protocol review.
2. Obtain a lawful, independently adjudicated clinical-report corpus matched to the
   intended assertion/relation/laboratory tasks. NBME can only cover feature spans.
3. Obtain the matched LIDC-IDRI CT series for the local XML annotations.
4. Consider BraTS or BTCV/TotalSegmentator data only after the common volumetric
   pipeline has passed geometry, leakage and held-out evaluation checks.

ACDC, Kvasir-SEG, PTB-XL, MURA and the fracture export are already present and should
not be downloaded again. Presence alone does not remove their recorded rights,
privacy, leakage, validation or task-scope blockers.
