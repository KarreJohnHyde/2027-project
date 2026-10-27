"""
Authentication and User Management Router.
"""

from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, RATE_LIMIT_LOGIN_PER_MINUTE
from app.database import get_db
from app.security import rate_limit
from app.models.entities import User, UserRole, VerificationStatus
from app.schemas.entities import Token, UserCreate, UserResponse
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
    # Check if username or email exists
    existing = db.query(User).filter(
        (User.username == user_in.username) | (User.email == user_in.email)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered."
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
        user = db.query(User).filter(func.lower(User.email) == username.strip().lower()).first()
    
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


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
