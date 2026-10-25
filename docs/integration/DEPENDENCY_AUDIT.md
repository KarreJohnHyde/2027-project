# Dependency and compatibility audit

Snapshot date: 2026-10-23  
Scope: installed environments plus dependency manifests in the repositories named by the MedTwin master prompt.

## Executive finding

The current CUDA/PyTorch environment can support controlled research inference, but it is not a universal environment for all supplied repositories. MedCAT v1 and scispaCy require NumPy below 2, while the canonical environment and CogStack MedCAT v2 use NumPy 2. SemEHR requires Python 2.7, and the longitudinal research repositories require model/data/hardware resources that are absent. The safe design is a small canonical API plus optional, versioned adapters in separate environments or containers.

No external clinical model is classified as operational. Source code, framework imports, example data, and example adapters are insufficient without the activation artifact bundle.

## Local toolchain evidence

| Environment/tool | Observed state | Use |
|---|---|---|
| System Node.js | `v24.22.1`; npm `11.19.1` | Compatible with canonical Vite app; root `package.json` requires Node >=22.12 |
| `.venv` | CPython `3.12.15`; no `pip` module; uv-style environment; `pypdf 5.5.0` and `python-docx 1.1.2` installed with `uv pip` | Canonical local backend/GPU research environment; use `uv` for deliberate pinned changes |
| `.venv-medtw` | CPython `3.12.10`; pip `26.2.2`; NumPy/PyTorch absent | Minimal candidate environment, not proof of a service installation |
| `.venv-blender` | CPython `3.13.13`; `torch` and importable `bpy` absent | Do not treat as the Blender runtime; `bpy` is available only inside Blender's embedded executable |
| Blender | `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` | Use explicitly for controlled export/inspection jobs |
| `.mise.toml` | Requests Node 22 and pnpm 10.34.3 | `mise` itself was not located in this pass |

### Installed GPU stack in `.venv`

| Package/check | Observed result |
|---|---|
| NumPy | `2.5.2` |
| PyTorch | `2.14.1+cu130` |
| PyTorch CUDA runtime | `13.0` |
| `torch.cuda.is_available()` | `True` |
| GPU | NVIDIA GeForce RTX 5060 Laptop GPU |
| torchvision | `0.29.1+cu130` |
| torchaudio | `2.11.0+cu130` |
| MONAI source import | Successful from `MONAI-dev`, version reported as `0+unknown` |

PyTorch CUDA availability was directly queried; it is not inferred from `nvidia-smi`. The environment audit performed before this documentation pass also completed a CUDA tensor operation and a small MONAI CUDA forward pass. That establishes framework execution only. It does not establish that any medical task model, checkpoint, preprocessing pipeline, or performance claim is operational.

The `torch`/`torchvision` versions align by release family, while `torchaudio 2.11.0` is version-skewed from `torch 2.14.1`. Pin a mutually supported trio before audio/ECG work. The current `.venv` has no importable `medcat`, `scispacy`, `radgraph`, `spacy`, `transformers`, `pydicom`, `nibabel`, `SimpleITK`, or installed `monai` distribution.

## Canonical application dependencies

### Frontend

The root app uses React 19, Vite 8, TypeScript 5.7, Tailwind 4, Three.js, React Three Fiber/Drei, Recharts, PDF.js, Mammoth, Framer Motion, and Zustand. Root scripts provide `typecheck`, `lint`, `build`, and the combined `check` command. This is the only frontend that should receive application changes.

### Backend

`backend/requirements.txt` pins FastAPI 0.159.1, Uvicorn 0.54.0, SQLAlchemy 2.1.6, multipart handling, JOSE/cryptography, bcrypt, NumPy 2.5.2, Pillow, pypdf, and python-docx. Imaging/ML wheels live behind a separate requirements boundary. Keep that split: document/case APIs should start even when an optional medical model adapter is unavailable.

The missing local document packages were installed during integration and then exercised against both supplied MedTwin and DeepSA PDF files, the supplied MedTwin DOCX manuscript, an in-memory DOCX fixture, and an image-only PDF rejection fixture. This verifies embedded-text PDF and DOCX parser execution; it does not provide OCR for scanned PDFs or clinical extraction accuracy.

## External component compatibility

