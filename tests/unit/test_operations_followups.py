import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, SystemSettings
from app.services.operations.enqueue import enqueue
from app.services.operations.executors import load_default_executors
from app.services.operations.followups import (
    FOLLOWUPS,
    chain_for,
    enqueue_backup_followups,
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


@pytest.fixture()
def repo(db):
    load_default_executors()
    r = Repository(name="r", path="/tmp/r", encryption="none", compression="lz4")
    db.add(r)
    db.add(SystemSettings())
    db.commit()
    return r


@pytest.mark.unit
def test_chain_table_matches_spec_7_4():
    assert FOLLOWUPS == {
        "import_connect": ("stats", "archive_sync", "history_index"),
        "backup": ("archive_sync", "history_index", "stats"),
        "prune": ("archive_sync", "stats"),
        "delete_archive": ("archive_sync", "stats"),
        "compact": ("stats",),
        "check": (),
        "wipe": ("archive_sync", "stats"),
        "restore": (),
        "restore_check": (),
        "rclone_sync": (),
        "package_install": (),
        "stats": (),
        "archive_sync": ("prune_compare",),
        "history_index": (),
        "prune_compare": (),
    }


@pytest.mark.unit
def test_prune_compare_follows_a_listing_that_changed_the_archive_set(
    db, repo, monkeypatch
):
    """Spec 4.5: the comparison hangs off archive_sync only when rows were
    added or removed, so an unchanged listing does not spend four dry runs."""
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    sync = enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    sync.status = "completed"
    sync.result = {"listed": 3, "new": 0, "removed_archive_ids": []}
    db.commit()
    assert (
        enqueue_followups(db, sync, depends_on_id=sync.id, available={"prune_compare"})
        == []
    )

    sync.result = {"listed": 4, "new": 1, "removed_archive_ids": []}
    db.commit()
    ops = enqueue_followups(
        db, sync, depends_on_id=sync.id, available={"prune_compare"}
    )
    assert [o.kind for o in ops] == ["prune_compare"]
    assert ops[0].depends_on_id == sync.id
    assert ops[0].trigger == "followup"


@pytest.mark.unit
def test_prune_compare_follows_a_listing_that_removed_archives(db, repo, monkeypatch):
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    sync = enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    sync.status = "completed"
    sync.result = {"listed": 2, "new": 0, "removed_archive_ids": [7]}
    db.commit()
    ops = enqueue_followups(
        db, sync, depends_on_id=sync.id, available={"prune_compare"}
    )
    assert [o.kind for o in ops] == ["prune_compare"]


@pytest.mark.unit
def test_prune_compare_does_not_follow_when_automatic_previews_are_off(
    db, repo, monkeypatch
):
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    db.query(SystemSettings).first().auto_prune_preview = False
    sync = enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    sync.status = "completed"
    sync.result = {"listed": 4, "new": 1, "removed_archive_ids": [7]}
    db.commit()
    assert (
        enqueue_followups(db, sync, depends_on_id=sync.id, available={"prune_compare"})
        == []
    )


@pytest.mark.unit
def test_chain_for_filters_to_available_executors():
    assert chain_for("import_connect") == ["stats", "archive_sync", "history_index"]
    assert chain_for("import_connect", available={"stats", "archive_sync"}) == [
        "stats",
        "archive_sync",
    ]
    assert chain_for("prune", available={"stats", "archive_sync"}) == [
        "archive_sync",
        "stats",
    ]
    assert chain_for("check") == []


@pytest.mark.unit
def test_chain_for_rejects_unknown_kind():
    with pytest.raises(ValueError):
        chain_for("bogus")


@pytest.mark.unit
def test_chain_for_drops_history_kinds_for_community():
    assert chain_for("backup", history=False) == [
        "archive_sync",
        "stats",
    ]
    assert chain_for("import_connect", history=False) == ["stats", "archive_sync"]
    assert chain_for("backup") == [
        "archive_sync",
        "history_index",
        "stats",
    ]
    assert chain_for(
        "backup", available={"archive_sync", "history_index"}, history=False
    ) == ["archive_sync"]


@pytest.mark.unit
def test_history_enabled_follows_plan(db_session):
    from app.database.models import LicensingState
    from app.services.operations.followups import history_enabled

    assert history_enabled(db_session) is False
    # get_or_create_licensing_state creates the single row on first access
    # above, so flip that row's plan rather than inserting a second one
    # (LicensingState lookups always take the first row in the table).
    state = db_session.query(LicensingState).first()
    state.plan = "pro"
    state.status = "active"
    db_session.commit()
    assert history_enabled(db_session) is True


@pytest.mark.unit
def test_no_chain_carries_a_separate_removal_stage():
    """archive_sync deletes the archives its listing no longer sees (#1141),
    so no chain on any plan or mode needs history_merge after it; only
    history_index is plan gated (spec 11.2)."""
    from app.services.operations.followups import PLAN_GATED_KINDS

    assert PLAN_GATED_KINDS == {"history_index"}
    for kind in FOLLOWUPS:
        for history in (True, False):
            assert "history_merge" not in chain_for(kind, history=history)
    assert chain_for("prune", history=False) == ["archive_sync", "stats"]


@pytest.mark.unit
def test_enqueue_backup_followups_creates_the_backup_chain(db, repo, monkeypatch):
    """A backup that completed outside the runner (#933) enqueues the spec
    7.4 chain as a follow-up run. The index is built on every plan, so
    history_index is in it."""
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    ops = enqueue_backup_followups(
        db, repo.id, scheduled_job_id=None, backup_plan_run_id=None
    )
    assert [o.kind for o in ops] == [
        "archive_sync",
        "history_index",
        "stats",
    ]
    assert {o.trigger for o in ops} == {"followup"}
    assert {o.priority for o in ops} == {10}
    assert ops[1].depends_on_id == ops[0].id
    assert len({o.run_id for o in ops}) == 1


@pytest.mark.unit
def test_enqueue_backup_followups_skips_when_an_index_run_is_queued(
    db, repo, monkeypatch
):
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    assert enqueue_backup_followups(db, repo.id) == []


@pytest.mark.unit
def test_enqueue_backup_followups_ignores_a_running_index_run(db, repo, monkeypatch):
    """A running listing may predate the backup, so it does not satisfy it."""
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    running = enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    running.status = "running"
    db.commit()
    ops = enqueue_backup_followups(db, repo.id, commit=False)
    db.commit()
    assert [o.kind for o in ops] == [
        "archive_sync",
        "history_index",
        "stats",
    ]
    assert db.query(Operation).filter_by(status="queued").count() == 3


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["stats", "history_index", "history_merge"])
def test_queued_non_listing_work_does_not_suppress_backup_followups(
    db, repo, monkeypatch, kind
):
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    enqueue(db, kind, repository_id=repo.id, trigger="reconcile")
    ops = enqueue_backup_followups(db, repo.id)
    assert any(op.kind == "archive_sync" for op in ops)


