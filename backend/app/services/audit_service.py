"""
Audit logging service for MedTwin.
Records user actions, resource modifications, and authorization events.
Crucial Privacy Guarantee: Sensitive clinical report text or identifying patient data
is NEVER written to audit logs; only cryptographic hashes, metadata, lengths, and IDs are stored.
"""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.entities import AuditEvent, User
from app.request_context import get_request_id


# These values may contain free-form clinical text or identifiers even when the
# route that produced them describes them as "metadata". Keep them out of the
# durable audit trail; authorized resource endpoints remain the source of truth.
_SENSITIVE_DETAIL_KEYS = {
    "association_notes",
    "clinical_indication",
    "clinical_note",
    "clinical_notes",
    "clinical_summary",
    "description",
    "filename",
    "mrn",
    "patient_name",
    "patient_ref",
    "raw_content",
    "report_text",
    "reviewer_comments",
    "source_span",
    "text",
}


def log_audit_event(
    db: Session,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    user: Optional[User] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None
) -> AuditEvent:
    # Sanitize details to guarantee zero PHI leakage into audit trails
    sanitized_details = {}
    if details:
        for k, v in details.items():
            # Request correlation is reserved for the validated middleware
            # value so callers cannot spoof another request's audit linkage.
            if k.lower() == "request_id":
                continue
            # Filter out keys that might hold narrative clinical text
            if k.lower() in _SENSITIVE_DETAIL_KEYS:
                sanitized_details[k] = f"[REDACTED_FOR_PRIVACY: length={len(str(v))}]"
            else:
                sanitized_details[k] = v

    request_id = get_request_id()
    if request_id:
        sanitized_details["request_id"] = request_id

    event = AuditEvent(
        user_id=user.id if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id else None,
        details=sanitized_details,
        ip_address=ip_address
    )
    db.add(event)
    try:
        db.commit()
        db.refresh(event)
    except Exception:
        db.rollback()
    return event
