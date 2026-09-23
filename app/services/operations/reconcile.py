"""Reconcile loop (spec section 7.5). Replaces stats_refresh_scheduler:
instead of calling Borg for every repository in a loop, it enqueues one
index run per repository and lets the runner pace the work."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.database.database import SessionLocal
from app.database.models import Operation, Repository, SystemSettings, utc_now
from app.services.operations.enqueue import enqueue_chain
from app.services.operations.executors import registered_kinds
from app.services.operations.followups import (
    PLAN_GATED_KINDS,
    history_possible_for,
)
from app.services.operations.index_mode import (
    DEFAULT_INDEX_MODE,
    filter_kinds,
    mode_for_repository,
)
from app.services.operations.vocab import PRIORITY_RECONCILE

logger = structlog.get_logger()

RECONCILE_CHAIN = ("archive_sync", "history_index", "stats")
DEFAULT_INTERVAL_MINUTES = 60
# How often to re-check the setting while reconciliation is disabled
# (stats_refresh_interval_minutes <= 0), so a later positive update resumes
# it without a process restart. The wait for the next run is cut into the
# same slices, so a changed interval applies within one of them.
POLL_INTERVAL_WHEN_DISABLED_MINUTES = 5


def has_active_index_work(db: Session, repository_id: int) -> bool:
    """True when a reconcile run for the repository would only pile up: index
    work is already waiting to start, or an archive sync is in flight. A
    running history index, merge or stats refresh does not count. History
    can take hours, and holding the hourly sync behind it would leave the
    archive list stale while nothing is wrong; a merge or stats is bounded
    by the info timeout, and the run queued behind it starts once it is
    done (the tick runs the index operations of one repository one at a
    time)."""
    waiting = db.query(Operation.id).filter(
        Operation.repository_id == repository_id,
        Operation.category == "index",
        Operation.status == "queued",
    )
    syncing = db.query(Operation.id).filter(
        Operation.repository_id == repository_id,
        Operation.kind == "archive_sync",
        Operation.status == "running",
    )
    return waiting.first() is not None or syncing.first() is not None


def reconcile_kinds(
    db: Session, *, history: bool = True, mode: str = DEFAULT_INDEX_MODE
) -> list:
    """The reconcile chain, minus kinds this install has no executor for,
    kinds this repository cannot have built (`history`, the executor gate),
    and kinds the repository's index mode does not refresh (spec 6.8)."""
    available = registered_kinds()
    return filter_kinds(
        mode,
        [
            k
            for k in RECONCILE_CHAIN
            if k in available and (history or k not in PLAN_GATED_KINDS)
        ],
    )


def enqueue_reconcile_run(
    db: Session,
    repository_id: int,
    *,
    manual: bool = False,
    force: bool = False,
    commit: bool = True,
) -> list:
    """One repository's reconcile run. Returns the operations enqueued, or an
    empty list when index work for the repository is already in flight, so a
    burst of callers (a run of archive deletes, say) queues one run rather
    than one per call.

    `manual=True` is a user asking for this run: an `off` repository is
    listed once anyway (spec 6.8, "manual work is not gated by the mode"),
    but history is never re-enabled behind a mode that excludes it, and
    nothing is scheduled to repeat. The trigger stays `reconcile` either
    way: it names the chain, and the resync route has always recorded its
    runs under it.

    `force=True` skips the in-flight check. The catch-up run on returning to
    `full` (spec 6.8) needs it: the work already queued was built for the
    narrower mode and will never produce the history stages, so deferring to
    it would mean no catch-up at all until the next tick. The reopen of a
    repository moved from an agent back to the server is the same case: the
    agent's listing that may still be queued carries no history stage.
    """
    mode = mode_for_repository(db, repository_id)
    if manual and mode == "off":
        # The one-off look: archive_sync and stats, this once.
        mode = "archives"
    # The executor gate is per repository (an agent's repository gets a
    # history stage only while its agent runs `repository.diff`).
    kinds = reconcile_kinds(
        db, history=history_possible_for(db, repository_id), mode=mode
    )
    if not kinds or (not force and has_active_index_work(db, repository_id)):
        return []
    return enqueue_chain(
        db,
        kinds,
        repository_id=repository_id,
        trigger="reconcile",
        priority=PRIORITY_RECONCILE,
        commit=commit,
    )


