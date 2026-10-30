"""Request-time source and restore restrictions preserve existing workflows."""

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.database.models import (
    AgentJob,
    AgentMachine,
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    Operation,
    UserRepositoryPermission,
)
from app.services.backup_plan_execution_service import backup_plan_execution_service
from app.services.operations.backup_facade import resolve_backup_job
from app.utils import local_paths
from tests.unit.test_api_backup_plans import (
    _create_execution_plan,
    _create_repo,
    _payload,
    _plan_backup_seam,
    _set_plan,
)


@pytest.fixture
def source_roots(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    data = allowed / "private-data"
    data.mkdir()
    app = allowed / "application"
    app.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (allowed / "link").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(
        type(local_paths.settings),
        "get_local_mount_points",
        lambda self: [str(allowed)],
    )
    monkeypatch.setattr(local_paths.settings, "data_dir", str(data))
    monkeypatch.setattr(local_paths, "_APP_DIR", str(app))
    return {
        "allowed": allowed,
        "outside": outside,
        "data": data,
        "app": app,
        "parent": allowed,
        "root": "/",
        "link": allowed / "link",
        "sibling": tmp_path / "allowed-sibling",
    }


def grant_operator(db, user, repository):
    db.add(
        UserRepositoryPermission(
            user_id=user.id, repository_id=repository.id, role="operator"
        )
    )
    db.commit()


def plan_payload(repo_id, path, *, structured):
    return _payload(
        [repo_id],
        source_directories=[str(path)],
        source_locations=[{"source_type": "local", "paths": [str(path)]}]
        if structured
        else None,
    )


@pytest.mark.parametrize("field", ["custom_flags", "custom_flags_override"])
@pytest.mark.parametrize("form", ["equals", "separate"])
@pytest.mark.parametrize("path_kind,expected", [("outside", 403), ("allowed", 201)])
def test_operator_pattern_root_on_create(
    test_client,
    test_db,
    operator_user,
    operator_headers,
    source_roots,
    field,
    form,
    path_kind,
    expected,
):
    repo = _create_repo(test_db, "Pattern root", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    root = str(source_roots[path_kind] / "root")
    flags = f'--pattern="r {root}"' if form == "equals" else f'--pattern "R {root}"'
    payload = plan_payload(
        repo.id, source_roots["allowed"] / "source", structured=False
    )
    if field == "custom_flags":
        payload[field] = flags
    else:
        payload["repositories"][0][field] = flags
    response = test_client.post(
        "/api/backup-plans/", json=payload, headers=operator_headers
    )
    assert response.status_code == expected
    assert test_db.query(BackupPlan).count() == (1 if expected == 201 else 0)
    if expected == 403:
        assert response.json()["detail"] == {
            "key": "backend.errors.filesystem.permissionDenied",
            "params": {"path": root},
        }


def test_operator_pattern_non_root_is_unaffected(
    test_client, test_db, operator_user, operator_headers, source_roots
):
    repo = _create_repo(test_db, "Other patterns", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    payload = plan_payload(
        repo.id, source_roots["allowed"] / "source", structured=False
    )
    payload["custom_flags"] = (
        '--pattern="- /outside" --pattern="+ /outside" --pattern="P sh"'
    )
    response = test_client.post(
        "/api/backup-plans/", json=payload, headers=operator_headers
    )
    assert response.status_code == 201


def test_operator_may_keep_but_not_add_outside_pattern_root(
    test_client, test_db, operator_user, operator_headers, admin_headers, source_roots
):
    repo = _create_repo(test_db, "Stored pattern", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    payload = plan_payload(
        repo.id, source_roots["allowed"] / "source", structured=False
    )
    payload["custom_flags"] = f'--pattern="R {source_roots["outside"] / "old"}"'
    created = test_client.post(
        "/api/backup-plans/", json=payload, headers=admin_headers
    )
    assert created.status_code == 201
    endpoint = f"/api/backup-plans/{created.json()['id']}"
    payload.update(schedule_enabled=True, cron_expression="0 2 * * *")
    assert (
        test_client.put(endpoint, json=payload, headers=operator_headers).status_code
        == 200
    )
    new_root = str(source_roots["outside"] / "new")
    payload["custom_flags"] += f' --pattern="R {new_root}"'
    denied = test_client.put(endpoint, json=payload, headers=operator_headers)
    assert denied.status_code == 403
    assert denied.json()["detail"]["params"]["path"] == new_root


def test_admin_can_add_outside_pattern_root(
    test_client, test_db, admin_headers, source_roots
):
    repo = _create_repo(test_db, "Admin pattern", "/inert/repository")
    payload = plan_payload(
        repo.id, source_roots["allowed"] / "source", structured=False
    )
    payload["custom_flags"] = f'--pattern="R {source_roots["outside"]}"'
    assert (
        test_client.post(
            "/api/backup-plans/", json=payload, headers=admin_headers
        ).status_code
        == 201
    )


@pytest.mark.parametrize("structured", [False, True], ids=["legacy", "structured"])
@pytest.mark.parametrize("action", ["create", "update"])
@pytest.mark.parametrize(
    "path_kind", ["outside", "data", "app", "parent", "root", "link", "sibling"]
)
def test_operator_cannot_set_unapproved_source(
    test_client,
    test_db,
    operator_user,
    operator_headers,
    admin_headers,
    source_roots,
    action,
    structured,
    path_kind,
):
    repo = _create_repo(test_db, "Source policy", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    before = 0
    endpoint = "/api/backup-plans/"
    if action == "update":
        initial = test_client.post(
            endpoint,
            json=plan_payload(
                repo.id, source_roots["allowed"] / "project", structured=structured
            ),
            headers=admin_headers,
        )
        assert initial.status_code == 201
        endpoint += str(initial.json()["id"])
        before = 1
    request = test_client.put if action == "update" else test_client.post
    response = request(
        endpoint,
        json=plan_payload(repo.id, source_roots[path_kind], structured=structured),
        headers=operator_headers,
    )
    assert response.status_code == 403
    assert (
        response.json()["detail"]["key"] == "backend.errors.filesystem.permissionDenied"
    )
    assert test_db.query(BackupPlan).count() == before
    assert test_db.query(Operation).count() == 0
    assert test_db.query(AgentJob).count() == 0
    assert not (source_roots["allowed"] / "project").exists()


@pytest.mark.parametrize("structured", [False, True])
def test_operator_can_add_approved_source_with_spaces(
    test_client, test_db, operator_user, operator_headers, source_roots, structured
):
    repo = _create_repo(test_db, "Approved", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    source = str(source_roots["allowed"] / "project with spaces")
    response = test_client.post(
        "/api/backup-plans/",
        json=plan_payload(repo.id, source, structured=structured),
        headers=operator_headers,
    )
    assert response.status_code == 201
    assert response.json()["source_directories"] == [source]
    assert test_db.query(AgentJob).count() == 0


@pytest.mark.parametrize(
    "path_kind", ["outside", "data", "app", "parent", "root", "link"]
)
def test_admin_can_still_set_broad_sources(
    test_client, test_db, admin_headers, source_roots, path_kind
):
    repo = _create_repo(test_db, "Admin source", "/inert/repository")
    response = test_client.post(
        "/api/backup-plans/",
        json=plan_payload(repo.id, source_roots[path_kind], structured=True),
        headers=admin_headers,
    )
    assert response.status_code == 201
    assert response.json()["source_directories"] == [str(source_roots[path_kind])]


def test_operator_can_edit_or_remove_existing_broad_sources(
    test_client, test_db, operator_user, operator_headers, admin_headers
):
    repo = _create_repo(test_db, "Existing source", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    payload = _payload([repo.id], source_directories=["/", "/existing"])
    created = test_client.post(
        "/api/backup-plans/", json=payload, headers=admin_headers
    )
    assert created.status_code == 201
    payload.update(schedule_enabled=True, cron_expression="0 2 * * *")
    updated = test_client.put(
        f"/api/backup-plans/{created.json()['id']}",
        json=payload,
        headers=operator_headers,
    )
    assert updated.status_code == 200
    payload["source_directories"] = ["/"]
    removed = test_client.put(
        f"/api/backup-plans/{created.json()['id']}",
        json=payload,
        headers=operator_headers,
    )
    assert removed.status_code == 200
    assert removed.json()["source_directories"] == ["/"]


def test_operator_cannot_keep_broad_sources_of_a_plan_without_repositories(
    test_client, test_db, operator_user, operator_headers, admin_headers
):
    # Once its repositories are gone any operator may edit the plan, so its
    # sources are no longer ones that operator was trusted with.
    old_repo = _create_repo(test_db, "Removed repository", "/inert/removed")
    own_repo = _create_repo(test_db, "Operator repository", "/inert/own")
    grant_operator(test_db, operator_user, own_repo)
    created = test_client.post(
        "/api/backup-plans/",
        json=_payload([old_repo.id], source_directories=["/"]),
        headers=admin_headers,
    )
    assert created.status_code == 201
    plan_id = created.json()["id"]
    test_db.query(BackupPlanRepository).filter_by(backup_plan_id=plan_id).delete()
    test_db.commit()

    payload = _payload([own_repo.id], source_directories=["/"])
    denied = test_client.put(
        f"/api/backup-plans/{plan_id}", json=payload, headers=operator_headers
    )
    assert denied.status_code == 403
    assert (
        denied.json()["detail"]["key"] == "backend.errors.filesystem.permissionDenied"
    )
    assert test_db.query(BackupPlanRepository).count() == 0

    allowed = test_client.put(
        f"/api/backup-plans/{plan_id}", json=payload, headers=admin_headers
    )
    assert allowed.status_code == 200


def test_stored_sources_that_no_longer_decode_are_checked_as_new(
    test_client,
    test_db,
    operator_user,
    operator_headers,
    admin_headers,
    source_roots,
):
    repo = _create_repo(test_db, "Legacy plan", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    created = test_client.post(
        "/api/backup-plans/",
        json=_payload([repo.id], source_directories=["/"]),
        headers=admin_headers,
    )
    assert created.status_code == 201
    plan = test_db.get(BackupPlan, created.json()["id"])
    # a remote source whose connection is gone does not decode any more
    plan.source_locations = None
    plan.source_type = "remote"
    plan.source_ssh_connection_id = None
    test_db.commit()
    endpoint = f"/api/backup-plans/{plan.id}"

    broad = _payload([repo.id], source_directories=["/"])
    assert (
        test_client.put(endpoint, json=broad, headers=operator_headers).status_code
        == 403
    )
    approved = _payload(
        [repo.id], source_directories=[str(source_roots["allowed"] / "project")]
    )
    assert (
        test_client.put(endpoint, json=approved, headers=operator_headers).status_code
        == 200
    )
    assert (
        test_client.put(endpoint, json=broad, headers=admin_headers).status_code == 200
    )


def _db_payload(repo_id, source_path, dump_path):
    return _payload(
        [repo_id],
        source_directories=[str(source_path)],
        source_locations=[
            {
                "source_type": "local",
                "paths": [str(source_path)],
                "database": {
                    "engine": "PostgreSQL",
                    "capture_mode": "dump",
                    "dump_path": str(dump_path),
                },
            }
        ],
    )


@pytest.mark.parametrize(
    "dump_kind,expected", [("tmp", 201), ("data", 403), ("app", 403), ("parent", 403)]
)
def test_operator_metadata_dump_path_confined_to_outside_reserved(
    test_client,
    test_db,
    operator_user,
    operator_headers,
    source_roots,
    dump_kind,
    expected,
):
    _set_plan(test_db, "pro")  # database sources are a pro feature
    # the dump directory the app writes and later deletes: a reserved target is
    # refused, a scratch directory outside the mounts is allowed
    repo = _create_repo(test_db, "Dump policy", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    dumps = {
        "tmp": "/var/tmp/borg-ui/database-dumps/pg",
        "data": str(source_roots["data"]),
        "app": str(source_roots["app"]),
        "parent": str(source_roots["parent"].parent),
    }
    response = test_client.post(
        "/api/backup-plans/",
        json=_db_payload(repo.id, source_roots["allowed"] / "pgdata", dumps[dump_kind]),
        headers=operator_headers,
    )
    assert response.status_code == expected
    if expected == 403:
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.filesystem.permissionDenied"
        )


def test_admin_metadata_dump_path_unrestricted(
    test_client, test_db, admin_headers, source_roots
):
    _set_plan(test_db, "pro")  # database sources are a pro feature
    repo = _create_repo(test_db, "Admin dump", "/inert/repository")
    response = test_client.post(
        "/api/backup-plans/",
        json=_db_payload(
            repo.id, source_roots["allowed"] / "pgdata", source_roots["data"]
        ),
        headers=admin_headers,
    )
    assert response.status_code == 201


def test_operator_may_keep_an_existing_reserved_dump_path(
    test_client, test_db, operator_user, operator_headers, admin_headers, source_roots
):
    _set_plan(test_db, "pro")  # database sources are a pro feature
    repo = _create_repo(test_db, "Kept dump", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    created = test_client.post(
        "/api/backup-plans/",
        json=_db_payload(
            repo.id, source_roots["allowed"] / "pgdata", source_roots["data"]
        ),
        headers=admin_headers,
    )
    assert created.status_code == 201
    pid = created.json()["id"]
    # operator changes only the schedule; the admin's dump path stays
    body = _db_payload(
        repo.id, source_roots["allowed"] / "pgdata", source_roots["data"]
    )
    body.update(schedule_enabled=True, cron_expression="0 5 * * *")
    kept = test_client.put(
        f"/api/backup-plans/{pid}", json=body, headers=operator_headers
    )
    assert kept.status_code == 200
    # but moving it to another reserved directory is refused
    moved = _db_payload(
        repo.id, source_roots["allowed"] / "pgdata", source_roots["app"]
    )
    denied = test_client.put(
        f"/api/backup-plans/{pid}", json=moved, headers=operator_headers
    )
    assert denied.status_code == 403


def test_operator_can_copy_admin_repository_sources(
    test_client, test_db, operator_user, operator_headers
):
    repo = _create_repo(
        test_db,
        "Existing repository",
        "/inert/repository",
        source_directories=json.dumps(["/"]),
    )
    grant_operator(test_db, operator_user, repo)
    response = test_client.post(
        f"/api/backup-plans/from-repository/{repo.id}",
        json={"move_source_settings": False},
        headers=operator_headers,
    )
    assert response.status_code == 201
    assert response.json()["backup_plan"]["source_directories"] == ["/"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "trigger,caller", [("manual", "admin"), ("manual", "operator"), ("schedule", None)]
)
async def test_existing_broad_plan_still_executes(
    test_client,
    test_db,
    admin_headers,
    operator_user,
    operator_headers,
    trigger,
    caller,
):
    repo = _create_repo(test_db, "Existing run", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    plan, run = _create_execution_plan(
        test_db, [repo], source_directories=json.dumps(["/"])
    )
    test_db.delete(run)
    test_db.commit()
    if trigger == "manual":
        with patch(
            "app.services.backup_plan_execution_service.asyncio.create_task",
            side_effect=lambda coro: coro.close(),
        ):
            response = test_client.post(
                f"/api/backup-plans/{plan.id}/run",
                headers=admin_headers if caller == "admin" else operator_headers,
            )
        assert response.status_code == 202
        run_id = response.json()["id"]
    else:
        plan.schedule_enabled = True
        plan.cron_expression = "0 2 * * *"
        plan.next_run = datetime(2026, 1, 1)
        test_db.commit()
        with patch(
            "app.services.backup_plan_execution_service.asyncio.create_task",
            side_effect=lambda coro: coro.close(),
        ):
            assert (
                await backup_plan_execution_service.dispatch_due_runs(
                    test_db, datetime(2026, 1, 2)
                )
                == 1
            )
        run_id = test_db.query(BackupPlanRun).filter_by(backup_plan_id=plan.id).one().id
    consumed = []

    async def execute(job_id, repository, db, **kwargs):
        consumed.append(kwargs["source_directories"])
        job = resolve_backup_job(db, job_id)
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        db.commit()

    with patch(
        "app.services.operations.backup_facade.wait_for_backup_operation",
        new=_plan_backup_seam(execute),
    ):
        await backup_plan_execution_service.execute_run(run_id)
    assert consumed == [["/"]]


@pytest.mark.parametrize("cwd_kind", ["allowed", "outside"])
def test_new_relative_sources_are_refused(
    test_client,
    test_db,
    operator_user,
    operator_headers,
    admin_headers,
    source_roots,
    monkeypatch,
    cwd_kind,
):
    # A relative source names a directory only together with the one Borg
    # runs in, which a backup may change (the restore canary runs in the data
    # directory). Administrators keep relative sources.
    repo = _create_repo(test_db, "Relative source", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    monkeypatch.chdir(source_roots[cwd_kind])
    payload = plan_payload(repo.id, "project", structured=False)
    response = test_client.post(
        "/api/backup-plans/", json=payload, headers=operator_headers
    )
    assert response.status_code == 403
    assert test_db.query(BackupPlan).count() == 0
    allowed = test_client.post(
        "/api/backup-plans/", json=payload, headers=admin_headers
    )
    assert allowed.status_code == 201
    assert allowed.json()["source_directories"] == ["project"]


@pytest.mark.parametrize("structured", [False, True], ids=["legacy", "structured"])
def test_operator_cannot_climb_out_behind_a_relative_symlink(
    test_client, test_db, operator_user, operator_headers, source_roots, structured
):
    # allowed/lnk -> a/b: resolving first lands in allowed/outside, while Borg
    # drops ".." first and reads the sibling "outside" of the mount point.
    allowed = source_roots["allowed"]
    (allowed / "a" / "b").mkdir(parents=True)
    (allowed / "lnk").symlink_to("a/b", target_is_directory=True)
    repo = _create_repo(test_db, "Dot-dot source", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    for path in (f"{allowed}/lnk/../../outside", f"{allowed}/a/../a/b"):
        response = test_client.post(
            "/api/backup-plans/",
            json=plan_payload(repo.id, path, structured=structured),
            headers=operator_headers,
        )
        assert response.status_code == 403
    assert test_db.query(BackupPlan).count() == 0


def test_operator_source_with_a_nul_byte_is_refused_not_a_server_error(
    test_client, test_db, operator_user, operator_headers, source_roots
):
    repo = _create_repo(test_db, "NUL source", "/inert/repository")
    grant_operator(test_db, operator_user, repo)
    response = test_client.post(
        "/api/backup-plans/",
        json=plan_payload(
            repo.id, f"{source_roots['allowed']}/a\x00b", structured=True
        ),
        headers=operator_headers,
    )
    # refused before anything is stored, whichever check sees it first;
    # never a server error
    assert response.status_code in (403, 422)
    assert test_db.query(BackupPlan).count() == 0


@pytest.fixture
def agent_repository(test_db, operator_user):
    agent = AgentMachine(
        name="Policy agent",
        agent_id="inert-policy-agent",
        token_hash="inert",
        token_prefix="inert",
        status="online",
        capabilities=["repository.restore"],
    )
    test_db.add(agent)
    test_db.flush()
    repo = _create_repo(
        test_db,
        "Agent policy",
        "/inert/agent-repository",
        executor_type="agent",
        execution_target="agent",
        agent_machine_id=agent.id,
    )
    grant_operator(test_db, operator_user, repo)
    return repo


def test_operator_pattern_root_on_a_disabled_link_is_checked(
    test_client, test_db, operator_user, operator_headers, source_roots
):
    # resuming a link does not save its flags again, so they are checked when
    # the plan is saved, whether the link is enabled or not
    _set_plan(test_db, "pro")  # several repositories in one plan
    first = _create_repo(test_db, "Enabled link", "/inert/first")
    second = _create_repo(test_db, "Disabled link", "/inert/second")
    grant_operator(test_db, operator_user, first)
    grant_operator(test_db, operator_user, second)
    payload = _payload(
        [first.id, second.id],
        source_directories=[str(source_roots["allowed"] / "project")],
    )
    payload["repositories"][1]["enabled"] = False
    payload["repositories"][1]["custom_flags_override"] = (
        f'--pattern="R {source_roots["outside"]}"'
    )
    response = test_client.post(
        "/api/backup-plans/", json=payload, headers=operator_headers
    )
    assert response.status_code == 403
    assert test_db.query(BackupPlan).count() == 0


def test_operator_cannot_add_pattern_root_to_agent_link(
    test_client, test_db, admin_headers, operator_headers, agent_repository
):
    repo = agent_repository
    payload = _payload(
        [repo.id],
        source_type="agent",
        source_directories=["/inert/source"],
        source_locations=[
            {
                "source_type": "agent",
                "agent_machine_id": repo.agent_machine_id,
                "paths": ["/inert/source"],
            }
        ],
    )
    created = test_client.post(
        "/api/backup-plans/", json=payload, headers=admin_headers
    )
    assert created.status_code == 201
    payload["repositories"][0]["custom_flags_override"] = '--pattern="R /inert/extra"'
    denied = test_client.put(
        f"/api/backup-plans/{created.json()['id']}",
        json=payload,
        headers=operator_headers,
    )
    assert denied.status_code == 403
    assert denied.json()["detail"] == {
        "key": "backend.errors.filesystem.permissionDenied",
        "params": {"path": "/inert/extra"},
    }
    assert (
        test_client.put(
            f"/api/backup-plans/{created.json()['id']}",
            json=payload,
            headers=admin_headers,
        ).status_code
        == 200
    )


def test_operator_can_copy_existing_agent_repository_sources(
    test_client, test_db, operator_headers, agent_repository
):
    repo = agent_repository
    repo.source_directories = json.dumps(["/"])
    repo.source_locations = json.dumps(
        [
            {
                "source_type": "agent",
                "agent_machine_id": repo.agent_machine_id,
                "paths": ["/"],
            }
        ]
    )
    test_db.commit()
    response = test_client.post(
        f"/api/backup-plans/from-repository/{repo.id}",
        json={"move_source_settings": False},
        headers=operator_headers,
    )
    assert response.status_code == 201
    assert response.json()["backup_plan"]["source_directories"] == ["/"]


@pytest.mark.parametrize(
    "action,change", [("create", "path"), ("update", "path"), ("update", "agent")]
)
def test_operator_cannot_add_agent_source(
    test_client,
    test_db,
    admin_headers,
    operator_headers,
    agent_repository,
    action,
    change,
):
    repo = agent_repository
    payload = _payload(
        [repo.id],
        source_type="agent",
        source_directories=["/existing"],
        source_locations=[
            {
                "source_type": "agent",
                "agent_machine_id": repo.agent_machine_id,
                "paths": ["/existing"],
            }
        ],
    )
    endpoint = "/api/backup-plans/"
    if action == "update":
        created = test_client.post(endpoint, json=payload, headers=admin_headers)
        assert created.status_code == 201
        endpoint += str(created.json()["id"])
        unchanged = test_client.put(
            endpoint,
            json={**payload, "description": "Schedule maintenance"},
            headers=operator_headers,
        )
        assert unchanged.status_code == 200
        if change == "path":
            payload["source_locations"][0]["paths"] = ["/changed"]
            payload["source_directories"] = ["/changed"]
        else:
            payload["source_locations"][0]["agent_machine_id"] += 1
    response = (test_client.put if action == "update" else test_client.post)(
        endpoint, json=payload, headers=operator_headers
    )
    assert response.status_code == 403
    assert test_db.query(BackupPlan).count() == (1 if action == "update" else 0)
    assert test_db.query(AgentJob).count() == 0
    assert test_db.query(Operation).count() == 0


@pytest.mark.parametrize("caller,expected", [("operator", 403), ("admin", 200)])
def test_agent_restore_request_role_boundary(
    test_client,
    test_db,
    admin_headers,
    operator_headers,
    agent_repository,
    tmp_path,
    monkeypatch,
    caller,
    expected,
):
    from app.api import restore

    monkeypatch.setattr(restore, "wake_runner", lambda: None)
    destination = tmp_path / "not-created"
    response = test_client.post(
        "/api/restore/start",
        headers=operator_headers if caller == "operator" else admin_headers,
        json={
            "repository": agent_repository.path,
            "repository_id": agent_repository.id,
            "archive": "normal",
            "paths": [],
            "destination": str(destination),
        },
    )
    assert response.status_code == expected
    if caller == "operator":
        assert response.json()["detail"] == {
            "key": "backend.errors.auth.notEnoughPermissions"
        }
    operations = test_db.query(Operation).filter_by(kind="restore").all()
    assert len(operations) == (1 if caller == "admin" else 0)
    if operations:
        assert operations[0].execution_mode == "agent"
    assert test_db.query(AgentJob).count() == 0
    assert not destination.exists()


@pytest.mark.asyncio
async def test_agent_restore_check_keeps_internal_temp_target(
    test_db, agent_repository, monkeypatch
):
    from app.services.restore_check_service import RestoreCheckService
    from app.services import repository_executor, agent_job_dispatcher

    service = RestoreCheckService()
    service._agent_list_archives = AsyncMock(return_value=[{"name": "normal"}])
    service._await_agent_operation = AsyncMock(return_value={"return_code": 0})
    service._append_agent_logs = Mock()
    service._save_job_logs = Mock()
    service._send_completion_notification = AsyncMock()
    queued = []

    def queue(db, repository, *, operation, **kwargs):
        queued.append(operation)
        return SimpleNamespace(id=99)

    monkeypatch.setattr(
        repository_executor, "queue_agent_repository_operation_job", queue
    )
    monkeypatch.setattr(
        agent_job_dispatcher, "dispatch_agent_job_best_effort", AsyncMock()
    )
    job = SimpleNamespace(
        full_archive=True,
        probe_paths=None,
        archive_name=None,
        archive_id=None,
        error_message=None,
    )
    await service._execute_agent_restore_check(test_db, job, 1, agent_repository)
    assert queued == [{"archive": "normal", "paths": [], "target": {"type": "temp"}}]
    assert job.status == "completed"
