"""Series inference (spec section 6.6).

Borg 2 names a series directly. For Borg 1 the series is the literal prefix
of a schedule or plan archive name template that targets the repository,
else the archive name with a trailing timestamp stripped, else "default".
"""

import fnmatch
import re
from typing import Optional, Sequence

from sqlalchemy.orm import Session

from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
)
from app.utils.archive_names import TIME_PLACEHOLDER_PATTERN, build_archive_name

DEFAULT_SERIES = "default"

_TIMESTAMP_SUFFIXES = (
    # 2026-09-02T02:00:00, 2026-09-02_02-00-00, 2026-09-02 02:00:00,
    # optional fraction and zone offset
    re.compile(
        r"[-_.]?\d{4}-\d{2}-\d{2}[T_ -]\d{2}[:\-.]?\d{2}[:\-.]?\d{2}"
        r"(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?$"
    ),
    # 20260902T020000, 20260902_020000, 20260902-020000
    re.compile(r"[-_.]?\d{8}[T_-]?\d{6}$"),
    # 2026-09-02
    re.compile(r"[-_.]?\d{4}-\d{2}-\d{2}$"),
    # unix epoch seconds
    re.compile(r"[-_.]?\d{10}$"),
)


def strip_timestamp(name: str) -> Optional[str]:
    """Return the name without its trailing timestamp, or None when there is
    no timestamp or nothing would remain.

    Applied until no pattern matches: a name from a template that carries both
    (`nas-2026-04-30-1777586400`) kept its date after the epoch came off, so
    every archive of that template became a series of its own (issue #943).
    """
    result = name
    while True:
        for pattern in _TIMESTAMP_SUFFIXES:
            stripped = pattern.sub("", result, count=1).rstrip("-_.")
            if stripped != result and stripped:
                result = stripped
                break
        else:
            return result if result != name else None


def template_prefix(
    template: Optional[str], *, job_name: str, repo_name: Optional[str]
) -> Optional[str]:
    """The literal prefix backups from this template share: the template
    rendered with its time placeholders removed. Without a template the
    default name builder applies, so the prefix is job (and repo) name."""
    prefix = build_archive_name(
        job_name, repo_name, template, timestamp="", stable_series=True
    )
    return prefix or None


# Stand-ins for time placeholders while a template renders into a glob: the
# rendered literal text is escaped first, then these become wildcards.
_DIGITS_MARK = "\ue000"
_ANY_MARK = "\ue001"
# What a sibling's archive name looks like, to test it against a plan's glob.
_SAMPLE_TIME = {
    "timestamp": "2026-01-01T00:00:00.000",
    "date": "2026-01-01",
    "time_str": "00:00:00",
    "unix_timestamp": "1767225600",
}


_UNRESOLVED_PLACEHOLDER = re.compile(r"\{[^{}]*\}")


class PruneScopeError(ValueError):
    """A plan-scoped prune cannot be limited to the plan's own archives."""


def plan_archive_glob(
    template: Optional[str], *, job_name: str, repo_name: Optional[str]
) -> str:
    """Borg 1 `--glob-archives` pattern matching the names this template
    gives backups (issue #1549). Time placeholders become `[0-9]*` so plan
    "nas" does not match plan "nas-docs"; a formatted one (`{now:%a}`) and
    Borg's own placeholders (`{hostname}`) can be anything, so `*`. Glob
    characters in the literal text are escaped as one-character classes
    (`[[]`, `[*]`, `[?]`), so they match only themselves.
    """
    marked = (
        TIME_PLACEHOLDER_PATTERN.sub(
            lambda m: _ANY_MARK if ":" in m.group(0) else _DIGITS_MARK, template
        )
        if template
        else template
    )
    name = build_archive_name(job_name, repo_name, marked, timestamp=_DIGITS_MARK)
    name = re.sub(r"[*?\[]", lambda m: f"[{m.group(0)}]", name)
    name = re.sub(r"\{[^{}]*\}", "*", name)
    return name.replace(_DIGITS_MARK, "[0-9]*").replace(_ANY_MARK, "*")


