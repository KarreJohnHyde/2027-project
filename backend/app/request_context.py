"""Validated request correlation IDs shared by HTTP and audit code."""

from __future__ import annotations

from contextvars import ContextVar, Token
import re
from typing import Any
from uuid import uuid4


REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_MAX_LENGTH = 128

# Keep correlation IDs safe for response headers and single-line logs. UUIDs,
# common trace IDs, and caller-generated identifiers using dots/underscores are
# accepted; whitespace, path separators, Unicode, and control characters are not.
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", re.ASCII)
_current_request_id: ContextVar[str | None] = ContextVar(
    "medtwin_request_id", default=None
)


def is_safe_request_id(value: object) -> bool:
    """Return whether *value* can safely be echoed and written to logs."""

    return (
        isinstance(value, str)
        and 0 < len(value) <= REQUEST_ID_MAX_LENGTH
        and _SAFE_REQUEST_ID.fullmatch(value) is not None
    )


def select_request_id(candidate: str | None) -> str:
    """Accept a safe caller ID or replace it with a server-generated UUIDv4."""

    return candidate if is_safe_request_id(candidate) else str(uuid4())


def bind_request_id(request_id: str) -> Token[str | None]:
    """Bind a validated ID for the lifetime of the current request task."""

    return _current_request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the prior task context after a request completes."""

    _current_request_id.reset(token)


def get_request_id(request: Any | None = None) -> str | None:
    """Read the request ID from Request.state or the current task context."""

    if request is not None:
        state = getattr(request, "state", None)
        request_id = getattr(state, "request_id", None) if state is not None else None
        if is_safe_request_id(request_id):
            return request_id
    return _current_request_id.get()
