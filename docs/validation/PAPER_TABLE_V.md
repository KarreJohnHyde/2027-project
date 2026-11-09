# Table V — results by task, dataset, comparison and evidence

Every number below is copied from a committed evaluation artifact; nothing is estimated or carried over
from another model or dataset. All results are **internal held-out test splits** of public datasets
(split manifests in `_derived/datasets/*/samples.csv`); **no external validation exists for any model**.
Intervals are 95% bootstrap intervals (1,000 resamples) over the stated cluster unit. Model selection
was done on the validation split; the test split was read once with the frozen checkpoint.

Sources: `docs/validation/models/<model_id>.json`, `benchmarks/results/http-benchmark-20261023-224119.json`,
`benchmarks/results/report-workflow-benchmark-20261023-223734.json`,
`benchmarks/results/ocr-benchmark-20261029-212009.json`, `docs/validation/UPLOAD_INFERENCE_PARITY.json`.

## What was actually compared

The draft table named comparisons that were **not run**. The real comparisons are:

| Draft wording | What was run |
| --- | --- |
| CNN vs ResNet/DenseNet | ResNet-18 vs EfficientNet-B0, compared on **validation** macro-F1 for model selection; only the selected network was scored on test. DenseNet was not trained or evaluated as a baseline (DenseNet-121 appears only as the third-party chest-radiograph model, which MedTwin has not evaluated). |
| Faster R-CNN vs YOLO | Faster R-CNN (ResNet-50-FPN v2) only. YOLO was not run. |
| U-Net vs nnU-Net | MONAI U-Net (2-D) and 3-D U-Net only. nnU-Net was not run. |
| 1-D CNN vs CNN-LSTM | 1-D ResNet only. CNN-LSTM was not run. |
| Cox vs naive baseline | Penalised Cox vs the Kaplan–Meier reference (integrated Brier score). This comparison was run. |
| MURA, GRAZPEDWRI-DX | Not run: MURA weights are missing (registry status `WEIGHTS_MISSING`); GRAZPEDWRI-DX is not available locally. |

## Table

| Task | Dataset (test split) | Model / comparison | Measured result (95% CI) |
| --- | --- | --- | --- |
| Image classification | Kvasir v2, 8 classes; 1,202 images, 1,194 near-duplicate groups | ResNet-18 selected over EfficientNet-B0 (val macro-F1 0.943 vs 0.940) | Acc 0.926 (0.911–0.940); macro-F1 0.926 (0.911–0.940); macro AUROC (one-vs-rest) 0.995; ECE 0.020 → 0.019 after temperature scaling |
| Image classification | GastroVision, 27 classes; 1,225 images, 1,223 groups | EfficientNet-B0 selected over ResNet-18 (0.555 vs 0.410) | Acc 0.737 (0.713–0.761); macro-F1 0.553 (0.507–0.589); balanced acc 0.622 (0.574–0.693); macro AUROC 0.979; ECE 0.047 → 0.035 |
| Image classification | C-NMC (ALL vs normal cells); 1,867 images, 28 subject groups | EfficientNet-B0 selected over ResNet-18 (0.821 vs 0.783) | Acc 0.807 (0.659–0.894); macro-F1 0.790 (0.626–0.877); AUROC 0.867; ECE 0.138 → 0.020 |
| Image classification | MURA | — | Not run (weights missing) |
| Detection | ARCADE stenosis; 300 images, 386 reference boxes | Faster R-CNN R50-FPN v2 | mAP@[.50:.95] 0.062; AP50 0.203; at the validation-chosen threshold 0.75: P 0.215, R 0.381, F1 0.275 |
| Detection | Kidney-stone CT slices (TEZ); 196 images, 402 boxes | Faster R-CNN R50-FPN v2 | mAP@[.50:.95] 0.231; AP50 0.629; at threshold 0.85: P 0.742, R 0.550, F1 0.631 |
| Detection | GRAZPEDWRI-DX | — | Not run (dataset not available locally) |
| Segmentation | ACDC cine MRI; 100 frames, 50 patients | 3-D U-Net | Mean case macro Dice 0.750 (0.719–0.778); Dice RV 0.707, myocardium 0.731, LV 0.812; HD95 81.6 / 58.6 / 53.7 mm. IoU not computed |
| Segmentation | Kvasir-SEG; 120 images | 2-D U-Net (352×352) | Dice 0.768 (0.725–0.809); IoU 0.670; HD95 73.6 px at model resolution |
| Segmentation | ARCADE SYNTAX; 300 images | 2-D U-Net (512×512) | Vessel Dice 0.683 (0.665–0.699); vessel IoU 0.535; mean per-image segment Dice 0.307 (0.291–0.323); macro segment Dice 0.201 |
| ECG | PTB-XL fold 10; 2,163 records, 1,881 patients; 5 superclasses | 1-D ResNet | Macro AUROC 0.917 (0.909–0.925); macro-F1 at validation thresholds 0.734 (0.717–0.750); macro AUPRC 0.805; mean ECE 0.027 → 0.015 (Platt) |
| Survival | Heart-failure clinical records; 90 patients, 29 events | Penalised Cox vs Kaplan–Meier | Harrell C 0.671 (0.569–0.774); integrated Brier 0.168 vs 0.158 for Kaplan–Meier (skill −0.065: **no gain over the naive reference**); tertile calibration at 90 and 180 days in the report |
| Survival | PBC (Mayo); 104 patients, 35 events | Penalised Cox vs Kaplan–Meier | Harrell C 0.786 (0.709–0.854); integrated Brier 0.105 vs 0.146 (skill 0.281); tertile calibration at 1, 3 and 5 years in the report |
| Clinical NLP | — | — | Not run (no annotated clinical corpus) |
| Lab-report extraction | Annotated reports / expert reference | — | Not run (no expert-annotated report set) |
| Lab-report OCR (synthetic) | Synthetic rendered lab reports (clean / photographed / low-resolution) | RapidOCR as configured vs Windows OCR | Lab-row recall 0.962 / 0.926 / 0.943 vs 0.74 / 0.54 / 0.58; character error rate 0.026 on clean pages. **Synthetic pages, not clinical reports** |
| Fusion | — | — | Not run (no paired multimodal data) |
| 3-D mapping | — | — | Not run (atlas association is schematic, L1; no image-to-atlas registration) |
| Forecasting | — | — | Not eligible (no longitudinal outcome data for a forecasting target) |
| Service latency | Same-host loopback; GET catalog endpoint; 3 repeats × 200 requests | 1 uvicorn worker | Concurrency 1: p50 2.4–3.4 ms, p95 14.7–21.0 ms, 187–252 req/s; concurrency 8: p50 25–47 ms, p95 62–141 ms, 130–273 req/s; 0 errors in 1,200 requests |
| Service workflow | Synthetic de-identified report: create case → upload → analysis job → reloads; 3 repeats × 20 | Rule-based text pipeline | Concurrency 1: p50 67–147 ms, p95 94–223 ms, 6.2–12.7 workflows/s; concurrency 4: p50 168–248 ms, p95 368–400 ms, 14.1–16.0 workflows/s; 0 failures in 120 workflows |
| Upload-path parity | The seven 2-D test splits above (5,210 images) | Served inference path vs predictions saved at training | Same top class on 4,293 of 4,294 classifier images; detector operating points reproduced (kidney stone exactly; stenosis 537 vs 536 false positives); Kvasir-SEG mask Dice in source pixels 0.768 vs 0.768 at the model grid |

