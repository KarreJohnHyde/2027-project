"""
Authentication, Password Hashing, JWT Tokens and Role-Based Access Control.
Includes strict case-level authorization checks to prevent cross-user data leakage.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import InvalidTokenError
import bcrypt
from sqlalchemy.orm import Session

from app import config
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.models.entities import Case, CaseMembership, User, UserRole, VerificationStatus
from app.schemas.entities import TokenData

# OAuth2 scheme. A missing bearer token is not an error by itself: the browser session cookie is tried next.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

PRIVILEGED_ROLES = frozenset({
    UserRole.ADMIN,
    UserRole.CLINICIAN,
    UserRole.RESEARCHER,
})


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pw_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    pw_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """The signed-in account: a bearer token (API clients, existing integrations) or else the browser session cookie."""
    if token:
        return user_from_bearer(token, db)
    from app.services import browser_sessions

    raw = request.cookies.get(browser_sessions.COOKIE_NAME)
    if raw:
        user, session = browser_sessions.resolve(db, raw)
        if user is not None:
            if request.method not in browser_sessions.SAFE_METHODS and not browser_sessions.is_web_client(request):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                    detail=f"CLIENT_HEADER_REQUIRED: a request signed in by the browser cookie must send {browser_sessions.CLIENT_HEADER}.")
            request.state.browser_session_id = session.id
            return user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="SESSION_EXPIRED: this browser's session has ended; enter again.",
                            headers={"WWW-Authenticate": "Bearer"})
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})


def user_from_bearer(token: str, db: Session) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                             options={"require": ["exp", "iat", "sub"]})
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        role: str = payload.get("role")
        token_data = TokenData(username=username, role=UserRole(role) if role else None)
    except (InvalidTokenError, ValueError, TypeError):
        raise credentials_exception

    user = db.query(User).filter(User.username == token_data.username).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(*allowed_roles: UserRole):
    """Enforce role and independently persisted professional verification."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted for role: {current_user.role}"
            )
        if (
            current_user.role in PRIVILEGED_ROLES
            and current_user.verification_status != VerificationStatus.VERIFIED
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Professional privileges require a verified account.",
            )
        return current_user
    return role_checker


def verify_case_access(case_id: int, user: User, db: Session, access: str = "write") -> Case:
    """
    Enforces authorization check on every protected case operation.
    Prevents unauthorized cross-case access and data leakage.
    Admins can access all cases; creators have full access. Explicit members
    have EDITOR (read/write) or VIEWER (read) access. The default is write,
    so an endpoint grants viewers access only by declaring access="read".
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case with ID {case_id} not found."
        )

    # Demo accounts stay isolated even on an explicitly shared installation.
    if user.is_guest and case.created_by_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo accounts can access their own cases only.")
    if (config.SHARED_WORKSPACE and not user.is_guest) or user.role == UserRole.ADMIN or case.created_by_id == user.id:
        return case

    membership = db.query(CaseMembership).filter(
        CaseMembership.case_id == case.id,
        CaseMembership.user_id == user.id,
    ).first()
    if membership and (membership.role == "EDITOR" or (membership.role == "VIEWER" and access == "read")):
        return case

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied: You do not have permission to view or modify this case."
    )
