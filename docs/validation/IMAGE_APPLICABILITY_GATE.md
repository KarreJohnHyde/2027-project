# Image applicability gate for the 2-D research models

Status: `IMPLEMENTED_TESTED`. It checks resemblance to each model's training images. It is not a
quality check, not a clinical safety guarantee, and an image that passes can still be outside what
the model handles.

## What it does

Before a 2-D research model runs on an upload (`backend/app/services/model_inference.py`
`check_distribution`), the image is passed through the model itself and summarised by:

- statistics of the model's input tensor after the model's own preprocessing (per-channel mean
  and spread, intensity quantiles, and for colour input the spread of channel differences);
- every network stage averaged over space: ResNet layers 1–4 (Kvasir v2), EfficientNet-B0 stages
  1–8 (GastroVision, C-NMC), the detector's ResNet stages 1–4 (ARCADE stenosis, TEZ kidney stone),
  every U-Net encoder level and the bottleneck (Kvasir-SEG, ARCADE SYNTAX).

Per stage, a probabilistic-PCA Gaussian (64 principal directions plus one residual variance) is
fitted on up to 3,000 training images of that model (`app/services/image_ood.py`). An image's
score is the mean over stages of its Mahalanobis distance divided by the median distance of the
validation images. The limit is the 0.99 quantile of the validation images' scores, so about 1% of
images like the validation split are refused by construction. A refused image is not passed to the
model (`MODEL_INPUT_OUT_OF_DISTRIBUTION`, with the score and limit). The decision does not depend
on the modality the user declares.

Each reference is stored next to its checkpoint (`ood_reference.npz`, no pickled objects), bound by
SHA-256 in the registry (`ood_reference_path`, `ood_reference_sha256`) and to the checkpoint and
feature version in its metadata. A model whose reference is missing, altered or built for another
checkpoint is not runnable (`OOD_REFERENCE_MISSING`, `OOD_REFERENCE_HASH_MISMATCH`).

The printed-document check (`DOCUMENT_PHOTO_GATE.md`) still runs first.

## Measured behaviour (2026-10-28)

`scripts/build_image_ood_references.py`, seed 20261028. Own test images: the model's test split
(up to 1,500), never used for fitting or calibration. Other domains: 300 test images from each other
image family.

| Model | Own test images refused | GI endoscopy | Coronary angiography | CT | Blood-cell microscopy |
| --- | --- | --- | --- | --- | --- |
| Kvasir v2 classifier | 0.6% | — | 100% | 100% | 100% |
| GastroVision classifier | 0.7% | — | **14.7%** | 100% | 100% |
| Kvasir-SEG polyp segmenter | **11.7%** | — | 100% | 100% | 100% |
| ARCADE stenosis detector | **9.3%** | 100% | — | 100% | 100% |
| ARCADE SYNTAX segmenter | 0% | 67.7% | — | 93.9% | 100% |
| TEZ kidney-stone detector | 5.1% | 100% | 100% | — | 100% |
| C-NMC blood-cell classifier | 1.9% | 100% | 100% | 100% | — |

Per-model evidence (counts, Wilson intervals, score quantiles): `docs/validation/models/<model>.ood.json`.

Owner's photographs (independent of calibration; processed in memory only, nothing stored): a
phone photograph of a chest X-ray film, a photograph of an ultrasound montage, two report pages with
endoscopy thumbnails and a laboratory report page were refused by all seven models (35 of 35). The
X-ray film photograph carries only 5 lines of printed text and passes the document check; the
applicability gate is what stops it.

## How the rule was chosen, and what that means for the numbers

Three variants were compared on the cached features of the same sets: the largest stage score
instead of the mean, the 0.995 quantile, and calibration on validation images pooled with half of
each test split. The largest stage score let most angiograms through the colour-endoscopy models;
pooling lowered false refusals for the stenosis and kidney-stone detectors but let the Kvasir-SEG
test split's heavy tail widen that limit until CT and angiography passed. Because the variant was
selected after seeing these cross-domain results, the cross-domain refusal rates above are
optimistic estimates; the owner's photographs are the only check independent of that choice.

## Limits

- False refusals are high where a publisher's test split differs from its validation split:
  Kvasir-SEG 11.7%, ARCADE stenosis 9.3%, TEZ 5.1%. Those test images are themselves unlike the
  training data, so refusing them is the gate working as specified; it does reduce coverage.
- GastroVision accepts most coronary angiograms (14.7% refused) and the SYNTAX segmenter accepts a
  third of GI endoscopy frames. Declaring the right modality remains necessary.
- Calibration sets are small for some models (132–200 validation images), so limits are uncertain.
- Only these four image families were tested as other domains; natural photographs, other
  radiology modalities and scanned films beyond the owner's examples were not.