| Component | Manifest constraints and services | Compatibility result | Required boundary |
|---|---|---|---|
| MONAI-dev | Python >=3.10, PyTorch >=2.8, NumPy >=1.24,<3 | Core packages are compatible and source import works; no task checkpoint exists | Direct library only through a versioned imaging adapter and complete artifact bundle |
| scispacy-main | Python >=3.9,<3.13, spaCy >=3.7,<3.9, NumPy <2, nmslib, separately downloaded language model | Incompatible with core NumPy 2.5.2; no model installed | Separate Python 3.12/NumPy 1.26 environment or container |
| MedCAT-main (v1) | Python >=3.9, NumPy >=1.26,<2, spaCy 3, Transformers, PyTorch; external UMLS/SNOMED model pack | Incompatible with core NumPy; no model pack; license metadata conflict | Separate Python 3.12/NumPy 1.26 service; do not activate until model terms and evaluation are complete |
| cogstack-nlp MedCAT v2 | Python >=3.10, NumPy >=2 on Python 3.12, optional spaCy/meta-cat dependencies | Base dependency direction fits NumPy 2, but this is a large monorepo and no model pack is configured | Independently pinned service image; select v1 or v2 experimentally rather than installing both blindly |
| radgraph-master | Python >=3.8, PyTorch >=2.1, Transformers >=4.39, h5py/nltk/dotmap; model download/cache required | Package absent and local weights absent | Isolated radiology NLP service with immutable model cache and offline evaluation |
| CogStack-SemEHR | Python 2.7.13, 2017-era NumPy/SciPy, Elasticsearch 7, Bio-Yodie/GATE, R | Incompatible and archived | Disabled/reference-only; port concepts, not runtime |
| health-assistant-main | Modern FastAPI, Celery, PostgreSQL, Redis, FHIR, optional spaCy/scispaCy/Transformers/Torch, React 18 | Technically runnable as a separate platform, but duplicates MedTwin and has a large service footprint | Narrow contract adapter or reference implementation only |
| metriport-develop | Node/TypeScript monorepo; PostgreSQL, DynamoDB, OpenSearch, AWS/HIE credentials; Unix-oriented scripts | Not appropriate inside the canonical Node process; licensing varies by package | Deferred FHIR/CDA adapter or separate deployment after legal/security review |
| TwinWeaver-main | Core includes pandas, Transformers, OpenAI, and vLLM; fine-tuning pins torch 2.9.1; advanced example states >=30 GB GPU | Current GPU is about 8 GB; vLLM is not validated on this Windows host; bundled LoRA artifact is incomplete | Disabled research environment until a defined target/data/artifact exists |
| Foresight-main.zip | Transformers, Datasets, flash-attn; MIMIC-style data; malformed setup metadata | Archive-only, no checkpoint, no tests, package/dependency declaration broken | Reference-only reproducibility project, never a default adapter |
| 3d-anatomy-atlas-main | Node >=22.12, pnpm 10, WebGL2 | Toolchain-compatible but CPAL attribution and pending data audit matter | Asset adapter only after per-asset licensing/anatomy review |
| human-atlas-main | Node >=22.13, Three.js, meshoptimizer; custom compressed BodyParts3D buffers | Toolchain-compatible; custom loader required | Asset-source adapter with CC-BY attribution; L1 reference only |
| anatomy-main | Node >=22.13, vinext/Next/Three.js | Could run technically, but no root license or model provenance was found | Disabled pending legal provenance |
| SIH_26047-main | Python >=3.11, FastAPI, PostgreSQL/pgvector, OCR, Google GenAI; React 18/Vite 5 | Overlapping full app and remote AI dependency; no root license | Reference patterns only |
| medical-main | Node built-ins, static HTML/JS, in-memory demos | Runs as a demo but violates canonical auth/evidence requirements | Disabled/reference-only |
| medvault-ai-main | FastAPI/pypdf/ReportLab/Pillow; in-memory global state and sample records | Useful parser ideas, not production-safe or evaluated | Reference-only until extracted into tested pure functions |

## Checkpoint and model evidence

- MONAI is a framework checkout; no brain, lung, GI, detection, or segmentation checkpoint was found.
- scispaCy source is present; no version-matched `en_core_sci_*` or task-specific NER model is installed.
- MedCAT v1 source is present; no usable production model pack is present. The small example CDB/vocabulary files are test resources, not production artifacts.
- CogStack NLP contains legacy example CDB files but no validated production MedTwin model pack.
- RadGraph source is present; model weights/cache are absent.
- TwinWeaver includes two 8,929,696-byte LoRA adapter files. Their generated model cards omit training data, license, intended use, limitations, and evaluation, and the base model is absent. They are therefore disabled.
- Foresight has no checkpoint in its archive.
- Human Atlas `.bin` files are geometry buffers, not neural-network weights.

## Environment boundary recommendation

Do not install all repositories into `.venv`. Use these logical boundaries when a concrete experiment is approved:

1. `medtwin-core-py312`: canonical FastAPI/document processing, NumPy 2, no optional NLP model.
2. `medtwin-imaging-py312-cu`: pinned PyTorch/torchvision/MONAI with one task adapter loaded lazily; CPU fallback and VRAM budget.
3. `medtwin-nlp-numpy1-py312`: scispaCy and/or MedCAT v1 with NumPy 1.26, exact spaCy/model pins, no access to clinical data until evaluation passes.
4. `medtwin-medcat-v2-py312`: only if v2 wins the benchmark; NumPy 2 and its own model pack.
5. `medtwin-radgraph`: separate immutable environment/image because of Transformers/model-cache requirements.
6. Legacy/research components (SemEHR, Foresight, TwinWeaver) remain disabled unless promoted by a dedicated reproducibility protocol.

Each service must return a common result envelope containing case/job identifiers, input SHA-256, adapter/version, preprocessing version, artifact/checkpoint hash, timestamps, source spans or spatial evidence, calibrated uncertainty when available, abstention state, limitations, and verification status.

## Activation checklist

An adapter remains unavailable in the UI until all items are present:

- compatible and locked environment;
- source and model licenses;
- task/label definition;
- dataset version and patient/study split manifest;
- preprocessing version;
- checkpoint SHA-256;
- held-out predictions and evaluation report;
- calibration parameters and decision/abstention thresholds;
- model card and limitations;
- deterministic smoke test plus success/failure integration tests; and
- resource envelope for CPU, GPU VRAM, latency, memory, and concurrency.

This dependency audit supports integration planning. It is not a medical-device, privacy, security, or clinical validation assessment.
