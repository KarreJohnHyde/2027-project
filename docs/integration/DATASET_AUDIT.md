# MedTwin Dataset Audit

> **Path-discovery snapshot.** This conservative 33-path inventory intentionally performs no task activation. The later label- and split-aware audit is `dataset_registry/tasks.json` / `docs/data/DATA_READINESS_MATRIX.md`: 61 dataset units and 34 task units, with 9 ready for training, 1 exploratory-only, and 24 blocked. The two denominators describe different evidence stages and must not be compared as if one rewrote the other.

## Decision

The 33 paths named in the MedTwin master prompt are now represented in
`dataset_registry/datasets.json`. The registry is a discovery inventory, not a
training approval list. Every entry remains `DISCOVERED_CATALOG_ONLY`, or is
explicitly marked as a non-dataset engineering artifact. No collection is yet
eligible for model training or clinical validation.

This conservative result is intentional. A readable image and a disease-like
folder name do not establish provenance, a label definition, a patient-disjoint
split, or permission to use the data.

## Scope and method

- Source roots: the dataset directories explicitly listed in the master prompt.
- Traversal: sorted, read-only, no symlink following, bounded at 200,000 files
  and 50,000 directories per root.
- Observed: 154,817 files and 46.06 GiB across the registered paths. These are
  raw, non-deduplicated observations; they must not be summed as independent
  samples because several roots overlap.
- Format probes: up to 12 files of each applicable media type per path.
- Annotation checks: COCO referential checks, sampled YOLO syntax checks, CSV
  header/row counts, image/mask filename pairing, and NIfTI header checks.
- Duplicate check: same normalized filename and byte size across roots, followed
  by full SHA-256 within a 256-file/1 GiB budget and a 50-group reporting cap.
- Privacy: DICOM tags were deliberately not read or emitted. De-identification
  therefore remains unknown.
- Labels: directory names are preserved only as observed directory names. They
  are not promoted into `classes` unless a machine-readable annotation or
  configuration declares them.

The scanner completed without truncating any registered root. All sampled PNG,
JPEG, DICOM-preamble, and uncompressed NIfTI readability checks succeeded. This
only establishes bounded file readability, not medical validity.

## High-value findings

| Finding | Evidence | Risk | Severity / confidence | Required action |
|---|---|---|---|---|
| License is unresolved for most roots | 30 of 33 entries have `license_status: unknown`; the other three are the `train/images`, `valid/images`, and `test/images` Roboflow subset governed by the root metadata, not the rest of those mixed roots | Training, redistribution, or publication could violate source terms | High / high | Obtain the original dataset card and license for every source and map each file to that source |
| No leakage-safe split evidence | No patient/study identity manifest was found; nine paths merely have split-like directory names | Image-level splits can leak the same patient/study into train and test and invalidate metrics | High / high | Build a patient/study manifest from authoritative metadata, then regenerate disjoint splits and freeze their hashes |
| Kvasir data is represented more than once | 14,610 cross-root filename/size candidate groups were found; the bounded SHA-256 check filled its 50-group report cap with confirmed exact copies between `kvasir-dataset-v2` and standalone category roots | Counting these roots together inflates sample counts and creates leakage | High / high | Treat `kvasir-dataset-v2` as one candidate collection and the standalone category folders as aliases until a complete deduplication manifest proves otherwise |
| COCO training IDs are not unique | `data/stenosis/train/annotations/train.json` has 560 duplicate annotation IDs; `data/syntax/train/annotations/train.json` has 1,348 | COCO tooling and evaluators can overwrite or mis-associate annotations | High / high | Create a derived, versioned annotation repair with globally unique IDs; retain and hash the originals |
| COCO file references are otherwise structurally consistent | Six manifests declare 3,000 image records and 10,233 annotations; sampled/full manifest checks found zero missing image references, orphan image/category references, invalid positive-size bboxes, or duplicate image IDs | Structural consistency helps adapter work but does not validate label correctness | Low / high | Preserve as a useful baseline after licensing, label ontology, and split provenance are resolved |
| NIfTI components are incomplete as a local pair | 51 `volume-*.nii` files have matching numbered masks; 80 additional masks (indices 51–130) have no locally registered volume | The full 131-mask collection cannot be trained or evaluated from these roots alone | High / high | Locate the missing volumes or register the 51-pair subset explicitly; never silently discard the 80 unmatched masks |
| NIfTI transform codes differ | All 12 sampled volume/mask pairs matched dimensions, voxel spacing, quaternion values, and s-form matrices, but none matched both qform/sform codes | Different loaders may choose different transforms even when numeric values appear aligned | Medium / high | Review the originating dataset specification and test loader-specific orientation before deriving normalized copies |
| DICOM privacy and identity are unverified | `Brain_Stroke_CT_Dataset` contains 6,850 DICOM files; `ST000001` contains 350. Tags were not emitted, and no de-identification attestation was found | Files could contain PHI; patient grouping and leakage cannot be assessed | High / high | Run an approved local DICOM de-identification audit that emits only safe aggregate findings and stable pseudonymous study keys |
| `DATASET` aggregates multiple sources | Two local source notes list several Kaggle, Roboflow, and Mendeley sources without a per-file origin/license mapping | Labels and licenses may differ inside one root | High / high | Create a per-file source manifest before selecting any subset |
| MURA and PTB-XL are not registered | No root directory name matched MURA or PTB-XL | The planned core image and ECG experiments cannot start from this inventory | Blocking / medium | Acquire the datasets through their official licensed access paths and register immutable versions and official patient-aware folds |

