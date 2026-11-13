# MedTwin measured architecture

```mermaid
flowchart LR
  UI[React / Vite research workspace] -->|versioned API; dev/preview proxy| API[FastAPI /api/v1]
  API --> AUTH[Case authorization and input contracts]
  AUTH --> STORE[Original bytes / SHA-256 / encrypted uploads]
  AUTH --> DB[(SQLAlchemy / persistent case and audit database)]
  API --> QUEUE[Durable job queue]
  QUEUE --> WORKER[Separate Python worker]
  WORKER --> DOC[PDF text or local OCR / NLP / laboratory rules]
  WORKER --> GATE[Model hash / usage / content / applicability gates]
  GATE --> ML[Existing PyTorch / MONAI checkpoints]
  DOC --> EVIDENCE[Source-linked immutable evidence]
  ML --> EVIDENCE
  EVIDENCE --> DB
  DB --> REVIEW[Append-only review / independent correction decisions]
  REVIEW --> UI
  UI --> VIEW[Source-image overlay and generic L1 Three.js atlas]
  UI --> EXPORT[Reviewed JSON / SHA-256 / print report]
```

The inspected checkout has a FastAPI service and Vite API proxy; no separate Node API gateway was identified. The executed QA workflows use local SQLite and encrypted uploads, not a live Supabase/PostgreSQL deployment. Supabase client/deployment support exists but was not provisioned or independently verified here. Atlas association remains generic L1; source-image masks do not create patient-specific atlas coordinates.
