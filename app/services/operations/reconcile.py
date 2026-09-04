"""Reconcile loop (spec section 7.5). Replaces stats_refresh_scheduler:
instead of calling Borg for every repository in a loop, it enqueues one
index run per repository and lets the runner pace the work."""

import asyncio
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.database.models import Operation, Repository, SystemSettings, utc_now
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.executors import registered_kinds
from app.services.operations.followups import PLAN_GATED_KINDS, history_enabled
from app.services.operations.vocab import PRIORITY_RECONCILE

logger = structlog.get_logger()

RECONCILE_CHAIN = ("archive_sync", "history_merge", "history_index", "stats")
DEFAULT_INTERVAL_MINUTES = 60
# How often to re-check the setting while reconciliation is disabled
# (stats_refresh_interval_minutes <= 0), so a later positive update resumes
# it without a process restart.
POLL_INTERVAL_WHEN_DISABLED_MINUTES = 5


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


def enqueue_reconcile_runs(db: Session, *, history: Optional[bool] = None) -> int:
    available = registered_kinds()
    if history is None:
        history = history_enabled(db)
    kinds = [
        k
        for k in RECONCILE_CHAIN
        if k in available and (history or k not in PLAN_GATED_KINDS)
    ]
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
    db.commit()
    logger.info("Reconcile runs enqueued", repositories=count, kinds=kinds)
    return count


def bootstrap_history_once(db: Session) -> int:
    """First startup after phase 2: enqueue a reconcile run for every
    repository at priority 20 (spec 14). Recorded on SystemSettings so it
    runs once per install, not once per restart."""
    system_settings = db.query(SystemSettings).first()
    if system_settings is None or system_settings.history_bootstrap_at is not None:
        return 0
    # Claim first and commit, so a second process starting at the same time
    # sees the timestamp and stops rather than enqueueing a duplicate set of
    # chains. The conditional UPDATE is what makes the claim exclusive; only
    # the caller whose UPDATE matched a row goes on.
    claimed = (
        db.query(SystemSettings)
        .filter(
            SystemSettings.id == system_settings.id,
            SystemSettings.history_bootstrap_at.is_(None),
        )
        .update({"history_bootstrap_at": utc_now()}, synchronize_session=False)
    )
    db.commit()
    if not claimed:
        return 0
    try:
        count = enqueue_reconcile_runs(db)
    except Exception:
        # Release the claim, or the bootstrap is recorded as done and the
        # install never gets its history.
        db.rollback()
        db.query(SystemSettings).filter(SystemSettings.id == system_settings.id).update(
            {"history_bootstrap_at": None}, synchronize_session=False
        )
        db.commit()
        raise
    logger.info("History bootstrap enqueued", repositories=count)
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
        self.running = True
        logger.info("Reconcile scheduler started")
        while self.running:
            interval = self._interval_minutes()
            if interval <= 0:
                await asyncio.sleep(POLL_INTERVAL_WHEN_DISABLED_MINUTES * 60)
                continue
            await asyncio.sleep(interval * 60)
            if not self.running:
                break
            interval = self._interval_minutes()
            if interval <= 0:
                continue
            db = SessionLocal()
            try:
                enqueue_reconcile_runs(db)
            except Exception as exc:
                logger.error("Reconcile run failed", error=str(exc))
            finally:
                db.close()


reconcile_scheduler = ReconcileScheduler()
