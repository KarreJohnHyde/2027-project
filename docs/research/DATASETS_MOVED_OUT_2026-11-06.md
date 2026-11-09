# Datasets moved out of the project (2026-11-06)

**Current status:** the owner subsequently requested permanent deletion. All 925 original
manifest-listed entries below have now been deleted, along with almost all additional cleanup
payloads. The obsolete quarantine `restore.ps1` was removed; the deleted data cannot be restored
with the earlier move records. Approximately 67.22 MB of read-only DeepSA Git objects remains.
See `docs/data/PUBLIC_DATA_ACQUISITION_2026-11-06.md` and
`artifacts/audits/cleanup-2026-11-06/permanent-cleanup-result.json` for current results. The
following sections describe the earlier move-only state.

Later on the same day, another 17 unused folders (4.78 GB) were moved into this quarantine's
`additional-cleanup` subdirectory. Permanent deletion was blocked by automatic approval review;
the earlier quarantine remains on disk. See `docs/data/PUBLIC_DATA_ACQUISITION_2026-11-06.md`
and `artifacts/audits/cleanup-2026-11-06/result.json` for the additional moves. The original
`restore.ps1` below covers only the earlier moves.

The owner asked for unused datasets that cannot be used without a licence to be removed. Nothing was deleted. The
items below were moved to `D:\MedTwin_Removed_Datasets_2026-11-06`. That folder holds `moved.json` (each original
path, new path, size and reason) and `restore.ps1`, which moves everything back. Delete that folder yourself to
reclaim the 59.6 GB.

## What was moved

These are items whose licence is unverified with no recorded owner authorisation (`dataset_registry/tasks.json`),
plus local copies the project's own records describe as truncated or without licence text. Before the move, each
item was checked against the model registry, the derived sample manifests and the serving and training code. None of
them refers to these folders.

| Folder | Registry dataset | Size |
| --- | --- | --- |
| `segmentations`, `volume_pt1` to `volume_pt5` | liver-ct-volumes (an unlicensed LiTS copy; the licensed MSD Task03 copy is being downloaded) | 30.95 GB |
| `tfrecords` | unknown-tfrecords | 7.93 GB |
| `DATASET` | brain-tumor-ct-mri, dataset-train-test-unlabelled, kidney-ct-normal-tumor, liver-fibrosis-f0-f4, thermal-dataset-folder | 4.18 GB |
| `split_data` | kidney-ct-4class | 2.23 GB |
| `resized_images` | resized-images | 2.22 GB |
| `Brain_Stroke_CT_Dataset`, `External_test` | brain-stroke-ct, brain-stroke-ct-3class-external | 1.57 GB |
| `cerebrovascular lesions` | cerebrovascular-lesions-ct | 1.35 GB |
| `CLL`, `FL`, `MCL` | lymphoma-cll-fl-mcl | 1.62 GB |
| `Ultrasound Fetus Dataset` | ultrasound-fetus | 0.64 GB |
| `BEHSOF` | behsof-nafld | 0.35 GB |
| `LungcancerDataSet`, `MedTwin_Datasets/Lung_Cancer` | lung-cancer-ct (IQ-OTH/NCCD; no licence text) | 0.49 GB |
| `ST000001` | st000001-mr-study (DICOM study of unknown origin) | 0.32 GB |
| `Training`, `Testing`, `mri-tumor-detection-dataset(...)` | brain-mri-tumor-4class-a, mri-tumor-detection-small | 0.16 GB |
| `_imports/archives/archive_00` | brain-ct-hemorrhage-binary | 0.15 GB |
| `Otoscopic_Data`, `2d segmentation dataset`, `hypothyroid` | otoscopic-images, 2d-segmentation-pairs, thyroid-csv | 0.16 GB |
| `MedTwin_Datasets/_Downloads`, `MedTwin_Datasets/Tuberculosis/Montgomery*.zip` | truncated NLM TB downloads (superseded by the NLM mirror) and an unlicensed pneumonia zip | 2.70 GB |
| `MedTwin_Datasets/Pneumonia` | pneumonia radiographs without licence text | 2.48 GB |
| 893 loose root files | the CSV and table sets (heart, stroke, diabetes, support2, mtsamples, medquad, nbme, ...) and the VOC image root | 0.10 GB |

## What stayed

- **`train`, `test`, `valid`:** these folders also hold the licensed kidney-stone data (TEZ ROI, CC BY 4.0) that a
  registered model uses. The blocked brain-MRI and stroke files inside them were not separated out.
- **TotalSegmentator repository files and `LIDC-XML-only`:** code under Apache-2.0, and LIDC data under CC BY 3.0
  (verified 2026-11-06).
- **Root folders in neither registry:** `chest_xray`, `COVID-19_Radiography_Dataset`, `TB_Chest_Radiography_Database`,
  `HAM10000_images_part_1/2`, `picai_public_images_fold0`–`4`, `Dataset_BUSI_with_GT`, `lung_colon_image_set`,
  `bone_marrow_cell_dataset`, `siim-acr-pneumothorax`, `head_ct`, `Head_CT_Hemorrhage`, `Brain_CT_Hemorrhage`,
  `Brain_Hemorrhage_Multiclass`, `Brain_Data_Organised`, `colored_images`, `CORD`, `COCO`, `ADE ner+relation`,
  `Doctor's Handwritten Prescription BD dataset`, `PNG`, `images`, `labels`, `masks`, `YOLO` and `train-0`. The
  project has no licence record for them; some carry open licences and others restrictive ones. Each needs its
  licence checked before it is kept or moved.
