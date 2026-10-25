"""Research analytics and manuscript traceability."""

from __future__ import annotations

from collections import Counter
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.database import get_db
from app.models.entities import User
from app.services.analytics_service import research_overview
from app.services.auth import get_current_user

router = APIRouter(tags=["Research Analytics"])
TRACEABILITY_PATH = PROJECT_ROOT / "docs" / "research" / "traceability.json"


@router.get("/analytics/research")
def get_research_analytics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Charts computed from real workspace artifacts, each with its provenance."""
    return research_overview(db, current_user)


@router.get("/research/traceability")
def get_traceability(current_user: User = Depends(get_current_user)):
    try:
        payload = json.loads(TRACEABILITY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "NOT_AVAILABLE", "reason": "docs/research/traceability.json has not been generated.", "claims": []}
    payload["status_counts"] = dict(Counter(claim["status"] for claim in payload.get("claims", [])))
    return payload
