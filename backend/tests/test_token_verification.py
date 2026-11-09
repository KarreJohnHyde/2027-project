"""Reject forged or incomplete credentials before any database lookup."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.config import SECRET_KEY, ALGORITHM
from app.services.auth import get_current_user


@pytest.mark.parametrize("kind", ["expired", "missing_exp", "missing_iat", "missing_sub", "wrong_key", "unsigned"])
def test_invalid_credentials_are_rejected_before_database_lookup(kind):
    now = datetime.now(timezone.utc)
    claims = {"sub": "synthetic-user", "iat": now, "exp": now + timedelta(minutes=1)}
    key, algorithm = SECRET_KEY, ALGORITHM
    if kind == "expired":
        claims["exp"] = now - timedelta(minutes=1)
    elif kind.startswith("missing_"):
        claims.pop(kind.removeprefix("missing_"))
    elif kind == "wrong_key":
        key = "different-signing-key-with-32-bytes-minimum"
    elif kind == "unsigned":
        key, algorithm = "", "none"
    token = jwt.encode(claims, key, algorithm=algorithm)
    with pytest.raises(HTTPException) as refused:
        get_current_user(token=token, db=None)
    assert refused.value.status_code == 401