## Structurally useful subsets

These observations identify candidates for further curation; none is a model or
clinical validation claim.

- `2d-segmentation-dataset`: 2,027 image filenames pair one-to-one with 2,027
  mask filenames. Twelve sampled pairs were readable and dimension-matched. Each
  sampled grayscale mask had five distinct values; the meaning of those values
  is undocumented and was not inferred.
- Root Roboflow subset: `data.yaml`, `README.dataset.txt`, and
  `README.roboflow.txt` declare a 1,300-image kidney-stone YOLOv8 export under
  `train/images`, `valid/images`, and `test/images`, licensed CC BY 4.0. The
  observed 1,054/123/123 image-label pairs match that total. Sixty label files
  per split were syntax-checked with no invalid normalized five-field rows.
  Patient independence, label quality, and the unusual declared class name
  `Tas_Var` remain unverified. Other files in the root `train` and `test`
  directories are outside this license/configuration scope.
- `ST000001`: 350 DICOM files have 350 same-stem JPEG files. This is filename
  evidence only; pixel equivalence and derivation history were not tested.
- `Brain_Stroke_CT_Dataset`: the external CSV has 200 rows and columns
  `image_id` and `Stroke`. The label encoding and linkage to the 16,323 observed
  media files are not documented locally.

## Registry inventory

`Media files` is a file count, not a patient, study, deduplicated sample, or
independent observation count.

