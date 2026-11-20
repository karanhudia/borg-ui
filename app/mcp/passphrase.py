"""Generated repository passphrases (spec 2026-11-14-mcp-server, 5.9).

The passphrase is made here, sent to the create route in-process and never
returned. `mark_unsaved` is the only direct database write in `app/mcp/`: no
REST client can set the flag, so only this path raises the banner.
"""

from __future__ import annotations

import secrets

from app.database.models import Repository
from app.mcp.db import session_scope


def generate() -> str:
    # 192 bits on one line; the create route refuses line breaks.
    return secrets.token_urlsafe(24)


def mark_unsaved(app, repo_id: int) -> None:
    with session_scope(app) as db:
        updated = (
            db.query(Repository)
            .filter(Repository.id == repo_id)
            .update({Repository.passphrase_unsaved: True})
        )
        if updated != 1:
            raise LookupError(f"repository {repo_id} not found")
