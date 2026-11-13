# Model Arena contract

Authenticated read-only routes at the canonical prefix:

- `GET /universal/arena/models`: `schema_version`, notice and saved model snapshots.
- `POST /universal/arena/compare`: strict `{left_id,right_id}` (1–128 characters), rejecting unknown models and extra arguments.

Each snapshot records task, ordered labels, dataset/preprocessing/checkpoint identities, current serving gate, current evaluation-file SHA-256, saved counts/metrics/calibration/thresholds/intervals and report binding status. Binding checks compare declared report model, checkpoint and dataset identifiers plus registered prediction path. A missing or mismatched binding stays explicit; historical prediction-byte immutability cannot be retroactively established from a path alone.

Comparison requires distinct models, identical task, ordered labels and target definitions, identical dataset version, report binding and counts, plus a digest over sorted actual held-out `(record_id,patient_id,labels)` tuples. CSV input is bounded; unknown IDs/labels, duplicate records, absent patient keys, unsupported artifact formats and unmatched cohorts refuse comparison. Equal counts alone are insufficient. Prediction file SHA-256 identifies the currently inspected bytes.

Result status is `COMPARABLE_RECORDED_COHORT` or `COMPARISON_UNAVAILABLE`; reasons are retained. Candidate-minus-baseline deltas exclude sample counts. `significance` remains `NOT_COMPUTED_NO_SUPERIORITY_CLAIM`. Recorded cohort matching does not establish clinical validity, paired bootstrap significance, absence of dataset bias, a new runtime accuracy result or a new independent final test. No calibration or threshold is fitted and no model runs from this endpoint.