def enqueue_reconcile_runs(db: Session) -> int:
    # No early return on an empty chain: the chain now differs per
    # repository (spec 6.8), so it is resolved inside the loop, and the
    # kinds are left out of the log for the same reason.
    count = 0
    for repo in db.query(Repository).all():
        if enqueue_reconcile_run(db, repo.id, commit=False):
            count += 1
    db.commit()
    logger.info("Reconcile runs enqueued", repositories=count)
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


def seconds_until_due(
    last_tick: Optional[datetime], interval_minutes: int, now: datetime
) -> float:
    """Seconds until `last_tick + interval`; 0 when that has passed. No last
    tick, or one in the future (the clock moved back), is due now."""
    if last_tick is None or last_tick > now:
        return 0.0
    try:
        due = last_tick + timedelta(minutes=interval_minutes)
    except OverflowError:
        # An interval past the datetime range is never due.
        return float("inf")
    return max(0.0, (due - now).total_seconds())


class ReconcileScheduler:
    """Runs the reconcile tick every `stats_refresh_interval_minutes`,
    counted from the last tick rather than from process start: a restart
    neither skips a tick nor moves the time of the next one. The time of the
    last tick is stored on SystemSettings."""

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

    def _last_tick_at(self) -> Optional[datetime]:
        db = SessionLocal()
        try:
            settings = db.query(SystemSettings).first()
            return settings.last_reconcile_tick_at if settings else None
        finally:
            db.close()

    def _tick(self, now: datetime) -> None:
        db = SessionLocal()
        try:
            enqueue_reconcile_runs(db)
            # Stored after the enqueue, so a tick that failed is repeated
            # after a restart. A tick that enqueued nothing still counts.
            # Two commits on purpose: a failed write of the time must not
            # undo the enqueue, and a tick repeated after a crash in between
            # skips the repositories whose run is still queued.
            # The settings row is not created here; until it exists the
            # tick time is only kept in memory.
            db.query(SystemSettings).update(
                {"last_reconcile_tick_at": now}, synchronize_session=False
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Reconcile run failed", error=str(exc))
        finally:
            db.close()

    def stop(self) -> None:
        self.running = False

    async def start(self) -> None:
        # Startup registers the executors, recovers interrupted operations
        # and starts the runner before this loop, so a tick that is overdue
        # at start can be enqueued right away; the runner paces the work.
        self.running = True
        logger.info("Reconcile scheduler started")
        poll = POLL_INTERVAL_WHEN_DISABLED_MINUTES * 60
        last_tick = None
        last_tick_read = False
        while self.running:
            if not last_tick_read:
                # A failed read is retried, not taken as "no tick yet":
                # that would run a tick at once and move the schedule.
                try:
                    last_tick = self._last_tick_at()
                    last_tick_read = True
                except Exception as exc:
                    logger.warning("Failed to read last reconcile tick", error=str(exc))
                    await asyncio.sleep(poll)
                    continue
            interval = self._interval_minutes()
            if interval <= 0:
                await asyncio.sleep(poll)
                continue
            now = utc_now()
            wait = seconds_until_due(last_tick, interval, now)
            if wait > 0:
                await asyncio.sleep(min(wait, poll))
                continue
            # Kept in memory as well, so a tick that failed waits a full
            # interval within this process, as it always has.
            last_tick = now
            self._tick(now)
            # A tick that outlasts the interval leaves the next one due at
            # once; give way to the event loop in between.
            await asyncio.sleep(0)


reconcile_scheduler = ReconcileScheduler()