| Registry ID | Kind | Files | Media files | Leading extensions | Annotation evidence | Split evidence | License |
|---|---|---:|---:|---|---|---|---|
| `2d-segmentation-dataset` | dataset candidate | 4,054 | 4,054 | `.png`: 4,054 | image/mask filename pairs | unverified | unknown |
| `behsof` | dataset candidate | 1,669 | 1,669 | `.jpg`: 1,669 | unknown | unverified | unknown |
| `benchmarks` | engineering artifact, not a medical dataset | 5 | 0 | code/results | none | not applicable | unknown |
| `brain-stroke-ct-dataset` | dataset candidate | 16,324 | 16,323 | `.png`: 9,473; `.dcm`: 6,850 | CSV, semantics unverified | unverified | unknown |
| `cerebrovascular-lesions` | dataset candidate | 10,865 | 10,865 | `.png`: 10,865 | unknown | unverified | unknown |
| `data` | dataset candidate | 9,801 | 9,795 | `.jpg`: 6,795; `.png`: 3,000 | six COCO JSON manifests | unverified | unknown |
| `dataset` | mixed dataset candidate | 24,714 | 24,712 | `.jpg`: 23,021; `.png`: 1,671 | source notes only | directory names only | unknown |
| `dyed-lifted-polyps` | possible fragment | 1,000 | 1,000 | `.jpg`: 1,000 | unknown | unverified | unknown |
| `dyed-resection-margins` | possible fragment | 1,000 | 1,000 | `.jpg`: 1,000 | unknown | unverified | unknown |
| `esophagitis` | possible fragment | 1,000 | 1,000 | `.jpg`: 1,000 | unknown | unverified | unknown |
| `external-test` | possible split fragment | 639 | 639 | `.jpg`: 639 | unknown | name only | unknown |
| `gastrovision` | dataset candidate | 8,000 | 8,000 | `.jpg`: 8,000 | unknown | unverified | unknown |
| `kvasir-dataset-v2` | dataset candidate | 8,000 | 8,000 | `.jpg`: 8,000 | unknown locally | unverified | unknown locally |
| `lungcancerdataset` | dataset candidate | 2,274 | 2,274 | `.png`: 1,185; `.jpg`: 1,089 | unknown | unverified | unknown |
| `mri-tumor-detection-dataset-training-and-testing` | dataset candidate | 113 | 113 | `.jpg`: 113 | unknown | directory names only | unknown |
| `normal-cecum` | possible fragment | 1,000 | 1,000 | `.jpg`: 1,000 | unknown | unverified | unknown |
| `normal-pylorus` | possible fragment | 1,000 | 1,000 | `.jpg`: 1,000 | unknown | unverified | unknown |
| `normal-z-line` | possible fragment | 1,000 | 1,000 | `.jpg`: 1,000 | unknown | unverified | unknown |
| `polyps` | possible fragment | 1,000 | 1,000 | `.jpg`: 1,000 | unknown | unverified | unknown |
| `segmentations` | possible dataset component | 131 | 131 | `.nii`: 131 | masks inferred only from filenames, not semantics | unverified | unknown |
| `split-data` | dataset candidate | 15,569 | 15,569 | `.jpg`: 14,788; `.png`: 781 | unknown | directory names only | unknown |
| `st000001` | dataset candidate | 700 | 700 | `.dcm`: 350; `.jpg`: 350 | no labels | unverified | unknown |
| `test` | mixed collection/split | 7,067 | 6,944 | `.jpg`: 6,432; `.png`: 512 | scoped YOLO subset | name only | scoped Roboflow subset declares CC BY 4.0 |
| `testing` | possible split fragment | 1,600 | 1,600 | `.jpg`: 1,600 | unknown | name only | unknown |
| `train` | mixed collection/split | 29,395 | 28,341 | `.jpg`: 26,289; `.png`: 2,052 | scoped YOLO subset | name only | scoped Roboflow subset declares CC BY 4.0 |
| `training` | possible split fragment | 5,600 | 5,600 | `.jpg`: 5,600 | unknown | name only | unknown |
| `ulcerative-colitis` | possible fragment | 1,000 | 1,000 | `.jpg`: 1,000 | unknown | unverified | unknown |
| `valid` | mixed collection/split | 246 | 123 | `.jpg`: 123; `.txt`: 123 | scoped YOLO subset | name only | scoped Roboflow subset declares CC BY 4.0 |
| `volume-pt1` | possible dataset component | 11 | 11 | `.nii`: 11 | unknown | unverified | unknown |
| `volume-pt2` | possible dataset component | 10 | 10 | `.nii`: 10 | unknown | unverified | unknown |
| `volume-pt3` | possible dataset component | 10 | 10 | `.nii`: 10 | unknown | unverified | unknown |
| `volume-pt4` | possible dataset component | 10 | 10 | `.nii`: 10 | unknown | unverified | unknown |
| `volume-pt5` | possible dataset component | 10 | 10 | `.nii`: 10 | unknown | unverified | unknown |

The JSON registry contains full extension counts, observed top-level directories,
bounded probe results, annotation details, limitations, and duplicate evidence
for each row.

## Activation requirements

A dataset adapter must remain disabled for training/evaluation until an immutable
bundle supplies all of the following:

1. Authoritative source, version, download/retrieval date, and license text.
2. Intended unit of analysis: patient, study, series, image, frame, or volume.
3. Explicit task and label ontology, including annotation instructions.
4. Stable pseudonymous patient/study keys and a leakage audit.
5. Train/validation/test manifest with file hashes and patient-disjoint proof.
6. Modality-specific decode checks and a corruption report.
7. Preprocessing version, exclusion rules, and derived-file provenance.
8. Dataset card describing demographic/technical coverage and known limitations.

Only after that bundle exists should `training_eligible` or
`validation_eligible` change from `false`.

## Reproduce the audit

From `D:\project` with the existing Python 3.12 environment:

```powershell
.\.venv\Scripts\python.exe scripts\audit_datasets.py
.\.venv\Scripts\python.exe -m json.tool dataset_registry\datasets.json > $null
```

The scanner reads source datasets and writes only the registry JSON. It does not
move, rename, delete, normalize, de-identify, or rewrite any source file.

## Assumptions and open questions

- Root-level metadata was associated with only the exact paths named by
  `data.yaml`; it was not generalized to unrelated files sharing the same root.
- Publicly known dataset names were not used as proof of the local copy's
  license or version. Those must be reconciled against original distribution
  records.
- No temporal analysis applies because the directories do not provide a
  trustworthy ingestion or acquisition history.
- Archive contents were outside this dataset-path audit. MURA or PTB-XL could be
  present inside an uninspected archive; the registry makes no such claim.
