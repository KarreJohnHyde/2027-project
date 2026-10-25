# MedTwin Workspace Audit & Asset Manifest

> Historical inventory. The verified status and claim boundaries are maintained in `docs/testing/EXECUTED_TEST_RESULTS.md` and `docs/implementation_status.md`. Source presence or adapter code in this file must not be interpreted as completed clinical validation.

**Date:** October 2026  
**Audited Directory:** `d:\project`  
**Research Specification:** *MedTwin: A Real-Time Multimodal Digital Twin Framework for 3D Anatomical Tracking and Disease Forecasting* (IEEE Manuscript, Sathyabama Institute of Science and Technology, 2026).

---

## 1. Directory Structure

```
d:\project
├── backend/
│   ├── app/
│   │   ├── models/            # SQLAlchemy entity models (User, Case, Exam, UploadedFile, Finding, etc.)
│   │   ├── routers/           # FastAPI modular endpoints (auth, cases, files, analysis, fusion, anatomy, etc.)
│   │   ├── schemas/           # Pydantic v2 validation contracts
│   │   ├── services/          # Pure computational services (fusion, registration, forecasting, etc.)
│   │   ├── config.py          # Centralized configuration & environment constants
│   │   ├── database.py        # SQLAlchemy session & SQLite/Postgres engine
│   │   └── main.py            # FastAPI ASGI app entry point & seed initialization
│   ├── tests/                 # Pytest test suite (22 unit & integration tests)
│   ├── uploads/               # Controlled server-side file store
│   └── run.py                 # Backend launch script (uvicorn)
├── src/
│   ├── components/            # React 19 UI components & 3D Three.js canvas
│   ├── services/              # Typed API client (api.ts)
│   ├── types/                 # TypeScript interfaces (medtwin.ts)
│   ├── App.tsx                # Primary view router & application orchestrator
│   └── main.tsx               # React DOM entry point
├── public/
│   └── models/                # Converted Blender GLB anatomical assets (Untitled.glb - Untitled3.glb)
├── Untitled.blend - Untitled3.blend # Native Blender 3D scene files
├── inspect_blend.py           # Headless Blender inspection utility
├── export_blend_to_glb.py     # Headless Blender GLB conversion script
├── docker-compose.yml         # Container orchestration manifest
├── Dockerfile.frontend        # Multi-stage frontend container specification
├── package.json               # Node.js dependencies
└── pytest.ini                 # Python test configuration
```

---

## 2. Startup, Build & Test Commands

| Layer | Action | Command | Status |
| :--- | :--- | :--- | :--- |
| **Backend** | Start Service | `.\.venv\Scripts\python.exe backend/run.py` | Working (`http://127.0.0.1:8000`) |
| **Backend** | Run Tests | `.\.venv\Scripts\python.exe -m pytest backend/tests -v` | **26/26 Passing (100%)** |
| **Frontend** | Dev Server | `npm run dev` | Working (`http://localhost:5173`) |
| **Frontend** | Typecheck & Build | `npm run build` (`tsc -b && vite build`) | **Zero Errors (Code 0)** |
| **Frontend** | Linter | `npm run lint` (`oxlint`) | **0 Errors, 0 Warnings** |
| **Blender** | Scene Inspection | `.\.venv\Scripts\python.exe inspect_blend.py --all` | Verified via Blender 5.2.2 LTS |

---

## 3. Database Schema & Persistence

- **Engine:** SQLite (WAL mode, Foreign Keys enforced, in `backend/medtwin.db`).
- **PostgreSQL Compatibility:** Fully defined with standard SQLAlchemy types for multi-user production deployments.
- **Seeded Demo Accounts:**
  - `clinician` (`CLINICIAN`, `ChangeMe123!`)
  - `researcher` (`RESEARCHER`, `ChangeMe123!`)
  - `admin` (`ADMIN`, `ChangeMe123!`)
- **Core Entities:** `User`, `Case`, `Examination`, `UploadedFile`, `InferenceRun`, `Finding`, `ClinicalReportStatement`, `MultimodalFusionRecord`, `ConcordanceRecord`, `AnatomicalAsset`, `AnatomicalMapping`, `ForecastRecord`, `HumanReview`, `AuditEvent`, `OrderedPackage`, `LabInvestigationReport`.

---

## 4. 3D Anatomical Assets Inventory (Verified via Blender 5.2.2 LTS)

| Blend File | GLB File | Size | Mesh Objects & Hierarchy |
| :--- | :--- | :--- | :--- |
| `Untitled.blend` | `public/models/Untitled.glb` | 15.2 MB | 18 Objects, 6 Meshes (`Object_30.001-002`, `Icosphere.001-002`), Armatures `GLTF_created_0` |
| `Untitled1.blend` | `public/models/Untitled1.glb` | 106.7 MB | 44 Objects, 41 Meshes (`Object_2` to `Object_42`, up to 65,533 vertices per node) |
| `Untitled2.blend` | `public/models/Untitled2.glb` | 11.6 MB | 8 Objects, 2 Meshes (`Object_30`, `Icosphere`), Armature `GLTF_created_0`, Empty `heart.2_2` |
| `Untitled3.blend` | `public/models/Untitled3.glb` | 106.9 MB | 36 Objects, 30 Meshes (`defaultMaterial` to `defaultMaterial.029`, 65,532 vertices each) |

---

## 5. Available Datasets & Model Checkpoints

- **Musculoskeletal Radiographs:** Evaluated under MURA protocol. ResNet architecture implemented; demo/uncalibrated state explicitly flagged.
- **Digital ECG Records:** Evaluated under PTB-XL & MIT-BIH protocol. 1-D CNN rhythm classifier adapter implemented with bSQI signal quality gate.
- **Clinical NLP Corpus:** Evaluated under BioClinical-BERT entity extraction with rule-based NegEx negation parser and character offset spans.
- **Paired Multimodal Records:** Note: No public hospital dataset provides genuine triplet pairs across all three modalities for identical patient timestamps. Masked gated fusion enforces paired-data validation; synthetic fixtures test arithmetic masking mechanics only.
