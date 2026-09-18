"""Retention comparison (spec 4.5): a fixed set of policies run through the
prune preview's dry run and stored per repository. Wording is fixed:
compared policies, would free at least. Nothing here picks a policy for the user."""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import Archive, PruneComparison, Repository
from app.services.operations.repository_status import pending_removed_ids
from app.services.prune_preview import (
    DryRunFailed,
    Retention,
    retention_defaults,
    run_candidate,
)
from app.utils.datetime_utils import serialize_datetime, utc_now

logger = logging.getLogger(__name__)

PRESETS: list[tuple[str, str, Retention]] = [
    (
        "standard",
        "Standard",
        Retention(keep_daily=7, keep_weekly=4, keep_monthly=6, keep_yearly=1),
    ),
    (
        "longer",
        "Longer",
        Retention(keep_daily=14, keep_weekly=8, keep_monthly=12, keep_yearly=2),
    ),
    (
        "wide",
        "Wide",
        Retention(keep_daily=30, keep_weekly=0, keep_monthly=12, keep_yearly=3),
    ),
]

_KEEP_FIELDS = (
    "keep_hourly",
    "keep_daily",
    "keep_weekly",
    "keep_monthly",
    "keep_quarterly",
    "keep_yearly",
    "keep_within",
)


def _current(db: Session, repository: Repository) -> Optional[Retention]:
    defaults = retention_defaults(db, repository)
    if defaults["source"] == "default":
        # The dialog's prefill, not a policy anyone set (spec 4.5: no source,
        # no policy).
        return None
    retention = Retention(
        **{
            k: defaults.get(k) or (None if k == "keep_within" else 0)
            for k in _KEEP_FIELDS
        }
    )
    return retention if retention.has_rule else None


def candidates(
    db: Session, repository: Repository
) -> list[tuple[str, str, Optional[Retention]]]:
    """The current policy first (None when there is none), then the presets
    that differ from it."""
    current = _current(db, repository)
    rows: list[tuple[str, str, Optional[Retention]]] = [("current", "Current", current)]
    for key, label, preset in PRESETS:
        if current is not None and preset.as_params() == current.as_params():
            continue
        rows.append((key, label, preset))
    return rows


def current_archive_count(db: Session, repository: Repository) -> int:
    removed = pending_removed_ids(db, repository.id)
    q = db.query(Archive.id).filter(Archive.repository_id == repository.id)
    if removed:
        q = q.filter(Archive.id.notin_(removed))
    return q.count()


async def run_comparison(
    db: Session,
    repository: Repository,
    *,
    run_id: Optional[str],
    depends_on_id: Optional[int],
) -> list[PruneComparison]:
    """Run every candidate, then replace the repository's rows wholesale. A
    candidate whose dry run failed is left out; the others still land. When
    none did, the previous rows stay: an outage should not erase a good
    comparison."""
    count = current_archive_count(db, repository)
    computed_at = utc_now()
    rows: list[PruneComparison] = []
    for key, label, retention in candidates(db, repository):
        if retention is None:
            rows.append(
                PruneComparison(
                    repository_id=repository.id,
                    candidate=key,
                    label=label,
                    retention=None,
                    kept_count=count,
                    deleted_count=0,
                    freed_at_least=0,
                    partial_measure=False,
                    operation_id=None,
                    archive_count_at=count,
                    computed_at=computed_at,
                )
            )
            continue
        try:
            result = await run_candidate(
                db,
                repository,
                retention,
                user_id=None,
                run_id=run_id,
                depends_on_id=depends_on_id,
            )
        except DryRunFailed:
            continue
        except Exception:
            # run_prune_dry_run already failed the candidate's inline row.
            logger.exception("prune_compare: %s dry run raised", key)
            continue
        rows.append(
            PruneComparison(
                repository_id=repository.id,
                candidate=key,
                label=label,
                retention=retention.as_params(),
                kept_count=result.kept_count,
                deleted_count=result.deleted_count,
                freed_at_least=result.freed_at_least,
                partial_measure=result.partial_measure,
                operation_id=result.operation.id,
                archive_count_at=count,
                computed_at=computed_at,
            )
        )
    if not rows:
        return []
    db.query(PruneComparison).filter(
        PruneComparison.repository_id == repository.id
    ).delete(synchronize_session=False)
    db.add_all(rows)
    db.commit()
    return rows


def _row_payload(row: PruneComparison) -> dict:
    return {
        "key": row.candidate,
        "label": row.label,
        "retention": row.retention,
        "kept_count": row.kept_count,
        "deleted_count": row.deleted_count,
        "freed_at_least": row.freed_at_least,
        "partial_measure": row.partial_measure,
        "operation_id": row.operation_id,
    }


def stored(db: Session, repository: Repository) -> dict:
    rows = (
        db.query(PruneComparison)
        .filter(PruneComparison.repository_id == repository.id)
        .order_by(PruneComparison.id)
        .all()
    )
    if not rows:
        return {
            "computed_at": None,
            "archive_count_at": None,
            "stale": True,
            "candidates": [],
        }
    count_at = rows[0].archive_count_at
    return {
        "computed_at": serialize_datetime(rows[0].computed_at),
        "archive_count_at": count_at,
        "stale": current_archive_count(db, repository) != count_at,
        "candidates": [_row_payload(r) for r in rows],
    }


def space_savings(db: Session, repositories: list[Repository]) -> list[dict]:
    """Dashboard: the row that frees the most per repository, top three,
    repositories with nothing computed or nothing to free left out."""
    by_id = {r.id: r for r in repositories}
    rows = (
        db.query(PruneComparison)
        .filter(
            PruneComparison.repository_id.in_(list(by_id)),
            PruneComparison.freed_at_least > 0,
        )
        .all()
    )
    best: dict[int, PruneComparison] = {}
    for row in rows:
        if (
            row.repository_id not in best
            or row.freed_at_least > best[row.repository_id].freed_at_least
        ):
            best[row.repository_id] = row
    out = []
    for repo_id, row in best.items():
        repository = by_id[repo_id]
        out.append(
            {
                "repository_id": repo_id,
                "repository_name": repository.name,
                "candidate": row.candidate,
                "label": row.label,
                "retention": row.retention,
                "freed_at_least": row.freed_at_least,
                "computed_at": serialize_datetime(row.computed_at),
                "stale": current_archive_count(db, repository) != row.archive_count_at,
            }
        )
    out.sort(key=lambda r: r["freed_at_least"], reverse=True)
    return out[:3]
