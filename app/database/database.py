from sqlalchemy import create_engine, event, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from app.config import settings
import os
from pathlib import Path

# Ensure database directory exists before creating engine
if settings.database_url.startswith("sqlite:///"):
    # Extract database file path from URL
    # Format: sqlite:////absolute/path/to/db.db
    db_path = settings.database_url.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)

    # Create directory if it doesn't exist
    if db_dir and not os.path.exists(db_dir):
        Path(db_dir).mkdir(parents=True, exist_ok=True)
        print(f"Created database directory: {db_dir}")

# Create database engine with connection pooling
# Note: echo=False disables SQL query logging for performance
# Use LOG_LEVEL=DEBUG environment variable if you need to debug SQL queries
engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,  # Always disable SQL logging for performance (creates massive log spam)
)

# Enable foreign key constraints for SQLite
# This is required for CASCADE deletes to work properly
if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL lets readers proceed without blocking the single writer, and
        # busy_timeout retries a transiently-locked write instead of raising
        # "database is locked" -- both matter under the concurrent multi-repo
        # maintenance load that a plan run creates.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def _set_utc_session_timezone(dbapi_conn, connection_record):
    # SET TIME ZONE is transactional: run outside a transaction, otherwise the
    # pool's reset-on-return rollback reverts it and only the connection's
    # first checkout is UTC (every reuse falls back to the server default).
    # The SQLAlchemy recipe for SET-on-connect: flip the DBAPI connection to
    # autocommit around the statement, then restore.
    previous_autocommit = dbapi_conn.autocommit
    dbapi_conn.autocommit = True
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute("SET TIME ZONE 'UTC'")
        cursor.close()
    finally:
        dbapi_conn.autocommit = previous_autocommit


def register_utc_session_timezone(target_engine) -> None:
    """Pin the session timezone to UTC on PostgreSQL connections.

    Datetime columns store naive UTC. An aware value written to
    `timestamp without time zone` is converted through the SESSION zone
    before the offset is stripped - correct only while that zone is UTC.
    Pinning it here makes the convention hold by construction instead of
    by the server's or environment's default. No-op on SQLite, whose
    storage never consults a session zone.
    """
    if target_engine.dialect.name != "postgresql":
        return
    event.listen(target_engine, "connect", _set_utc_session_timezone)


register_utc_session_timezone(engine)


# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Every constraint needs a name it was given deliberately, not one the database
# happened to invent: SQLite cannot ALTER a constraint, so changing one means
# rebuilding the table and recreating the constraint by name. An unnamed
# constraint cannot be recreated, and the rebuild fails.
# "ix" reproduces the names SQLAlchemy already generates, so no index is renamed.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Create base class for models
Base = declarative_base(metadata=MetaData(naming_convention=NAMING_CONVENTION))


def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
