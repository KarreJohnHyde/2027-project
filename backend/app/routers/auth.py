"""
Authentication and User Management Router.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

import secrets

from app.config import (ACCESS_TOKEN_EXPIRE_MINUTES, RATE_LIMIT_ENTRY_PER_MINUTE, RATE_LIMIT_GUEST_PER_MINUTE, RATE_LIMIT_LOGIN_PER_MINUTE,
                        RATE_LIMIT_SESSION_PER_MINUTE, VISITOR_SESSION_DAYS)
from app import config as app_config
from app.database import get_db
from app.security import rate_limit
from app.models.entities import Case, User, UserRole, VerificationStatus
from app.schemas.entities import GuestSession, SignInLinkRedeem, Token, UserCreate, UserResponse, VisitorEntry, VisitorSession
from app.services import browser_sessions
from app.services import job_queue
from app.services.guest_demo import GUEST_PREFIX, GUEST_SESSION_HOURS, create_guest_demo, run_demo_analyses

VISITOR_PREFIX = "visitor-"
from app.services.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    user_from_bearer,
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


@router.post("/login", dependencies=[Depends(rate_limit("login", RATE_LIMIT_LOGIN_PER_MINUTE))])
async def login_for_access_token(
    request: Request,
    response: Response,
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

    if browser_sessions.is_web_client(request):
        # The web client keeps no token: an existing account is remembered by the same HttpOnly session cookie.
        raw, session = browser_sessions.create(db, user, "ACCOUNT", timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        return _browser_reply(request, response, user, raw, session)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "verification_status": user.verification_status,
    }


def _idempotency_key(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    if not 8 <= len(value) <= 128:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key must be 8 to 128 characters.")
    return value


def _bearer(user: User, lifetime: timedelta) -> str:
    return create_access_token(
        data={"sub": user.username, "role": user.role.value, "verification_status": user.verification_status.value, "user_id": user.id},
        expires_delta=lifetime,
    )


def _browser_reply(request: Request, response: Response, user: User, raw: str, session) -> dict:
    """The web client's answer: the session goes into the HttpOnly cookie; the body carries the profile only."""
    browser_sessions.set_cookie(response, request, raw, session)
    return {"user": UserResponse.model_validate(user).model_dump(mode="json"),
            "session": {"kind": session.kind, "expires_at": session.expires_at.replace(tzinfo=timezone.utc).isoformat()}}


