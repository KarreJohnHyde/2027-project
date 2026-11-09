# Multimodal training resources — 7 November 2026

The owner requested suitable GitHub/Kaggle datasets, model files and dependencies for 2D training, testing, detection/localization, multimodal fusion and 2D/3D work. This pass selects complementary resources for those tasks and reuses existing data. It is a bounded acquisition plan, not a claim to download every medical dataset or finish every model in the project.

## Verified results from this pass

- **Installed:** 110 research dependencies added, 292 distributions total; all 182 previous versions unchanged. `uv pip check` passes. The exact add-on pins are in `backend/requirements-multimodal-lock.txt`.
- **Completed data/model files:** VQA-RAD's 315 images and source QA/read-me files passed publisher checksum verification. The prepared manifest contains 2,248 QA rows referencing 314 images, with 1,537/366/345 questions in the image-grouped train/validation/test split. One supplied image is not referenced by the QA JSON. BiomedCLIP's 783,705,670-byte checkpoint, configuration and tokenizer files are also downloaded and hash-verified.
- **Paired clinical-image data prepared:** PAD-UFES-20 is downloaded, checksum-verified and extracted. Its manifest joins all 2,298 images to 1,373 patients and six diagnoses. The generated split has no patient or identical-image cross-split overlap. Its 21 metadata features exclude diagnosis and biopsy indicators; preprocessing/encoding must still be fitted on the training split when a fusion experiment is implemented.
- **Existing queue completed:** all 217 earlier artifacts (210 KiTS19 CTs and seven MedMNIST NPZs) are verified. All 210 KiTS CT/mask pairs have matching NIfTI shapes and affines. This header check does not establish label quality or complete a volumetric training manifest.
- **Paired 2D/3D data completed:** all 1,124 selected DeepFluoro files passed pinned checksum verification. The six CT/mask pairs have matching shapes/affines, and all 366 X-rays have adjacent pose files and multichannel masks. The download worker does not unpickle poses; a separate read-only check safely loaded one pose dictionary with `weights_only=True` and observed a `[1,4,4]` pose tensor plus an intrinsics dictionary. Coordinate/protocol validation is still required before registration evaluation.
- **CBIS-DDSM completed:** the archive is checksum-verified and all 10,237 JPEG files and six CSV tables are extracted. The publisher tables have 31 patients shared between train/test. A separate 3,568-case metadata manifest now keeps every publisher-test patient held out and assigns the remaining patients to train/validation, producing 2,436/345/787 train/validation/test cases with zero patient overlap. Original tables are unchanged. Pixel/crop/ROI coordinate correspondence remains unvalidated, so detection training is still gated on that audit.
- **Software checks passed on CUDA:** differentiable image warp, labelled-volume resampling, DICOM pixel-to-reference geometry, lossless JPEG-LS and JPEG 2000 round trips, a synthetic native-frame GLB mesh, and differentiable DRR projection with finite pose gradients. The verified pretrained BiomedCLIP checkpoint was loaded locally and produced finite 512-dimensional image/text features without network access. No clinical performance was measured.
- **Tests:** all 15 acquisition/extraction/grouping checks and 38 existing DICOM/scan/surface/ECG-fusion regressions passed (53 total). Synthetic execution is not clinical validation.

All **1,452 newly selected artifacts / 12.91 GB** have now downloaded and passed their pinned checksums. Preparation of the three datasets in the main queue passed. The earlier **LIDC subset download has resumed**, with CQ500 and MSD liver queued after it subject to storage headroom. Completion of those older cohorts is tracked independently; this report does not claim that they are finished.

Evidence: `artifacts/audits/multimodal-install-2026-11-07.json`, `multimodal-stack-2026-11-07.json`, `kits19-pairing-2026-11-07.json` and `_derived/datasets/multimodal/vqa-rad/preparation.json`. These local artifacts/derived manifests are Git-ignored.

## New acquisition

`dataset_registry/multimodal_resources.json` records **328 artifacts totalling 9,721,886,020 bytes (9.72 GB)**, all now downloaded and checksum-verified. The manifest includes source versions/revisions, publisher checksums, licences and task limitations. Its worker continues with the older CT cohort downloads after preparing the new resources.

A separate paired 2D/3D acquisition, `dataset_registry/deepfluoro_resources.json`, adds **1,124 files / 3,190,645,471 bytes (3.19 GB)**. Together the two new manifests contain **1,452 files / 12.91 GB**. DeepFluoro is completed and verified independently of the other queue.

