#!/usr/bin/env python3
"""
Reset a user's password directly in the database.

This is an emergency recovery tool for administrators when a user is locked out
and no recovery path is available via the web UI (see issue #350).

Usage:
    python -m app.scripts.reset_password <username> <new_password>

    # Or within Docker:
    docker exec -it borg-ui python -m app.scripts.reset_password admin newpassword123

Environment variables:
    BORG_DB_PATH  Path to a SQLite database file to operate on instead of the
                  application's DATABASE_URL (legacy override).

Exit codes:
    0  Password reset successfully
    1  Error (wrong arguments, user not found, empty password, DB error)
"""

import os
import sys

import bcrypt
from sqlalchemy import create_engine, text

from app.database.url_utils import sqlite_database_missing


def _database_url() -> str:
    """The database to operate on: BORG_DB_PATH (legacy) or DATABASE_URL."""
    override = os.environ.get("BORG_DB_PATH")
    if override:
        return f"sqlite:///{override}"
    from app.config import settings

    return settings.database_url


def reset_password(username: str, new_password: str, database_url: str) -> None:
    """Reset the password for *username* in the database at *database_url*.

    Sets must_change_password to false so the admin-initiated reset does not
    force the user to change their password again immediately after logging in.

    Raises SystemExit(1) on any error condition.
    """
    if not new_password:
        print("Error: new_password must not be empty.", file=sys.stderr)
        sys.exit(1)

    # Connecting would create a missing SQLite file; fail instead.
    if sqlite_database_missing(database_url):
        print(f"Error: Database not found ({database_url}).", file=sys.stderr)
        sys.exit(1)

    password_hash = bcrypt.hashpw(
        new_password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    try:
        engine = create_engine(database_url)
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT id FROM users WHERE username = :username"),
                {"username": username},
            ).fetchone()
            if row is None:
                print(f"Error: User '{username}' not found.", file=sys.stderr)
                sys.exit(1)

            conn.execute(
                text(
                    "UPDATE users SET password_hash = :password_hash,"
                    " must_change_password = :off WHERE username = :username"
                ),
                {"password_hash": password_hash, "off": False, "username": username},
            )
        print(f"Password reset successfully for user '{username}'.")

    except SystemExit:
        raise
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python -m app.scripts.reset_password <username> <new_password>",
            file=sys.stderr,
        )
        sys.exit(1)

    reset_password(sys.argv[1], sys.argv[2], _database_url())
