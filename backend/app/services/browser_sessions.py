"""Browser sessions: the entry page's persistent, passwordless sign-in.

A visitor who enters their details gets an opaque random token in an HttpOnly cookie; the database keeps only its
SHA-256 (BrowserSession.token_hash). The same browser is recognised on every later visit while the session is valid,
without a password and without matching on name, age, gender, address or fingerprint. Sessions expire, can be revoked
(sign out) and are rotated: a session older than ROTATE_AFTER is replaced on the next restore, and the old token keeps
working for ROTATION_GRACE so requests already in flight do not fail.

A cookie-authenticated request that changes state must carry CLIENT_HEADER. Browsers do not let another site add a
custom header without a CORS preflight, which the API's CORS policy refuses, so a cross-site form or script cannot
use the cookie (CSRF protection on top of SameSite=Lax).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Request, Response
from sqlalchemy.orm import Session

from app import config
from app.models.entities import BrowserSession, User

COOKIE_NAME = "medtwin_session"
COOKIE_PATH = "/api"
CLIENT_HEADER = "X-MedTwin-Client"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
ROTATE_AFTER = timedelta(hours=12)
ROTATION_GRACE = timedelta(minutes=2)
LAST_USED_RESOLUTION = timedelta(minutes=5)
ENTRY_KEY_WINDOW = timedelta(hours=1)
KINDS = ("VISITOR", "GUEST", "ACCOUNT")
# A one-time sign-in link for a registered account. It is stored like a session but is never accepted as one: it can
# only be exchanged, once and within LINK_LIFETIME, for a new ACCOUNT session (POST /auth/link).
LINK_KIND = "SIGNIN_LINK"
LINK_LIFETIME = timedelta(minutes=15)


def _now() -> datetime:
    """Naive UTC: SQLite returns naive datetimes, so every comparison here uses naive UTC values."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create(db: Session, user: User, kind: str, lifetime: timedelta, entry_key: Optional[str] = None,
           expires_at: Optional[datetime] = None) -> tuple[str, BrowserSession]:
    """A new session for ``user``; returns the raw token (only ever placed in the cookie) and the stored row."""
    if kind not in KINDS:
        raise ValueError(f"unknown session kind {kind}")
    raw = secrets.token_urlsafe(32)
    now = _now()
    session = BrowserSession(user_id=user.id, token_hash=digest(raw), kind=kind, created_at=now, last_used_at=now,
                             expires_at=_naive(expires_at) if expires_at else now + lifetime,
                             entry_key_hash=digest(entry_key) if entry_key else None)
    db.add(session)
    db.commit()
    db.refresh(session)
    return raw, session


def find_by_entry_key(db: Session, entry_key: str, kind: str) -> Optional[BrowserSession]:
    """The session an earlier request with the same Idempotency-Key created, within ENTRY_KEY_WINDOW."""
    session = (db.query(BrowserSession)
               .filter(BrowserSession.entry_key_hash == digest(entry_key), BrowserSession.kind == kind)
               .order_by(BrowserSession.id.desc()).first())
    if session is None or _now() - _naive(session.created_at) > ENTRY_KEY_WINDOW:
        return None
    return session


def resolve(db: Session, raw: Optional[str]) -> tuple[Optional[User], Optional[BrowserSession]]:
    """The active account and session for a cookie value; (None, None) when missing, unknown, expired or revoked."""
    if not raw or len(raw) > 128:
        return None, None
    session = db.query(BrowserSession).filter(BrowserSession.token_hash == digest(raw)).first()
    if session is None or session.kind not in KINDS:
        return None, None
    now = _now()
    if _naive(session.expires_at) <= now or (session.revoked_at is not None and _naive(session.revoked_at) <= now):
        return None, None
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None, None
    if now - _naive(session.last_used_at) > LAST_USED_RESOLUTION:
        session.last_used_at = now
        db.commit()
    return user, session


def _registered(user: Optional[User]) -> bool:
    return user is not None and user.is_active and not user.is_guest and not user.is_visitor


def issue_sign_in_link(db: Session, user: User, lifetime: timedelta = LINK_LIFETIME) -> str:
    """A one-time code that opens ``user`` (a registered account) in one browser. It is issued only by a command run on
    the server's own machine (scripts/account_access.py), so control of that machine is the proof of ownership; the
    database keeps only its SHA-256."""
    if not _registered(user):
        raise ValueError("Sign-in links are for active registered accounts only (not visitors or demo accounts).")
    raw = secrets.token_urlsafe(32)
    now = _now()
    db.add(BrowserSession(user_id=user.id, token_hash=digest(raw), kind=LINK_KIND, created_at=now, last_used_at=now,
                          expires_at=now + lifetime))
    db.commit()
    return raw


def redeem_sign_in_link(db: Session, raw: Optional[str]) -> Optional[User]:
    """The account a sign-in link opens, consuming the link; None when it is unknown, used, expired or the account is
    no longer an active registered account. Two browsers racing for one link: only one wins."""
    if not raw or len(raw) > 128:
        return None
    link = db.query(BrowserSession).filter(BrowserSession.token_hash == digest(raw), BrowserSession.kind == LINK_KIND).first()
    now = _now()
    if link is None or link.revoked_at is not None or _naive(link.expires_at) <= now:
        return None
    consumed = (db.query(BrowserSession).filter(BrowserSession.id == link.id, BrowserSession.revoked_at.is_(None))
                .update({"revoked_at": now, "last_used_at": now}, synchronize_session=False))
    db.commit()
    if consumed != 1:
        return None
    user = db.get(User, link.user_id)
    return user if _registered(user) else None


def needs_rotation(session: BrowserSession) -> bool:
    return session.revoked_at is None and _now() - _naive(session.created_at) >= ROTATE_AFTER


def rotate(db: Session, session: BrowserSession, lifetime: timedelta) -> tuple[str, BrowserSession]:
    """Replace a session with a fresh token. Visitor and account sessions slide forward by ``lifetime``; a guest
    session keeps its original expiry (a demo never outlives its window)."""
    user = db.get(User, session.user_id)
    expires = None if session.kind != "GUEST" else _naive(session.expires_at)
    raw, replacement = create(db, user, session.kind, lifetime, expires_at=expires)
    session.revoked_at = _now() + ROTATION_GRACE
    session.replaced_by_id = replacement.id
    db.commit()
    return raw, replacement


def revoke(db: Session, session: BrowserSession) -> None:
    session.revoked_at = _now()
    db.commit()


def _secure(request: Request) -> bool:
    """Secure cookies on HTTPS (directly or behind a proxy that says so) and whenever configured."""
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return config.COOKIE_SECURE or request.url.scheme == "https" or forwarded == "https"


def set_cookie(response: Response, request: Request, raw: str, session: BrowserSession) -> None:
    max_age = max(0, int((_naive(session.expires_at) - _now()).total_seconds()))
    response.set_cookie(COOKIE_NAME, raw, max_age=max_age, path=COOKIE_PATH, httponly=True, secure=_secure(request), samesite="lax")


def clear_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH, httponly=True, secure=_secure(request), samesite="lax")


def is_web_client(request: Request) -> bool:
    return bool(request.headers.get(CLIENT_HEADER))
