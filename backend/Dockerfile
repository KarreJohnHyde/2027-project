FROM python:3.12-slim

WORKDIR /app

# No .git directory is copied; pass the commit so evaluation runs record it.
ARG MEDTWIN_CODE_COMMIT=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DATASET_REGISTRY_PATH=/app/dataset_registry/datasets.json \
    DATASET_TASK_AUDIT_PATH=/app/dataset_registry/tasks.json \
    MODEL_REGISTRY_PATH=/app/model_registry/models.json \
    MEDTWIN_PROJECT_ROOT=/app/project \
    MEDTWIN_CODE_COMMIT=${MEDTWIN_CODE_COMMIT}

# opencv-python (required by the RapidOCR engine) loads libGL and GLib at import time.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-ml.txt ./
RUN python -m pip install --upgrade pip setuptools==84.2.1 \
    && python -m pip install -r requirements.txt \
    && python -m pip install -r requirements-ml.txt

# Production runs an immutable, prebuilt environment. Keep the patched runtime
# dependencies, check consistency, and remove the unused package installer.
RUN python -m pip check && python -m pip uninstall -y pip

COPY backend/app ./app
COPY dataset_registry/datasets.json dataset_registry/tasks.json ./dataset_registry/
COPY dataset_registry/datasets.json dataset_registry/tasks.json dataset_registry/release_context.json ./project/dataset_registry/
COPY ml_training/*.py ./project/ml_training/
COPY model_registry/ ./model_registry/
# Generated evidence read by the research, traceability and anatomy endpoints.
COPY docs/research/traceability.json ./project/docs/research/traceability.json
COPY docs/validation/ ./project/docs/validation/
COPY docs/anatomy/derivatives.json ./project/docs/anatomy/derivatives.json
COPY public/anatomy/manifest.json ./project/public/anatomy/manifest.json
COPY public/anatomy/atlas-index.json ./project/public/anatomy/atlas-index.json
COPY docs/universal/evidence/ ./project/docs/universal/evidence/
COPY benchmarks/results/ ./project/benchmarks/results/

RUN addgroup --system medtwin \
    && adduser --system --ingroup medtwin medtwin \
    && mkdir -p /app/uploads /data/uploads \
    && chown -R medtwin:medtwin /app /data

ENV PYTHONPATH=/app/project

USER medtwin

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
