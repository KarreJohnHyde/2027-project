# MedTwin workspace inventory

Snapshot date: 2026-10-23  
Workspace: `D:\project`

## Scope and safety

This is a metadata inventory, not an integration or clinical-validation claim. The pass:

- enumerated every immediate root entry;
- inspected marker files in the 15 extracted repositories named by the master prompt;
- read the central directory of every root ZIP without extracting or decompressing payloads;
- counted dataset files and extensions without opening medical payloads; and
- preserved all datasets, archives, research documents, environments, checkpoints, and anatomy assets.

The exact machine-readable record is in `FILE_REGISTRY.json`. The scan deliberately skipped recursive cache trees such as `.git`, `node_modules`, `dist`, and virtual environments. Root files larger than 8 MiB were not hashed during this bounded pass.

## Snapshot summary

| Item | Count or size | Interpretation |
|---|---:|---|
| Root entries | 205 | 136 files and 69 directories at scan time |
| ZIP archives | 69 | 21.44 GiB compressed; 170,278 members |
| ZIP central directories readable | 69 | Metadata readable; payload CRCs were not revalidated |
| Detected unsafe ZIP paths | 0 | No absolute or `..` traversal member was found |
| Estimated ZIP payload size | 47.77 GiB | Do not duplicate extraction without a storage plan |
| Extracted named repositories | 15 | All named repositories except Foresight |
| Archive-only named repositories | 1 | `Foresight-main.zip` |
| Root GLB models | 33 | Cataloged; root-level licensing is generally not documented |
| Dataset/split directories | 32 | 154,812 files, about 46.06 GiB |
| Virtual environments | 3 | `.venv`, `.venv-blender`, `.venv-medtw` |
| Free space on `D:` during scan | 93.48 GiB | Sufficient for current work, not a reason to re-extract duplicates |

The root also contains the canonical React/FastAPI application, generated build/cache directories, benchmark output, research documents, two registry directories, Blender sources, textures, and development tooling. Their individual paths and categories are recorded under `root_entries` in `FILE_REGISTRY.json`.

## Named repository disposition

| Source | Presence | Inventory disposition |
|---|---|---|
| `3d-anatomy-atlas-main` | Extracted + ZIP | Asset source only; code is CPAL-1.0 and upstream says its asset/anatomy audit is pending |
| `anatomy-main` | Extracted + ZIP | Disabled pending a code license and provenance for its nine GLBs |
| `cogstack-nlp-main` | Extracted + ZIP | Candidate isolated clinical-NLP service; no production model pack verified |
| `CogStack-SemEHR-master` | Extracted + ZIP | Archived Python 2.7 system; reference only |
| `health-assistant-main` | Extracted + ZIP | Candidate narrow FHIR/biomarker adapter; do not merge the full application |
| `human-atlas-main` | Extracted + ZIP | Candidate whole-body reference asset adapter; MIT code and CC-BY-4.0 BodyParts3D data |
| `MedCAT-main` | Extracted + ZIP | Candidate isolated MedCAT v1 service; model pack missing and NumPy constraint conflicts |
| `medical-main` | Extracted + ZIP | Demo/reference only; no license file, simulated processing, fixed demo accounts |
| `medvault-ai-main` | Extracted + ZIP | Rule-engine reference only until its in-memory/demo assumptions are removed and evaluated |
| `metriport-develop` | Extracted + ZIP | Deferred narrow interoperability adapter after the canonical data model stabilizes |
| `MONAI-dev` | Extracted + ZIP | Direct framework candidate; no task checkpoint or clinical model is active |
| `radgraph-master` | Extracted + ZIP | Candidate isolated radiology NLP service; no local weights verified |
| `scispacy-main` | Extracted + ZIP | Candidate isolated biomedical NLP service; no model package and NumPy conflict |
| `SIH_26047-main` | Extracted + ZIP | Reference only; overlapping full app, external AI service, and no root license |
| `TwinWeaver-main` | Extracted + ZIP | Research reference only; incomplete adapter artifact and hardware/dependency mismatch |
| `Foresight-main.zip` | Archive only | Disabled/reference only; malformed packaging metadata, no tests or weights |
| `Fullstack Software Development.zip` | Archive only; paths overlap current root | Historical snapshot only; never extract over the canonical tree |

Full entry points, dependency evidence, licenses, tests, checkpoint evidence, and limitations are in `COMPONENT_REGISTRY.json`.

## Archive registry

All 69 archives have an explicit record under `archives` in `FILE_REGISTRY.json`, including size, member count, aggregate compressed/uncompressed size, expansion ratio, top-level paths, unsafe-path count, encrypted/symlink counts, extraction evidence, and a content fingerprint derived from member CRC and size metadata.

### Repository and project archives

`3d-anatomy-atlas-main.zip`, `anatomy-main.zip`, `cogstack-nlp-main.zip`, `CogStack-SemEHR-master.zip`, `Foresight-main.zip`, `Fullstack Software Development.zip`, `health-assistant-main.zip`, `human-atlas-main.zip`, `MedCAT-main.zip`, `medical-main.zip`, `MedTwin_2_Research_Package.zip`, `MedTwin_2_Validation_Kit.zip`, `medvault-ai-main.zip`, `metriport-develop.zip`, `MONAI-dev.zip`, `radgraph-master.zip`, `scispacy-main.zip`, `SIH_26047-main.zip`, and `TwinWeaver-main.zip`.

