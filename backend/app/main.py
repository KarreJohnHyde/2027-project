"""Canonical FastAPI entrypoint for the MedTwin research application."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import (
    API_PREFIX,
    CORS_ORIGINS,
    DEBUG,
    DESCRIPTION,
    DEV_SEED_CASE_ENABLED,
    DEV_SEED_EMAIL,
    DEV_SEED_ENABLED,
    DEV_SEED_FULL_NAME,
    DEV_SEED_PASSWORD,
    DEV_SEED_ROLE,
    DEV_SEED_USERNAME,
    ENVIRONMENT,
    PROJECT_NAME,
    VERSION,
)
from app.database import Base, SessionLocal, engine, get_db, schema_lock
from app.migrations import run_migrations
from app.models.entities import (
    AnatomicalAsset,
    Case,
    RepresentationLevel,
    User,
    UserRole,
    VerificationStatus,
)
from app.routers import (
    analysis,
    anatomy,
    anatomy_studio,
    auth,
    cases,
    demographics,
    catalog,
    comparison,
    concordance,
    evaluation,
    files,
    findings,
    forecast,
    fusion,
    jobs,
    members,
    metrics,
    modalities,
    portal,
    prognosis,
    provenance,
    queue,
    registry,
    datasets,
    research,
    research_models,
    reviews,
    system,
)
from app.request_context import REQUEST_ID_HEADER, get_request_id
from app.security import RequestIdMiddleware, SecurityHeadersMiddleware
from app.services import upload_store
from app.services.auth import get_password_hash
from app.services.anatomy_registry import REFERENCE_ASSETS


logger = logging.getLogger(__name__)


def seed_reference_assets(db: Session) -> None:
    """Register generic L1 reference assets; never imply patient-specific anatomy."""
    changed = False
    for definition in REFERENCE_ASSETS:
        exists = db.query(AnatomicalAsset).filter(
            AnatomicalAsset.asset_path == definition["asset_path"]
        ).first()
        if exists:
            continue
        db.add(
            AnatomicalAsset(
                **definition,
                format="glb",
                representation_level=RepresentationLevel.L1_GENERIC,
                is_available=True,
            )
        )
        changed = True
    if changed:
        db.commit()


def seed_development_data(db: Session) -> None:
    """Create an opt-in development user (and optional empty case) from environment values."""
    if not DEV_SEED_ENABLED:
        return
    if ENVIRONMENT not in {"development", "test"}:
        raise RuntimeError("DEV_SEED_ENABLED is allowed only in development or test environments.")
    if not DEV_SEED_USERNAME or not DEV_SEED_PASSWORD or not DEV_SEED_EMAIL:
        raise RuntimeError(
            "DEV_SEED_USERNAME, DEV_SEED_PASSWORD, and DEV_SEED_EMAIL are required when DEV_SEED_ENABLED=true."
        )
    if len(DEV_SEED_PASSWORD) < 12:
        raise RuntimeError("DEV_SEED_PASSWORD must contain at least 12 characters.")

    try:
        role = UserRole(DEV_SEED_ROLE)
    except ValueError as exc:
        allowed = ", ".join(role.value for role in UserRole)
        raise RuntimeError(f"DEV_SEED_ROLE must be one of: {allowed}.") from exc

    user = db.query(User).filter(User.username == DEV_SEED_USERNAME).first()
    if user is None:
        user = User(
            username=DEV_SEED_USERNAME,
            email=DEV_SEED_EMAIL,
            hashed_password=get_password_hash(DEV_SEED_PASSWORD),
            full_name=DEV_SEED_FULL_NAME,
            role=role,
            verification_status=(
                VerificationStatus.UNVERIFIED
                if role == UserRole.PUBLIC
                else VerificationStatus.VERIFIED
            ),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if DEV_SEED_CASE_ENABLED:
        existing = db.query(Case).filter(Case.created_by_id == user.id).first()
        if existing is None:
            today_prefix = f"DEV-{datetime.now(timezone.utc):%Y%m%d}"
            seq = 1
            while db.query(Case).filter(Case.pseudonymous_id == f"{today_prefix}-{seq:03d}").first() is not None:
                seq += 1
            db.add(
                Case(
                    pseudonymous_id=f"{today_prefix}-{seq:03d}",
                    patient_ref=None,
                    description="De-identified development case. No clinical inference has been run.",
                    created_by_id=user.id,
                )
            )
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    with schema_lock(engine):
        Base.metadata.create_all(bind=engine)
        run_migrations(engine)
    upload_store.startup_cleanup()
    with SessionLocal() as db:
        seed_reference_assets(db)
        seed_development_data(db)
    yield


app = FastAPI(
    title=PROJECT_NAME,
    version=VERSION,
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-MedTwin-Render", REQUEST_ID_HEADER],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIdMiddleware)

for router in (
    auth.router,
    members.router,
    portal.router,
    cases.router,
    demographics.router,
    files.router,
    analysis.router,
    jobs.router,
    queue.router,
    findings.router,
    provenance.router,
    registry.router,
    datasets.router,
    fusion.router,
    concordance.router,
    anatomy.router,
    forecast.router,
    reviews.router,
    system.router,
    catalog.router,
    comparison.router,
    metrics.router,
    anatomy_studio.router,
    modalities.router,
    prognosis.router,
    evaluation.router,
    research.router,
    research_models.router,
):
    app.include_router(router, prefix=API_PREFIX)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    """Unversioned infrastructure probe; product resources live below /api/v1."""
    from app.routers.system import get_system_health

    return get_system_health(db=db)


@app.get("/")
def root():
    return {
        "framework": PROJECT_NAME,
        "version": VERSION,
        "status": "ONLINE",
        "api_prefix": API_PREFIX,
        "api_docs": "/docs",
        "research_notice": (
            "MedTwin is a software-only research prototype. "
            "It is not a validated diagnostic device or a replacement for clinical judgment."
        ),
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = get_request_id(request)
    logger.exception(
        "Unhandled request failure on %s [request_id=%s]",
        request.url.path,
        request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers={REQUEST_ID_HEADER: request_id} if request_id else None,
        content={
            "error": "InternalServerError",
            "message": str(exc) if DEBUG else "The request could not be completed.",
            "path": request.url.path,
            "request_id": request_id,
        },
    )
