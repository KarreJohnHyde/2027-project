"""
Authentication and User Management Router.
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

import secrets

from app.config import (ACCESS_TOKEN_EXPIRE_MINUTES, RATE_LIMIT_ENTRY_PER_MINUTE, RATE_LIMIT_GUEST_PER_MINUTE, RATE_LIMIT_LOGIN_PER_MINUTE,
                        VISITOR_SESSION_DAYS)
from app.database import get_db
from app.security import rate_limit
from app.models.entities import User, UserRole, VerificationStatus
from app.schemas.entities import GuestSession, Token, UserCreate, UserResponse, VisitorEntry, VisitorSession
from app.services.guest_demo import GUEST_PREFIX, GUEST_SESSION_HOURS, create_guest_demo

VISITOR_PREFIX = "visitor-"
from app.services.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user
)
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    for prefix in (GUEST_PREFIX, VISITOR_PREFIX):
        if user_in.username.strip().lower().startswith(prefix):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Usernames starting with '{prefix}' are reserved.")
    # Usernames identify accounts; email addresses may be shared.
    existing = db.query(User).filter(User.username == user_in.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered."
        )

    # Self-registration never confers a professional or administrative role.
    # Professional roles and their verification state are provisioned only
    # through a controlled out-of-band process until an audited admin workflow
    # is implemented.
    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=UserRole.PUBLIC,
        verification_status=VerificationStatus.UNVERIFIED,
        is_active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    log_audit_event(
        db=db,
        action="USER_REGISTERED",
        resource_type="USER",
        resource_id=str(new_user.id),
        user=new_user,
        details={
            "username": new_user.username,
            "role": new_user.role.value,
            "requested_role": user_in.requested_role,
            "requested_department": user_in.requested_department,
            "requested_department_other": user_in.requested_department_other,
            "verification_status": new_user.verification_status.value,
        }
    )

    return new_user


@router.post("/login", response_model=Token, dependencies=[Depends(rate_limit("login", RATE_LIMIT_LOGIN_PER_MINUTE))])
async def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db)
):
    # Support both JSON payload and OAuth2 form data
    username = None
    password = None
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            body = await request.json()
            username = body.get("username")
            password = body.get("password")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            username = form.get("username")
            password = form.get("password")
        except Exception:
            pass

    if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required."
        )
    username = username.strip()

    user = db.query(User).filter(User.username == username).first()
    if user is None and isinstance(username, str):
        email_matches = db.query(User).filter(func.lower(User.email) == username.lower()).limit(2).all()
        if len(email_matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This email is shared by multiple accounts. Sign in with your username.",
            )
        user = email_matches[0] if email_matches else None
    
    if not user or not verify_password(password, user.hashed_password):
        log_audit_event(
            db=db,
            action="LOGIN_FAILED",
            resource_type="AUTH",
            details={"attempted_username": username if "@" not in username else "[email identifier]"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user account.")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.username,
            "role": user.role.value,
            "verification_status": user.verification_status.value,
            "user_id": user.id,
        },
        expires_delta=access_token_expires
    )

    log_audit_event(
        db=db,
        action="LOGIN_SUCCESS",
        resource_type="AUTH",
        user=user,
        details={
            "username": user.username,
            "role": user.role.value,
            "verification_status": user.verification_status.value,
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "verification_status": user.verification_status,
    }


@router.post("/enter", response_model=VisitorSession, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("enter", RATE_LIMIT_ENTRY_PER_MINUTE))])
def enter(entry: VisitorEntry, db: Session = Depends(get_db)):
    """The entry page: name, age, gender and role open a private workspace with every feature, without a
    password. The token is the account's only key; the browser keeps it to continue later."""
    suffix = secrets.token_hex(5)
    user = User(
        username=f"{VISITOR_PREFIX}{suffix}", email=f"{VISITOR_PREFIX}{suffix}@visitor.invalid",
        hashed_password=get_password_hash(secrets.token_urlsafe(32)),  # never shown: there is no password sign-in
        full_name=entry.name.strip(), role=UserRole.PUBLIC, verification_status=VerificationStatus.UNVERIFIED,
        is_active=True, is_visitor=True, age=entry.age, gender=entry.gender, stated_role=entry.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_audit_event(db=db, action="VISITOR_ENTERED", resource_type="USER", resource_id=str(user.id), user=user,
                    details={"stated_role": entry.role})
    lifetime = timedelta(days=VISITOR_SESSION_DAYS)
    token = create_access_token(
        data={"sub": user.username, "role": user.role.value, "verification_status": user.verification_status.value, "user_id": user.id},
        expires_delta=lifetime,
    )
    return {"access_token": token, "token_type": "bearer", "user_id": user.id, "username": user.username, "role": user.role,
            "verification_status": user.verification_status, "expires_at": datetime.now(timezone.utc) + lifetime}


@router.post("/guest", response_model=GuestSession, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("guest", RATE_LIMIT_GUEST_PER_MINUTE))])
async def start_guest_demo(db: Session = Depends(get_db)):
    """Try the demo: a new guest account, signed in for GUEST_SESSION_HOURS, with one synthetic case."""
    user, case, _ = await create_guest_demo(db)
    lifetime = timedelta(hours=GUEST_SESSION_HOURS)
    token = create_access_token(
        data={"sub": user.username, "role": user.role.value, "verification_status": user.verification_status.value, "user_id": user.id},
        expires_delta=lifetime,
    )
    return {"access_token": token, "token_type": "bearer", "user_id": user.id, "username": user.username, "role": user.role,
            "verification_status": user.verification_status, "case_id": case.id, "expires_at": datetime.now(timezone.utc) + lifetime}


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
