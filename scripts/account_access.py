"""Operator access to registered accounts, run on the machine that hosts the MedTwin database.

  list                         registered accounts with how many cases each owns or shares, and private reference packets
  link  --username NAME | --user-id N
                               a one-time sign-in link (15 minutes) that opens that account in one browser
  share --cases 7 8 9 --with NAME | --with-user-id N [--role EDITOR|VIEWER]
                               share cases with a registered account, exactly as their creator would in the app

Running this command needs access to this machine and its database, which is the proof of ownership: nothing here
matches people by name, and nothing is printed about patients. Point it at the same database as the backend (the
same DATABASE_URL / MEDTWIN_* environment). Every action is written to the audit log.

  .\\.venv\\Scripts\\python.exe scripts\\account_access.py list
  .\\.venv\\Scripts\\python.exe scripts\\account_access.py link --username my_account
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import SessionLocal  # noqa: E402
from app.models.entities import Case, CaseMembership, User  # noqa: E402
from app.services import browser_sessions, private_references  # noqa: E402
from app.services.audit_service import log_audit_event  # noqa: E402

ISSUED_BY = "local operator command (scripts/account_access.py)"


def registered(db, username: str | None, user_id: int | None) -> User:
    user = db.get(User, user_id) if user_id is not None else db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active or user.is_guest or user.is_visitor:
        raise SystemExit("No active registered account matches. Run 'list' to see them.")
    return user


def packets(user: User) -> int:
    try:
        return len(private_references.listing(user))
    except Exception:  # noqa: BLE001 - an unreadable store is reported as unknown, never fatal for listing
        return -1


def command_list(db, _args) -> None:
    users = (db.query(User).filter(User.is_guest.is_(False), User.is_visitor.is_(False), User.is_active.is_(True))
             .order_by(User.id).all())
    print(f"{'id':>4}  {'username':<32} {'role':<11} {'verified':<11} {'own cases':>9} {'shared':>6} {'references':>10}")
    for user in users:
        owned = db.query(Case).filter(Case.created_by_id == user.id).count()
        shared = db.query(CaseMembership).filter(CaseMembership.user_id == user.id, CaseMembership.role.in_(("VIEWER", "EDITOR"))).count()
        count = packets(user)
        print(f"{user.id:>4}  {user.username:<32} {user.role.value:<11} {user.verification_status.value:<11} {owned:>9} {shared:>6} "
              f"{'?' if count < 0 else count:>10}")


def command_link(db, args) -> None:
    user = registered(db, args.username, args.user_id)
    code = browser_sessions.issue_sign_in_link(db, user)
    log_audit_event(db=db, action="SIGN_IN_LINK_ISSUED", resource_type="USER", resource_id=str(user.id), user=user,
                    details={"issued_by": ISSUED_BY, "minutes": int(browser_sessions.LINK_LIFETIME.total_seconds() // 60)})
    base = args.base_url.rstrip("/")
    print("Open this link in the browser you want to sign in. It works once and expires in "
          f"{int(browser_sessions.LINK_LIFETIME.total_seconds() // 60)} minutes; do not share it.")
    # The code is in the fragment (#), which browsers never send to a server, so it stays out of logs and referrers.
    print(f"{base}/account#link={code}")


def command_share(db, args) -> None:
    member = registered(db, args.with_username, args.with_user_id)
    for case_id in args.cases:
        case = db.get(Case, case_id)
        if case is None:
            print(f"case {case_id}: not found; skipped")
            continue
        if case.created_by_id == member.id:
            print(f"case {case_id}: already owned by that account; nothing to do")
            continue
        membership = db.query(CaseMembership).filter(CaseMembership.case_id == case_id, CaseMembership.user_id == member.id).first()
        if membership is None:
            membership = CaseMembership(case_id=case_id, user_id=member.id, role=args.role, granted_by_id=case.created_by_id)
            db.add(membership)
        else:
            membership.role = args.role
        db.commit()
        granter = db.get(User, case.created_by_id) if case.created_by_id else None
        log_audit_event(db=db, action="CASE_MEMBER_GRANTED", resource_type="CASE", resource_id=str(case_id), user=granter,
                        details={"member_user_id": member.id, "role": args.role, "issued_by": ISSUED_BY})
        print(f"case {case_id}: shared with account {member.id} as {args.role}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="registered accounts and what each can open")
    link = sub.add_parser("link", help="a one-time sign-in link for a registered account")
    who = link.add_mutually_exclusive_group(required=True)
    who.add_argument("--username")
    who.add_argument("--user-id", type=int)
    link.add_argument("--base-url", default="http://127.0.0.1:8443", help="where the web app runs (default: the dev stack)")
    share = sub.add_parser("share", help="share cases with a registered account, as their creator would")
    share.add_argument("--cases", type=int, nargs="+", required=True)
    member = share.add_mutually_exclusive_group(required=True)
    member.add_argument("--with", dest="with_username")
    member.add_argument("--with-user-id", type=int)
    share.add_argument("--role", choices=("EDITOR", "VIEWER"), default="EDITOR")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        {"list": command_list, "link": command_link, "share": command_share}[args.command](db, args)
    finally:
        db.close()


if __name__ == "__main__":
    main()
