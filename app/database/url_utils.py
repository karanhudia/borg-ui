"""Database-URL helpers shared by the standalone admin/startup scripts.

Deliberately free of import side effects (no engine, no settings), so a
script can use the guard before deciding whether to connect at all.
"""

from pathlib import Path

from sqlalchemy.engine import make_url


def sqlite_database_missing(database_url: str) -> bool:
    """True when the URL points at a SQLite file that does not exist yet.

    Scripts check this before connecting, because connecting would create an
    empty database file. A server database is always "present" — a missing
    schema there surfaces as a query error instead.
    """
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        return False
    # sqlite:// leaves url.database empty (Path(None) would raise), and
    # sqlite:///:memory: is a real in-memory database, not a missing file.
    if not url.database or url.database == ":memory:":
        return False
    return not Path(url.database).exists()
