# Chest radiograph research model (third-party, not evaluated by MedTwin)

Status: `READY_UNVALIDATED` when the optional package and weights are present; otherwise
`DEPENDENCY_MISSING` or `WEIGHTS_MISSING`. Outputs are labelled
`RESEARCH_ONLY_THIRD_PARTY_PRETRAINED_NOT_EVALUATED_LOCALLY` and stored as findings pending human review.

## What it is

`backend/app/services/cxr_research.py` runs three pretrained models from TorchXRayVision 1.5.7
(Cohen et al., MIDL 2022; Apache-2.0 library):

| Role | Weights (release v1) | Output |
| --- | --- | --- |
| Classifier | DenseNet-121 `densenet121-res224-all` | 18 thoracic findings, each scaled by the publisher so 0.5 is its operating point |
| Anatomy | ChestX-Det PSPNet | 14 structures; lungs, heart and diaphragm are outlined |
| Input similarity | ResNet-101 autoencoder | reconstruction error, reported only |

The weights were trained by their publisher on public digital radiographs (NIH ChestX-ray14,
PadChest, CheXpert, MIMIC-CXR, Google, OpenI, RSNA/Kaggle). MedTwin has no labelled chest
radiographs and has not evaluated them. `scripts/fetch_cxr_weights.py` fetches them once into
`artifacts/third_party/torchxrayvision` (not in Git); their SHA-256 are checked before loading and the
service never downloads while serving. Install with `backend/requirements-research-cxr.txt`.

## How it runs

`POST /api/v1/uploads/{id}/chest-radiograph-analysis` (Medical Imaging, chest radiograph panel), after
the user states the PNG/JPEG/BMP upload is a frontal chest radiograph:

1. The printed-document check shared by all image models (8+ printed lines refuse).
2. Anatomy gate: both lungs must each cover at least 3% of the analysed square, the right lung on
   the image's left. Otherwise nothing is scored (`MODEL_INPUT_INCOMPATIBLE`).
3. The 18 scores, with the operating point and a display-only weak band of ±0.10.
4. Grad-CAM attention for the three highest scores, summarised by lung zone (each lung's height in
   thirds) and drawn over the image: where a score depends on, not a lesion outline.
5. A comparison with what the case's reports state about each label, restricted to statements about
   the label's own organ system that are certain or uncertain (not "to rule out"). Agreement is not
   proof of correctness, and a CT or ultrasound report describes a different examination.

## Observed on the demonstration film photograph (2026-10-29)

A phone photograph of a printed frontal film, cropped to the film: both lungs were found on their
expected sides, but all 18 scores lay within ±0.06 of the operating point (highest 0.56), so no finding
is distinguished. The right-lung outline extended below the visibly elevated right hemidiaphragm, so
no lung-base measurement is reported from it. Both point to the domain shift a film photograph
represents for models trained on digital radiographs.