@pytest.mark.unit
def test_running_listing_with_queued_children_does_not_suppress_followups(
    db, repo, monkeypatch
):
    from app.services.operations.enqueue import enqueue_chain

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    chain = enqueue_chain(
        db,
        ["archive_sync", "history_merge", "stats"],
        repository_id=repo.id,
        trigger="reconcile",
    )
    chain[0].status = "running"
    db.commit()
    ops = enqueue_backup_followups(db, repo.id)
    assert any(op.kind == "archive_sync" for op in ops)


@pytest.mark.unit
@pytest.mark.parametrize(
    "parent_status,skip_reason,suppresses",
    [
        ("completed", None, True),
        ("completed_with_warnings", None, True),
        ("skipped", "agent_diff_unsupported", True),
        ("skipped", "plan_locked", True),
        ("skipped", None, True),
        ("skipped", "dependency_failed", False),
        ("failed", None, False),
        ("cancelled", None, False),
        ("running", None, False),
        ("queued", None, False),
        ("missing", None, False),
    ],
)
def test_only_listing_with_satisfied_parent_suppresses_followups(
    db, repo, monkeypatch, parent_status, skip_reason, suppresses
):
    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    parent = enqueue(db, "stats", repository_id=repo.id, trigger="manual")
    listing = enqueue(
        db,
        "archive_sync",
        repository_id=repo.id,
        depends_on_id=parent.id,
        trigger="manual",
    )
    if parent_status == "missing":
        # Model a missing dependency defensively (foreign keys are disabled here).
        listing.depends_on_id = parent.id + 1000
    else:
        parent.status = parent_status
        parent.skip_reason = skip_reason
    db.commit()
    ops = enqueue_backup_followups(db, repo.id)
    assert bool(ops) is not suppresses
    if ops:
        assert ops[0].kind == "archive_sync"


