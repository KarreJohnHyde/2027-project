# Source-repository inventory and integration status

Audited 2026-10-27 on the local workstation. A downloaded or extracted source tree is **not** an
installed runtime, and an installed package is not an integrated, tested capability. Status
words: `PRESENT` (archive in Downloads), `EXTRACTED` (source folder under `D:\project`, never
tracked by Git), `INSTALLED` (importable in the runtime that would use it), `INTEGRATED` (used by
MedTwin code), `TESTED` (covered by an executed automated test), `MISSING`, `BLOCKED`.

## 1. Repository archives and extracted folders

Downloads holds **25** repository archives: the 13 named by the owner plus 12 later ones. All
extracted folders are untracked. The 12 later ones are excluded locally through
`.git/info/exclude` (not published), so they cannot be committed by accident.

| Repository | Archive | Extracted | Runtime state | Use in MedTwin |
| --- | --- | --- | --- | --- |
| cogstack-nlp | PRESENT (310 MB) | EXTRACTED | not installed | Reference only |
| CogStack-SemEHR | PRESENT | EXTRACTED | not installed (legacy Python 2.7) | Reference only; never executed |
| Foresight | PRESENT (0.1 MB) | not extracted | not installed | Not used |
| health-assistant | PRESENT | EXTRACTED | not installed | Not used |
| MedCAT | PRESENT | EXTRACTED | `MISSING` | `BLOCKED`: no licensed concept bundle (UMLS/SNOMED) is configured |
| medical | PRESENT | EXTRACTED | not installed | Not used |
| medvault-ai | PRESENT | EXTRACTED | not installed | Not used |
| metriport | PRESENT (110 MB) | EXTRACTED | not installed | Not used (FHIR import is native) |
| MONAI | PRESENT | EXTRACTED | `INSTALLED` monai 1.6.1 (.venv) | `INTEGRATED`/`TESTED`: volumetric training and cardiac MRI evaluation (`ml_training/volumetric*.py`) |
| RadGraph | `radgraph-master.zip` **no longer in Downloads** (seen earlier in this session); `radgraph-master (1).zip` PRESENT (sha256 e8902dc0…) | both EXTRACTED | `MISSING` | `BLOCKED`: dependencies and model weights not present; no radiology relation gold set |
| scispaCy | PRESENT | EXTRACTED | `INSTALLED` in WSL (`~/.medtwin/venv-nlp`: spaCy 3.7.5, scispaCy 0.5.5, en_core_sci_sm 0.5.4) | `INTEGRATED`/`TESTED`: optional secondary NER (`MEDTWIN_SCISPACY=wsl`) |
| SIH_26047 | PRESENT | EXTRACTED | not installed | Not used |
| TwinWeaver | PRESENT (57 MB) | EXTRACTED | not installed | Not used |
| medspaCy | PRESENT | EXTRACTED | `MISSING` | `BLOCKED` in the shared NLP environment: medspaCy 1.3.1 pulls spaCy 3.8.18 and newer thinc/blis, which breaks scispaCy 0.5.5 and its spaCy 3.7 model. Needs its own environment (below). MedTwin's rule engine implements the ConText negation, uncertainty, experiencer and temporality scheme natively and is regression-tested |
| OHIF Viewers | PRESENT (107 MB) | EXTRACTED | not installed | Not adopted: one primary viewer only |
| Cornerstone3D | PRESENT (123 MB) | EXTRACTED | `MISSING` (npm) | Not yet needed: the built-in viewer covers single images, DICOM objects and NIfTI with source-pixel overlays. Needed once multi-file DICOM series and multiplanar views are built |
| Playwright | PRESENT | EXTRACTED (not needed) | `INSTALLED` playwright-core 1.63.0 (`tools/browser-qa`) | `INTEGRATED`/`TESTED`: browser walkthrough driving the system Edge |
| MONAI Label | PRESENT | EXTRACTED | `MISSING` | `BLOCKED`: needs an annotation-server deployment and a clinician annotation workflow decision |
| nnU-Net v2 | PRESENT | EXTRACTED | `MISSING` | Not installed until a licence-cleared 3-D segmentation task is scheduled (cardiac MRI uses MONAI) |
| TotalSegmentator | PRESENT | EXTRACTED | `MISSING` (an earlier probe that said "installed" was the extracted folder on the path) | `BLOCKED`: pretrained weights are a separate download, some tasks carry non-commercial or commercial-licence terms, and the owner has not approved the download |
| highdicom | PRESENT | EXTRACTED | `MISSING` | Needed for DICOM SEG export after series assembly exists |
| pydicom | PRESENT | EXTRACTED (not needed) | `INSTALLED` 3.0.2 | `INTEGRATED`/`TESTED`: DICOM upload reading (`backend/app/services/imaging_readers.py`) |
| NiBabel | PRESENT | EXTRACTED (not needed) | `INSTALLED` 5.4.2 | `INTEGRATED`/`TESTED`: NIfTI reading and volumetric training |
| SimpleITK | PRESENT | EXTRACTED (not needed) | `INSTALLED` 2.5.6 | `INTEGRATED`: NRRD/MetaImage reading; registration not implemented |

## 2. Packages added in this session

| Package | Where | Why | Evidence |
| --- | --- | --- | --- |
| wordninja 2.0.0 (MIT, pure Python) | `.venv`, pinned in `backend/requirements.txt` | Splits OCR-glued words ("Nopleural effusion orpneumothorax") with an exact offset map back to the source | `backend/tests/test_report_photo_extraction.py` |
| pip 25.0.1 (bundled `ensurepip`) | WSL `~/.medtwin/venv-nlp` | Lets the environment report what an install would change; nothing else was installed | medspaCy dry run recorded above |

## 3. Next commands (not run)

medspaCy in its own WSL environment, so the working scispaCy environment is untouched:

```bash
python3 -m venv ~/.medtwin/venv-medspacy
~/.medtwin/venv-medspacy/bin/python -m pip install "medspacy==1.3.1"
```

Then add a fail-closed adapter that runs medspaCy ConText as a second assertion opinion. It
should report disagreements with the rule engine for review, not override it.

Cornerstone3D (only with multi-file DICOM series assembly):
`npm install @cornerstonejs/core @cornerstonejs/tools @cornerstonejs/dicom-image-loader` at exact
pinned versions, after a bundle-size and licence review.