Ranges in the service rows are the spread across the three repeats, not confidence intervals.

## LaTeX

```latex
\begin{table*}[t]
\caption{Results by task, dataset, comparison and evidence (internal held-out test splits; no external validation)}
\label{tab:results}
\centering
\footnotesize
\begin{tabular}{p{2.0cm}p{3.6cm}p{3.4cm}p{7.2cm}}
\hline
Task & Dataset (test split) & Model / comparison & Measured result (95\% CI) \\
\hline
Classification & Kvasir v2, 8 classes; 1,202 images & ResNet-18 (selected over EfficientNet-B0 on validation) & Acc 0.926 (0.911--0.940); macro-F1 0.926 (0.911--0.940); macro AUROC 0.995; ECE 0.020$\rightarrow$0.019 \\
Classification & GastroVision, 27 classes; 1,225 images & EfficientNet-B0 (selected over ResNet-18) & Acc 0.737 (0.713--0.761); macro-F1 0.553 (0.507--0.589); macro AUROC 0.979 \\
Classification & C-NMC; 1,867 images, 28 subjects & EfficientNet-B0 (selected over ResNet-18) & Acc 0.807 (0.659--0.894); macro-F1 0.790 (0.626--0.877); AUROC 0.867 \\
Classification & MURA & -- & Not run (weights missing) \\
Detection & ARCADE stenosis; 300 images, 386 boxes & Faster R-CNN R50-FPN v2 & mAP 0.062; AP50 0.203; P 0.215, R 0.381 at threshold 0.75 \\
Detection & Kidney-stone CT; 196 images, 402 boxes & Faster R-CNN R50-FPN v2 & mAP 0.231; AP50 0.629; P 0.742, R 0.550 at threshold 0.85 \\
Detection & GRAZPEDWRI-DX & -- & Not run (dataset unavailable) \\
Segmentation & ACDC; 100 frames, 50 patients & 3-D U-Net & Macro Dice 0.750 (0.719--0.778); RV 0.707, Myo 0.731, LV 0.812 \\
Segmentation & Kvasir-SEG; 120 images & 2-D U-Net & Dice 0.768 (0.725--0.809); IoU 0.670 \\
Segmentation & ARCADE SYNTAX; 300 images & 2-D U-Net & Vessel Dice 0.683 (0.665--0.699); IoU 0.535; segment Dice 0.307 \\
ECG & PTB-XL fold 10; 2,163 records & 1-D ResNet & Macro AUROC 0.917 (0.909--0.925); macro-F1 0.734 (0.717--0.750) \\
Survival & Heart failure; 90 patients, 29 events & Cox vs Kaplan--Meier & C 0.671 (0.569--0.774); IBS 0.168 vs 0.158 (no gain) \\
Survival & PBC (Mayo); 104 patients, 35 events & Cox vs Kaplan--Meier & C 0.786 (0.709--0.854); IBS 0.105 vs 0.146 \\
Clinical NLP & -- & -- & Not run (no annotated corpus) \\
Lab extraction & Expert-annotated reports & -- & Not run (no annotated set) \\
Lab OCR (synthetic) & Rendered synthetic reports & RapidOCR vs Windows OCR & Row recall 0.962/0.926/0.943 vs 0.74/0.54/0.58 (clean/photo/low-res) \\
Fusion & -- & -- & Not run (no paired data) \\
3-D mapping & -- & -- & Not run (schematic L1 only) \\
Forecasting & -- & -- & Not eligible \\
Service & Loopback, catalog GET, 3$\times$200 requests & 1 worker & c=1: p50 2.4--3.4 ms, p95 14.7--21.0 ms; c=8: p50 25--47 ms, p95 62--141 ms; 0 errors \\
Service & Synthetic report workflow, 3$\times$20 & Rule-based pipeline & c=1: p50 67--147 ms, p95 94--223 ms; c=4: p95 368--400 ms; 0 failures \\
\hline
\end{tabular}
\end{table*}
```
