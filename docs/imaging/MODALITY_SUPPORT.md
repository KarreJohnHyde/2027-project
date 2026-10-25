# Modality support

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
| CT | Single DICOM objects, NIfTI-1, NRRD, MetaImage; PNG/JPEG research slices. Multi-file DICOM series assembly is not implemented. | TEZ kidney-stone detector is `READY_UNVALIDATED`; brain/lung adapters lack weights. | none |
| MRI | Single DICOM objects, NIfTI-1, NRRD, MetaImage. Multi-file DICOM series assembly is not implemented. | The cardiac cine-MRI 3-D U-Net has internal held-out evidence (evaluation-only; no upload inference). Brain adapter lacks weights. | none |
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
| ECG | CSV plus training-time WFDB parser in `ml_training`; no patient upload inference contract | PTB-XL baseline is `READY_UNVALIDATED` evaluation-only. | none |
| EEG | EDF reader not installed (`UNSUPPORTED_MODALITY`) | no model | none |
| Clinical documents | PDF (embedded text/local OCR), DOCX, XLSX, CSV/text/JSON | Rules and optional scispaCy execute but are unvalidated; MedCAT/RadGraph dependencies are missing. | none |
| FHIR R4 | JSON resources, including coded/datetime/range Observations | no model | none |
| HL7 v2 | Reader not installed (`UNSUPPORTED_MODALITY`) | no model | none |

## Research-model input rules

- The seven connected 2-D models accept an associated **PNG, JPEG, or BMP** raster
  upload. DICOM and volumetric containers are refused because these checkpoints were
  trained on 2-D raster inputs.
- The user declares/confirms the trained input type. Modality checks prevent obvious
  mismatches, but there is **no objective task-specific image-quality or OOD detector**.
- Outputs are temperature-scaled class probabilities, validation-thresholded boxes in
  source pixels, or COCO-RLE masks mapped to source pixels with nearest-neighbour
  resampling. They remain research-only and pending review.
- A box/mask never becomes patient anatomy: `representation_level = L1_GENERIC`,
  anatomical region absent, and mapping status remains source-coordinate/not mappable
  unless a clinician establishes only a schematic organ association.
- PTB-XL and the two survival models are evaluation-only and are never run on uploads.

The separate `ml_training.volumetric` path accepts paired 3-D NIfTI volumes for research
training/evaluation and is not connected to upload inference. Synthetic train/evaluate/
checkpoint/resume executed successfully. After the owner's recorded authorization it
trained the cardiac cine-MRI segmenter (macro Dice 0.750 on 50 test patients; cardiac
indices in its report); it remains evaluation evidence only. See `docs/imaging/VOLUMETRIC_SEGMENTATION_PIPELINE.md`.

## DICOM-series boundary

The current reader validates and displays one DICOM object at a time. It does not offer
atomic series upload or group/order instances by `SeriesInstanceUID`, `InstanceNumber`,
and geometry. It therefore cannot claim series completeness or a series-level volume.
The API exposes `DICOM_SERIES` as unavailable until those behaviours and tests exist.

## Registry boundary correction

Modality association is explicit through each registry entry's
`supported_modalities`; substring matching is not used. This prevents unrelated models
from appearing under modalities with short overlapping tokens.
