"""Downgrading the MCP revision must not turn MCP tokens into personal ones."""

import pytest
from alembic import command
from sqlalchemy import text

from app.database.db_upgrade import _alembic_config, _engine

REVISION = "e4b7c2a9d1f3"
PREVIOUS = "d3e8a1c6b2f9"


def _migrate(url, target, *, down=False):
    engine = _engine(url)
    config = _alembic_config(url)
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        (command.downgrade if down else command.upgrade)(config, target)
        connection.commit()
    engine.dispose()


@pytest.mark.unit
def test_downgrade_revokes_mcp_tokens_and_keeps_personal_ones(tmp_path):
    url = f"sqlite:///{tmp_path / 'borg.db'}"
    _migrate(url, REVISION)
    engine = _engine(url)
    with engine.begin() as db:
        db.execute(text("PRAGMA foreign_keys=OFF"))  # no user row needed
        for token_id, kind in ((1, "api"), (2, "mcp")):
            db.execute(
                text(
                    "INSERT INTO api_tokens (id, user_id, name, token_hash, prefix, kind, created_at) "
                    "VALUES (:id, 1, :kind, 'h', 'borgui_x', :kind, '2026-11-01')"
                ),
                {"id": token_id, "kind": kind},
            )
    engine.dispose()

    _migrate(url, PREVIOUS, down=True)
    engine = _engine(url)
    with engine.connect() as db:
        names = [row[0] for row in db.execute(text("SELECT name FROM api_tokens"))]
    engine.dispose()
    assert names == ["api"]
