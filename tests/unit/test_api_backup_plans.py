import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database.models import (
    BackupJob,
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    BackupPlanRunRepository,
    CheckJob,
    CompactJob,
    LicensingState,
    PruneJob,
    Repository,
    Script,
    ScriptExecution,
    ScheduledJob,
    ScheduledJobRepository,
    SSHConnection,
    UserRepositoryPermission,
)
from app.services.backup_plan_execution_service import backup_plan_execution_service


def _create_repo(test_db, name: str, path: str, **kwargs) -> Repository:
    repo = Repository(
        name=name,
        path=path,
        encryption="none",
        repository_type="local",
        mode="full",
        **kwargs,
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


def _create_ssh_connection(test_db, **kwargs) -> SSHConnection:
    connection = SSHConnection(
        host=kwargs.pop("host", "remote.example"),
        username=kwargs.pop("username", "tester"),
        port=kwargs.pop("port", 22),
        status=kwargs.pop("status", "connected"),
        **kwargs,
    )
    test_db.add(connection)
    test_db.commit()
    test_db.refresh(connection)
    return connection


def _create_script(test_db, name: str, **kwargs) -> Script:
    script = Script(
        name=name,
        file_path=kwargs.pop(
            "file_path", f"library/{name.lower().replace(' ', '-')}.sh"
        ),
        category=kwargs.pop("category", "custom"),
        timeout=kwargs.pop("timeout", 300),
        run_on=kwargs.pop("run_on", "always"),
        parameters=kwargs.pop("parameters", None),
        **kwargs,
    )
    test_db.add(script)
    test_db.commit()
    test_db.refresh(script)
    return script


def _set_plan(test_db, plan: str) -> None:
    state = test_db.query(LicensingState).first()
    if state is None:
        state = LicensingState(instance_id="test-instance-backup-plans")
        test_db.add(state)
    state.plan = plan
    state.status = "active"
    test_db.commit()


def _payload(repo_ids: list[int], **overrides):
    payload = {
        "name": "Nightly project plan",
        "description": "Main project backup",
        "enabled": True,
        "source_type": "local",
        "source_ssh_connection_id": None,
        "source_directories": ["/srv/project"],
        "exclude_patterns": ["*.tmp"],
        "archive_name_template": "{plan_name}-{repo_name}-{now}",
        "compression": "lz4",
        "custom_flags": None,
        "upload_ratelimit_kib": None,
        "repository_run_mode": "series",
        "max_parallel_repositories": 1,
        "failure_behavior": "continue",
        "schedule_enabled": False,
        "cron_expression": None,
        "timezone": "UTC",
        "run_repository_scripts": False,
        "run_prune_after": False,
        "run_compact_after": False,
        "run_check_after": False,
        "check_max_duration": 3600,
        "check_extra_flags": None,
        "prune_keep_hourly": 0,
        "prune_keep_daily": 7,
        "prune_keep_weekly": 4,
        "prune_keep_monthly": 6,
        "prune_keep_quarterly": 0,
        "prune_keep_yearly": 1,
        "repositories": [
            {
                "repository_id": repo_id,
                "enabled": True,
                "execution_order": index + 1,
                "compression_source": "plan",
                "compression_override": None,
                "custom_flags_override": None,
                "upload_ratelimit_kib_override": None,
                "failure_behavior_override": None,
            }
            for index, repo_id in enumerate(repo_ids)
        ],
    }
    payload.update(overrides)
    return payload


def _create_execution_plan(test_db, repos: list[Repository], **overrides):
    plan_values = {
        "name": "Plan execution",
        "enabled": True,
        "source_type": "local",
        "source_directories": json.dumps(["/srv/project"]),
        "exclude_patterns": json.dumps([]),
        "archive_name_template": "{plan_name}-{repo_name}-{now}",
        "compression": "lz4",
        "repository_run_mode": "series",
        "max_parallel_repositories": 1,
        "failure_behavior": "continue",
        "schedule_enabled": False,
        "timezone": "UTC",
        "run_repository_scripts": False,
        "run_prune_after": False,
        "run_compact_after": False,
        "run_check_after": False,
        "check_max_duration": 3600,
        "check_extra_flags": None,
        "prune_keep_hourly": 0,
        "prune_keep_daily": 7,
        "prune_keep_weekly": 4,
        "prune_keep_monthly": 6,
        "prune_keep_quarterly": 0,
        "prune_keep_yearly": 1,
        "created_at": datetime.utcnow(),
    }
    plan_values.update(overrides)
    plan = BackupPlan(**plan_values)
    test_db.add(plan)
    test_db.flush()
    for index, repo in enumerate(repos):
        test_db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=repo.id,
                enabled=True,
                execution_order=index + 1,
                created_at=datetime.utcnow(),
            )
        )
    run = BackupPlanRun(
        backup_plan_id=plan.id,
        trigger="manual",
        status="pending",
        created_at=datetime.utcnow(),
    )
    test_db.add(run)
    test_db.flush()
    for repo in repos:
        test_db.add(
            BackupPlanRunRepository(
                backup_plan_run_id=run.id,
                repository_id=repo.id,
                status="pending",
            )
        )
    test_db.commit()
    return plan, run


def _create_scheduled_plan(test_db, repos: list[Repository], **overrides):
    plan_values = {
        "name": "Scheduled plan",
        "enabled": True,
        "source_type": "local",
        "source_directories": json.dumps(["/srv/project"]),
        "exclude_patterns": json.dumps([]),
        "archive_name_template": "{plan_name}-{repo_name}-{now}",
        "compression": "lz4",
        "repository_run_mode": "series",
        "max_parallel_repositories": 1,
        "failure_behavior": "continue",
        "schedule_enabled": True,
        "cron_expression": "0 3 * * *",
        "timezone": "UTC",
        "next_run": datetime(2026, 1, 1, 1, 59),
        "run_repository_scripts": False,
        "run_prune_after": False,
        "run_compact_after": False,
        "run_check_after": False,
        "check_max_duration": 3600,
        "prune_keep_hourly": 0,
        "prune_keep_daily": 7,
        "prune_keep_weekly": 4,
        "prune_keep_monthly": 6,
        "prune_keep_quarterly": 0,
        "prune_keep_yearly": 1,
        "created_at": datetime.utcnow(),
    }
    plan_values.update(overrides)
    plan = BackupPlan(**plan_values)
    test_db.add(plan)
    test_db.flush()
    for index, repo in enumerate(repos):
        test_db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=repo.id,
                enabled=True,
                execution_order=index + 1,
                created_at=datetime.utcnow(),
            )
        )
    test_db.commit()
    test_db.refresh(plan)
    return plan