def _schedules_for(db: Session, repository: Repository) -> list[ScheduledJob]:
    direct = (
        db.query(ScheduledJob).filter(ScheduledJob.repository_id == repository.id).all()
    )
    linked_ids = [
        row.scheduled_job_id
        for row in db.query(ScheduledJobRepository.scheduled_job_id)
        .filter(ScheduledJobRepository.repository_id == repository.id)
        .all()
    ]
    linked = (
        db.query(ScheduledJob).filter(ScheduledJob.id.in_(linked_ids)).all()
        if linked_ids
        else []
    )
    seen: set[int] = set()
    result = []
    for job in direct + linked:
        if job.id not in seen:
            seen.add(job.id)
            result.append(job)
    return result


def _plans_for(
    db: Session, repository: Repository, *, active_links_only: bool = False
) -> list[BackupPlan]:
    """Plans targeting the repository.

    `active_links_only` drops plans whose link to this repository is disabled.
    The executor skips those links, so their cadence and prune settings say
    nothing about what this repository receives or keeps. Series prefixes want
    them anyway: a link disabled today still named the archives it wrote
    yesterday.
    """
    links = db.query(BackupPlanRepository.backup_plan_id).filter(
        BackupPlanRepository.repository_id == repository.id
    )
    if active_links_only:
        links = links.filter(BackupPlanRepository.enabled.is_(True))
    plan_ids = [row.backup_plan_id for row in links.all()]
    if not plan_ids:
        return []
    return db.query(BackupPlan).filter(BackupPlan.id.in_(plan_ids)).all()


def series_prefixes_for_repository(db: Session, repository: Repository) -> list[str]:
    """Template prefixes of every schedule and plan targeting the repository,
    longest first so "nas-docs" wins over "nas"."""
    prefixes: set[str] = set()
    for job in _schedules_for(db, repository):
        prefix = template_prefix(
            job.archive_name_template, job_name=job.name, repo_name=repository.name
        )
        if prefix:
            prefixes.add(prefix)
    for plan in _plans_for(db, repository):
        prefix = template_prefix(
            plan.archive_name_template, job_name=plan.name, repo_name=repository.name
        )
        if prefix:
            prefixes.add(prefix)
    return sorted(prefixes, key=len, reverse=True)


def plan_prune_match(db: Session, plan: BackupPlan, repository: Repository) -> str:
    """The archive filter that limits this plan's prune to its own archives:
    a `--glob-archives` pattern on Borg 1, an exact `-a id:<series>` on
    Borg 2. Raises PruneScopeError when another plan or schedule targeting
    the repository writes names the filter also matches, since pruning
    those under this plan's retention is the loss the scope exists to stop.
    """
    borg2 = getattr(repository, "borg_version", 1) == 2
    if borg2:
        series = template_prefix(
            plan.archive_name_template, job_name=plan.name, repo_name=repository.name
        )

        def matches(name: str) -> bool:
            return name == series

        if _UNRESOLVED_PLACEHOLDER.search(series):
            # Borg fills these in at create time; the exact selector would
            # not match the real name, and a sibling's could expand to it.
            raise PruneScopeError(
                f"Prune limited to this plan was not run: its archive name "
                f"'{series}' has a placeholder Borg fills in, so its archives "
                "cannot be selected by name. Use a template without one."
            )
        result = f"id:{series}"
    else:
        glob = plan_archive_glob(
            plan.archive_name_template, job_name=plan.name, repo_name=repository.name
        )

        def matches(name: str) -> bool:
            return fnmatch.fnmatchcase(name, glob)

        result = glob

    siblings = [("schedule", s) for s in _schedules_for(db, repository)] + [
        ("plan", p) for p in _plans_for(db, repository) if p.id != plan.id
    ]
    for kind, source in siblings:
        if borg2:
            sample = template_prefix(
                source.archive_name_template,
                job_name=source.name,
                repo_name=repository.name,
            )
        else:
            sample = build_archive_name(
                source.name,
                repository.name,
                source.archive_name_template,
                **_SAMPLE_TIME,
            )
        if sample and _UNRESOLVED_PLACEHOLDER.search(sample):
            # Borg expands it at create time (`{hostname}`, `{now:%a}`), so
            # whether the real names overlap this plan's cannot be told here.
            raise PruneScopeError(
                f"Prune limited to this plan was not run: {kind} "
                f"'{source.name}' names its archives with a placeholder Borg "
                "fills in, so its archives cannot be told apart from this "
                "plan's."
            )
        if sample and matches(sample):
            raise PruneScopeError(
                f"Prune limited to this plan was not run: archives of {kind} "
                f"'{source.name}' also match '{result}'. Use different archive name templates "
                "for the two."
            )
    return result