`Foresight-main.zip` is the only archive whose top-level path is absent. It was inspected in place and not extracted. `Fullstack Software Development.zip` contains root paths such as `src/` and `backend/`; extracting it in place could overwrite the current application.

### Numbered dataset archives

`archive.zip` and `archive (1).zip` through `archive (22).zip` are all readable. Their top-level names reveal brain CT/MRI, lung, GI, segmentation, NIfTI volume, and train/test split collections, but directory names do not establish licenses, patient independence, or label validity.

- `archive (8).zip` is the largest expansion risk: 5.19 GB on disk and approximately 30.94 GB of members. Its existing top-level `segmentations` and `volume_pt1` through `volume_pt5` paths are present; no extraction is warranted.
- `archive (16).zip` and `archive (18).zip` have identical sorted member CRC/size fingerprints. They are a potential duplicate representation of Kvasir images with different top-level layouts. This is metadata evidence, not a cryptographic proof; preserve both until a controlled content-deduplication review.
- All numbered archives report zero detected traversal members.

### Anatomy archives

`anatomy-of-the-airways.zip`, `brain.zip`, `brain-hologram.zip`, `brain-model.zip`, `brain-point-cloud.zip`, `human-brain.zip`, `human-brain (1).zip`, `human-kidney.zip`, `human-pancreas-cross-section.zip`, `interior-heart-high-detail.zip`, `kidney.zip`, `kidney (1).zip`, `kidney (2).zip`, `lung-carcinoma.zip`, `lungs-normal-study.zip`, `male-skeleton.zip`, `medicine-organ-the-human-kidney.zip`, `nephron.zip`, `nephron (1).zip`, `nephron (2).zip`, `neurology.zip`, `pancreas.zip`, `pulmones-con-transparencia.zip`, `realistic-human-lungs.zip`, `small-and-large-intestine.zip`, `structure-of-nephron.zip`, and `struktur-paru-paru-manusia-3d-model.zip` all have readable central directories and existing corresponding root top-level paths.

Presence is not provenance. These archives and the 33 root GLBs remain unavailable for production selection until each has a source URL, license, attribution text, anatomy level, checksum, and validation status. The one attributed model already copied to `public/models` is governed by its own `ATTRIBUTION.md` and is still reference anatomy rather than patient-specific reconstruction.

## Dataset directory evidence

The 32 directories cataloged as datasets or splits are:

`2d segmentation dataset`, `BEHSOF`, `Brain_Stroke_CT_Dataset`, `cerebrovascular lesions`, `data`, `DATASET`, `dyed-lifted-polyps`, `dyed-resection-margins`, `esophagitis`, `External_test`, `Gastrovision`, `kvasir-dataset-v2`, `LungcancerDataSet`, `mri-tumor-detection-dataset(training and testing)`, `normal-cecum`, `normal-pylorus`, `normal-z-line`, `polyps`, `segmentations`, `split_data`, `ST000001`, `test`, `Testing`, `train`, `Training`, `ulcerative-colitis`, `valid`, and `volume_pt1` through `volume_pt5`.

Notable format evidence:

- `Brain_Stroke_CT_Dataset`: 9,473 PNG, 6,850 DICOM, and one CSV among 16,324 files.
- `Gastrovision`: 8,000 JPG files.
- `kvasir-dataset-v2`: 8,000 JPG files.
- GI class-named directories: 1,000 JPG files each across eight categories.
- `segmentations` plus `volume_pt1` through `volume_pt5`: 182 NIfTI files totaling roughly 28.8 GiB.
- `data`: 6,795 JPG, 3,000 PNG, and six JSON annotation files.
- `train`, `test`, and `valid`: mixed image and text labels, but provenance and patient-level partitioning remain unverified.

These are counts, not evidence of suitability. All remain `DATASET_SOURCE` candidates with `license_status=unknown` until documentation, consent/de-identification, label definitions, patient identifiers, and leakage-aware split manifests are established.

## Root 3D assets

The registry explicitly lists all 33 GLBs. They cover brain, heart, lung, kidney/nephron, liver, pancreas, intestine, skeleton, airway, and whole-body studies. Root filenames alone are insufficient to establish source, license, anatomical accuracy, or clinical use. Accordingly:

1. keep originals immutable;
2. never expose every root GLB automatically;
3. create a manifest entry only after checksum, license, attribution, anatomy level, format/extension validation, and browser loading tests; and
4. label generic models as L1 reference anatomy, never as a patient digital twin.

## Unknown or unsupported items

- `source/` is retained as an unclassified source tree; it requires a separate bounded review before reuse.
- Root binary assets with autogenerated or ambiguous names, such as `4c183daa67a34efca2480a5862d7ceb0.glb`, stay disabled until provenance is resolved.
- Generated/cache trees (`dist`, `.pytest_cache`, `node_modules`) are present but excluded from source classification.
- Existing virtual environments are preserved and are not application source.

## Reproduce the inventory

From `D:\project`:

```powershell
.\.venv\Scripts\python.exe scripts\generate_workspace_inventory.py
```

The script writes only `docs/integration/FILE_REGISTRY.json`. It does not extract archives or read medical payload contents.
