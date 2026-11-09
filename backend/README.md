# MedTwin API

Current execution status: [runtime repair, CT manifests, dependency migration and remaining work](../docs/development/PRIORITY_EXECUTION_2026-11-09.md). The backend starts with the signed local Python runtime; the optional scikit-learn extension remains policy-blocked. The liver cohort has a checked 131-case manifest and a commercial-training hold. Docker recovery checks pass, but [four high backend OS findings remain](../docs/security/IMAGE_SECURITY_REVIEW_2026-11-09.md). Runtime pip is removed from the immutable container: install dependencies during the image build. See the [recovery/release runbook](../docs/deployment/RECOVERY_AND_RELEASE_2026-11-09.md) and India review before deployment.

Research-only FastAPI service for persistent case observations, audit events, and
traceable report extraction. It accepts PDF, DOCX, JSON, CSV, TXT, and Markdown
reports, plus web-ready GLB/glTF anatomy assets. SQLite is used for local
development and can be replaced behind the same API boundary with PostgreSQL.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/run.py
```

Then configure the web client:

```bash
VITE_MEDTWIN_API_URL=http://localhost:8000
```

## Optional multimodal research environment

The existing GPU/medical-imaging environment can be extended with
`backend/requirements-multimodal.txt` for image/text encoders, volume transforms,
DICOM codecs, mesh handling and 2D/3D projection research. Keep the current GPU
package versions constrained when installing it. Dataset/model acquisition,
source licences, resumable commands and readiness limits are documented in
[`MULTIMODAL_RESOURCES_2026-11-07.md`](../docs/data/MULTIMODAL_RESOURCES_2026-11-07.md).

These are optional local research dependencies; the minimal web service does not
need the notebook/rendering stack, and downloading model weights does not enable
a clinical model automatically.

## API surface

Task-scoped automatic upload routing is available at
`POST /api/v1/uploads/{id}/model-selection` and
`POST /api/v1/uploads/{id}/automatic-inference`. Measured, public-data learning
experiments are exposed at `GET /api/v1/research-learning`. See
[learning and routing](../docs/development/LEARNING_AND_ROUTING_2026-11-07.md)
for source contracts, scope, reproduction commands and remaining gaps.

- `POST /api/cases/{case_id}/reports/upload` — persist and analyze a report
- `POST /api/cases/{case_id}/anatomy-assets` — validate, store, and inventory a GLB/glTF
- `GET /api/cases/{case_id}/observations` — retrieve longitudinal history
- `POST /api/analyze/report` — traceable extraction
- `POST /api/analyze/compare` — old-versus-new report delta
- `POST /api/forecast/baseline` — eligibility-gated linear baseline
- `GET /api/metrics/ieee-validation` — evaluation evidence and live service latency
- `GET /api/models` — model artifact and validation status
- `WS /ws/telemetry/{case_id}` — edge pipeline telemetry

Native `.blend` files must be exported from Blender as glTF 2.0 `.glb` files
with named nodes, animations, and vertex groups preserved before upload.

Do not use identifiable patient data in this research prototype. The included
extractor is deterministic and traceable, not a validated diagnostic model.
Validated model adapters should preserve the same abstention, provenance, and
calibration contracts before replacing it.
