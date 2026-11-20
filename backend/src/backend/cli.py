"""Admin tasks that must not be exposed over HTTP.

    uv run python -m backend.cli create-admin admin@example.com
        (prompts for the password; or pass --password for scripts)
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from backend.core.db import new_session
from backend.core.security import hash_password
from backend.models import User


def create_admin(email: str, password: str | None, full_name: str | None) -> None:
    password = password or getpass.getpass("Password (min 8 chars): ")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters")
    email = email.lower()
    with new_session() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            user.role, user.password_hash = "admin", hash_password(password)
            print(f"Updated existing user {email}: role=admin, password reset")
        else:
            db.add(User(email=email, full_name=full_name, role="admin",
                        password_hash=hash_password(password)))
            print(f"Created admin {email}")
        db.commit()


def main() -> None:
    ap = argparse.ArgumentParser(prog="backend.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ca = sub.add_parser("create-admin")
    ca.add_argument("email")
    ca.add_argument("--password")
    ca.add_argument("--name")
    args = ap.parse_args()
    if args.cmd == "create-admin":
        create_admin(args.email, args.password, args.name)


if __name__ == "__main__":
    main()
