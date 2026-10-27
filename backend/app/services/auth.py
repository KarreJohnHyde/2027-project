"""
Authentication, Password Hashing, JWT Tokens and Role-Based Access Control.
Includes strict case-level authorization checks to prevent cross-user data leakage.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.orm import Session

from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.models.entities import Case, CaseMembership, User, UserRole, VerificationStatus
from app.schemas.entities import TokenData

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

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


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        role: str = payload.get("role")
        token_data = TokenData(username=username, role=UserRole(role) if role else None)
    except (JWTError, ValueError, TypeError):
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

    # Admin override
    if user.role == UserRole.ADMIN or case.created_by_id == user.id:
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
