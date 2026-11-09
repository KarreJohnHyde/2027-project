# skin_padufes_image_classifier

Research-only image_only classifier on PAD-UFES-20.

Patient-separated test: 304 images; accuracy 0.5592, macro F1 0.5387.

- Internal patient-separated holdout from PAD-UFES-20, not independent external or clinical validation.
- Six clinical skin-lesion categories; not all skin diseases, dermoscopy, histopathology or whole-slide interpretation.
- Training source has variable diagnostic confirmation; a predicted class is not a confirmed diagnosis.
- Only five melanoma images are present in the frozen test split; rare-class estimates are unstable.
- Frozen ImageNet ResNet18 features; regularization and temperature selected on validation only.
- Source age/gender/region can encode cohort bias; no clinical fairness or safety claim.
- Research-only; no treatment, exclusion of malignancy or clinical activation.

Data: CC BY 4.0, https://data.mendeley.com/datasets/zr7vgbcyr2/1. Encoder: torchvision/ImageNet pretrained ResNet18; separate weight/data commercial review required.