@pytest.mark.unit
def test_listing_behind_queued_parent_with_failed_ancestor_does_not_suppress(
    db, repo, monkeypatch
):
    from app.services.operations.enqueue import enqueue_chain

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    chain = enqueue_chain(
        db,
        ["stats", "history_index", "archive_sync"],
        repository_id=repo.id,
        trigger="manual",
    )
    chain[0].status = "failed"
    db.commit()
    ops = enqueue_backup_followups(db, repo.id)
    assert ops and ops[0].kind == "archive_sync"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("plan", ["community", "pro"])
async def test_backup_followup_chain_deletes_removed_archive_and_keeps_survivor(
    db, repo, monkeypatch, tmp_path, plan
):
    import asyncio
    from datetime import datetime
    from unittest.mock import AsyncMock

    from app.core.borg_router import BorgRouter
    from app.database.models import Archive, LicensingState
    from app.services.operations.executors import index, history
    from app.services.operations.runner import OperationRunner
    from app.services.storage_usage import SizeResult

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr("app.config.settings.index_archive_info_per_run", 0)
    db.add(LicensingState(instance_id="followup-test", plan=plan, status="active"))
    survivor = Archive(
        repository_id=repo.id,
        borg_id="aa11",
        name="nas-2026-09-01",
        series="nas",
        start=datetime(2026, 9, 1),
        history_state="indexed",
    )
    removed = Archive(
        repository_id=repo.id,
        borg_id="bb22",
        name="nas-2026-09-02",
        series="nas",
        start=datetime(2026, 9, 2),
    )
    db.add_all([survivor, removed])
    repo.archive_count = 2
    repo.last_backup = removed.start
    db.commit()
    survivor_id, removed_id = survivor.id, removed.id
    monkeypatch.setattr(
        BorgRouter,
        "list_archives_checked",
        AsyncMock(
            return_value=(
                True,
                [
                    {
                        "id": "aa11",
                        "name": "nas-2026-09-01",
                        "time": "2026-09-01T00:00:00.000000",
                    }
                ],
            )
        ),
    )
    monkeypatch.setattr(
        index, "_prepare_repository_borg_env", lambda repository, db: ({}, None)
    )
    monkeypatch.setattr(
        index,
        "measure_repository_size",
        AsyncMock(return_value=SizeResult(bytes=123, source="borg1_cache_stats")),
    )
    runner = OperationRunner(
        session_factory=sessionmaker(bind=db.get_bind()),
        registry={
            "archive_sync": index.run_archive_sync,
            "history_index": history.run_history_index,
            "stats": index.run_stats,
        },
    )
    ops = enqueue_backup_followups(db, repo.id)
    for _ in range(10):
        await runner.tick()
        if runner.running_tasks:
            await asyncio.gather(*list(runner.running_tasks.values()))
    db.expire_all()
    assert db.get(Archive, removed_id) is None
    assert db.get(Archive, survivor_id).borg_id == "aa11"
    assert db.query(Archive).filter_by(repository_id=repo.id).count() == 1
    assert repo.archive_count == 1
    assert repo.last_backup == datetime(2026, 9, 1)
    assert all(db.get(Operation, op.id).status == "completed" for op in ops)


@pytest.mark.unit
def test_enqueue_followups_skips_a_chain_already_queued_on_the_repository(
    db, repo, monkeypatch
):
    """The shape of a plan backup with inline prune and compact: the backup's
    chain is queued first, then prune and compact finish. Their chains are
    subsets of what already waits, so they enqueue nothing (the queued rows
    start after now and see the pruned repository)."""
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    backup = enqueue(db, "backup", repository_id=repo.id, trigger="plan")
    backup.status = "completed"
    db.commit()
    chain = enqueue_followups(db, backup, depends_on_id=backup.id)
    assert [o.kind for o in chain] == [
        "archive_sync",
        "history_index",
        "stats",
    ]

    last = None
    for kind in ("prune", "compact"):
        step = enqueue(
            db,
            kind,
            repository_id=repo.id,
            trigger="plan",
            run_id=backup.run_id,
            depends_on_id=backup.id,
        )
        step.status = "completed"
        db.commit()
        assert enqueue_followups(db, step, depends_on_id=step.id) == []
        last = step

    assert db.query(Operation).filter(Operation.trigger == "followup").count() == 3
    # The refresh is the last thing the run does: its head now hangs off
    # the compact, the last stage to finish, and the rest of the chain
    # still hangs off the head.
    db.refresh(chain[0])
    assert last is not None and chain[0].depends_on_id == last.id
    assert chain[1].depends_on_id == chain[0].id


