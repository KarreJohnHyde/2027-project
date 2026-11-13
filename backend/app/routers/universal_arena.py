"""Authenticated read-only public research artifacts; no private case input."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from app.models.entities import User
from app.services.auth import get_current_user
from app.services import universal_arena

router = APIRouter(prefix="/universal/arena", tags=["Universal research arena"])

class ComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left_id: str = Field(min_length=1, max_length=128)
    right_id: str = Field(min_length=1, max_length=128)

@router.get("/models")
def models(current_user: User = Depends(get_current_user)):
    return universal_arena.list_models()


@router.get("/models/{model_id}/diagnostics")
def diagnostics(model_id: str, arm: Literal["ecg_only", "fusion"] | None = None, current_user: User = Depends(get_current_user)):
    try:
        return universal_arena.diagnostics(model_id, arm)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown research model.") from None

@router.post("/compare")
def compare(request: ComparisonRequest, current_user: User = Depends(get_current_user)):
    try:
        return universal_arena.compare_models(request.left_id, request.right_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown research model.") from None
