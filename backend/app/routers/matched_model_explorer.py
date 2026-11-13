"""Authenticated, read-only exploration of permitted matched public records."""
from fastapi import APIRouter, Depends
from app.models.entities import User
from app.services.auth import get_current_user
from app.schemas.matched_model_explorer import MatchedRecordsQuery, MatchedRecordsResponse
from app.services.matched_model_explorer import query_records

router = APIRouter(prefix="/universal/research/matched-records", tags=["Matched model record explorer"])


@router.post("/query", response_model=MatchedRecordsResponse)
def records(request: MatchedRecordsQuery, current_user: User = Depends(get_current_user)):
    return query_records(request)
