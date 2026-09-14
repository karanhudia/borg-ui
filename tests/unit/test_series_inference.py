import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    Base,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
)
from app.services.operations.series import (
    crons_for_repository,
    infer_series,
    keep_within_days,
    retention_days_for_repository,
    series_prefixes_for_repository,
    strip_timestamp,
    template_prefix,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("nas-2026-09-02T02:00:00", "nas"),
        ("nas-2026-09-02T02:00:00.123456", "nas"),
        ("nas-2026-09-02_02-00-00", "nas"),
        ("nas-2026-09-02 02:00:00", "nas"),
        ("nas-20260902T020000", "nas"),
        ("nas-20260902_020000", "nas"),
        ("nas-2026-09-02", "nas"),
        ("nas-1756778400", "nas"),
        # a template carrying both a date and an epoch: stripping once left
        # the date on and made every archive its own series (issue #943)
        ("nas-2026-04-30-1777586400", "nas"),
        ("nas-2026-04-30T02:00:00-1777586400", "nas"),
        ("docs-laptop-2026-09-02T02:00:00+02:00", "docs-laptop"),
        ("2026-09-02T02:00:00", None),
        ("nas", None),
    ],
)
def test_strip_timestamp(name, expected):
    assert strip_timestamp(name) == expected


@pytest.mark.unit
def test_template_prefix_drops_time_placeholders():
    assert (
        template_prefix("{job_name}-{now}", job_name="nightly", repo_name="nas")
        == "nightly"
    )
    assert (
        template_prefix(
            "{repo_name}-{job_name}-{now:%Y%m%d}", job_name="n", repo_name="nas"
        )
        == "nas-n"
    )
    assert template_prefix(None, job_name="nightly", repo_name="nas") == "nightly-nas"
    assert template_prefix("{now}", job_name="x", repo_name=None) == "x"


@pytest.mark.unit
def test_infer_series_prefers_longest_prefix_then_timestamp_then_default():
    prefixes = ["nas", "nas-docs"]
    assert infer_series("nas-docs-2026-09-02T02:00:00", 1, prefixes) == "nas-docs"
    assert infer_series("nas-2026-09-02T02:00:00", 1, prefixes) == "nas"
    assert infer_series("nas", 1, prefixes) == "nas"
    assert infer_series("photos-2026-09-02T02:00:00", 1, prefixes) == "photos"
    assert infer_series("manual", 1, prefixes) == "default"
    assert (
        infer_series("nas-2026-09-02T02:00:00", 2, prefixes)
        == "nas-2026-09-02T02:00:00"
    )


@pytest.mark.unit
def test_series_prefixes_come_from_schedules_and_plans(db):
    repo = Repository(name="nas", path="/tmp/nas", encryption="none", compression="lz4")
    other = Repository(name="o", path="/tmp/o", encryption="none", compression="lz4")
    db.add_all([repo, other])
    db.commit()
    direct = ScheduledJob(
        name="nightly",
        cron_expression="0 2 * * *",
        repository_id=repo.id,
        archive_name_template="{job_name}-{now}",
    )
    linked = ScheduledJob(name="weekly", cron_expression="0 3 * * 0")
    unrelated = ScheduledJob(
        name="other", cron_expression="0 4 * * *", repository_id=other.id
    )
    db.add_all([direct, linked, unrelated])
    db.commit()
    db.add(
        ScheduledJobRepository(
            scheduled_job_id=linked.id, repository_id=repo.id, execution_order=0
        )
    )
    plan = BackupPlan(
        name="photos plan",
        source_directories="[]",
        archive_name_template="{plan_name}-{repo_name}-{now}",
    )
    db.add(plan)
    db.commit()
    db.add(
        BackupPlanRepository(
            backup_plan_id=plan.id, repository_id=repo.id, execution_order=0
        )
    )
    db.commit()

    prefixes = series_prefixes_for_repository(db, repo)
    assert prefixes == sorted(
        {"nightly", "weekly-nas", "photos-plan-nas"}, key=len, reverse=True
    )
    # Every cadence targeting the repository counts, not whichever row came
    # first: the heatmap unions their expected days (PR #1051 review).
    assert sorted(c for c, _ in crons_for_repository(db, repo)) == [
        "0 2 * * *",
        "0 3 * * 0",
    ]
    assert series_prefixes_for_repository(db, other) == ["other-o"]


@pytest.mark.unit
def test_retention_window_ignores_disabled_sources(db):
    """A disabled schedule never runs its prune, so its keeps must not widen
    the window and put genuinely pruned days back in the red."""
    repo = Repository(name="nas", path="/tmp/nas", encryption="none", compression="lz4")
    db.add(repo)
    db.commit()
    db.add_all(
        [
            ScheduledJob(
                name="nightly",
                cron_expression="0 2 * * *",
                repository_id=repo.id,
                enabled=True,
                run_prune_after=True,
                prune_keep_daily=7,
            ),
            ScheduledJob(
                name="retired",
                cron_expression="0 3 * * *",
                repository_id=repo.id,
                enabled=False,
                run_prune_after=True,
                prune_keep_daily=365,
            ),
        ]
    )
    db.commit()

    assert retention_days_for_repository(db, repo) == 7


@pytest.mark.unit
def test_a_disabled_plan_link_gives_no_cadence_but_keeps_its_prefix(db):
    """The executor skips a disabled link, so the plan never writes here and
    its cron says nothing about this repository. Its prefix still has to name
    the archives it wrote while the link was on."""
    repo = Repository(name="nas", path="/tmp/nas", encryption="none", compression="lz4")
    db.add(repo)
    db.commit()
    plan = BackupPlan(
        name="photos plan",
        source_directories="[]",
        archive_name_template="{plan_name}-{now}",
        enabled=True,
        schedule_enabled=True,
        schedule_mode="cron",
        cron_expression="0 5 * * *",
        run_prune_after=True,
        prune_keep_daily=365,
    )
    db.add(plan)
    db.commit()
    db.add(
        BackupPlanRepository(
            backup_plan_id=plan.id,
            repository_id=repo.id,
            execution_order=0,
            enabled=False,
        )
    )
    db.commit()

    assert crons_for_repository(db, repo) == []
    assert retention_days_for_repository(db, repo) is None
    assert series_prefixes_for_repository(db, repo) == ["photos-plan"]


@pytest.mark.unit
def test_keep_within_days_matches_borg_units():
    """Borg's own `interval()` reads 1m as 744 hours and 1y as 8760, so a
    month is 31 days and a year 365, not 366."""
    assert keep_within_days("48H") == 2
    assert keep_within_days("30d") == 30
    assert keep_within_days("4w") == 28
    assert keep_within_days("1m") == 31
    assert keep_within_days("1y") == 365
    assert keep_within_days("nonsense") is None
    assert keep_within_days(None) is None
