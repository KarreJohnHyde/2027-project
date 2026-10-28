"""Case sharing: explicit memberships managed by the case creator or an admin."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Case, CaseMembership, User, UserRole
from app.services.audit_service import log_audit_event
from app.services.auth import get_current_user, verify_case_access

router = APIRouter(prefix="/cases", tags=["Case Membership"])


class MembershipCreate(BaseModel):
    username: str = Field(..., max_length=64)
    # PATIENT and CAREGIVER open only the read-only portal (app/routers/portal.py), never the clinical endpoints.
    role: Literal["VIEWER", "EDITOR", "PATIENT", "CAREGIVER"]


def _require_owner(case: Case, user: User) -> None:
    if user.role != UserRole.ADMIN and case.created_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the case creator or an admin can manage members.")


def _serialize(membership: CaseMembership, member: User) -> dict:
    return {"user_id": member.id, "username": member.username, "full_name": member.full_name, "role": membership.role, "created_at": membership.created_at.isoformat()}


@router.get("/{case_id}/members")
def list_members(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    rows = db.query(CaseMembership, User).join(User, User.id == CaseMembership.user_id).filter(CaseMembership.case_id == case_id).all()
    return [_serialize(membership, member) for membership, member in rows]


@router.post("/{case_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(case_id: int, payload: MembershipCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = verify_case_access(case_id, current_user, db)
    _require_owner(case, current_user)
    member = db.query(User).filter(User.username == payload.username, User.is_active.is_(True)).first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active user with that username.")
    if member.id == case.created_by_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The case creator already has full access.")
    if payload.role in ("PATIENT", "CAREGIVER") and member.role != UserRole.PUBLIC:
        # Portal links are for the person's own (self-registered) account, not a clinical account.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Patient and caregiver access is granted to personal accounts only.")
    membership = db.query(CaseMembership).filter(CaseMembership.case_id == case_id, CaseMembership.user_id == member.id).first()
    if membership:
        membership.role = payload.role
    else:
        membership = CaseMembership(case_id=case_id, user_id=member.id, role=payload.role, granted_by_id=current_user.id)
        db.add(membership)
    db.commit()
    db.refresh(membership)
    log_audit_event(db=db, action="CASE_MEMBER_GRANTED", resource_type="CASE", resource_id=str(case_id), user=current_user,
                    details={"member_user_id": member.id, "role": payload.role})
    return _serialize(membership, member)


@router.delete("/{case_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(case_id: int, user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = verify_case_access(case_id, current_user, db)
    _require_owner(case, current_user)
    membership = db.query(CaseMembership).filter(CaseMembership.case_id == case_id, CaseMembership.user_id == user_id).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found.")
    db.delete(membership)
    db.commit()
    log_audit_event(db=db, action="CASE_MEMBER_REVOKED", resource_type="CASE", resource_id=str(case_id), user=current_user, details={"member_user_id": user_id})