def crons_for_repository(
    db: Session, repository: Repository
) -> list[tuple[str, Optional[str]]]:
    """Cron expression and timezone of every enabled cron schedule and backup
    plan that targets the repository, for the missed-run rule (spec 9.5).

    A repository backed up by a plan has no `ScheduledJob`, so reading
    schedules alone left the cadence unknown (issue #943). A repository with
    more than one cadence expects the days of all of them, so every match is
    returned rather than whichever row came first.
    """
    crons: list[tuple[str, Optional[str]]] = []
    for job in _schedules_for(db, repository):
        if job.enabled and job.schedule_mode == "cron" and job.cron_expression:
            crons.append((job.cron_expression, job.timezone))
    for plan in _plans_for(db, repository, active_links_only=True):
        if (
            plan.enabled
            and plan.schedule_enabled
            and plan.schedule_mode == "cron"
            and plan.cron_expression
        ):
            crons.append((plan.cron_expression, plan.timezone))
    return crons


# Borg's own units: `interval("1m")` is 744 hours and `interval("1y")` 8760,
# so a month is 31 days and a year 365.
_WITHIN_UNIT_DAYS = {"H": 1 / 24, "d": 1, "w": 7, "m": 31, "y": 365}


def keep_within_days(value: Optional[str]) -> Optional[float]:
    """Borg's `--keep-within` interval (`48H`, `30d`, `4w`) in days."""
    if not value:
        return None
    text = value.strip()
    unit = _WITHIN_UNIT_DAYS.get(text[-1:])
    if unit is None:
        return None
    try:
        return int(text[:-1]) * unit
    except ValueError:
        return None


def retention_days_for_repository(db: Session, repository: Repository) -> Optional[int]:
    """How many days back a daily archive is still expected to exist, from the
    prune settings of every schedule and plan that targets the repository, or
    None when nothing here prunes it.

    A day older than this has no archive because retention removed it, which
    is not a missed run (issue #943). The widest setting wins; only the daily
    keeps and `keep_within` count, since weekly and monthly keeps leave most
    days without an archive by design.
    """
    # ponytail: only prune we run ourselves is visible here. A repository
    # pruned by an external cron reports no retention window, and its missed
    # days rest on the run records alone; read prune operations if that turns
    # out to matter.
    sources = [
        source
        for source in list(_schedules_for(db, repository))
        + list(_plans_for(db, repository, active_links_only=True))
        # A disabled source never runs its prune, so its keeps say nothing
        # about what is retained; counting them widened the window and put
        # genuinely pruned days back in the red (PR #1051 review).
        if source.enabled and source.run_prune_after
    ]
    if not sources:
        return None
    spans = [0.0]
    for source in sources:
        spans.append(float(source.prune_keep_daily or 0))
        within = keep_within_days(source.prune_keep_within)
        if within:
            spans.append(within)
    return int(max(spans))


def infer_series(name: str, borg_version: int, prefixes: Sequence[str] = ()) -> str:
    if borg_version == 2:
        return name
    # Sort here rather than trust caller order, so the longest (most
    # specific) matching prefix always wins regardless of how it was
    # passed in.
    for prefix in sorted(prefixes, key=len, reverse=True):
        if name == prefix or name.startswith(prefix + "-"):
            return prefix
    stripped = strip_timestamp(name)
    if stripped:
        return stripped
    return DEFAULT_SERIES
