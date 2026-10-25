"""
System Telemetry, Health, and Audit Inspection Router.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
import psutil
import torch
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.config import ANATOMY_MANIFEST_PATH, PROJECT_NAME, UPLOAD_DIR, VERSION, RESEARCH_ONLY_NOTICE
from app.database import engine, get_db
from app.migrations import migration_status
from app.services import job_queue, upload_store
from app.services.model_registry import list_models
from app.models.entities import Case, Finding, AuditEvent, QueuedJob, User, UserRole
from app.schemas.entities import SystemHealthResponse, AuditEventResponse
from app.services.auth import get_current_user, require_role

router = APIRouter(prefix="/system", tags=["System & Telemetry"])


@router.get("/health", response_model=SystemHealthResponse)
@router.get("/status")
def get_system_health(db: Session = Depends(get_db)):
    """
    Returns framework telemetry, PyTorch CUDA status, and database statistics.
    """
    cuda_avail = torch.cuda.is_available()
    gpu_name = torch.cuda.get_device_name(0) if cuda_avail else None

    cases_count = db.query(Case).count()
    findings_count = db.query(Finding).count()

    return {
        "status": "HEALTHY",
        "app_name": PROJECT_NAME,
        "project": PROJECT_NAME,
        "version": VERSION,
        "cuda_available": cuda_avail,
        "gpu_name": gpu_name,
        "research_notice": RESEARCH_ONLY_NOTICE,
        "notice": RESEARCH_ONLY_NOTICE,
        "database_status": "CONNECTED",
        "health_scope": "API_AND_DATABASE_ONLY",
        "active_cases": cases_count,
        "active_cases_count": cases_count,
        "total_findings": findings_count,
        "models_status": {
            "image_classifier": "MODEL_UNAVAILABLE",
            "ecg_classifier": "MODEL_UNAVAILABLE",
            "clinical_nlp": "RULE_BASELINE_AVAILABLE_UNVALIDATED",
            "gated_fusion": "PENDING_PAIRED_DATA_AND_MODEL_VALIDATION",
            "registration_gate": "MAPPING_UNSUPPORTED_WITHOUT_VERIFIED_LANDMARK_MANIFEST"
        }
    }


@router.get("/readiness")
def get_readiness(db: Session = Depends(get_db)):
    """Readiness: database reachable, migrations applied, storage writable, registries loadable.

    Optional AI components are reported but never make the service unready.
    """
    checks = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"ready": True}
    except Exception as exc:
        checks["database"] = {"ready": False, "error": type(exc).__name__}
    migrations = migration_status(engine)
    checks["migrations"] = {"ready": not migrations["pending"], **migrations}
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        probe = UPLOAD_DIR / ".readiness-probe"
        probe.write_bytes(b"ok")
        probe.unlink()
        checks["upload_storage"] = {"ready": True}
    except OSError as exc:
        checks["upload_storage"] = {"ready": False, "error": type(exc).__name__}
    try:
        checks["model_registry"] = {"ready": True, "models": list_models()["model_count"]}
    except Exception as exc:
        checks["model_registry"] = {"ready": False, "error": str(exc)}
    checks["anatomy_manifest"] = {"ready": ANATOMY_MANIFEST_PATH.exists(), "optional": True}
    try:
        checks["storage_encryption"] = upload_store.readiness()
    except Exception as exc:  # malformed key configuration
        checks["storage_encryption"] = {"ready": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        counts = dict(db.query(QueuedJob.status, func.count(QueuedJob.id)).group_by(QueuedJob.status).all())
        oldest = db.query(func.min(QueuedJob.created_at)).filter(QueuedJob.status == "QUEUED").scalar()
        checks["job_queue"] = {"ready": True, "execution_mode": job_queue.execution_mode(), "counts": counts,
                               "oldest_queued_at": oldest.isoformat() if oldest else None, "optional": True}
    except Exception as exc:
        checks["job_queue"] = {"ready": False, "error": type(exc).__name__, "optional": True}
    required = ("database", "migrations", "upload_storage", "model_registry", "storage_encryption")
    return {"ready": all(checks[name]["ready"] for name in required), "checks": checks}


@router.get("/gpu")
def get_gpu_telemetry(current_user: User = Depends(get_current_user)):
    """Device inventory and memory. No model is resident: models load on demand only."""
    process = psutil.Process()
    memory = psutil.virtual_memory()
    payload = {
        "cuda_available": torch.cuda.is_available(),
        "torch_version": torch.__version__,
        "cuda_build": torch.version.cuda,
        "host_memory": {"total_bytes": memory.total, "available_bytes": memory.available, "process_rss_bytes": process.memory_info().rss},
        "loaded_models": [],
        "inference_concurrency_limit": 1,
    }
    if torch.cuda.is_available():
        free, total = torch.cuda.mem_get_info()
        payload["device"] = {
            "name": torch.cuda.get_device_name(0),
            "capability": list(torch.cuda.get_device_capability(0)),
            "memory_total_bytes": total,
            "memory_free_bytes": free,
            "memory_allocated_by_process_bytes": torch.cuda.memory_allocated(0),
        }
    return payload


@router.get("/audit", response_model=List[AuditEventResponse])
def get_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN))
):
    """
    Inspects persisted audit logs. The current database rows are not a
    cryptographically tamper-evident retention system.
    Clinical report text is not copied into these audit responses.
    """
    logs = db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(limit).all()
    return logs
