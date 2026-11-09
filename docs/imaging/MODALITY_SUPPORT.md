# Modality support

> **2026-10-29 reconciliation:** constrained ECG upload inference and cardiac MRI NIfTI/DICOM-series research inference are implemented. Older evaluation-only/unsupported wording below is historical. See [upload parity](../validation/UPLOAD_INFERENCE_PARITY.md) and the [current audit](../verification/COMPLETENESS_AUDIT_2026-10-29.md); parity is not independent clinical validation.

Source of truth: `GET /api/v1/modalities` and
`backend/app/services/modality_registry.py`, shown in **Medical Imaging -> Modality
support**. Opening a file is not interpreting it. File acceptance, preprocessing,
research-model coverage, and clinical validation are separate states.

**SUPPORTED** below means the format is content-signature checked, accepted, stored in
the configured encrypted upload store, and displayed/read with available metadata. A
“research model” passed licence/report/checkpoint gates for its stated internal research
scope. **No modality has a clinically validated model.**

| Modality | Files accepted | Registered model state | Clinical tasks |
| --- | --- | --- | --- |
| CT | Single DICOM objects, NIfTI-1, NRRD, MetaImage; PNG/JPEG research slices. Multi-file DICOM series are validated, ordered and rendered plane by plane (`/cases/{id}/dicom-series/assemble`, `/render`). | TEZ kidney-stone detector is `READY_UNVALIDATED`; brain/lung adapters lack weights. | none |
| MRI | Single DICOM objects, NIfTI-1, NRRD, MetaImage. Multi-file DICOM series are validated, ordered and rendered plane by plane. | The cardiac cine-MRI 3-D U-Net runs research-only on single NIfTI frames and on assembled DICOM series inside its development spacing envelope (`docs/validation/UPLOAD_INFERENCE_PARITY.md`; series input reproduces the NIfTI path on 98 of 98 public test frames, `docs/validation/SERIES_INFERENCE_PARITY.json`; the in-plane orientation convention of scanner series is assumed, not verified). Brain adapter lacks weights. | none |
| X-ray | DICOM, PNG/JPEG/BMP | MURA and lung adapters lack usable authorized weights; bone-fracture task remains audit-blocked. | none |
| Ultrasound / Doppler | DICOM, PNG/JPEG/BMP | no runnable model | none |
| PET / SPECT / PET-CT | Single DICOM objects and NIfTI/NRRD/MetaImage volumes; no DICOM-series assembly | no runnable model | none |
| Angiography (XA) | DICOM; PNG/JPEG research frames | ARCADE stenosis detector and SYNTAX segmenter are `READY_UNVALIDATED`; DeepSA is `UNSUPPORTED`. | none |
| CT/MR angiography | DICOM/volume readers within the single-object/volume boundary | no separate validated model | none |
| Mammography / dental / fluoroscopy | DICOM; dental also PNG/JPEG/BMP | no runnable model | none |
| GI endoscopy | PNG/JPEG/BMP, single DICOM objects | Kvasir v2 and GastroVision classifiers plus Kvasir-SEG segmenter are `READY_UNVALIDATED`; GastroVision is exploratory-only evidence. | none |
| Microscopy / haematology | PNG/JPEG/BMP | C-NMC ALL-vs-normal classifier is `READY_UNVALIDATED`; native BMP upload/display/inference is tested. | none |
| Histopathology / dermatology / retinal | PNG/JPEG/BMP; retinal also single DICOM objects | no runnable model | none |
| Echocardiography | Single DICOM objects frame by frame | EchoNet use permission and model integration remain unavailable. | none |
| ECG | WFDB format-16 header + signal file and CSV with a time column (`backend/app/services/ecg_inference.py`); 100 Hz, 10 s, 12 leads only, nothing resampled. Photographs or scans of printed ECGs are images, not signals. | PTB-XL baseline is `READY_UNVALIDATED` with research-only upload inference; parity with its held-out predictions in `docs/validation/UPLOAD_INFERENCE_PARITY.md`. | none |
| EEG / physiological signals | EDF, EDF+C/D and BDF/BDF+ read exactly (`backend/app/services/edf_reader.py`): header and record-size checks, physical units from header gains, min/max envelope preview, EDF+ annotations (de-identified). Patient and recording identification fields are never displayed. EDF+D is read but not previewed. | no model | none |
| Clinical documents | PDF (embedded text/local OCR), DOCX, XLSX, CSV/text/JSON | Rules and optional scispaCy execute but are unvalidated; MedCAT/RadGraph dependencies are missing. | none |
| FHIR R4 | JSON resources, including coded/datetime/range Observations | no model | none |
| HL7 v2 | `.hl7` observation-result messages (`backend/app/services/hl7_import.py`): OBR, OBX (NM, single-number SN, text and coded values; OBX-7 ranges, OBX-8 flags, OBX-11 X/D/W results withheld) and NTE. Patient, visit, order-staff and sender fields are never read. | no model | none |

