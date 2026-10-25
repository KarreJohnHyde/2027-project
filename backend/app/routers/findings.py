"""
Findings Retrieval Router for MedTwin.
Provides access to case findings, statements, and evidence provenance.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Finding, User
from app.schemas.entities import FindingResponse
from app.services.auth import get_current_user, verify_case_access

router = APIRouter(tags=["Evidence & Findings"])


@router.get("/cases/{case_id}/findings", response_model=List[FindingResponse])
def get_case_findings(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = verify_case_access(case_id, current_user, db, access="read")
    return case.findings


@router.get("/findings/{finding_id}", response_model=FindingResponse)
def get_finding_detail(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")

    verify_case_access(finding.case_id, current_user, db, access="read")
    return finding