@pytest.mark.unit
class TestBackupPlanRoutes:
    def test_crud_single_repository_plan(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")

        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [repo.id], run_check_after=True, check_extra_flags=" --verify-data "
            ),
            headers=admin_headers,
        )

        assert create_response.status_code == 201
        created = create_response.json()
        assert created["name"] == "Nightly project plan"
        assert created["source_directories"] == ["/srv/project"]
        assert created["repository_count"] == 1
        assert created["check_extra_flags"] == "--verify-data"
        assert created["repositories"][0]["repository_id"] == repo.id

        list_response = test_client.get("/api/backup-plans/", headers=admin_headers)
        assert list_response.status_code == 200
        assert [plan["id"] for plan in list_response.json()["backup_plans"]] == [
            created["id"]
        ]

        update_payload = _payload(
            [repo.id],
            name="Updated project plan",
            run_check_after=True,
            check_extra_flags=" --repair --save-space ",
        )
        update_response = test_client.put(
            f"/api/backup-plans/{created['id']}",
            json=update_payload,
            headers=admin_headers,
        )

        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Updated project plan"
        assert update_response.json()["check_extra_flags"] == "--repair --save-space"

        delete_response = test_client.delete(
            f"/api/backup-plans/{created['id']}", headers=admin_headers
        )
        assert delete_response.status_code == 200

        get_response = test_client.get(
            f"/api/backup-plans/{created['id']}", headers=admin_headers
        )
        assert get_response.status_code == 404

    def test_create_plan_defaults_to_repository_scripts_enabled(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        payload = _payload([repo.id])
        payload.pop("run_repository_scripts")

        response = test_client.post(
            "/api/backup-plans/",
            json=payload,
            headers=admin_headers,
        )

        assert response.status_code == 201
        assert response.json()["run_repository_scripts"] is True

    def test_create_plan_stores_plan_level_scripts(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        pre_script = _create_script(test_db, "Prepare Source")
        post_script = _create_script(test_db, "Cleanup Source")

        response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [repo.id],
                pre_backup_script_id=pre_script.id,
                post_backup_script_id=post_script.id,
                pre_backup_script_parameters={"TARGET": "database"},
                post_backup_script_parameters={"STATUS_FILE": "/tmp/status"},
            ),
            headers=admin_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["pre_backup_script_id"] == pre_script.id
        assert body["post_backup_script_id"] == post_script.id
        assert body["pre_backup_script_parameters"] == {"TARGET": "database"}
        assert body["post_backup_script_parameters"] == {"STATUS_FILE": "/tmp/status"}

    def test_create_plan_rejects_missing_plan_level_script(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")

        response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo.id], pre_backup_script_id=99999),
            headers=admin_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"] == {
            "key": "backend.errors.scripts.scriptNotFound"
        }

    def test_run_response_includes_plan_script_executions(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        script = _create_script(test_db, "Prepare Source")
        plan, run = _create_execution_plan(test_db, [repo])
        execution = ScriptExecution(
            script_id=script.id,
            backup_plan_id=plan.id,
            backup_plan_run_id=run.id,
            hook_type="pre-backup",
            status="failed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            execution_time=1.25,
            exit_code=42,
            stdout="hello",
            stderr="boom",
            error_message="failed loudly",
            triggered_by="backup_plan",
        )
        test_db.add(execution)
        test_db.commit()

        response = test_client.get(
            f"/api/backup-plans/runs/{run.id}", headers=admin_headers
        )

        assert response.status_code == 200
        script_executions = response.json()["script_executions"]
        assert len(script_executions) == 1
        row = script_executions[0]
        assert row["id"] == execution.id
        assert row["script_id"] == script.id
        assert row["script_name"] == "Prepare Source"
        assert row["hook_type"] == "pre-backup"
        assert row["status"] == "failed"
        assert row["execution_time"] == 1.25
        assert row["exit_code"] == 42
        assert row["error_message"] == "failed loudly"
        assert row["has_logs"] is True
        assert row["started_at"]
        assert row["completed_at"]

    def test_create_plan_supports_remote_source(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        source_connection = _create_ssh_connection(test_db)

        response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [repo.id],
                source_type="remote",
                source_ssh_connection_id=source_connection.id,
                source_directories=["/home/tester/project"],
            ),
            headers=admin_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["source_type"] == "remote"
        assert body["source_ssh_connection_id"] == source_connection.id
        assert body["source_directories"] == ["/home/tester/project"]

    def test_remote_source_requires_connection(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")

        response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [repo.id],
                source_type="remote",
                source_ssh_connection_id=None,
            ),
            headers=admin_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"] == {
            "key": "backend.errors.backupPlans.sourceConnectionRequired"
        }

    def test_create_plan_from_repository_copies_backup_settings(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(
            test_db,
            "Primary",
            "/repos/primary",
            compression="zstd,5",
            source_directories=json.dumps(["/srv/project", "/srv/shared"]),
            exclude_patterns=json.dumps(["*.tmp", "cache/"]),
            custom_flags="--one-file-system",
        )

        response = test_client.post(
            f"/api/backup-plans/from-repository/{repo.id}",
            json={
                "copy_schedule": True,
                "disable_repository_schedule": False,
                "move_source_settings": False,
            },
            headers=admin_headers,
        )

        assert response.status_code == 201
        body = response.json()
        plan = body["backup_plan"]
        assert plan["name"] == "Primary Backup Plan"
        assert plan["source_directories"] == ["/srv/project", "/srv/shared"]
        assert plan["exclude_patterns"] == ["*.tmp", "cache/"]
        assert plan["compression"] == "zstd,5"
        assert plan["custom_flags"] == "--one-file-system"
        assert plan["run_repository_scripts"] is True
        assert plan["repositories"][0]["repository_id"] == repo.id
        assert body["copied_schedule_id"] is None
        assert body["source_settings_moved"] is False

    def test_create_plan_from_repository_copies_schedule_and_disables_original(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(
            test_db,
            "Primary",
            "/repos/primary",
            source_directories=json.dumps(["/srv/project"]),
            exclude_patterns=json.dumps(["*.tmp"]),
        )
        schedule = ScheduledJob(
            name="Primary nightly",
            cron_expression="0 2 * * *",
            timezone="UTC",
            repository_id=repo.id,
            enabled=True,
            next_run=datetime.utcnow(),
            archive_name_template="{job_name}-{repo_name}-{now}",
            run_prune_after=True,
            run_compact_after=True,
            prune_keep_daily=14,
            prune_keep_weekly=8,
        )
        test_db.add(schedule)
        test_db.commit()
        test_db.refresh(schedule)

        response = test_client.post(
            f"/api/backup-plans/from-repository/{repo.id}",
            json={"copy_schedule": True, "disable_repository_schedule": True},
            headers=admin_headers,
        )

        assert response.status_code == 201
        body = response.json()
        plan = body["backup_plan"]
        assert body["copied_schedule_id"] == schedule.id
        assert body["repository_schedule_disabled"] is True
        assert plan["schedule_enabled"] is True
        assert plan["cron_expression"] == "0 2 * * *"
        assert plan["archive_name_template"] == "{job_name}-{repo_name}-{now}"
        assert plan["run_prune_after"] is True
        assert plan["run_compact_after"] is True
        assert plan["prune_keep_daily"] == 14
        assert plan["prune_keep_weekly"] == 8

        test_db.refresh(schedule)
        assert schedule.enabled is False
        assert schedule.next_run is None
        test_db.refresh(repo)
        assert repo.source_directories is None
        assert repo.exclude_patterns is None
        assert repo.source_ssh_connection_id is None

    def test_create_plan_from_repository_keeps_shared_schedule_enabled(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo_a = _create_repo(
            test_db,
            "Primary",
            "/repos/primary",
            source_directories=json.dumps(["/srv/project"]),
        )
        repo_b = _create_repo(
            test_db,
            "Secondary",
            "/repos/secondary",
            source_directories=json.dumps(["/srv/project"]),
        )
        schedule = ScheduledJob(
            name="Shared nightly",
            cron_expression="0 2 * * *",
            timezone="UTC",
            enabled=True,
            next_run=datetime.utcnow(),
        )
        test_db.add(schedule)
        test_db.flush()
        test_db.add_all(
            [
                ScheduledJobRepository(
                    scheduled_job_id=schedule.id,
                    repository_id=repo_a.id,
                    execution_order=1,
                ),
                ScheduledJobRepository(
                    scheduled_job_id=schedule.id,
                    repository_id=repo_b.id,
                    execution_order=2,
                ),
            ]
        )
        test_db.commit()
        test_db.refresh(schedule)

        response = test_client.post(
            f"/api/backup-plans/from-repository/{repo_a.id}",
            json={"copy_schedule": True, "disable_repository_schedule": True},
            headers=admin_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["copied_schedule_id"] == schedule.id
        assert body["repository_schedule_disabled"] is False
        assert body["repository_schedule_disable_reason"] == "shared_schedule"
        test_db.refresh(schedule)
        assert schedule.enabled is True

    def test_create_plan_from_repository_requires_source_directories(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")

        response = test_client.post(
            f"/api/backup-plans/from-repository/{repo.id}",
            json={},
            headers=admin_headers,
        )

        assert response.status_code == 422
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.backupPlans.sourceRequired"
        )

    def test_multi_repository_plan_requires_pro(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")

        response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo_a.id, repo_b.id]),
            headers=admin_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["feature"] == "backup_plan_multi_repository"

    def test_parallel_plan_requires_pro_even_for_one_repository(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")

        response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [repo.id],
                repository_run_mode="parallel",
                max_parallel_repositories=2,
            ),
            headers=admin_headers,
        )

        assert response.status_code == 403
        assert response.json()["detail"]["feature"] == "backup_plan_multi_repository"

    def test_backup_plan_policy_allows_community_single_repository_series(
        self, test_db
    ):
        from app.services.backup_plan_policy import (
            evaluate_backup_plan_feature_access,
        )

        _set_plan(test_db, "community")

        decision = evaluate_backup_plan_feature_access(
            test_db,
            enabled_repository_count=1,
            repository_run_mode="series",
        )

        assert decision.allowed is True
        assert decision.feature == "backup_plan_multi_repository"
        assert decision.reason is None

    def test_backup_plan_policy_denies_community_multi_repository(self, test_db):
        from app.services.backup_plan_policy import (
            evaluate_backup_plan_feature_access,
        )

        _set_plan(test_db, "community")

        decision = evaluate_backup_plan_feature_access(
            test_db,
            enabled_repository_count=2,
            repository_run_mode="series",
        )

        assert decision.allowed is False
        assert decision.feature == "backup_plan_multi_repository"
        assert decision.reason == "multi_repository"

    def test_backup_plan_policy_denies_community_parallel(self, test_db):
        from app.services.backup_plan_policy import (
            evaluate_backup_plan_feature_access,
        )

        _set_plan(test_db, "community")

        decision = evaluate_backup_plan_feature_access(
            test_db,
            enabled_repository_count=1,
            repository_run_mode="parallel",
        )

        assert decision.allowed is False
        assert decision.feature == "backup_plan_multi_repository"
        assert decision.reason == "parallel"

    def test_create_plan_can_clear_legacy_source_settings_for_selected_repository(
        self, test_client: TestClient, admin_headers, test_db
    ):
        connection = _create_ssh_connection(test_db)
        repo = _create_repo(
            test_db,
            "Primary",
            "/repos/primary",
            source_directories=json.dumps(["/legacy/source"]),
            exclude_patterns=json.dumps(["legacy.tmp"]),
            source_ssh_connection_id=connection.id,
        )

        response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [repo.id],
                clear_legacy_source_repository_ids=[repo.id],
            ),
            headers=admin_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["source_directories"] == ["/srv/project"]

        test_db.refresh(repo)
        assert repo.source_directories is None
        assert repo.exclude_patterns is None
        assert repo.source_ssh_connection_id is None

    def test_update_plan_can_clear_legacy_source_settings_for_added_repository(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "pro")
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(
            test_db,
            "Secondary",
            "/repos/secondary",
            source_directories=json.dumps(["/legacy/secondary"]),
            exclude_patterns=json.dumps(["secondary.tmp"]),
        )
        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo_a.id]),
            headers=admin_headers,
        )
        assert create_response.status_code == 201
        plan_id = create_response.json()["id"]

        response = test_client.put(
            f"/api/backup-plans/{plan_id}",
            json=_payload(
                [repo_a.id, repo_b.id],
                clear_legacy_source_repository_ids=[repo_b.id],
            ),
            headers=admin_headers,
        )

        assert response.status_code == 200
        test_db.refresh(repo_b)
        assert repo_b.source_directories is None
        assert repo_b.exclude_patterns is None

    def test_plan_save_rejects_clearing_unselected_repository_source_settings(
        self, test_client: TestClient, admin_headers, test_db
    ):
        selected_repo = _create_repo(test_db, "Primary", "/repos/primary")
        unselected_repo = _create_repo(
            test_db,
            "Secondary",
            "/repos/secondary",
            source_directories=json.dumps(["/legacy/secondary"]),
            exclude_patterns=json.dumps(["secondary.tmp"]),
        )

        response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [selected_repo.id],
                clear_legacy_source_repository_ids=[unselected_repo.id],
            ),
            headers=admin_headers,
        )

        assert response.status_code == 422
        assert (
            response.json()["detail"]["key"]
            == "backend.errors.backupPlans.clearLegacyRepositoryNotSelected"
        )
        test_db.refresh(unselected_repo)
        assert unselected_repo.source_directories == json.dumps(["/legacy/secondary"])
        assert unselected_repo.exclude_patterns == json.dumps(["secondary.tmp"])

    def test_pro_plan_can_target_multiple_repositories(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "pro")
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")

        response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [repo_a.id, repo_b.id],
                repository_run_mode="parallel",
                max_parallel_repositories=2,
            ),
            headers=admin_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["repository_count"] == 2
        assert body["repository_run_mode"] == "parallel"

    def test_community_cannot_run_existing_multi_repository_plan_after_downgrade(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "pro")
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")
        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo_a.id, repo_b.id]),
            headers=admin_headers,
        )
        assert create_response.status_code == 201
        plan_id = create_response.json()["id"]
        _set_plan(test_db, "community")

        response = test_client.post(
            f"/api/backup-plans/{plan_id}/run", headers=admin_headers
        )

        assert response.status_code == 403
        assert response.json()["detail"]["feature"] == "backup_plan_multi_repository"

    def test_community_cannot_run_existing_parallel_plan_after_downgrade(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "pro")
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [repo.id],
                repository_run_mode="parallel",
                max_parallel_repositories=2,
            ),
            headers=admin_headers,
        )
        assert create_response.status_code == 201
        plan_id = create_response.json()["id"]
        _set_plan(test_db, "community")

        response = test_client.post(
            f"/api/backup-plans/{plan_id}/run", headers=admin_headers
        )

        assert response.status_code == 403
        assert response.json()["detail"]["feature"] == "backup_plan_multi_repository"

    def test_community_can_update_existing_pro_plan_back_to_single_series(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "pro")
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")
        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload(
                [repo_a.id, repo_b.id],
                repository_run_mode="parallel",
                max_parallel_repositories=2,
            ),
            headers=admin_headers,
        )
        assert create_response.status_code == 201
        plan_id = create_response.json()["id"]
        _set_plan(test_db, "community")

        update_response = test_client.put(
            f"/api/backup-plans/{plan_id}",
            json=_payload(
                [repo_a.id],
                name="Community-safe plan",
                repository_run_mode="series",
                max_parallel_repositories=1,
            ),
            headers=admin_headers,
        )

        assert update_response.status_code == 200
        body = update_response.json()
        assert body["name"] == "Community-safe plan"
        assert body["repository_count"] == 1
        assert body["repository_run_mode"] == "series"

    def test_viewer_must_have_access_to_all_plan_repositories(
        self, test_client: TestClient, admin_headers, auth_headers, test_db, test_user
    ):
        _set_plan(test_db, "pro")
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")
        permission = UserRepositoryPermission(
            user_id=test_user.id, repository_id=repo_a.id, role="viewer"
        )
        test_db.add(permission)
        test_db.commit()

        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo_a.id, repo_b.id]),
            headers=admin_headers,
        )
        plan_id = create_response.json()["id"]

        list_response = test_client.get("/api/backup-plans/", headers=auth_headers)
        assert list_response.status_code == 200
        assert list_response.json()["backup_plans"] == []

        get_response = test_client.get(
            f"/api/backup-plans/{plan_id}", headers=auth_headers
        )
        assert get_response.status_code == 403

    def test_run_backup_plan_creates_plan_run(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo.id]),
            headers=admin_headers,
        )
        plan_id = create_response.json()["id"]

        def close_background_task(coro):
            coro.close()
            return None

        with patch(
            "app.services.backup_plan_execution_service.asyncio.create_task",
            side_effect=close_background_task,
        ):
            response = test_client.post(
                f"/api/backup-plans/{plan_id}/run", headers=admin_headers
            )

        assert response.status_code == 202
        body = response.json()
        assert body["backup_plan_id"] == plan_id
        assert body["status"] == "pending"
        assert len(body["repositories"]) == 1
        assert body["repositories"][0]["repository_id"] == repo.id

        run = test_db.query(BackupPlanRun).filter_by(backup_plan_id=plan_id).one()
        assert run.trigger == "manual"

    def test_activity_and_backup_jobs_include_plan_context(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        plan, run = _create_execution_plan(test_db, [repo])
        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            backup_plan_id=plan.id,
            backup_plan_run_id=run.id,
            status="completed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        test_db.add(backup_job)
        test_db.commit()

        activity_response = test_client.get(
            "/api/activity/recent?job_type=backup", headers=admin_headers
        )
        jobs_response = test_client.get(
            f"/api/backup/jobs?repository={repo.path}",
            headers=admin_headers,
        )
        manual_jobs_response = test_client.get(
            f"/api/backup/jobs?manual_only=true&repository={repo.path}",
            headers=admin_headers,
        )

        assert activity_response.status_code == 200
        activity = next(
            item for item in activity_response.json() if item["id"] == backup_job.id
        )
        assert activity["triggered_by"] == "backup_plan"
        assert activity["backup_plan_id"] == plan.id
        assert activity["backup_plan_run_id"] == run.id
        assert activity["backup_plan_name"] == plan.name

        assert jobs_response.status_code == 200
        job = next(
            item for item in jobs_response.json()["jobs"] if item["id"] == backup_job.id
        )
        assert job["triggered_by"] == "backup_plan"
        assert job["backup_plan_id"] == plan.id
        assert job["backup_plan_run_id"] == run.id
        assert job["backup_plan_name"] == plan.name
        assert manual_jobs_response.status_code == 200
        assert all(
            item["id"] != backup_job.id for item in manual_jobs_response.json()["jobs"]
        )

    def test_run_backup_plan_rejects_active_run(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo.id]),
            headers=admin_headers,
        )
        plan_id = create_response.json()["id"]
        test_db.add(
            BackupPlanRun(backup_plan_id=plan_id, trigger="manual", status="running")
        )
        test_db.commit()

        response = test_client.post(
            f"/api/backup-plans/{plan_id}/run", headers=admin_headers
        )

        assert response.status_code == 409

    def test_toggle_enabled_scheduled_plan_disables_and_clears_next_run(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        plan = _create_scheduled_plan(test_db, [repo])

        response = test_client.post(
            f"/api/backup-plans/{plan.id}/toggle", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is False
        assert body["next_run"] is None
        test_db.refresh(plan)
        assert plan.enabled is False
        assert plan.next_run is None

    def test_toggle_disabled_scheduled_plan_enables_and_sets_next_run(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        plan = _create_scheduled_plan(
            test_db,
            [repo],
            enabled=False,
            next_run=None,
        )

        response = test_client.post(
            f"/api/backup-plans/{plan.id}/toggle", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["enabled"] is True
        assert body["next_run"] is not None
        test_db.refresh(plan)
        assert plan.enabled is True
        assert plan.next_run is not None

    def test_community_cannot_enable_existing_multi_repository_plan_after_downgrade(
        self, test_client: TestClient, admin_headers, test_db
    ):
        _set_plan(test_db, "pro")
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")
        plan = _create_scheduled_plan(
            test_db,
            [repo_a, repo_b],
            enabled=False,
            next_run=None,
        )
        _set_plan(test_db, "community")

        response = test_client.post(
            f"/api/backup-plans/{plan.id}/toggle", headers=admin_headers
        )

        assert response.status_code == 403
        assert response.json()["detail"]["feature"] == "backup_plan_multi_repository"
        test_db.refresh(plan)
        assert plan.enabled is False
        assert plan.next_run is None

    def test_dispatch_due_runs_starts_scheduled_plan_and_advances_next_run(
        self, test_db
    ):
        _set_plan(test_db, "community")
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        now = datetime(2026, 1, 1, 2, 0)
        plan = _create_scheduled_plan(
            test_db,
            [repo],
            next_run=now - timedelta(minutes=1),
        )

        def close_background_task(coro):
            coro.close()
            return None

        with patch(
            "app.services.backup_plan_execution_service.asyncio.create_task",
            side_effect=close_background_task,
        ) as mock_create_task:
            dispatched = backup_plan_execution_service.dispatch_due_runs(test_db, now)

        assert dispatched == 1
        mock_create_task.assert_called_once()
        test_db.refresh(plan)
        assert plan.last_run == now
        assert plan.next_run > now

        run = test_db.query(BackupPlanRun).filter_by(backup_plan_id=plan.id).one()
        assert run.trigger == "schedule"
        assert run.status == "pending"

    def test_dispatch_due_runs_skips_and_advances_paid_only_plan_after_downgrade(
        self, test_db
    ):
        _set_plan(test_db, "community")
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")
        now = datetime(2026, 1, 1, 2, 0)
        plan = _create_scheduled_plan(
            test_db,
            [repo_a, repo_b],
            next_run=now - timedelta(minutes=1),
        )

        with patch(
            "app.services.backup_plan_execution_service.asyncio.create_task"
        ) as mock_create_task:
            dispatched = backup_plan_execution_service.dispatch_due_runs(test_db, now)

        assert dispatched == 0
        mock_create_task.assert_not_called()
        assert (
            test_db.query(BackupPlanRun).filter_by(backup_plan_id=plan.id).count() == 0
        )
        test_db.refresh(plan)
        assert plan.last_run is None
        assert plan.next_run > now

    def test_dispatch_due_runs_skips_plan_with_active_run(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        now = datetime(2026, 1, 1, 2, 0)
        plan = _create_scheduled_plan(
            test_db,
            [repo],
            next_run=now - timedelta(minutes=1),
        )
        active_run = BackupPlanRun(
            backup_plan_id=plan.id,
            trigger="manual",
            status="running",
            created_at=datetime.utcnow(),
        )
        test_db.add(active_run)
        test_db.commit()

        with patch(
            "app.services.backup_plan_execution_service.asyncio.create_task"
        ) as mock_create_task:
            dispatched = backup_plan_execution_service.dispatch_due_runs(test_db, now)

        assert dispatched == 0
        mock_create_task.assert_not_called()
        assert (
            test_db.query(BackupPlanRun).filter_by(backup_plan_id=plan.id).count() == 1
        )

    def test_dispatch_due_runs_ignores_disabled_plan_schedule(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        now = datetime(2026, 1, 1, 2, 0)
        _create_scheduled_plan(
            test_db,
            [repo],
            schedule_enabled=False,
            next_run=now - timedelta(minutes=1),
        )

        with patch(
            "app.services.backup_plan_execution_service.asyncio.create_task"
        ) as mock_create_task:
            dispatched = backup_plan_execution_service.dispatch_due_runs(test_db, now)

        assert dispatched == 0
        mock_create_task.assert_not_called()
        assert test_db.query(BackupPlanRun).count() == 0

    def test_cancel_backup_plan_run_marks_pending_children_cancelled(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo.id]),
            headers=admin_headers,
        )
        plan_id = create_response.json()["id"]
        run = BackupPlanRun(
            backup_plan_id=plan_id,
            trigger="manual",
            status="running",
            created_at=datetime.utcnow(),
        )
        test_db.add(run)
        test_db.flush()
        test_db.add(
            BackupPlanRunRepository(
                backup_plan_run_id=run.id,
                repository_id=repo.id,
                status="pending",
            )
        )
        test_db.commit()

        response = test_client.post(
            f"/api/backup-plans/runs/{run.id}/cancel", headers=admin_headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["run"]["status"] == "cancelled"
        assert body["run"]["repositories"][0]["status"] == "cancelled"
        assert body["cancelled_repositories"] == 1

    def test_cancel_backup_plan_run_cancels_running_backup_job(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo.id]),
            headers=admin_headers,
        )
        plan_id = create_response.json()["id"]
        run = BackupPlanRun(
            backup_plan_id=plan_id,
            trigger="manual",
            status="running",
            created_at=datetime.utcnow(),
        )
        test_db.add(run)
        test_db.flush()
        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            backup_plan_id=plan_id,
            backup_plan_run_id=run.id,
            status="running",
            created_at=datetime.utcnow(),
        )
        test_db.add(backup_job)
        test_db.flush()
        test_db.add(
            BackupPlanRunRepository(
                backup_plan_run_id=run.id,
                repository_id=repo.id,
                backup_job_id=backup_job.id,
                status="running",
            )
        )
        test_db.commit()

        with patch(
            "app.services.backup_plan_execution_service.backup_service.cancel_backup",
            return_value=True,
        ) as cancel_backup:
            response = test_client.post(
                f"/api/backup-plans/runs/{run.id}/cancel", headers=admin_headers
            )

        assert response.status_code == 200
        cancel_backup.assert_called_once_with(backup_job.id)
        body = response.json()
        assert body["run"]["status"] == "cancelled"
        assert body["run"]["repositories"][0]["backup_job"]["status"] == "cancelled"
        assert body["processes_terminated"] == 1

    def test_cancel_backup_plan_run_preserves_completed_children(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")
        repo_c = _create_repo(test_db, "Tertiary", "/repos/tertiary")
        _set_plan(test_db, "pro")
        create_response = test_client.post(
            "/api/backup-plans/",
            json=_payload([repo_a.id, repo_b.id, repo_c.id]),
            headers=admin_headers,
        )
        assert create_response.status_code == 201
        plan_id = create_response.json()["id"]
        run = BackupPlanRun(
            backup_plan_id=plan_id,
            trigger="manual",
            status="running",
            created_at=datetime.utcnow(),
        )
        test_db.add(run)
        test_db.flush()
        completed_job = BackupJob(
            repository=repo_a.path,
            repository_id=repo_a.id,
            backup_plan_id=plan_id,
            backup_plan_run_id=run.id,
            status="completed",
            completed_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        running_job = BackupJob(
            repository=repo_b.path,
            repository_id=repo_b.id,
            backup_plan_id=plan_id,
            backup_plan_run_id=run.id,
            status="running",
            created_at=datetime.utcnow(),
        )
        test_db.add_all([completed_job, running_job])
        test_db.flush()
        test_db.add_all(
            [
                BackupPlanRunRepository(
                    backup_plan_run_id=run.id,
                    repository_id=repo_a.id,
                    backup_job_id=completed_job.id,
                    status="completed",
                    completed_at=datetime.utcnow(),
                ),
                BackupPlanRunRepository(
                    backup_plan_run_id=run.id,
                    repository_id=repo_b.id,
                    backup_job_id=running_job.id,
                    status="running",
                ),
                BackupPlanRunRepository(
                    backup_plan_run_id=run.id,
                    repository_id=repo_c.id,
                    status="pending",
                ),
            ]
        )
        test_db.commit()

        with patch(
            "app.services.backup_plan_execution_service.backup_service.cancel_backup",
            return_value=True,
        ):
            response = test_client.post(
                f"/api/backup-plans/runs/{run.id}/cancel", headers=admin_headers
            )

        assert response.status_code == 200
        body = response.json()
        statuses = {
            child["repository_id"]: child["status"]
            for child in body["run"]["repositories"]
        }
        assert statuses[repo_a.id] == "completed"
        assert statuses[repo_b.id] == "cancelled"
        assert statuses[repo_c.id] == "cancelled"
        assert body["cancelled_repositories"] == 2
        test_db.refresh(completed_job)
        test_db.refresh(running_job)
        assert completed_job.status == "completed"
        assert running_job.status == "cancelled"

    @pytest.mark.asyncio
    async def test_execute_plan_run_uses_plan_source_settings(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        plan = BackupPlan(
            name="Plan execution",
            enabled=True,
            source_type="local",
            source_directories=json.dumps(["/srv/project"]),
            exclude_patterns=json.dumps(["*.tmp"]),
            archive_name_template="{plan_name}-{repo_name}-{now}",
            compression="zstd,3",
            repository_run_mode="series",
            max_parallel_repositories=1,
            failure_behavior="continue",
            schedule_enabled=False,
            timezone="UTC",
            run_repository_scripts=False,
            run_prune_after=False,
            run_compact_after=False,
            run_check_after=False,
            check_max_duration=3600,
            prune_keep_hourly=0,
            prune_keep_daily=7,
            prune_keep_weekly=4,
            prune_keep_monthly=6,
            prune_keep_quarterly=0,
            prune_keep_yearly=1,
            created_at=datetime.utcnow(),
        )
        test_db.add(plan)
        test_db.flush()
        test_db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=repo.id,
                enabled=True,
                execution_order=1,
                created_at=datetime.utcnow(),
            )
        )
        run = BackupPlanRun(
            backup_plan_id=plan.id,
            trigger="manual",
            status="pending",
            created_at=datetime.utcnow(),
        )
        test_db.add(run)
        test_db.flush()
        test_db.add(
            BackupPlanRunRepository(
                backup_plan_run_id=run.id,
                repository_id=repo.id,
                status="pending",
            )
        )
        test_db.commit()

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            assert repository == repo.path
            assert kwargs["source_directories"] == ["/srv/project"]
            assert kwargs["exclude_patterns_override"] == ["*.tmp"]
            assert kwargs["compression_override"] == "zstd,3"
            assert kwargs["skip_hooks"] is True
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        with patch(
            "app.services.backup_plan_execution_service.backup_service.execute_backup",
            side_effect=fake_execute_backup,
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.refresh(run)
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_plan_run_uses_stable_archive_name_for_borg2_repo(
        self, test_db
    ):
        repo = _create_repo(
            test_db,
            "Primary Repo",
            "/repos/primary-borg2",
            borg_version=2,
        )
        _plan, run = _create_execution_plan(
            test_db,
            [repo],
            name="Monthly Plan",
            archive_name_template="{plan_name}-{repo_name}-{now}",
        )

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            assert repository == repo.path
            assert kwargs["archive_name"] == "Monthly-Plan-Primary-Repo"
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        with patch(
            "app.services.backup_plan_execution_service.backup_service.execute_backup",
            side_effect=fake_execute_backup,
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.refresh(run)
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_plan_run_uses_remote_plan_source_settings(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        source_connection = _create_ssh_connection(test_db)
        _plan, run = _create_execution_plan(
            test_db,
            [repo],
            source_type="remote",
            source_ssh_connection_id=source_connection.id,
            source_directories=json.dumps(["/home/tester/project"]),
            exclude_patterns=json.dumps(["node_modules"]),
        )

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            assert repository == repo.path
            assert kwargs["source_directories"] == ["/home/tester/project"]
            assert kwargs["source_ssh_connection_id"] == source_connection.id
            assert kwargs["exclude_patterns_override"] == ["node_modules"]
            job = db.query(BackupJob).filter_by(id=job_id).one()
            assert job.source_ssh_connection_id == source_connection.id
            assert job.backup_plan_id is not None
            assert job.backup_plan_run_id == run.id
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        with patch(
            "app.services.backup_plan_execution_service.backup_service.execute_backup",
            side_effect=fake_execute_backup,
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.expire_all()
        backup_job = test_db.query(BackupJob).filter_by(backup_plan_run_id=run.id).one()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        assert run.status == "completed"
        assert backup_job.source_ssh_connection_id == source_connection.id

    @pytest.mark.asyncio
    async def test_execute_plan_run_wraps_repositories_with_plan_scripts(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        pre_script = _create_script(test_db, "Prepare Source")
        post_script = _create_script(test_db, "Cleanup Source")
        _plan, run = _create_execution_plan(
            test_db,
            [repo],
            pre_backup_script_id=pre_script.id,
            post_backup_script_id=post_script.id,
        )
        calls = []

        async def fake_plan_script(run_id, context, *, hook_type, backup_result=None):
            calls.append((hook_type, backup_result))
            return True, None

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            calls.append(("backup", repository))
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        with (
            patch.object(
                backup_plan_execution_service,
                "_execute_plan_script",
                side_effect=fake_plan_script,
            ),
            patch(
                "app.services.backup_plan_execution_service.backup_service.execute_backup",
                side_effect=fake_execute_backup,
            ),
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.expire_all()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        assert calls == [
            ("pre-backup", None),
            ("backup", repo.path),
            ("post-backup", "success"),
        ]
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_execute_plan_run_records_plan_script_executions(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        pre_script = _create_script(test_db, "Prepare Source")
        post_script = _create_script(test_db, "Cleanup Source")
        plan, run = _create_execution_plan(
            test_db,
            [repo],
            pre_backup_script_id=pre_script.id,
            post_backup_script_id=post_script.id,
        )
        for script in (pre_script, post_script):
            script_path = Path(settings.data_dir) / "scripts" / script.file_path
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text("echo plan script\n")

        async def fake_execute_script(script, timeout, env, context):
            hook_type = "pre-backup" if ":pre-backup:" in context else "post-backup"
            assert env["BORG_UI_BACKUP_PLAN_ID"] == str(plan.id)
            assert env["BORG_UI_BACKUP_PLAN_RUN_ID"] == str(run.id)
            return {
                "success": True,
                "exit_code": 0,
                "stdout": f"{hook_type} stdout",
                "stderr": "",
                "execution_time": 0.01,
            }

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        with (
            patch(
                "app.services.backup_plan_execution_service.execute_script",
                side_effect=fake_execute_script,
            ),
            patch(
                "app.services.backup_plan_execution_service.backup_service.execute_backup",
                side_effect=fake_execute_backup,
            ),
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.expire_all()
        executions = (
            test_db.query(ScriptExecution)
            .filter(ScriptExecution.backup_plan_run_id == run.id)
            .order_by(ScriptExecution.id.asc())
            .all()
        )
        assert [execution.hook_type for execution in executions] == [
            "pre-backup",
            "post-backup",
        ]
        assert {execution.backup_plan_id for execution in executions} == {plan.id}
        assert [execution.status for execution in executions] == [
            "completed",
            "completed",
        ]
        assert executions[0].stdout == "pre-backup stdout"
        assert executions[1].stdout == "post-backup stdout"

    @pytest.mark.asyncio
    async def test_pre_plan_script_failure_aborts_plan_before_backups(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        pre_script = _create_script(test_db, "Prepare Source")
        _plan, run = _create_execution_plan(
            test_db,
            [repo],
            pre_backup_script_id=pre_script.id,
        )
        backup_mock = AsyncMock()

        async def fake_plan_script(run_id, context, *, hook_type, backup_result=None):
            assert hook_type == "pre-backup"
            return False, "prepare failed"

        with (
            patch.object(
                backup_plan_execution_service,
                "_execute_plan_script",
                side_effect=fake_plan_script,
            ),
            patch(
                "app.services.backup_plan_execution_service.backup_service.execute_backup",
                backup_mock,
            ),
        ):
            await backup_plan_execution_service.execute_run(run.id)

        backup_mock.assert_not_called()
        test_db.expire_all()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        child = run.repositories[0]
        assert run.status == "failed"
        assert run.error_message == "prepare failed"
        assert child.status == "failed"
        assert child.error_message == "prepare failed"

    @pytest.mark.asyncio
    async def test_post_plan_script_failure_marks_successful_run_warning(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        pre_script = _create_script(test_db, "Prepare Source")
        post_script = _create_script(test_db, "Cleanup Source")
        _plan, run = _create_execution_plan(
            test_db,
            [repo],
            pre_backup_script_id=pre_script.id,
            post_backup_script_id=post_script.id,
        )

        async def fake_plan_script(run_id, context, *, hook_type, backup_result=None):
            if hook_type == "post-backup":
                assert backup_result == "success"
                return False, "cleanup failed"
            return True, None

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        with (
            patch.object(
                backup_plan_execution_service,
                "_execute_plan_script",
                side_effect=fake_plan_script,
            ),
            patch(
                "app.services.backup_plan_execution_service.backup_service.execute_backup",
                side_effect=fake_execute_backup,
            ),
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.expire_all()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        child = run.repositories[0]
        assert child.status == "completed"
        assert run.status == "completed_with_warnings"
        assert run.error_message == "cleanup failed"

    @pytest.mark.asyncio
    async def test_series_stop_skips_remaining_repositories_after_failure(
        self, test_db
    ):
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")
        _plan, run = _create_execution_plan(
            test_db,
            [repo_a, repo_b],
            failure_behavior="stop",
        )
        executed_repositories = []

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            executed_repositories.append(repository)
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "failed"
            job.error_message = "backup failed"
            job.completed_at = datetime.utcnow()
            db.commit()

        with patch(
            "app.services.backup_plan_execution_service.backup_service.execute_backup",
            side_effect=fake_execute_backup,
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.expire_all()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        statuses = {child.repository_id: child.status for child in run.repositories}
        assert executed_repositories == [repo_a.path]
        assert statuses[repo_a.id] == "failed"
        assert statuses[repo_b.id] == "skipped"
        assert run.status == "failed"

    @pytest.mark.asyncio
    async def test_series_continue_runs_remaining_repositories_after_failure(
        self, test_db
    ):
        repo_a = _create_repo(test_db, "Primary", "/repos/primary")
        repo_b = _create_repo(test_db, "Secondary", "/repos/secondary")
        _plan, run = _create_execution_plan(
            test_db,
            [repo_a, repo_b],
            failure_behavior="continue",
        )
        executed_repositories = []

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            executed_repositories.append(repository)
            job = db.query(BackupJob).filter_by(id=job_id).one()
            if repository == repo_a.path:
                job.status = "failed"
                job.error_message = "backup failed"
            else:
                job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        with patch(
            "app.services.backup_plan_execution_service.backup_service.execute_backup",
            side_effect=fake_execute_backup,
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.expire_all()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        statuses = {child.repository_id: child.status for child in run.repositories}
        assert executed_repositories == [repo_a.path, repo_b.path]
        assert statuses[repo_a.id] == "failed"
        assert statuses[repo_b.id] == "completed"
        assert run.status == "partial"

    @pytest.mark.asyncio
    async def test_parallel_plan_respects_max_parallel_repositories(self, test_db):
        repos = [
            _create_repo(test_db, "Primary", "/repos/primary"),
            _create_repo(test_db, "Secondary", "/repos/secondary"),
            _create_repo(test_db, "Tertiary", "/repos/tertiary"),
        ]
        _plan, run = _create_execution_plan(
            test_db,
            repos,
            repository_run_mode="parallel",
            max_parallel_repositories=2,
        )
        active_count = 0
        max_seen = 0
        execution_order = []

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            nonlocal active_count, max_seen
            active_count += 1
            max_seen = max(max_seen, active_count)
            execution_order.append(repository)
            await asyncio.sleep(0.01)
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()
            active_count -= 1

        with patch(
            "app.services.backup_plan_execution_service.backup_service.execute_backup",
            side_effect=fake_execute_backup,
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.expire_all()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        assert max_seen == 2
        assert sorted(execution_order) == sorted(repo.path for repo in repos)
        assert {child.status for child in run.repositories} == {"completed"}
        assert run.status == "completed"

    @pytest.mark.asyncio
    async def test_maintenance_failure_marks_repository_warning(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        _plan, run = _create_execution_plan(
            test_db,
            [repo],
            run_prune_after=True,
        )

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        async def fake_run_maintenance(db, backup_job, repo, context, run_id):
            backup_job.maintenance_status = "prune_failed"
            db.commit()
            return "completed_with_warnings"

        with (
            patch(
                "app.services.backup_plan_execution_service.backup_service.execute_backup",
                side_effect=fake_execute_backup,
            ),
            patch.object(
                backup_plan_execution_service,
                "_run_maintenance",
                side_effect=fake_run_maintenance,
            ),
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.expire_all()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        child = run.repositories[0]
        backup_job = test_db.query(BackupJob).filter_by(backup_plan_run_id=run.id).one()
        assert child.status == "completed_with_warnings"
        assert backup_job.maintenance_status == "prune_failed"
        assert run.status == "completed_with_warnings"

    @pytest.mark.asyncio
    async def test_plan_maintenance_jobs_are_attributed_to_repository(self, test_db):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        _plan, run = _create_execution_plan(
            test_db,
            [repo],
            run_check_after=True,
            check_extra_flags="--verify-data",
            run_prune_after=True,
            run_compact_after=True,
        )

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        maintenance_calls = []

        class FakeBorgRouter:
            def __init__(self, repository):
                self.repository = repository

            async def check(self, job_id):
                maintenance_calls.append("check")
                job = test_db.query(CheckJob).filter_by(id=job_id).one()
                assert job.repository_id == repo.id
                assert job.extra_flags == "--verify-data"
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                test_db.commit()

            async def prune(self, job_id, **kwargs):
                maintenance_calls.append("prune")
                job = test_db.query(PruneJob).filter_by(id=job_id).one()
                assert job.repository_id == repo.id
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                test_db.commit()

            async def compact(self, job_id):
                maintenance_calls.append("compact")
                job = test_db.query(CompactJob).filter_by(id=job_id).one()
                assert job.repository_id == repo.id
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                test_db.commit()

        with (
            patch(
                "app.services.backup_plan_execution_service.backup_service.execute_backup",
                side_effect=fake_execute_backup,
            ),
            patch(
                "app.services.backup_plan_execution_service.BorgRouter",
                FakeBorgRouter,
            ),
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.expire_all()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        backup_job = test_db.query(BackupJob).filter_by(backup_plan_run_id=run.id).one()
        check_job = test_db.query(CheckJob).filter_by(repository_id=repo.id).one()
        prune_job = test_db.query(PruneJob).filter_by(repository_id=repo.id).one()
        compact_job = test_db.query(CompactJob).filter_by(repository_id=repo.id).one()
        assert run.status == "completed"
        assert backup_job.maintenance_status == "maintenance_completed"
        assert maintenance_calls == ["prune", "compact", "check"]
        assert check_job.scheduled_check is False
        assert prune_job.scheduled_prune is False
        assert compact_job.scheduled_compact is False

    @pytest.mark.asyncio
    async def test_cancel_after_backup_completion_does_not_start_maintenance(
        self, test_db
    ):
        repo = _create_repo(test_db, "Primary", "/repos/primary")
        _plan, run = _create_execution_plan(
            test_db,
            [repo],
            run_prune_after=True,
            run_compact_after=True,
        )

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            plan_run = db.query(BackupPlanRun).filter_by(id=run.id).one()
            plan_run.status = "cancelled"
            plan_run.completed_at = datetime.utcnow()
            child = (
                db.query(BackupPlanRunRepository)
                .filter_by(backup_plan_run_id=run.id, repository_id=repo.id)
                .one()
            )
            child.status = "cancelled"
            child.completed_at = datetime.utcnow()
            db.commit()

        maintenance_mock = AsyncMock(return_value="completed")
        with (
            patch(
                "app.services.backup_plan_execution_service.backup_service.execute_backup",
                side_effect=fake_execute_backup,
            ),
            patch.object(
                backup_plan_execution_service,
                "_run_maintenance",
                maintenance_mock,
            ),
        ):
            await backup_plan_execution_service.execute_run(run.id)

        maintenance_mock.assert_not_called()
        test_db.expire_all()
        run = test_db.query(BackupPlanRun).filter_by(id=run.id).one()
        child = run.repositories[0]
        backup_job = test_db.query(BackupJob).filter_by(backup_plan_run_id=run.id).one()
        assert run.status == "cancelled"
        assert child.status == "cancelled"
        assert backup_job.maintenance_status is None

    @pytest.mark.asyncio
    async def test_execute_plan_run_can_use_repository_compression_default(
        self, test_db
    ):
        repo = _create_repo(
            test_db,
            "Primary",
            "/repos/primary",
            compression="zstd,19",
        )
        plan = BackupPlan(
            name="Plan execution",
            enabled=True,
            source_type="local",
            source_directories=json.dumps(["/srv/project"]),
            exclude_patterns=json.dumps([]),
            archive_name_template="{plan_name}-{repo_name}-{now}",
            compression="lz4",
            repository_run_mode="series",
            max_parallel_repositories=1,
            failure_behavior="continue",
            schedule_enabled=False,
            timezone="UTC",
            run_repository_scripts=False,
            run_prune_after=False,
            run_compact_after=False,
            run_check_after=False,
            check_max_duration=3600,
            prune_keep_hourly=0,
            prune_keep_daily=7,
            prune_keep_weekly=4,
            prune_keep_monthly=6,
            prune_keep_quarterly=0,
            prune_keep_yearly=1,
            created_at=datetime.utcnow(),
        )
        test_db.add(plan)
        test_db.flush()
        test_db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=repo.id,
                enabled=True,
                execution_order=1,
                compression_source="repository",
                created_at=datetime.utcnow(),
            )
        )
        run = BackupPlanRun(
            backup_plan_id=plan.id,
            trigger="manual",
            status="pending",
            created_at=datetime.utcnow(),
        )
        test_db.add(run)
        test_db.flush()
        test_db.add(
            BackupPlanRunRepository(
                backup_plan_run_id=run.id,
                repository_id=repo.id,
                status="pending",
            )
        )
        test_db.commit()

        async def fake_execute_backup(job_id, repository, db, **kwargs):
            assert kwargs["compression_override"] == "zstd,19"
            job = db.query(BackupJob).filter_by(id=job_id).one()
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        with patch(
            "app.services.backup_plan_execution_service.backup_service.execute_backup",
            side_effect=fake_execute_backup,
        ):
            await backup_plan_execution_service.execute_run(run.id)

        test_db.refresh(run)
        assert run.status == "completed"