## Research-model input rules (updated 2026-11-06)

- The 2-D models accept a **PNG, JPEG or BMP** upload or **one DICOM frame**
  (`backend/app/services/dicom_raster.py`). A DICOM frame is converted the way a viewer exports it:
  - the Modality LUT is applied first;
  - then the model's declared DICOM window if its registry entry has one (the head CT model: 80 HU wide, level 40,
    truncated, measured from its training PNGs), otherwise the frame's own VOI;
  - MONOCHROME1 is inverted;
  - 8-bit stored values without a VOI are used as stored;
  - colour is decoded to RGB.

  The Modality tag must fit the declared input type, and a multi-frame file needs a frame choice. The converted frame,
  not the stored values, passes the document and applicability gates. The conversion is recorded with the run.
- The volume models accept **NIfTI, NRRD or single-file MetaImage** volumes, or an **assembled DICOM series**.
  - NRRD/MetaImage headers that point at a separate data file are refused at upload and before every read.
  - A series for a model whose development frames record an orientation (the CT models) is permuted and flipped into
    that orientation. Nothing is resampled, and the mask comes back on the series grid.
  - The cardiac model, whose frames record none, chooses the convention by anatomy
    (`docs/validation/CARDIAC_SCANNER_SERIES.md`).
- The neighbouring-slice head CT model runs only on an assembled axial head CT series. Each slice is windowed like
  the training images and checked against the model's applicability reference.
- The user declares/confirms the trained input type. Independently of that declaration,
  each model refuses images unlike its training images (feature-space applicability gate,
  `docs/validation/IMAGE_APPLICABILITY_GATE.md`). There is no image-quality detector.
- Outputs are temperature-scaled class probabilities, validation-thresholded boxes in
  source pixels, or COCO-RLE masks mapped to source pixels with nearest-neighbour
  resampling. They remain research-only and pending review.
- A box/mask never becomes patient anatomy: `representation_level = L1_GENERIC`,
  anatomical region absent, and mapping status remains source-coordinate/not mappable
  unless a clinician establishes only a schematic organ association.
- PTB-XL and the two survival models are evaluation-only and are never run on uploads.

The cardiac cine-MRI segmenter (macro Dice 0.750 on 50 test patients) and the brain MRI and CT segmenters run
research-only inside their development envelopes. See `docs/imaging/VOLUMETRIC_SEGMENTATION_PIPELINE.md` and
`docs/validation/UPLOAD_INFERENCE_PARITY.md`.

## DICOM series

Separately uploaded slices of one case are grouped by `SeriesInstanceUID` and ordered along the slice normal. Each
series is checked for orientation, matrix, gaps and duplicates. A cine series with several images per position is
assembled for one chosen phase (the p-th image by trigger time). There is no atomic series upload, so completeness
means "no gap between the slices supplied", not "every acquired slice".

## Registry boundary correction

Modality association is explicit through each registry entry's
`supported_modalities`; substring matching is not used. This prevents unrelated models
from appearing under modalities with short overlapping tokens.