@pytest.mark.unit
def test_enqueue_followups_leaves_another_runs_chain_where_it_is(db, repo, monkeypatch):
    """A reconcile's queued listing covers a manual prune's refresh, but it
    is not the prune's run, so it keeps its own dependency."""
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    sync = enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    enqueue(
        db,
        "history_merge",
        repository_id=repo.id,
        trigger="reconcile",
        run_id=sync.run_id,
        depends_on_id=sync.id,
    )
    enqueue(
        db,
        "stats",
        repository_id=repo.id,
        trigger="reconcile",
        run_id=sync.run_id,
        depends_on_id=sync.id,
    )
    prune = enqueue(db, "prune", repository_id=repo.id, trigger="manual")
    prune.status = "completed"
    db.commit()
    assert enqueue_followups(db, prune, depends_on_id=prune.id) == []
    db.refresh(sync)
    assert sync.depends_on_id is None


@pytest.mark.unit
def test_enqueue_followups_does_not_trust_a_chain_behind_a_failed_row(
    db, repo, monkeypatch
):
    """A queued chain whose dependency failed will be skipped as
    dependency_failed, so it covers nothing."""
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    failed = enqueue(db, "backup", repository_id=repo.id, trigger="plan")
    failed.status = "failed"
    db.commit()
    for kind, parent in (
        ("archive_sync", failed),
        ("history_merge", None),
        ("stats", None),
    ):
        parent = parent or db.query(Operation).order_by(Operation.id.desc()).first()
        enqueue(
            db,
            kind,
            repository_id=repo.id,
            trigger="followup",
            run_id=failed.run_id,
            depends_on_id=parent.id,
        )

    prune = enqueue(db, "prune", repository_id=repo.id, trigger="manual")
    prune.status = "completed"
    db.commit()
    chain = enqueue_followups(db, prune, depends_on_id=prune.id)
    assert [o.kind for o in chain] == ["archive_sync", "stats"]


@pytest.mark.unit
def test_enqueue_followups_does_not_trust_a_chain_behind_a_missing_row(
    db, repo, monkeypatch
):
    """The runner skips a queued row whose dependency no longer exists, so
    such a chain covers nothing and a fresh one is enqueued."""
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    orphan = enqueue(db, "archive_sync", repository_id=repo.id, trigger="followup")
    orphan.depends_on_id = 999_999
    db.commit()
    prune = enqueue(db, "prune", repository_id=repo.id, trigger="manual")
    prune.status = "completed"
    db.commit()
    chain = enqueue_followups(db, prune, depends_on_id=prune.id)
    assert [o.kind for o in chain] == ["archive_sync", "stats"]


@pytest.mark.unit
def test_enqueue_followups_ignores_a_running_chain(db, repo, monkeypatch):
    """A listing already running may have started before this operation
    changed the repository, so it does not count."""
    from app.services.operations.followups import enqueue_followups

    monkeypatch.setattr("app.services.operations.enqueue.wake_runner", lambda: None)
    running = enqueue(db, "archive_sync", repository_id=repo.id, trigger="reconcile")
    running.status = "running"
    db.commit()
    prune = enqueue(db, "prune", repository_id=repo.id, trigger="manual")
    prune.status = "completed"
    db.commit()
    chain = enqueue_followups(db, prune, depends_on_id=prune.id)
    assert [o.kind for o in chain] == ["archive_sync", "stats"]


