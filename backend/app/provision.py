"""Create or verify a professional account from the command line.

No public API grants a professional role, and the development seed is refused outside
development, so a deployment's first clinician, researcher or administrator is provisioned by
the operator against the deployment's own database (for a hosted database, export its
DATABASE_URL in the shell first):

    MEDTWIN_PROVISION_PASSWORD=... python -m app.provision --username dr.example \
        --email dr@example.org --role clinician [--full-name "Dr Example"]

An existing account is verified and given the role without touching its password. A new account
needs MEDTWIN_PROVISION_PASSWORD (at least 12 characters), read from the environment so it never
appears in shell history. Every change is written to the audit log.
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

from app.database import Base, SessionLocal, engine, schema_lock
from app.migrations import run_migrations
from app.models.entities import User, UserRole, VerificationStatus
from app.services.audit_service import log_audit_event
from app.services.auth import get_password_hash

PROFESSIONAL_ROLES = {role.value: role for role in (UserRole.CLINICIAN, UserRole.RESEARCHER, UserRole.ADMIN)}


def provision(username: str, email: str, role: UserRole, full_name: Optional[str] = None, password: Optional[str] = None) -> str:
    """Return the audit action recorded (provisioned or verified)."""
    with schema_lock(engine):
        Base.metadata.create_all(bind=engine)
        run_migrations(engine)
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            if not password or len(password) < 12:
                raise SystemExit("A new account needs MEDTWIN_PROVISION_PASSWORD with at least 12 characters.")
            user = User(username=username, email=email, full_name=full_name, hashed_password=get_password_hash(password),
                        role=role, verification_status=VerificationStatus.VERIFIED, is_active=True)
            db.add(user)
            action = "PROFESSIONAL_ACCOUNT_PROVISIONED"
        elif user.email != email:
            raise SystemExit("That username belongs to an account with a different email address; nothing was changed.")
        else:
            user.role, user.verification_status, user.is_active = role, VerificationStatus.VERIFIED, True
            action = "PROFESSIONAL_ACCOUNT_VERIFIED"
        db.commit()
        db.refresh(user)
        log_audit_event(db, action, "user", user.id, details={"role": role.value, "channel": "operator_command_line"})
    return action


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--username", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=sorted(PROFESSIONAL_ROLES))
    parser.add_argument("--full-name")
    arguments = parser.parse_args(argv)
    action = provision(arguments.username, arguments.email, PROFESSIONAL_ROLES[arguments.role], arguments.full_name,
                       os.getenv("MEDTWIN_PROVISION_PASSWORD"))
    print(f"{action}: {arguments.username} ({arguments.role}, verified)")


if __name__ == "__main__":
    main()
