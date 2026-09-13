from datetime import datetime
from typing import Optional

import structlog

from app.core.borg_errors import is_borg_warning_exit_code
from app.services.borg2_compact_stats import (
    MAX_COUNT,
    PRECISION_EXACT,
    PRECISION_ROUNDED,
)
from app.services.storage_usage import (
    SOURCE_COMPACT_STATS,
    SOURCE_STORAGE_USED,
    set_repository_size,
)

logger = structlog.get_logger()


def apply_compact_stats(job, repository, stats: Optional[dict]) -> bool:
    """Persist `borg compact --stats` output on the job and, where nothing
    else measures this repository, fill the repository size from it,
    labelled `compact_stats`: pack file bytes, as exact as Borg printed
    them (`stats["size_precision"]`). A measured size (the index sum, the
    Borg 1 cache statistics, or a size that predates the source label) is
    never replaced: the `stats` follow-up measures again after every
    compact anyway. A store walk (`storage_used`, store file bytes) and an
    older compact's figure give way to an exact compact figure; a rounded
    one (a compact without `BORG_UNITS=raw`) fills an empty size or
    replaces an older compact's. Returns whether the size was written. On
    an operation the facade files the statistics under `result["stats"]`;
    a pre-phase-5 legacy row has nowhere to keep them and drops the
    attribute with the instance."""
    if not stats:
        return False
    job.stats = stats
    exact = stats.get("size_precision", PRECISION_ROUNDED) == PRECISION_EXACT
    replaceable = (
        {SOURCE_COMPACT_STATS, SOURCE_STORAGE_USED} if exact else {SOURCE_COMPACT_STATS}
    )
    source = getattr(repository, "total_size_source", None)
    measured = (
        source not in replaceable
        if source is not None
        else bool(getattr(repository, "total_size", None))
    )
    if measured:
        logger.debug(
            "Measured repository size kept over compact statistics",
            repository_id=getattr(repository, "id", None),
            total_size_source=source,
            size_precision=stats.get("size_precision"),
        )
        return False
    size = stats.get("repository_size")
    # 0 is a measurement here (an emptied repository), unlike the size
    # fallbacks, where 0 means "could not measure". The upper bound keeps a
    # figure no Borg printed away from `format_bytes`.
    if not (
        isinstance(size, int) and not isinstance(size, bool) and 0 <= size < MAX_COUNT
    ):
        return False
    set_repository_size(repository, size, SOURCE_COMPACT_STATS)
    return True


def apply_compact_completion(
    job, repository, returncode: int, *, now=None, stats: Optional[dict] = None
) -> bool:
    """Apply the shared terminal compact state to a job and repository.
    Returns whether the repository size was written from `stats`."""
    completed_at = now or datetime.utcnow()
    job.completed_at = completed_at

    if returncode == 0:
        job.status = "completed"
        job.progress = 100
        job.progress_message = "Compact completed successfully"
        repository.last_compact = completed_at
        return apply_compact_stats(job, repository, stats)

    if is_borg_warning_exit_code(returncode):
        job.status = "completed_with_warnings"
        job.progress = 100
        job.progress_message = (
            f"Compact completed with warnings (exit code {returncode})"
        )
        job.error_message = job.progress_message
        repository.last_compact = completed_at
        return apply_compact_stats(job, repository, stats)

    job.status = "failed"
    job.error_message = f"Compact failed with exit code {returncode}"
    return False