@pytest.mark.unit
def test_history_capability_names_the_reason(db_session):
    """The agent first, then the plan: a repository whose agent does not
    advertise the diff job reads as agent-unsupported on every plan (an
    upgrade would not change it); one whose agent does is decided by the
    plan like a server repository: plan-locked on Community, available on
    Pro."""
    from app.database.models import AgentMachine, LicensingState
    from app.services.operations.followups import (
        history_capability,
        history_possible,
        history_possible_for,
    )

    older = AgentMachine(
        name="older",
        agent_id="agt_older",
        token_hash="x",
        token_prefix="x",
        status="online",
        capabilities=["repository.list_archives"],
    )
    current = AgentMachine(
        name="current",
        agent_id="agt_current",
        token_hash="y",
        token_prefix="y",
        status="online",
        capabilities=["repository.list_archives", "repository.diff"],
    )
    # advertised the job once, then revoked: the admission refuses it every
    # job, so the history it promised cannot be built either
    revoked = AgentMachine(
        name="revoked",
        agent_id="agt_revoked",
        token_hash="z",
        token_prefix="z",
        status="revoked",
        capabilities=["repository.list_archives", "repository.diff"],
    )
    db_session.add_all([older, current, revoked])
    db_session.flush()
    server = Repository(name="server", path="/repo/server", borg_version=1)
    # no agent assigned: nothing could run the job
    agent = Repository(
        name="agent",
        path="/repo/agent",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
    )
    old_agent = Repository(
        name="old-agent",
        path="/repo/old-agent",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=older.id,
    )
    capable = Repository(
        name="capable",
        path="/repo/capable",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=current.id,
    )
    revoked_agent = Repository(
        name="revoked-agent",
        path="/repo/revoked-agent",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=revoked.id,
    )
    db_session.add_all([server, agent, old_agent, capable, revoked_agent])
    db_session.commit()

    assert history_capability(db_session, server) == "plan_locked"
    assert history_capability(db_session, agent) == "agent_unsupported"
    assert history_capability(db_session, old_agent) == "agent_unsupported"
    assert history_capability(db_session, revoked_agent) == "agent_unsupported"
    assert history_capability(db_session, capable) == "plan_locked"
    state = db_session.query(LicensingState).first()
    state.plan = "pro"
    state.status = "active"
    db_session.commit()
    assert history_capability(db_session, server) == "available"
    assert history_capability(db_session, agent) == "agent_unsupported"
    assert history_capability(db_session, old_agent) == "agent_unsupported"
    assert history_capability(db_session, capable) == "available"
    assert history_possible(db_session, capable) is True
    assert history_possible_for(db_session, capable.id) is True
    assert history_capability(db_session, capable, history=False) == "plan_locked"
    assert history_possible(db_session, server) is True
    assert history_possible(db_session, agent) is False
    # the plan gate can be handed in by a caller that already read it
    assert history_capability(db_session, agent, history=False) == "agent_unsupported"
    assert history_capability(db_session, server, history=False) == "plan_locked"
    assert history_possible_for(db_session, agent.id) is False
    assert history_possible_for(db_session, server.id) is True
    # a missing repository keeps the plan answer
    assert history_possible_for(db_session, 999_999) is True
    assert history_possible_for(db_session, None) is True


@pytest.mark.unit
def test_enqueue_backup_followups_omits_history_index_for_an_agent_repository(db):
    agent = Repository(
        name="agent",
        path="/repo/agent",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
    )
    db.add(agent)
    db.commit()
    load_default_executors()
    ops = enqueue_backup_followups(db, agent.id)
    assert [o.kind for o in ops] == ["archive_sync", "stats"]


@pytest.mark.unit
def test_chain_for_repository_gives_an_agent_repository_no_history_stage(
    db, monkeypatch
):
    """The one place every follow-up site reads its gates: with the plan
    open and the mode `full`, a repository whose agent cannot produce the
    change listing gets no `history_index`; once its agent advertises the
    diff job it gets the same chain as a server repository."""
    from app.services.operations.followups import chain_for_repository

    monkeypatch.setattr(
        "app.services.operations.followups.history_enabled", lambda db: True
    )
    server = Repository(name="server", path="/repo/server", borg_version=1)
    agent = Repository(
        name="agent",
        path="/repo/agent",
        borg_version=1,
        executor_type="agent",
        execution_target="agent",
    )
    db.add_all([server, agent])
    db.commit()
    load_default_executors()

    assert chain_for_repository(db, "backup", server.id) == [
        "archive_sync",
        "history_index",
        "stats",
    ]
    assert chain_for_repository(db, "backup", agent.id) == [
        "archive_sync",
        "stats",
    ]
    # the mode still applies on top: an `archives` agent repository keeps
    # the listing and the size only
    agent.index_mode = "archives"
    db.commit()
    assert chain_for_repository(db, "backup", agent.id) == ["archive_sync", "stats"]

    from app.database.models import AgentMachine

    machine = AgentMachine(
        name="current",
        agent_id="agt_chain",
        token_hash="x",
        token_prefix="x",
        status="online",
        capabilities=["repository.diff"],
    )
    db.add(machine)
    db.flush()
    agent.agent_machine_id = machine.id
    agent.index_mode = "full"
    db.commit()
    assert chain_for_repository(db, "backup", agent.id) == [
        "archive_sync",
        "history_index",
        "stats",
    ]
