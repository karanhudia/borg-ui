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
    cron_for_repository,
    infer_series,
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
    assert cron_for_repository(db, repo)[0] == "0 2 * * *"
    assert series_prefixes_for_repository(db, other) == ["other-o"]
