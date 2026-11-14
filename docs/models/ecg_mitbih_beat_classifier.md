# Model card: Heartbeat class on single-lead ECG (MIT-BIH, inter-patient, research)

- **Model id:** `ecg_mitbih_beat_classifier` (registry status `READY_UNVALIDATED`; research-only)
- **Data:** MIT-BIH Arrhythmia Database 1.0.0, PhysioNet (Open Data Commons Attribution License v1.0).
- **Split:** inter-patient DS1/DS2 (de Chazal 2004); 4 DS1 records for validation (seeded); paced records excluded.
- **Checkpoint:** `artifacts/training/ecg_mitbih_beat_classifier-20261114T091730Z/model.pt`, SHA-256 `767badf89063eb685346cb80c48f8fbb0b3e4d08b847516d8ff30f3ef743a195`.

## Test results (22 unseen patients, evaluated once)

- Macro F1 0.423; accuracy 0.930 on 49661 beats.
- N: support 44218, sensitivity 99.1%, positive predictive value 95.2%.
- S: support 1836, sensitivity 1.3%, positive predictive value 26.4%.
- V: support 3219, sensitivity 73.0%, positive predictive value 66.7%.
- F: support 388, sensitivity 0.0%, positive predictive value n/a.

## Limitations

- Beat positions are the reference annotations; a deployed system needs its own beat detector, whose errors are not part of this evaluation.
- MIT-BIH holds 48 half-hour two-lead Holter records from 47 people (Boston, 1975-1979); the test part is 22 people.
- Single lead (MLII), 360 Hz only; other leads, sampling rates and devices are outside this model's evidence.
- Inter-patient supraventricular (S) beat detection is known to be hard; see the per-class sensitivity and its interval.
- Research-only output; not validated for clinical use.

Full report: `docs/validation/models/ecg_mitbih_beat_classifier.json`.
