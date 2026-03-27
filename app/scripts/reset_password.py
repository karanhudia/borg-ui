#!/usr/bin/env python3
"""
Reset a user's password directly in the SQLite database.

This is an emergency recovery tool for administrators when a user is locked out
and no recovery path is available via the web UI (see issue #350).

Usage:
    python -m app.scripts.reset_password <username> <new_password>

    # Or within Docker:
    docker exec -it borg-ui python -m app.scripts.reset_password admin newpassword123

Environment variables:
    BORG_DB_PATH  Path to the SQLite database file (default: /data/borg.db)

Exit codes:
    0  Password reset successfully
    1  Error (wrong arguments, user not found, empty password, DB error)
"""
import sys
import sqlite3
import os

import bcrypt

DEFAULT_DB_PATH = "/data/borg.db"


def reset_password(username: str, new_password: str, db_path: str) -> None:
    """Reset the password for *username* in the SQLite database at *db_path*.

    Sets must_change_password to 0 so the admin-initiated reset does not force
    the user to change their password again immediately after logging in.

    Raises SystemExit(1) on any error condition.
    """
    if not new_password:
        print("Error: new_password must not be empty.", file=sys.stderr)
        sys.exit(1)

    password_hash = bcrypt.hashpw(
        new_password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row is None:
            print(f"Error: User '{username}' not found.", file=sys.stderr)
            sys.exit(1)

        cursor.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE username = ?",
            (password_hash, username),
        )
        conn.commit()
        print(f"Password reset successfully for user '{username}'.")

    except SystemExit:
        raise
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        sys.exit(1)
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(
            "Usage: python -m app.scripts.reset_password <username> <new_password>",
            file=sys.stderr,
        )
        sys.exit(1)

    db_path = os.environ.get("BORG_DB_PATH", DEFAULT_DB_PATH)
    reset_password(sys.argv[1], sys.argv[2], db_path)
