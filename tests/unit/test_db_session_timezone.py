"""The engine pins the PostgreSQL session timezone to UTC.

Datetime columns store naive UTC; an aware value written to `timestamp
without time zone` converts through the SESSION zone before the offset is
stripped. The pin makes that safe by construction; these tests hold the pin
and the canonical naive-UTC helper in place.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import QueuePool

from app.database.database import (
    _set_utc_session_timezone,
    register_utc_session_timezone,
)
from app.utils.datetime_utils import utc_now

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
requires_postgres = pytest.mark.skipif(
    not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
)


def test_listener_pins_the_session_to_utc():
    conn = MagicMock()

    _set_utc_session_timezone(conn, None)

    conn.cursor.return_value.execute.assert_called_once_with("SET TIME ZONE 'UTC'")
    conn.cursor.return_value.close.assert_called_once()


def test_registration_is_a_noop_on_sqlite():
    engine = create_engine("sqlite://")

    register_utc_session_timezone(engine)

    assert not event.contains(engine, "connect", _set_utc_session_timezone)


def test_registration_attaches_on_postgresql():
    # Engine creation is lazy - no server is contacted here.
    engine = create_engine("postgresql+psycopg://user@localhost/borg_test")

    register_utc_session_timezone(engine)

    assert event.contains(engine, "connect", _set_utc_session_timezone)


def test_db_upgrade_engine_is_pinned_on_postgresql():
    # Alembic runs migrations on this engine's connection when one is
    # supplied (config.attributes["connection"]), bypassing env.py's own
    # engine - the pin must ride on the factory.
    from app.database.db_upgrade import _engine

    engine = _engine("postgresql+psycopg://user@localhost/borg_test")

    assert event.contains(engine, "connect", _set_utc_session_timezone)


@requires_postgres
def test_postgres_session_runs_utc_regardless_of_server_default():
    # Force a non-UTC session default via connection options so the
    # assertion cannot pass just because the server already defaults to
    # UTC (CI's postgres container does).
    connect_args = {"options": "-c timezone=Europe/Berlin"}

    control = create_engine(POSTGRES_URL, connect_args=connect_args)
    try:
        with control.connect() as conn:
            assert conn.execute(text("SHOW TIME ZONE")).scalar() == "Europe/Berlin"
    finally:
        control.dispose()

    # A single QueuePool connection, checked out twice. The connect event
    # fires once (physical connect); on the first return the pool issues its
    # reset-on-return rollback. If SET TIME ZONE ran inside a transaction it
    # would be reverted, and checkout #2 would report the server default -
    # the bug. Both checkouts must report UTC.
    engine = create_engine(
        POSTGRES_URL, connect_args=connect_args, poolclass=QueuePool, pool_size=1
    )
    register_utc_session_timezone(engine)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SHOW TIME ZONE")).scalar() == "UTC"
        # Same pooled connection, after reset-on-return.
        with engine.connect() as conn:
            assert conn.execute(text("SHOW TIME ZONE")).scalar() == "UTC"
    finally:
        engine.dispose()


def test_utc_now_is_naive_utc():
    value = utc_now()

    assert value.tzinfo is None
    reference = datetime.now(timezone.utc).replace(tzinfo=None)
    assert abs((reference - value).total_seconds()) < 5


def test_model_defaults_use_the_canonical_helper():
    # Column defaults (created_at/updated_at across the schema) funnel
    # through the one shared helper - asserted on the columns themselves,
    # not just the imported symbol.
    from app.database.database import Base
    from app.database import models

    # The symbol models exports IS the shared helper ...
    assert models.utc_now is utc_now

    # ... and every utc_now column default/onupdate produces its naive-UTC
    # form. (SQLAlchemy wraps the callable, so identity on .arg is not
    # checkable - the produced value is what the convention needs anyway.)
    seen = 0
    for table in Base.metadata.tables.values():
        for column in table.columns:
            for default in (column.default, column.onupdate):
                arg = getattr(default, "arg", None)
                if callable(arg) and getattr(arg, "__name__", "") == "utc_now":
                    produced = arg(None)
                    assert produced.tzinfo is None, f"{table.name}.{column.name}"
                    seen += 1
    # created_at defaults plus updated_at default+onupdate pairs.
    assert seen >= 20
