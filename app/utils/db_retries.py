import asyncio

from sqlalchemy.exc import OperationalError


def _is_sqlite_lock_error(db, exc: OperationalError) -> bool:
    bind = getattr(db, "bind", None)
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
    return dialect_name == "sqlite" and "database is locked" in str(exc).lower()


async def commit_with_retry(
    db,
    *,
    retries: int = 5,
    base_delay_seconds: float = 0.2,
    prepare=None,
    logger=None,
    action: str = "commit",
    **log_fields,
):
    """Retry transient SQLite lock failures during async job updates."""
    attempt = 0
    while True:
        try:
            if prepare is not None:
                prepare()
            db.commit()
            return
        except OperationalError as exc:
            db.rollback()
            if not _is_sqlite_lock_error(db, exc) or attempt >= retries:
                raise

            if logger is not None:
                logger.warning(
                    "Retrying database commit after SQLite lock",
                    action=action,
                    attempt=attempt + 1,
                    retries=retries,
                    error=str(exc),
                    **log_fields,
                )

            attempt += 1
            await asyncio.sleep(base_delay_seconds * attempt)
