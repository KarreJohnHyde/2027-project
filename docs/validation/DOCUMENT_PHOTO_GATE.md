# Document-photograph content gate for 2-D research models

Status: `IMPLEMENTED_TESTED` (software behaviour and in-domain false-refusal check).
It is **not** a general out-of-distribution detector; that is the applicability gate that runs after it
(`IMAGE_APPLICABILITY_GATE.md`).

## What it does

Before any 2-D research image model runs, `check_document_photograph`
(`backend/app/services/model_inference.py`) reads the upload with the local OCR engine.
An image with 8 or more lines of printed text is refused with
`MODEL_INPUT_INCOMPATIBLE`. The refusal message points the user to document text
extraction and asks for native frames or the original DICOM/PACS export. The check
does not depend on the modality the user declares. Every result records the line
count and limit in `input_content_check`. If OCR is unavailable, the result says
`NOT_CHECKED_OCR_UNAVAILABLE`; the existing format and modality gates still apply.

## Measured behaviour (2026-10-27)

Held-out test frames came from each model's registered split manifest: 25 per
model, seed 20261026. The script is `scratchpad/gate_calibration.py`, recorded
here.

| Model | Frames | Max text lines | Refused at limit 8 |
| --- | --- | --- | --- |
| Kvasir v2 8-class classifier | 25 | 3 | 0 |
| GastroVision 27-class classifier | 25 | 3 | 0 |
| Kvasir-SEG polyp segmenter | 25 | 2 | 0 |
| ARCADE stenosis detector | 25 | 0 | 0 |
| ARCADE SYNTAX segmenter | 25 | 0 | 0 |
| TEZ kidney-stone detector | 25 | 0 | 0 |
| C-NMC ALL-vs-normal classifier | 25 | 0 | 0 |

Owner-provided phone photographs of printed report pages (laboratory, radiology and
ENT reports) read 14–37 lines and were refused. The photographs were processed in
memory only; no image or text was stored in the repository.

## Limits

- 175 frames is a small in-domain sample; endoscopy frames with heavier burned-in
  text could approach the limit.
- Photographs of printed films and of ultrasound montages carry little printed text
  (0–5 lines in the owner's examples) and pass this gate. Every 2-D model's applicability
  gate refuses them (all owner examples, 35 of 35 model checks; `IMAGE_APPLICABILITY_GATE.md`).