@router.post("/enter", status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit("enter", RATE_LIMIT_ENTRY_PER_MINUTE))])
def enter(entry: VisitorEntry, request: Request, response: Response, db: Session = Depends(get_db),
          idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    """The entry page: name and role (age and gender optional) open a private workspace with every feature, without a
    password. The browser is remembered by an HttpOnly session cookie; a retried request with the same
    Idempotency-Key reuses the visitor it created, so a network retry never makes a second account. Nothing here
    matches people by name: two people with the same name are two visitors."""
    key = _idempotency_key(idempotency_key)
    lifetime = timedelta(days=VISITOR_SESSION_DAYS)
    earlier = browser_sessions.find_by_entry_key(db, key, "VISITOR") if key else None
    if earlier is not None:
        user = db.get(User, earlier.user_id)
        log_audit_event(db=db, action="VISITOR_ENTRY_RETRIED", resource_type="USER", resource_id=str(user.id), user=user, details={})
    else:
        suffix = secrets.token_hex(5)
        user = User(
            username=f"{VISITOR_PREFIX}{suffix}", email=f"{VISITOR_PREFIX}{suffix}@visitor.invalid",
            hashed_password=get_password_hash(secrets.token_urlsafe(32)),  # never shown: there is no password sign-in
            full_name=entry.name, role=UserRole.PUBLIC, verification_status=VerificationStatus.UNVERIFIED,
            is_active=True, is_visitor=True, age=entry.age, gender=entry.gender, stated_role=entry.role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        log_audit_event(db=db, action="VISITOR_ENTERED", resource_type="USER", resource_id=str(user.id), user=user,
                        details={"stated_role": entry.role})
    if browser_sessions.is_web_client(request):
        raw, session = browser_sessions.create(db, user, "VISITOR", lifetime, entry_key=key)
        return _browser_reply(request, response, user, raw, session)
    if key and earlier is None:
        browser_sessions.create(db, user, "VISITOR", lifetime, entry_key=key)  # records the key; the token is not used
    return {"access_token": _bearer(user, lifetime), "token_type": "bearer", "user_id": user.id, "username": user.username, "role": user.role,
            "verification_status": user.verification_status, "expires_at": datetime.now(timezone.utc) + lifetime}


@router.post("/guest", status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit("guest", RATE_LIMIT_GUEST_PER_MINUTE))])
async def start_guest_demo(request: Request, response: Response, background: BackgroundTasks, db: Session = Depends(get_db),
                           idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")):
    """Try the demo: a new guest account with one synthetic case, signed in for GUEST_SESSION_HOURS. The guest sees
    only its own case. A retried request with the same Idempotency-Key reopens the same demo.

    The demo answers as soon as its fictional documents are stored and queued; their ordinary analysis runs after
    the response (or on the worker), so a slow analysis never holds up, or times out, the sign-in."""
    key = _idempotency_key(idempotency_key)
    lifetime = timedelta(hours=GUEST_SESSION_HOURS)
    earlier = browser_sessions.find_by_entry_key(db, key, "GUEST") if key else None
    if earlier is not None:
        user = db.get(User, earlier.user_id)
        case = db.query(Case).filter(Case.created_by_id == user.id).order_by(Case.id.asc()).first()
        expires_at = earlier.expires_at
    else:
        user, case, _, job_ids = await create_guest_demo(db, defer_analysis=True)
        expires_at = None
        if job_queue.execution_mode() == "inline":
            background.add_task(run_demo_analyses, db.get_bind(), job_ids)
    if browser_sessions.is_web_client(request):
        raw, session = browser_sessions.create(db, user, "GUEST", lifetime, entry_key=key, expires_at=expires_at)
        return {**_browser_reply(request, response, user, raw, session), "case_id": case.id}
    if key and earlier is None:
        browser_sessions.create(db, user, "GUEST", lifetime, entry_key=key)
    return {"access_token": _bearer(user, lifetime), "token_type": "bearer", "user_id": user.id, "username": user.username, "role": user.role,
            "verification_status": user.verification_status, "case_id": case.id, "expires_at": datetime.now(timezone.utc) + lifetime}


def _lifetime(kind: str) -> timedelta:
    if kind == "GUEST":
        return timedelta(hours=GUEST_SESSION_HOURS)
    if kind == "ACCOUNT":  # a password account keeps the password sign-in lifetime, never the longer visitor one
        return timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return timedelta(days=VISITOR_SESSION_DAYS)


def _open_workspace_account(db: Session) -> User:
    key = app_config.OPEN_WORKSPACE_ACCOUNT
    user = db.get(User, int(key)) if key.isdigit() else db.query(User).filter(User.username == key).first()
    if user is None or not user.is_active or user.is_guest or user.is_visitor or user.role == UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="MEDTWIN_OPEN_WORKSPACE_ACCOUNT does not name an active registered account that is not an "
                                   "administrator. Fix the setting and restart the server.")
    return user


