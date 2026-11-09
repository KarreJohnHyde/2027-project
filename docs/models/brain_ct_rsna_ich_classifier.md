# Intracranial haemorrhage on head CT slices (RSNA ICH, research)
- epidural: AUROC 0.973; at the F1 threshold 0.138: sensitivity 0.424, specificity 0.995, PPV 0.245
- subdural: AUROC 0.969; at the F1 threshold 0.332: sensitivity 0.729, specificity 0.976, PPV 0.680
- intraparenchymal: AUROC 0.986; at the F1 threshold 0.414: sensitivity 0.794, specificity 0.991, PPV 0.823
- intraventricular: AUROC 0.992; at the F1 threshold 0.349: sensitivity 0.826, specificity 0.994, PPV 0.831
- subarachnoid: AUROC 0.969; at the F1 threshold 0.429: sensitivity 0.630, specificity 0.988, PPV 0.735
- any intracranial haemorrhage: AUROC 0.978; at the F1 threshold 0.442: sensitivity 0.834, specificity 0.976, PPV 0.855

- Data: RSNA ICH training set (PNG conversion), owner-confirmed licensed copy; 753,015 slices; whole patients 80/10/10.
- Held-out test: 74,811 slices of 1,894 unseen patients; mean AUROC 0.978; study-level any-haemorrhage AUROC 0.980.

## Limitations
- Haemorrhage subtypes only (RSNA labels); no ischaemic stroke, tumour, infection or other pathology.
- Slice-level model on single-window PNGs; it does not see neighbouring slices or other CT windows.
- Internal held-out test on unseen patients of the same RSNA collection; no external validation.
- Operating thresholds come from the validation patients (Youden's J); probabilities are not calibrated for any clinical population.
- Research-only output; not validated for clinical use.