| Resource | What is acquired | Supported work | Important boundary |
| --- | --- | --- | --- |
| [PAD-UFES-20 publisher](https://data.mendeley.com/datasets/zr7vgbcyr2/1), [Kaggle copy](https://www.kaggle.com/datasets/mahdavi1202/skin-cancer) | Original 2,298 smartphone clinical skin images and patient/lesion attributes, version 1 | Paired 2D image + clinical-table fusion; image-only comparison arm | CC BY 4.0. Split by patient and group duplicated image content. No lesion masks, 3D coordinates or longitudinal outcomes. Not the restricted PAD-UFES-20+ release. |
| [VQA-RAD, original OSF release](https://osf.io/89kps/) | 315 published radiology images, original QA JSON and read-me | Image/text/question-answer fusion and retrieval research | OSF project licence verified as CC0 1.0. Teaching images are not scanner volumes or an outcome-linked clinical report corpus. Patient independence is not established. |
| [CBIS-DDSM Kaggle release](https://www.kaggle.com/datasets/awsaf49/cbis-ddsm-breast-cancer-image-dataset) | Version 1 mammography JPEGs, clinical tables, crop/ROI information | 2D classification, image/table fusion and lesion-localization preparation | Kaggle distribution declares CC BY-SA 3.0; retain original TCIA attribution and terms. Full-image/crop/ROI correspondence and coordinates require checking before box/mask training. This conversion is not a native 3D mammography release. |
| [Microsoft BiomedCLIP](https://huggingface.co/microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224) | Pinned encoder checkpoint, model configuration, tokenizer, vocabulary, model card, MIT licence and the text-backbone architecture configuration | Biomedical image/text feature extraction and contrastive/retrieval/fusion experiments | A pretrained encoder is not an activated MedTwin lesion detector or clinically validated model. Task-specific training and evaluation remain separate. |
| [DeepFluoro original project](https://github.com/rg2/DeepFluoroLabeling-IPCAI2020), [permissioned DICOM remix](https://huggingface.co/datasets/eigenvivek/xvr-data/tree/main/deepfluoro) | Paired CTs, real fluoroscopy DICOM, 3D masks, packed multichannel 2D masks, fiducials and pose/calibration metadata for six cadaveric pelvic specimens | Actual paired 2D/3D localization and registration research alongside DiffDRR | The directory's data licence is CC BY-NC 4.0. Original GPL training code is not installed. Split by specimen and reconcile coordinate conventions before evaluating registration; this is not a general clinical cohort. |

The DeepFluoro mirror is documented by its author as a DICOM remix hosted with permission. Its own `deepfluoro/LICENSE` declares CC BY-NC 4.0; the mixed repository's root CC BY-NC-ND metadata was not substituted for this per-dataset licence. Direct JHU archive endpoints returned HTTP 403. Only the DeepFluoro directory is selected, excluding its older single-label 2D masks in favour of the more informative packed multichannel masks. Every file is checked against pinned LFS SHA-256 or Git-blob metadata. Downloaded `.pt` pose objects are not automatically unpickled. The worker validates CT/mask geometry and X-ray/pose file joins after acquisition; a coordinate adapter and registration protocol remain necessary.

The PAD publisher page was readable for source/rights verification, but its direct download endpoints returned HTTP 403. The reviewed public Kaggle copy was used under the publisher's CC BY 4.0 terms. An incorrectly cited Zenodo record encountered during research was rejected because its title/content did not match PAD-UFES-20; unrelated data were not downloaded.

OSF and Hugging Face artifacts carry published SHA-256 or pinned Git-blob integrity. Kaggle's public Google Storage responses provide CRC32C over the ZIP; this transport checksum is checked and a local SHA-256 is also recorded. CRC32C is a corruption check, not a publisher-signed cryptographic provenance assertion. No Kaggle credentials or account creation was needed.

## Existing resources reused

| Need | Retained project resources |
| --- | --- |
| 2D classification | Kvasir v2, GastroVision, C-NMC, MURA, RSNA ICH, NLM TB and the seven small MedMNIST benchmarks |
| 2D detection/localization | ARCADE stenosis/SYNTAX annotations, fracture YOLO labels, kidney-stone boxes, Kvasir-SEG masks; new CBIS-DDSM annotations after correspondence checks |
| Signal + clinical attributes | PTB-XL and the existing ECG + age/sex fusion model; its held-out comparison did not show an overall AUROC improvement over ECG alone |
| Multi-channel volumetric fusion | Existing ISLES DWI/ADC/FLAIR and MSD BrainTumour MRI channels; channels are paired within a subject |
| 2D scanner slices to 3D volumes/surfaces | DICOM series/NIfTI readers, native spacing/orientation handling, LIDC CT + reader XML, CQ500, MSD liver/pancreas, ACDC and the ongoing KiTS19 imaging acquisition |
| Meshes and spatial transforms | Existing SimpleITK, NiBabel, scikit-image and Trimesh; new TorchIO, Kornia and highdicom; existing browser Three.js renderer |

Classification labels alone do not supply lesion coordinates. A collection of unrelated 2D photographs or PNG slices cannot establish patient-specific 3D anatomy. Native scanner geometry or paired, calibrated projections and volumes are required for spatial reconstruction/registration work.

The earlier KiTS19 queue remains independent. After downloading the new resources, `--resume-existing` attempts the durable LIDC, CQ500 and MSD liver download scripts if they are not already running and sufficient storage remains. It does not restart GPU trainers. Older scripts' exit codes are recorded as requiring log review, rather than promoted to proof of complete verified cohorts.

## Optional research dependencies

`backend/requirements-multimodal.txt` is the local research requirements entry point. The install is constrained by the 182-package pre-existing environment snapshot; no existing package version may change.

| Package | Purpose / primary source |
| --- | --- |
| TorchIO 1.2.1 | Spatially consistent volume/image/label transformations and patch sampling — [official source](https://github.com/TorchIO-project/torchio) |
| Kornia 0.9.0 | Differentiable image geometry and transformations — [official source](https://github.com/kornia/kornia) |
| Trimesh 5.1.1 (already installed) | Mesh handling and GLB export — retained existing version |
| highdicom 0.28.2 | DICOM spatial abstractions and segmentation-object building blocks — [official source](https://github.com/ImagingDataCommons/highdicom) |
| pylibjpeg 2.1.0, libjpeg 2.5.0, openjpeg 2.6.0 | Compressed DICOM pixel-codec support; highdicom also requires pyjpegls |
| OpenCLIP 3.2.0 | Image/text encoder construction and research training utilities — [official source](https://github.com/mlfoundations/open_clip) |
| DiffDRR 0.6.1 | Differentiable CT-to-radiograph projection and 2D/3D registration research — [official source](https://github.com/eigenvivek/DiffDRR) |
| google-crc32c | Verify the checksum supplied by Kaggle's public Google Storage response |

OpenCLIP 4.2.1 was rejected because it requires a newer `timm`; 3.2.0 preserves the project's `timm` 1.0.22 and GPU framework locks. Trimesh was already installed and was retained. Packages are installed from their official published distributions, which link to their GitHub sources; redundant arbitrary source checkouts are not needed.

DiffDRR upstream requires `pyvista[all]`, so its rendering/notebook dependencies are installed as dependencies. Installing them does not start Jupyter or expose a new server. This is an optional research environment expansion, not an increase in the minimal web deployment dependencies. DiffDRR projects an existing volume; it does not recover ground-truth 3D anatomy from an arbitrary single image.

## Automatic preparation and software checks

`scripts/prepare_multimodal_resources.py` runs after artifact acquisition:

- Extracts ZIPs with path/link/size/space guards and ZIP CRC checks; differing existing files are not overwritten.
- Joins PAD images to their metadata, verifies the original 2,298-row count, groups by patient and exact image content, and writes local research JSONL manifests. Diagnosis/biopsy fields are excluded from the feature whitelist. The image/tabular fusion trainer and experiment protocol still need implementation.
- Joins VQA questions to images and keeps all questions for identical image content within one research split. This does not establish patient independence.
- Extracts CBIS-DDSM, inventories its clinical tables and original patient splits, and writes a separate patient-disjoint case metadata manifest. All original test patients stay held out, including their training-table cases; remaining patients are divided into train/validation. No boxes are invented from unverified crop coordinates.

Derived files go to `_derived/datasets/multimodal` (Git-ignored). Raw 2D datasets stay on C:; the paired DeepFluoro data use `D:\project\MedTwin_Datasets\DeepFluoro`, and model files use `artifacts/third_party/biomedclip` on D:. No new checkpoint is added to the application's clinical model registry.

`scripts/verify_multimodal_stack.py` provides synthetic, offline software checks: image warping; volume spacing and label resampling; lossless DICOM codec round trips; a mesh/GLB export; differentiable DRR projection/pose gradients; and 512-dimensional image/text encoder outputs. Its `--require-pretrained` option refuses to claim a pretrained check if the local checkpoint is still downloading. Execution results belong in `artifacts/audits/multimodal-stack-2026-11-07.json` only after the check actually succeeds.

## Operation and live status

Resume from `D:\project`:

```powershell
.\.venv\Scripts\python.exe -u scripts\acquire_multimodal_resources.py --run --resume-existing
.\.venv\Scripts\python.exe -u scripts\acquire_deepfluoro.py --run
```

Do not start another worker while one is running; a process lock prevents duplicate workers. Small independent files use four transfers; larger files are sequential. Partial transfers resume. Dataset/model roots keep 60/20 GiB free respectively, and archive extraction checks its expanded-byte budget. The retained floor is a guard, not a reservation against unrelated processes consuming disk.

Live status:

- `artifacts/downloads/multimodal_status.json`
- `artifacts/downloads/multimodal-acquisition.log`
- `artifacts/downloads/multimodal-acquisition-errors.log`
- Existing KiTS/MedMNIST queue: `artifacts/downloads/public_acquisition_status.json`
- Paired 2D/3D queue: `artifacts/downloads/deepfluoro_status.json`, `deepfluoro-acquisition.log` and `deepfluoro-acquisition-errors.log` (the stderr file also contains normal download progress)

The project still lacks a freely acquired, outcome-linked image/report/laboratory cohort for the requested general clinical fusion. Credentialed MIMIC/VinDr data and unlicensed checkpoints were not acquired through unofficial access paths. These limits remain visible rather than being filled with unrelated image/text pairs or invented 3D labels.