@router.get("/session", dependencies=[Depends(rate_limit("session", RATE_LIMIT_SESSION_PER_MINUTE))])
def restore_session(request: Request, response: Response, db: Session = Depends(get_db)):
    """Restore this browser's sign-in from its session cookie: the profile, and a fresh token once the current one
    is older than the rotation age. 401 when there is no valid session (the entry page is shown).

    In open-workspace mode (MEDTWIN_OPEN_WORKSPACE_ACCOUNT, a workstation the owner controls) there is no sign-in: a
    browser without a session, or with a visitor or demo session, opens the workspace as the configured account. A
    browser deliberately signed in to another registered account keeps it."""
    raw = request.cookies.get(browser_sessions.COOKIE_NAME)
    user, session = browser_sessions.resolve(db, raw)
    if app_config.OPEN_WORKSPACE and (user is None or session.kind != "ACCOUNT"):
        account = _open_workspace_account(db)
        if session is not None:
            browser_sessions.revoke(db, session)
        raw, session = browser_sessions.create(db, account, "ACCOUNT", _lifetime("ACCOUNT"))
        browser_sessions.set_cookie(response, request, raw, session)
        log_audit_event(db=db, action="OPEN_WORKSPACE_SESSION_STARTED", resource_type="USER", resource_id=str(account.id),
                        user=account, details={})
        return {"user": UserResponse.model_validate(account).model_dump(mode="json"), "open_workspace": True,
                "session": {"kind": session.kind, "expires_at": session.expires_at.replace(tzinfo=timezone.utc).isoformat(), "rotated": False}}
    if user is None:
        if raw:
            browser_sessions.clear_cookie(response, request)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="NO_SESSION: enter your details to begin.",
                            headers={"WWW-Authenticate": "Bearer"})
    rotated = False
    if browser_sessions.needs_rotation(session) and session.replaced_by_id is None:
        raw, session = browser_sessions.rotate(db, session, _lifetime(session.kind))
        browser_sessions.set_cookie(response, request, raw, session)
        rotated = True
    return {"user": UserResponse.model_validate(user).model_dump(mode="json"), "open_workspace": app_config.OPEN_WORKSPACE,
            "session": {"kind": session.kind, "expires_at": session.expires_at.replace(tzinfo=timezone.utc).isoformat(), "rotated": rotated}}


@router.post("/session/claim", dependencies=[Depends(rate_limit("session", RATE_LIMIT_SESSION_PER_MINUTE))])
def claim_session(request: Request, response: Response, db: Session = Depends(get_db),
                  authorization: Optional[str] = Header(default=None)):
    """Move a browser from the earlier stored bearer token to a session cookie. The caller proves ownership with that
    token (verified exactly as any bearer request); nothing is matched by name."""
    if not browser_sessions.is_web_client(request):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Only the web client claims a browser session ({browser_sessions.CLIENT_HEADER}).")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    user = user_from_bearer(authorization[7:].strip(), db)
    kind = "GUEST" if user.is_guest else "VISITOR" if user.is_visitor else "ACCOUNT"
    raw, session = browser_sessions.create(db, user, kind, _lifetime(kind))
    log_audit_event(db=db, action="BROWSER_SESSION_CLAIMED", resource_type="USER", resource_id=str(user.id), user=user, details={"kind": kind})
    return _browser_reply(request, response, user, raw, session)


@router.post("/link", dependencies=[Depends(rate_limit("login", RATE_LIMIT_LOGIN_PER_MINUTE))])
def redeem_sign_in_link(payload: SignInLinkRedeem, request: Request, response: Response, db: Session = Depends(get_db)):
    """Open a registered account in this browser with a one-time sign-in link. Links are issued only by a command run on
    the server's own machine (scripts/account_access.py link), work once, and expire after 15 minutes. This is the
    recovery path when an account's password is not to hand; nothing is matched by name."""
    if not browser_sessions.is_web_client(request):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Sign-in links open in the web app only ({browser_sessions.CLIENT_HEADER}).")
    user = browser_sessions.redeem_sign_in_link(db, payload.code)
    if user is None:
        log_audit_event(db=db, action="SIGN_IN_LINK_REFUSED", resource_type="AUTH", details={})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="This sign-in link is not valid: it may have been used already or expired. Ask for a new link.")
    raw, session = browser_sessions.create(db, user, "ACCOUNT", _lifetime("ACCOUNT"))
    log_audit_event(db=db, action="SIGN_IN_LINK_USED", resource_type="USER", resource_id=str(user.id), user=user, details={})
    return _browser_reply(request, response, user, raw, session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: Session = Depends(get_db)):
    """Sign this browser out: its session is revoked server-side and the cookie cleared. Accounts and data are kept."""
    if not browser_sessions.is_web_client(request):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Sign-out needs the web client header ({browser_sessions.CLIENT_HEADER}).")
    _, session = browser_sessions.resolve(db, request.cookies.get(browser_sessions.COOKIE_NAME))
    if session is not None:
        browser_sessions.revoke(db, session)
    reply = Response(status_code=status.HTTP_204_NO_CONTENT)
    browser_sessions.clear_cookie(reply, request)
    return reply


@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user
