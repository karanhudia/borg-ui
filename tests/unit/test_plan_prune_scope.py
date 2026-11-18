"""Plan-scoped prune (issue #1549): the archive filter a plan's prune gets,
and the refusal when another plan's or schedule's archives would match it."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    Base,
    Repository,
    ScheduledJob,
)
from app.services.operations.series import (
    PruneScopeError,
    plan_archive_glob,
    plan_prune_match,
)
from app.utils.archive_names import build_archive_name


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
    ("template", "plan", "repo", "expected"),
    [
        ("{plan_name}-{now}", "nas", "r", "nas-[0-9]*"),
        ("{plan_name}_{date}_{time}", "nas", "r", "nas_[0-9]*_[0-9]*"),
        ("{now}-{plan_name}", "nas", "r", "[0-9]*-nas"),
        ("{plan_name}-{repo_name}-{timestamp}", "my docs", "r", "my-docs-r-[0-9]*"),
        # a formatted placeholder may not start with a digit
        ("{plan_name}-{now:%a}", "nas", "r", "nas-*"),
        # Borg's own placeholders expand at create time, so match anything
        ("{hostname}-{plan_name}-{now}", "nas", "r", "*-nas-[0-9]*"),
        # glob characters in a name are escaped and match only themselves
        ("{plan_name}-{now}", "a[b]*", "r", "a[[]b][*]-[0-9]*"),
        # no template: the default name builder (plan, repo, timestamp)
        (None, "nas", "r", "nas-r-[0-9]*"),
        ("", "nas", "r", "nas-r-[0-9]*"),
    ],
)
def test_plan_archive_glob(template, plan, repo, expected):
    assert plan_archive_glob(template, job_name=plan, repo_name=repo) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "template",
    [
        "{plan_name}-{now}",
        "{plan_name}-{utcnow}",
        "{plan_name}_{date}_{time}",
        "{plan_name}-{timestamp}",
        "{now}-{plan_name}",
        None,
    ],
)
def test_glob_matches_the_names_backups_actually_get(template):
    import fnmatch

    name = build_archive_name(
        "nas",
        "r",
        template,
        timestamp="2026-11-18T02:00:00.123",
        date="2026-11-18",
        time_str="02:00:00",
        unix_timestamp="1763431200",
    )
    assert fnmatch.fnmatchcase(
        name, plan_archive_glob(template, job_name="nas", repo_name="r")
    )


def _repo(db, version=1):
    repo = Repository(
        name="shared",
        path="/tmp/shared",
        encryption="none",
        compression="lz4",
        borg_version=version,
    )
    db.add(repo)
    db.commit()
    return repo


def _plan(db, repo, name, template="{plan_name}-{now}"):
    plan = BackupPlan(
        name=name, source_directories="[]", archive_name_template=template
    )
    db.add(plan)
    db.commit()
    db.add(
        BackupPlanRepository(
            backup_plan_id=plan.id, repository_id=repo.id, execution_order=0
        )
    )
    db.commit()
    return plan


@pytest.mark.unit
def test_borg1_plan_gets_its_glob_and_ignores_a_longer_sibling(db):
    repo = _repo(db)
    nas = _plan(db, repo, "nas")
    _plan(db, repo, "nas-docs")
    assert plan_prune_match(db, nas, repo) == "nas-[0-9]*"


@pytest.mark.unit
def test_borg2_plan_gets_its_exact_series(db):
    repo = _repo(db, version=2)
    nas = _plan(db, repo, "nas")
    _plan(db, repo, "nas-docs")
    assert plan_prune_match(db, nas, repo) == "id:nas"


@pytest.mark.unit
@pytest.mark.parametrize("version", [1, 2])
def test_refuses_when_another_plan_writes_matching_names(db, version):
    repo = _repo(db, version=version)
    first = _plan(db, repo, "first", template="photos-{now}")
    _plan(db, repo, "second", template="photos-{now}")
    with pytest.raises(PruneScopeError, match="second"):
        plan_prune_match(db, first, repo)


@pytest.mark.unit
def test_refuses_when_a_schedule_writes_matching_names(db):
    repo = _repo(db)
    plan = _plan(db, repo, "nas", template="{hostname}-{now}")
    db.add(
        ScheduledJob(
            name="legacy",
            cron_expression="0 2 * * *",
            repository_id=repo.id,
            archive_name_template="box-{now}",
        )
    )
    db.commit()
    with pytest.raises(PruneScopeError, match="legacy"):
        plan_prune_match(db, plan, repo)


@pytest.mark.unit
def test_escaped_glob_characters_match_only_themselves():
    import fnmatch

    glob = plan_archive_glob("{plan_name}-{now}", job_name="db[1]", repo_name="r")
    assert fnmatch.fnmatchcase("db[1]-2026-11-18T02:00:00.123", glob)
    assert not fnmatch.fnmatchcase("dbx1x-2026-11-18T02:00:00.123", glob)


@pytest.mark.unit
def test_borg2_refuses_a_series_with_a_borg_placeholder(db):
    repo = _repo(db, version=2)
    plan = _plan(db, repo, "nas", template="{hostname}-{plan_name}")
    with pytest.raises(PruneScopeError, match="placeholder"):
        plan_prune_match(db, plan, repo)


@pytest.mark.unit
@pytest.mark.parametrize("version", [1, 2])
def test_refuses_when_a_sibling_name_has_a_borg_placeholder(db, version):
    """`{hostname}-{now}` on a host called `nas` writes `nas-<date>`: whether
    it overlaps this plan cannot be told from the template, so refuse."""
    repo = _repo(db, version=version)
    plan = _plan(db, repo, "nas")
    _plan(db, repo, "laptop", template="{hostname}-{now}")
    with pytest.raises(PruneScopeError, match="laptop"):
        plan_prune_match(db, plan, repo)


@pytest.mark.unit
def test_a_marker_character_in_a_name_is_refused():
    with pytest.raises(PruneScopeError):
        plan_archive_glob("{plan_name}-{now}", job_name="a\ue001b", repo_name="r")


@pytest.mark.unit
def test_refuses_a_sibling_whose_names_match_on_some_dates_only(db):
    """`photos-{date}-{now}` written on the 15th matches `photos-[0-9]*-15-[0-9]*`:
    one sample date cannot rule that out, the token comparison does."""
    repo = _repo(db)
    plan = _plan(db, repo, "a", template="photos-{date}-15-{now}")
    _plan(db, repo, "b", template="photos-{date}-{now}")
    with pytest.raises(PruneScopeError, match="'b'"):
        plan_prune_match(db, plan, repo)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mine", "theirs"),
    [
        ("{plan_name}-{now}", "{plan_name}-docs-{now}"),
        ("nas-{now}-daily", "nas-{now}-weekly"),
        (None, None),  # default names differ by plan name
    ],
)
def test_disjoint_templates_stay_eligible(db, mine, theirs):
    repo = _repo(db)
    plan = _plan(db, repo, "nas", template=mine)
    _plan(db, repo, "box", template=theirs)
    assert plan_prune_match(db, plan, repo)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("version", "template"),
    [(1, "{now}"), (1, "{now:%Y%m%d%H%M%S}")],
)
def test_refuses_a_selector_without_fixed_text(db, version, template):
    repo = _repo(db, version=version)
    plan = _plan(db, repo, "nas", template=template)
    with pytest.raises(PruneScopeError, match="fixed text"):
        plan_prune_match(db, plan, repo)


@pytest.mark.unit
def test_refuses_literal_braces():
    with pytest.raises(PruneScopeError, match="brace"):
        plan_archive_glob("nas-{{hostname}}-{now}", job_name="nas", repo_name="r")


@pytest.mark.unit
def test_a_legacy_path_only_schedule_counts_as_a_sibling(db):
    repo = _repo(db)
    plan = _plan(db, repo, "nas", template="photos-{now}")
    db.add(
        ScheduledJob(
            name="old",
            cron_expression="0 2 * * *",
            repository=repo.path,
            archive_name_template="photos-{now}",
        )
    )
    db.commit()
    with pytest.raises(PruneScopeError, match="old"):
        plan_prune_match(db, plan, repo)


@pytest.mark.unit
def test_refuses_when_a_sibling_checkpoint_would_match(db):
    """`db-[0-9]*point` matches `db-<time>-weekly.checkpoint`."""
    repo = _repo(db)
    plan = _plan(db, repo, "a", template="db-{now}point")
    _plan(db, repo, "b", template="db-{now}-weekly")
    with pytest.raises(PruneScopeError, match="'b'"):
        plan_prune_match(db, plan, repo)


@pytest.mark.unit
def test_refuses_a_name_with_a_brace():
    with pytest.raises(PruneScopeError, match="brace"):
        plan_archive_glob("{plan_name}-{now}", job_name="x{utcnow}", repo_name="r")


@pytest.mark.unit
def test_a_path_schedule_with_links_elsewhere_is_not_a_sibling(db):
    from app.database.models import ScheduledJobRepository

    repo = _repo(db)
    other = Repository(
        name="other", path="/tmp/other", encryption="none", compression="lz4"
    )
    db.add(other)
    db.commit()
    plan = _plan(db, repo, "nas", template="photos-{now}")
    job = ScheduledJob(
        name="old",
        cron_expression="0 2 * * *",
        repository=repo.path,
        archive_name_template="photos-{now}",
    )
    db.add(job)
    db.commit()
    db.add(
        ScheduledJobRepository(
            scheduled_job_id=job.id, repository_id=other.id, execution_order=0
        )
    )
    db.commit()
    assert plan_prune_match(db, plan, repo) == "photos-[0-9]*"
