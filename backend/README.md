# MedTwin API

Research-only FastAPI service for persistent case observations, audit events, and
traceable report extraction. It accepts PDF, DOCX, JSON, CSV, TXT, and Markdown
reports, plus web-ready GLB/glTF anatomy assets. SQLite is used for local
development and can be replaced behind the same API boundary with PostgreSQL.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
```

Then configure the web client:

```bash
VITE_MEDTWIN_API_URL=http://localhost:8000
```

## API surface

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
