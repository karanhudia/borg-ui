"""Database sessions for MCP code that runs outside a FastAPI dependency."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.orm import Session

from app.database.database import get_db


@contextmanager
def session_scope(app) -> Iterator[Session]:
    """A session from the app's `get_db`, honouring test overrides.

    Commits on a clean exit, rolls back on an error, always closes.
    """
    factory = app.dependency_overrides.get(get_db, get_db)
    generator = factory()
    db = next(generator)
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        generator.close()
