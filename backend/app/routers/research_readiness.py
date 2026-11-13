"""Authenticated measured-readiness summary, without case/private report disclosure."""
from fastapi import APIRouter, Depends
from app.models.entities import User, UserRole
from app.schemas.research_readiness import ResearchReadinessResponse
from app.services.auth import get_current_user
from app.services.research_readiness import readiness_summary

router = APIRouter(tags=["Measured research readiness"])


@router.get("/universal/research/readiness", response_model=ResearchReadinessResponse)
def measured_readiness(current_user: User = Depends(get_current_user)):
    return readiness_summary(independent_admin=current_user.role == UserRole.ADMIN and not current_user.is_guest)
