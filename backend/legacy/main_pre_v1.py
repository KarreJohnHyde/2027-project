from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sqlite3
import statistics
import struct
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("MEDTWIN_DB_PATH", Path(__file__).parent / "medtwin.db"))
FILE_STORE = Path(os.getenv("MEDTWIN_FILE_STORE", Path(__file__).parent / "storage"))
MAX_FILE_BYTES = int(os.getenv("MEDTWIN_MAX_FILE_BYTES", str(50 * 1024 * 1024)))

app = FastAPI(
    title="MedTwin Research API",
    version="0.1.0",
    description="Research-only case storage and traceable report extraction.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin for origin in os.getenv("MEDTWIN_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class ObservationIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    modality: str = Field(pattern="^(Image|ECG|Report)$")
    name: str = Field(min_length=1, max_length=255)
    date: str
    status: str
    summary: str
    confidence: float | None = None
    hash: str
    reportText: str | None = Field(default=None, max_length=1_000_000)


CONCEPTS = {
    "Pulmonary opacity": ("Respiratory", "Lungs", ("opacity", "opacification", "infiltrate")),
    "Pleural effusion": ("Respiratory", "Pleura", ("pleural effusion", "pleural fluid")),
    "Pneumothorax": ("Respiratory", "Pleura", ("pneumothorax",)),
    "Consolidation": ("Respiratory", "Lungs", ("consolidation",)),
    "Cardiomegaly": ("Cardiac", "Heart", ("cardiomegaly", "enlarged heart")),
    "Arrhythmia": ("Cardiac", "Heart", ("arrhythmia", "atrial fibrillation", "irregular rhythm")),
    "Fracture": ("Musculoskeletal", "Skeleton", ("fracture", "osseous injury")),
    "Hemorrhage": ("Neurological", "Brain", ("hemorrhage", "haemorrhage", "bleeding")),
}

METRICS = {
    "Heart rate": (r"(?:heart rate|hr)[:\s]*(\d{2,3})", "bpm"),
    "SpO₂": (r"(?:spo2|oxygen saturation)[:\s]*(\d{2,3})", "%"),
    "Ejection fraction": (r"(?:ejection fraction|ef)[:\s]*(\d{1,3})", "%"),
    "Glucose": (r"glucose[:\s]*(\d{2,3}(?:\.\d+)?)", "mg/dL"),
}


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                modality TEXT NOT NULL,
                name TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                confidence REAL,
                content_hash TEXT NOT NULL,
                report_text TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_observations_case_time
            ON observations(case_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                action TEXT NOT NULL,
                object_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS service_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS anatomical_assets (
                id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                name TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                path TEXT NOT NULL,
                nodes_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        connection.commit()


@app.on_event("startup")
def startup() -> None:
    init_db()
    FILE_STORE.mkdir(parents=True, exist_ok=True)


@app.middleware("http")
async def measure_latency(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - started) * 1000
    try:
        with closing(connect()) as connection:
            connection.execute(
                "INSERT INTO service_events (route, method, status_code, latency_ms, created_at) VALUES (?, ?, ?, ?, ?)",
                (request.url.path, request.method, response.status_code, latency_ms, datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()
    except sqlite3.Error:
        pass
    response.headers["Server-Timing"] = f"app;dur={latency_ms:.2f}"
    return response


def analyze_text(text: str) -> dict:
    findings = []
    for sentence in filter(None, (part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text))):
        lower = sentence.lower()
        for label, (system, region, terms) in CONCEPTS.items():
            term = next((candidate for candidate in terms if candidate in lower), None)
            if not term:
                continue
            index = lower.index(term)
            prefix = lower[max(0, index - 48):index]
            status = "negated" if re.search(r"\b(no|not|without|absent|negative for|free of|resolved)\b", prefix) else "present"
            severity_match = re.search(r"\b(severe|marked|moderate|mild|small|minimal)\b", lower)
            findings.append(
                {
                    "label": label,
                    "system": system,
                    "region": region,
                    "status": status,
                    "severity": severity_match.group(1) if severity_match else "unspecified",
                    "source": sentence,
                }
            )
    metrics = []
    for label, (pattern, unit) in METRICS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            metrics.append({"label": label, "value": float(match.group(1)), "unit": unit, "raw": match.group(0)})
    return {
        "engine": "medtwin-traceable-rules-v1",
        "findings": findings,
        "metrics": metrics,
        "notice": "Research extraction only; not a diagnosis or validated clinical model.",
    }


def extract_report_bytes(filename: str, payload: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension in {".txt", ".md", ".csv"}:
        return payload.decode("utf-8-sig")
    if extension == ".json":
        value = json.loads(payload.decode("utf-8-sig"))
        return value if isinstance(value, str) else json.dumps(value, indent=2)
    if extension == ".pdf":
        from pypdf import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(payload)).pages)
    if extension == ".docx":
        from docx import Document

        return "\n".join(paragraph.text for paragraph in Document(io.BytesIO(payload)).paragraphs)
    raise HTTPException(status_code=415, detail="Supported report formats: PDF, DOCX, JSON, CSV, TXT, MD.")


def parse_gltf_nodes(filename: str, payload: bytes) -> list[str]:
    if filename.lower().endswith(".gltf"):
        document = json.loads(payload.decode("utf-8"))
    elif filename.lower().endswith(".glb"):
        if len(payload) < 20 or payload[:4] != b"glTF":
            raise HTTPException(status_code=422, detail="Invalid GLB header.")
        _, version, total_length = struct.unpack("<4sII", payload[:12])
        if version != 2 or total_length != len(payload):
            raise HTTPException(status_code=422, detail="Only valid glTF 2.0 binary assets are supported.")
        chunk_length, chunk_type = struct.unpack("<II", payload[12:20])
        if chunk_type != 0x4E4F534A:
            raise HTTPException(status_code=422, detail="GLB JSON chunk is missing.")
        document = json.loads(payload[20:20 + chunk_length].decode("utf-8").rstrip("\x00 "))
    else:
        raise HTTPException(status_code=415, detail="Upload a web-ready .glb or .gltf asset.")
    return [node.get("name", f"node_{index}") for index, node in enumerate(document.get("nodes", []))]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return round(ordered[index], 2)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "medtwin-api"}


@app.get("/api/models")
def model_registry() -> dict:
    return {
        "models": [
            {"id": "traceable-nlp-v1", "task": "clinical_nlp", "status": "ready", "validated": False, "runtime": "python_regex"},
            {"id": "linear-forecast-v1", "task": "forecasting_baseline", "status": "ready", "validated": False, "runtime": "python"},
            {"id": "image-classifier", "task": "image_classification", "status": "missing_artifact", "validated": False},
            {"id": "image-localizer", "task": "detection_or_segmentation", "status": "missing_artifact", "validated": False},
            {"id": "ecg-classifier", "task": "ecg_classification", "status": "missing_artifact", "validated": False},
            {"id": "clinical-bert", "task": "clinical_ner", "status": "missing_artifact", "validated": False},
            {"id": "temporal-forecaster", "task": "lstm_or_tft", "status": "missing_artifact", "validated": False},
        ],
        "selection_policy": "A model is selectable only with weights, preprocessing version, label map, calibration metadata, and validation evidence.",
    }


@app.get("/api/metrics/ieee-validation")
def ieee_validation_metrics() -> dict:
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT latency_ms, status_code FROM service_events ORDER BY id DESC LIMIT 1000"
        ).fetchall()
    latencies = [float(row["latency_ms"]) for row in rows]
    failures = sum(1 for row in rows if int(row["status_code"]) >= 400)
    return {
        "paper_claims_results": False,
        "notice": "The IEEE manuscript defines an evaluation protocol but reports no experimental values.",
        "tasks": {
            "image_classification": {"metrics": ["AUROC", "F1", "specificity"], "status": "pending"},
            "detection": {"metrics": ["AP", "mAP", "recall"], "status": "not_run"},
            "segmentation": {"metrics": ["Dice", "IoU"], "status": "not_run"},
            "ecg": {"metrics": ["macro_F1", "AUROC"], "status": "pending"},
            "clinical_nlp": {"metrics": ["entity_precision", "entity_recall", "entity_F1"], "status": "pending"},
            "registration": {"metrics": ["held_out_TRE_mm"], "status": "not_run"},
            "calibration": {"metrics": ["Brier", "ECE"], "status": "pending"},
        },
        "service": {
            "samples": len(latencies),
            "p50_latency_ms": percentile(latencies, .50),
            "p95_latency_ms": percentile(latencies, .95),
            "failure_rate": round(failures / len(rows), 4) if rows else None,
        },
    }


@app.get("/api/cases/{case_id}/observations")
def list_observations(case_id: str) -> list[dict]:
    with closing(connect()) as connection:
        rows = connection.execute(
            "SELECT * FROM observations WHERE case_id = ? ORDER BY created_at DESC", (case_id,)
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/cases/{case_id}/observations")
def store_observation(case_id: str, observation: ObservationIn) -> dict:
    if observation.modality == "Report" and not observation.reportText:
        raise HTTPException(status_code=422, detail="Report text is required for report observations.")
    created_at = datetime.now(timezone.utc).isoformat()
    with closing(connect()) as connection:
        existing = connection.execute(
            "SELECT id FROM observations WHERE case_id = ? AND content_hash = ?",
            (case_id, observation.hash),
        ).fetchone()
        if existing:
            return {"id": existing["id"], "status": "existing", "idempotent": True}
        connection.execute(
            """
            INSERT INTO observations
            (id, case_id, modality, name, observed_at, status, summary, confidence, content_hash, report_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.id, case_id, observation.modality, observation.name, observation.date,
                observation.status, observation.summary, observation.confidence, observation.hash,
                observation.reportText, created_at,
            ),
        )
        connection.execute(
            "INSERT INTO audit_events (case_id, action, object_id, created_at) VALUES (?, ?, ?, ?)",
            (case_id, "observation.created", observation.id, created_at),
        )
        connection.commit()
    analysis = analyze_text(observation.reportText) if observation.reportText else None
    return {"id": observation.id, "status": "stored", "idempotent": False, "analysis": analysis}


@app.post("/api/cases/{case_id}/reports/upload")
async def upload_report(case_id: str, file: UploadFile = File(...), observed_at: str | None = Form(default=None)) -> dict:
    payload = await file.read(MAX_FILE_BYTES + 1)
    if len(payload) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds configured size limit.")
    text = extract_report_bytes(file.filename or "report.txt", payload).strip()
    if not text:
        raise HTTPException(status_code=422, detail="No extractable report text was found.")
    digest = hashlib.sha256(payload).hexdigest()
    case_directory = FILE_STORE / re.sub(r"[^a-zA-Z0-9_-]", "_", case_id)
    case_directory.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename or "report.txt")
    stored_path = case_directory / f"{digest[:12]}_{safe_name}"
    stored_path.write_bytes(payload)
    analysis = analyze_text(text)
    observation = ObservationIn(
        id=str(uuid.uuid4()),
        modality="Report",
        name=safe_name,
        date=observed_at or datetime.now(timezone.utc).isoformat(),
        status="Review" if any(item["status"] == "present" for item in analysis["findings"]) else "Ready",
        summary=f'{len(analysis["findings"])} findings and {len(analysis["metrics"])} metrics extracted.',
        hash=digest,
        reportText=text,
    )
    stored = store_observation(case_id, observation)
    return {**stored, "file": {"name": safe_name, "bytes": len(payload), "sha256": digest}, "analysis": analysis}


@app.post("/api/cases/{case_id}/anatomy-assets")
async def upload_anatomy_asset(case_id: str, file: UploadFile = File(...)) -> dict:
    payload = await file.read(MAX_FILE_BYTES + 1)
    if len(payload) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds configured size limit.")
    name = file.filename or "anatomy.glb"
    nodes = parse_gltf_nodes(name, payload)
    digest = hashlib.sha256(payload).hexdigest()
    asset_id = str(uuid.uuid4())
    case_directory = FILE_STORE / re.sub(r"[^a-zA-Z0-9_-]", "_", case_id) / "anatomy"
    case_directory.mkdir(parents=True, exist_ok=True)
    stored_path = case_directory / f"{digest[:12]}_{re.sub(r'[^a-zA-Z0-9._-]', '_', name)}"
    stored_path.write_bytes(payload)
    with closing(connect()) as connection:
        connection.execute(
            "INSERT INTO anatomical_assets (id, case_id, name, content_hash, path, nodes_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (asset_id, case_id, name, digest, str(stored_path), json.dumps(nodes), datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()
    return {
        "id": asset_id,
        "name": name,
        "sha256": digest,
        "nodes": nodes,
        "mapping_status": "registry_ready" if nodes else "no_named_nodes",
        "localization_status": "mapping_unsupported_until_registration_validation",
    }


@app.post("/api/analyze/compare")
def compare_report_payload(payload: dict) -> dict:
    previous_text = str(payload.get("previous_text", ""))
    current_text = str(payload.get("current_text", ""))
    if not previous_text.strip() or not current_text.strip():
        raise HTTPException(status_code=422, detail="Both previous_text and current_text are required.")
    previous = analyze_text(previous_text)
    current = analyze_text(current_text)
    previous_keys = {(item["label"], item["status"]) for item in previous["findings"]}
    current_keys = {(item["label"], item["status"]) for item in current["findings"]}
    old_metrics = {item["label"]: item for item in previous["metrics"]}
    deltas = []
    for metric in current["metrics"]:
        old = old_metrics.get(metric["label"])
        if not old:
            continue
        delta = metric["value"] - old["value"]
        deltas.append({
            **metric,
            "previous": old["value"],
            "delta": round(delta, 3),
            "percent_change": round(delta / abs(old["value"]) * 100, 3) if old["value"] else None,
        })
    return {
        "added": [item for item in current["findings"] if (item["label"], item["status"]) not in previous_keys],
        "removed": [item for item in previous["findings"] if (item["label"], item["status"]) not in current_keys],
        "persistent": [item for item in current["findings"] if (item["label"], item["status"]) in previous_keys],
        "metric_deltas": deltas,
    }


@app.post("/api/forecast/baseline")
def forecast_baseline(payload: dict) -> dict:
    values = payload.get("values", [])
    horizon_days = int(payload.get("horizon_days", 30))
    if not isinstance(values, list) or len(values) < 3 or not all(isinstance(value, (int, float)) for value in values):
        return {"status": "not_eligible", "reason": "At least three comparable numeric observations are required."}
    x_values = list(range(len(values)))
    x_mean = statistics.mean(x_values)
    y_mean = statistics.mean(values)
    denominator = sum((value - x_mean) ** 2 for value in x_values)
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values)) / denominator
    predicted = values[-1] + slope * max(1, horizon_days / 30)
    return {
        "status": "baseline_only",
        "model": "ordinary_least_squares",
        "horizon_days": horizon_days,
        "prediction": round(predicted, 3),
        "notice": "A validated LSTM/TFT artifact was not found; this is the paper-required linear baseline.",
    }


@app.websocket("/ws/telemetry/{case_id}")
async def telemetry(websocket: WebSocket, case_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            message = await websocket.receive_text()
            await websocket.send_json({
                "case_id": case_id,
                "event": "edge.telemetry",
                "received": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pipeline": {"nlp": "ready", "deep_models": "no_validated_artifact", "registration": "not_eligible"},
            })
    except WebSocketDisconnect:
        return


@app.post("/api/analyze/report")
def analyze_report(payload: dict) -> dict:
    text = payload.get("text", "")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=422, detail="A non-empty text field is required.")
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"sha256": content_hash, **analyze_text(text)}
