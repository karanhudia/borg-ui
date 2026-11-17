import asyncio
import concurrent.futures
import functools
import inspect

from sqlalchemy import create_engine, event, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
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
    # A failed statement's error text is logged; it must not carry the values,
    # secrets among them.
    hide_parameters=True,
)

# Enable foreign key constraints for SQLite
# This is required for CASCADE deletes to work properly
if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        """Configure each SQLite connection for integrity and lock tolerance."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL lets readers proceed without blocking the single writer, and
        # busy_timeout retries a transiently-locked write instead of raising
        # "database is locked" -- both matter under the concurrent multi-repo
        # maintenance load that a plan run creates. 5s was not enough: an
        # index run writing an archive list holds the lock for longer than
        # that, and the plan run beside it died recording why a repository
        # was busy.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
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


# not_null_violation and check_violation: the refusals whose detail repeats
# the row ("Failing row contains (...)", in the server's message language)
_ROW_REPEATING_SQLSTATES = frozenset({"23502", "23514"})


def _withhold_failing_row(context) -> None:
    # PostgreSQL repeats a refused row in its message, values included, and
    # the message is logged.
    orig = context.original_exception
    if getattr(orig, "sqlstate", None) not in _ROW_REPEATING_SQLSTATES:
        return
    detail = getattr(getattr(orig, "diag", None), "message_detail", None)
    if not detail:
        return
    for exc in (orig, context.sqlalchemy_exception):
        if exc is not None and exc.args and isinstance(exc.args[0], str):
            exc.args = (
                exc.args[0].replace(detail, "Failing row withheld."),
                *exc.args[1:],
            )


def register_failing_row_withholding(target_engine) -> None:
    """Keep the values of a row PostgreSQL refuses out of the error text, as
    `hide_parameters` keeps a statement's parameters out. No-op on SQLite,
    whose messages name the constraint only."""
    if target_engine.dialect.name != "postgresql":
        return
    event.listen(target_engine, "handle_error", _withhold_failing_row)


register_utc_session_timezone(engine)
register_failing_row_withholding(engine)


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


# A request's session holds a pooled connection from its first query until it
# commits, rolls back or closes; FastAPI closes it after the response. The pool
# (10 + 20) and the worker threads (30) are both shared. A request that holds a
# connection while it waits for a worker thread, while the threads wait for
# connections, waits until the pool timeout. So does the event loop when it
# waits for a connection: most come back through request cleanup that runs on
# the loop. The helpers below keep requests and the loop out of those waits.


def queries_in_threads(handler):
    """For a coroutine handler that passes the request's session to
    `run_off_loop` and never queries on the event loop itself. Its request
    waits for one of those threads next, so it is treated as a plain `def`
    handler is: authentication gives the connection back first."""
    handler.queries_in_threads = True
    return handler


def handler_uses_session_on_loop(request) -> bool:
    """Whether the request's handler is a coroutine that takes the request's
    session itself. It queries on the event loop, after its dependencies:
    the connection the session holds saves it a checkout there. Every other
    handler runs in a worker thread, queries in threads only
    (`queries_in_threads`), or does not use that session."""
    route = request.scope.get("route")
    endpoint = getattr(route, "endpoint", None)
    if endpoint is None or not inspect.iscoroutinefunction(endpoint):
        return False
    if getattr(endpoint, "queries_in_threads", False):
        return False
    return any(dependency.call is get_db for dependency in route.dependant.dependencies)


def handler_runs_in_worker(request) -> bool:
    """Whether the request's handler queries in threads only: a plain `def`
    function, which FastAPI runs in a worker thread, or a coroutine marked
    with `queries_in_threads`. A query it makes after its dependencies never
    waits for a connection on the event loop. False when the route is not
    known."""
    route = request.scope.get("route")
    endpoint = getattr(route, "endpoint", None)
    if endpoint is None:
        return False
    return not inspect.iscoroutinefunction(endpoint) or getattr(
        endpoint, "queries_in_threads", False
    )


def end_read_keeping_loaded(db: Session, *instances) -> None:
    """End the session's read transaction and keep `instances` as loaded.

    The rollback gives the connection back to the pool until the session
    needs one again, as the repository waiter does. A plain rollback expires
    every loaded instance, and the next attribute read would query again.
    Taken out of the session for the rollback and added back, the instances
    keep their values, and the next commit still writes what is changed on
    them.
    """
    for instance in instances:
        db.expunge(instance)
    db.rollback()
    for instance in instances:
        db.add(instance)


def ends_read_on_return(handler):
    """For a plain `def` handler: end its session's transaction when it
    returns. FastAPI validates the response of a `def` handler in another
    shared worker thread and closes the session only after that, so the
    request would wait for that thread while holding its connection. The
    handler returns values, not rows that still need the session.

    When it raises as well: a lock it took would stay until the session is
    closed, and the event loop has to take a turn for that."""

    @functools.wraps(handler)
    def wrapper(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        finally:
            for value in kwargs.values():
                if isinstance(value, Session):
                    value.rollback()

    return wrapper


def checkout_can_wait(bind) -> bool:
    """Whether a checkout from `bind` can wait for a connection. Only a
    QueuePool makes it wait. The other pools (in tests) share one connection,
    keep one per thread or open a new one: they never wait, and some must not
    hand a connection to another thread."""
    return isinstance(getattr(bind, "pool", None), QueuePool)


# Threads of their own for `run_off_loop`; its callers wait for one at a time.
_OFF_LOOP_THREADS = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="db-off-loop"
)


async def run_off_loop(function, *args):
    """Run `function` in a thread and return its result, for blocking database
    work of code on the event loop: on the loop, a wait for a pooled connection
    holds every request. The thread is not one of AnyIO's worker threads,
    which the requests holding the connections may wait for. A caller that is
    cancelled meanwhile still waits for the thread to finish before it goes
    on, so its cleanup never runs while the thread is still at work."""
    work = _OFF_LOOP_THREADS.submit(function, *args)
    try:
        return await asyncio.shield(asyncio.wrap_future(work))
    except asyncio.CancelledError:
        # `work` itself cannot be cancelled once it runs: wait for the thread.
        while not work.done():
            try:
                await asyncio.shield(asyncio.wrap_future(work))
            except (asyncio.CancelledError, Exception):
                pass
        raise


async def connect_off_loop(engine):
    """A connection checked out from `engine` by `run_off_loop`. A session
    bound to it keeps it across its commits, so none of its statements waits
    for a checkout on the loop. Closed again if the caller is cancelled while
    it is checked out."""
    connection = None

    def connect():
        nonlocal connection
        connection = engine.connect()

    try:
        await run_off_loop(connect)
    except BaseException:
        if connection is not None:
            connection.close()
        raise
    return connection
