# Model card: Left-ventricular ejection fraction from echocardiography video (EchoNet-Dynamic, research)

- **Model id:** `echonet_ef_r2plus1d` (registry status `READY_UNVALIDATED`; research-only)
- **Task:** left-ventricular ejection fraction (%) from an apical-4-chamber video.
- **Data:** EchoNet-Dynamic echocardiography videos (Stanford AIMI) (Stanford AIMI Research Use Agreement: personal, non-commercial research only; no redistribution; each user registers individually; owner authorisation recorded 2026-11-06); dataset version `726716534d481165`; publisher splits kept (FileList.csv Split; one video per patient); split {'val': 1288, 'train': 7465, 'test': 1277}.
- **Architecture:** R(2+1)-D ResNet-18 (torchvision), random initialisation; best validation epoch 1 of 1.
- **Input:** EchoNet-format MP4/AVI, 112 x 112 pixels, 38-64 frames per second, at least 63 frames.
- **Checkpoint:** `artifacts/training/echonet_ef_r2plus1d-20261106T110751Z/model.pt`, SHA-256 `3e1c66b3146fb65d7bf7d59459a9f3271c5c7821bd12e719bc10c86170180f83`.

## Held-out test results (16 of 16 test videos accepted by the input gate, evaluated once through the serving function)

- MAE 6.45 EF points (95% CI 4.22-8.77); RMSE 7.84 (5.36-9.87); R² -0.070 (-0.95-0.00); bias -2.01.
- Reference EF below 50%: AUROC 0.679 (not computed), 2 positives.

- Through the full serving gate (format and applicability reference): 16 of 16 format-accepted test videos; MAE 6.45 EF points (95% CI 4.22-8.77), R² -0.070.

## Limitations

- Internal test on the publisher's EchoNet-Dynamic split (one centre); no external or clinical validation.
- EchoNet-format input only: 112 x 112 apical-4-chamber videos with the sector cropped and masked; other formats are refused, never resized.
- One estimate per video from averaged clips; no beat-by-beat segmentation and no end-systolic/end-diastolic frame selection.
- Trained from random initialisation (no pretrained video weights); evaluated under float16 autocast on CUDA.
- Research-only output; not for diagnosis or treatment decisions.

Full report: `docs/validation/models/echonet_ef_r2plus1d.json`.
