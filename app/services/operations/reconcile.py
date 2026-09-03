"""Reconcile loop (spec section 7.5). Replaces stats_refresh_scheduler:
instead of calling Borg for every repository in a loop, it enqueues one
index run per repository and lets the runner pace the work."""

import asyncio

import structlog
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.database.models import Operation, Repository, SystemSettings, utc_now
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.executors import registered_kinds
from app.services.operations.vocab import PRIORITY_RECONCILE

logger = structlog.get_logger()

RECONCILE_CHAIN = ("archive_sync", "history_merge", "history_index", "stats")
DEFAULT_INTERVAL_MINUTES = 60


def has_active_index_work(db: Session, repository_id: int) -> bool:
    return (
        db.query(Operation.id)
        .filter(
            Operation.repository_id == repository_id,
            Operation.category == "index",
            Operation.status.in_(("queued", "running")),
        )
        .first()
        is not None
    )


def enqueue_reconcile_runs(db: Session) -> int:
    available = registered_kinds()
    kinds = [k for k in RECONCILE_CHAIN if k in available]
    if not kinds:
        return 0
    count = 0
    for repo in db.query(Repository).all():
        if has_active_index_work(db, repo.id):
            continue
        enqueue_chain(
            db,
            kinds,
            repository_id=repo.id,
            trigger="reconcile",
            priority=PRIORITY_RECONCILE,
            commit=False,
        )
        count += 1
    settings = db.query(SystemSettings).first()
    if settings is not None:
        settings.last_stats_refresh = utc_now()
    db.commit()
    logger.info("Reconcile runs enqueued", repositories=count, kinds=kinds)
    return count


class ReconcileScheduler:
    def __init__(self):
        self.running = False

    def _interval_minutes(self) -> int:
        db = SessionLocal()
        try:
            settings = db.query(SystemSettings).first()
            if settings and settings.stats_refresh_interval_minutes is not None:
                return settings.stats_refresh_interval_minutes
            return DEFAULT_INTERVAL_MINUTES
        except Exception as exc:
            logger.warning("Failed to read reconcile interval", error=str(exc))
            return DEFAULT_INTERVAL_MINUTES
        finally:
            db.close()

    def stop(self) -> None:
        self.running = False

    async def start(self) -> None:
        interval = self._interval_minutes()
        if interval <= 0:
            logger.info("Reconcile scheduler disabled (interval=0)")
            self.running = False
            return
        self.running = True
        logger.info("Reconcile scheduler started", interval_minutes=interval)
        while self.running:
            await asyncio.sleep(interval * 60)
            if not self.running:
                break
            interval = self._interval_minutes()
            if interval <= 0:
                logger.info("Reconcile disabled, stopping scheduler")
                self.running = False
                break
            db = SessionLocal()
            try:
                enqueue_reconcile_runs(db)
            except Exception as exc:
                logger.error("Reconcile run failed", error=str(exc))
            finally:
                db.close()


reconcile_scheduler = ReconcileScheduler()
