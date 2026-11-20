"""Manage: backup plans and schedules (plan phase 4, Task 6; spec 5.5 centrepiece)."""

import pytest

from tests.unit.mcp.test_tools_stubbed import run

V1 = {"id": 1, "name": "Photos", "path": "/data/example/photos", "borg_version": 1}
V2 = {"id": 2, "name": "Offsite", "path": "/data/example/offsite", "borg_version": 1}
REPOS = {"/api/repositories/": {"repositories": [V1, V2]}}
CONNS = {
    "/api/ssh-keys/connections": {
        "connections": [
            {"id": 4, "host": "nas.example.com", "username": "borg", "port": 22},
            {"id": 5, "host": "web.example.com", "username": "deploy", "port": 22},
        ]
    }
}
CRON_OK = {
    "POST /api/schedule/validate-cron": {
        "success": True,
        "cron_expression": "0 2 * * *",
        "timezone": "Europe/Berlin",
        "next_runs": ["2026-11-21T01:00:00+00:00", "2026-11-22T01:00:00+00:00"],
    }
}
CREATED = {"id": 12, "name": "Nightly photos", "next_run": "2026-11-21T01:00:00"}
FULL = {
    "name": "Nightly photos",
    "sources": [{"path": "/data/example/photos"}],
    "repositories": ["Photos"],
    "schedule": "0 2 * * *",
    "timezone": "Europe/Berlin",
}


def _routes(**extra):
    return {**REPOS, **CONNS, **CRON_OK, "POST /api/backup-plans/": CREATED, **extra}


@pytest.mark.unit
@pytest.mark.parametrize(
    "missing, said",
    [
        ("name", "a name"),
        ("sources", "what to back up"),
        ("repositories", "which repository"),
        ("schedule", "how often"),
    ],
)
def test_create_plan_missing_answers_posts_nothing(missing, said):
    args = {k: v for k, v in FULL.items() if k != missing}
    result, api = run("create_backup_plan", _routes(), **args)
    assert api.posts == []
    assert said in result.text
    assert result.data["missing"] == [missing]


@pytest.mark.unit
def test_create_plan_posts_and_lists_defaults_used():
    result, api = run("create_backup_plan", _routes(), **FULL)
    path, body = api.posts[-1]
    assert path == "/api/backup-plans/"
    assert body["name"] == "Nightly photos"
    assert body["source_locations"] == [
        {"source_type": "local", "paths": ["/data/example/photos"]}
    ]
    assert body["source_directories"] == ["/data/example/photos"]
    assert body["repositories"] == [{"repository_id": 1, "execution_order": 1}]
    assert body["cron_expression"] == "0 2 * * *"
    assert body["timezone"] == "Europe/Berlin"
    assert body["schedule_enabled"] is True
    assert body["prune_keep_daily"] == 7 and body["prune_keep_yearly"] == 1
    assert "Defaults I used" in result.text
    assert "7 daily" in result.text and "lz4" in result.text
    assert "Next run" in result.text


@pytest.mark.unit
def test_create_plan_given_retention_is_not_listed_as_default():
    result, api = run(
        "create_backup_plan",
        _routes(),
        **FULL,
        retention={"daily": 14, "weekly": 0, "monthly": 0, "yearly": 0},
        compression="zstd",
    )
    body = api.posts[-1][1]
    assert body["prune_keep_daily"] == 14 and body["prune_keep_monthly"] == 0
    assert "7 daily" not in result.text
    assert "lz4" not in result.text


@pytest.mark.unit
def test_create_plan_bad_cron_posts_nothing():
    routes = _routes(
        **{"POST /api/schedule/validate-cron": {"success": False, "error": "bad hour"}}
    )
    result, api = run(
        "create_backup_plan", routes, **{**FULL, "schedule": "0 25 * * *"}
    )
    assert [p for p, _ in api.posts if p == "/api/backup-plans/"] == []
    assert result.is_error


@pytest.mark.unit
def test_create_plan_manual_schedule():
    _, api = run("create_backup_plan", _routes(), **{**FULL, "schedule": "manual"})
    body = api.posts[-1][1]
    assert body["schedule_enabled"] is False
    assert "cron_expression" not in body


@pytest.mark.unit
def test_create_plan_groups_sources_by_endpoint():
    sources = [
        {"path": "/data/example/photos"},
        {"path": "/srv/a", "ssh_connection": "borg@nas.example.com"},
        {"path": "/srv/b", "ssh_connection": "borg@nas.example.com"},
        {"path": "/var/www", "ssh_connection": "deploy@web.example.com"},
    ]
    _, api = run(
        "create_backup_plan",
        _routes(),
        **{**FULL, "sources": sources, "repositories": ["Photos", "Offsite"]},
    )
    body = api.posts[-1][1]
    assert body["source_type"] == "mixed"
    assert body["source_locations"] == [
        {"source_type": "local", "paths": ["/data/example/photos"]},
        {
            "source_type": "remote",
            "source_ssh_connection_id": 4,
            "paths": ["/srv/a", "/srv/b"],
        },
        {"source_type": "remote", "source_ssh_connection_id": 5, "paths": ["/var/www"]},
    ]
    assert body["repositories"] == [
        {"repository_id": 1, "execution_order": 1},
        {"repository_id": 2, "execution_order": 2},
    ]


@pytest.mark.unit
def test_create_plan_source_on_both_ssh_and_agent_refused():
    sources = [
        {"path": "/x", "ssh_connection": "borg@nas.example.com", "agent": "laptop"}
    ]
    result, api = run("create_backup_plan", _routes(), **{**FULL, "sources": sources})
    assert result.is_error
    assert [p for p, _ in api.posts if p == "/api/backup-plans/"] == []


@pytest.mark.unit
def test_create_plan_scripts_and_after_steps():
    routes = _routes(**{"/api/scripts": [{"id": 3, "name": "pg dump"}]})
    _, api = run(
        "create_backup_plan",
        routes,
        **FULL,
        pre_backup_script="pg dump",
        after=["prune", "compact"],
    )
    body = api.posts[-1][1]
    assert body["pre_backup_script_id"] == 3
    assert body["run_prune_after"] is True and body["run_compact_after"] is True
    assert body["run_check_after"] is False


DETAIL = {
    "id": 12,
    "name": "Nightly photos",
    "description": None,
    "enabled": True,
    "source_type": "local",
    "source_ssh_connection_id": None,
    "source_directories": ["/data/example/photos"],
    "source_locations": [{"source_type": "local", "paths": ["/data/example/photos"]}],
    "exclude_patterns": [],
    "archive_name_template": "{plan_name}-{now}",
    "compression": "lz4",
    "repository_run_mode": "series",
    "max_parallel_repositories": 1,
    "failure_behavior": "continue",
    "schedule_enabled": True,
    "schedule_mode": "cron",
    "cron_expression": "0 2 * * *",
    "timezone": "UTC",
    "repositories": [
        {
            "id": 30,
            "repository_id": 1,
            "enabled": True,
            "execution_order": 1,
            "compression_source": "plan",
            "compression_override": None,
            "repository": {"id": 1, "name": "Photos"},
        }
    ],
    "script_hooks": [],
    "prune_keep_daily": 7,
    "prune_keep_weekly": 4,
    "prune_keep_monthly": 6,
    "prune_keep_yearly": 1,
    "next_run": "2026-11-21T02:00:00",
    "last_run": None,
}
PLANS = {"/api/backup-plans/": {"backup_plans": [DETAIL]}}


@pytest.mark.unit
def test_update_plan_keeps_unchanged_fields():
    routes = {
        **PLANS,
        "/api/backup-plans/12": DETAIL,
        "PUT /api/backup-plans/12": DETAIL,
    }
    result, api = run(
        "update_backup_plan",
        routes,
        backup_plan="Nightly",
        compression="zstd",
        retention={"daily": 14},
    )
    path, body = api.puts[0]
    assert path == "/api/backup-plans/12"
    assert body["compression"] == "zstd"
    assert body["prune_keep_daily"] == 14
    assert body["prune_keep_weekly"] == 4  # untouched
    assert body["source_directories"] == ["/data/example/photos"]
    assert body["repositories"] == [
        {
            "repository_id": 1,
            "enabled": True,
            "execution_order": 1,
            "compression_source": "plan",
            "compression_override": None,
        }
    ]
    assert "id" not in body and "next_run" not in body
    assert "lz4 → zstd" in result.text


@pytest.mark.unit
def test_update_plan_nothing_to_change():
    result, api = run("update_backup_plan", dict(PLANS), backup_plan="Nightly")
    assert api.puts == []
    assert result.is_error


@pytest.mark.unit
def test_set_plan_enabled_is_idempotent():
    routes = {**PLANS, "POST /api/backup-plans/12/toggle": {"enabled": False}}
    result, api = run(
        "set_backup_plan_enabled", routes, backup_plan="Nightly", enabled=True
    )
    assert api.posts == []
    assert "already on" in result.text
    _, api = run(
        "set_backup_plan_enabled", routes, backup_plan="Nightly", enabled=False
    )
    assert api.posts == [("/api/backup-plans/12/toggle", None)]


SCHEDULES = {
    "/api/schedule/": {
        "jobs": [
            {
                "id": 5,
                "name": "Nightly",
                "enabled": True,
                "cron_expression": "0 3 * * *",
                "schedule_mode": "cron",
                "timezone": "Europe/Berlin",
            }
        ]
    }
}


@pytest.mark.unit
def test_create_schedule_missing_answers():
    result, api = run("create_schedule", _routes(), name="Hourly")
    assert api.posts == []
    assert result.data["missing"] == ["repositories", "schedule"]


@pytest.mark.unit
def test_create_schedule_posts():
    routes = _routes(**{"POST /api/schedule/": {"job": {"id": 6, "name": "Hourly"}}})
    result, api = run(
        "create_schedule",
        routes,
        name="Hourly",
        repositories=["Photos", "Offsite"],
        schedule="0 2 * * *",
        timezone="Europe/Berlin",
    )
    path, body = api.posts[-1]
    assert path == "/api/schedule/"
    assert body["repository_ids"] == [1, 2]
    assert body["cron_expression"] == "0 2 * * *"
    assert "backup plan" in result.text.lower()


@pytest.mark.unit
def test_update_schedule_puts_changes_only():
    seen = []

    def validate(body):
        seen.append(body)
        return CRON_OK["POST /api/schedule/validate-cron"]

    routes = {
        **SCHEDULES,
        "POST /api/schedule/validate-cron": validate,
        "PUT /api/schedule/5": {"success": True},
    }
    _, api = run("update_schedule", routes, schedule="Nightly", cron="0 2 * * *")
    assert seen[0]["timezone"] == "Europe/Berlin"  # the stored zone, not UTC
    assert api.puts == [
        (
            "/api/schedule/5",
            {
                "cron_expression": "0 2 * * *",
                "schedule_mode": "cron",
                "timezone": "Europe/Berlin",
            },
        )
    ]


@pytest.mark.unit
def test_set_schedule_enabled_toggles_only_when_needed():
    routes = {**SCHEDULES, "POST /api/schedule/5/toggle": {"enabled": False}}
    _, api = run("set_schedule_enabled", routes, schedule="Nightly", enabled=True)
    assert api.posts == []
    _, api = run("set_schedule_enabled", routes, schedule="Nightly", enabled=False)
    assert api.posts == [("/api/schedule/5/toggle", None)]


@pytest.mark.unit
def test_duplicate_schedule_renames_the_copy():
    routes = {
        **SCHEDULES,
        "POST /api/schedule/5/duplicate": {"job": {"id": 7, "name": "Nightly (copy)"}},
        "PUT /api/schedule/7": {"success": True},
    }
    result, api = run(
        "duplicate_schedule", routes, schedule="Nightly", new_name="Weekly"
    )
    assert api.posts == [("/api/schedule/5/duplicate", None)]
    assert api.puts == [("/api/schedule/7", {"name": "Weekly"})]
    assert "*Weekly*" in result.text


@pytest.mark.unit
def test_create_plan_against_the_app(
    mcp, create_connection, admin_headers, seeded, test_db, tmp_path
):
    from app.database.models import BackupPlan

    _, token = create_connection(admin_headers, name="manage", level="manage")
    result = mcp(token).call(
        "create_backup_plan",
        name="Evening photos",
        sources=[{"path": str(tmp_path)}],
        repositories=["Photos"],
        schedule="30 21 * * *",
        timezone="Europe/Berlin",
    )
    assert not result["is_error"], result["text"]
    assert "Next run" in result["text"]
    assert "Defaults I used" in result["text"]
    plan = test_db.query(BackupPlan).filter(BackupPlan.name == "Evening photos").one()
    assert plan.cron_expression == "30 21 * * *"
    assert plan.timezone == "Europe/Berlin"
    assert plan.schedule_enabled
    assert [link.repository_id for link in plan.repositories] == [seeded["photos"].id]


@pytest.mark.unit
def test_update_plan_keeps_hook_passwords(
    mcp, create_connection, admin_headers, seeded, test_db, tmp_path
):
    """Review finding: the masked `***` must never be written back."""
    import json

    from app.core.security import decrypt_secret, encrypt_secret
    from app.database.models import (
        BackupPlan,
        BackupPlanRepository,
        BackupPlanScript,
        Script,
    )

    body = tmp_path / "dump.sh"
    body.write_text("echo dump\n")
    script = Script(
        name="db dump",
        file_path=str(body),
        parameters=json.dumps([{"name": "DB_PASSWORD", "type": "password"}]),
    )
    plan = BackupPlan(
        name="Hooked plan",
        source_directories=json.dumps([str(tmp_path)]),
        source_type="local",
        cron_expression="0 2 * * *",
        timezone="UTC",
    )
    test_db.add_all([script, plan])
    test_db.commit()
    test_db.add_all(
        [
            BackupPlanScript(
                backup_plan_id=plan.id,
                script_id=script.id,
                hook_type="pre-backup",
                parameter_values=json.dumps(
                    {"DB_PASSWORD": encrypt_secret("example-db-pw")}
                ),
            ),
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=seeded["photos"].id,
                execution_order=1,
            ),
        ]
    )
    test_db.commit()
    _, token = create_connection(admin_headers, name="m", level="manage")
    result = mcp(token).call(
        "update_backup_plan", backup_plan="Hooked plan", compression="zstd"
    )
    assert not result["is_error"], result["text"]
    test_db.expire_all()
    hook = test_db.query(BackupPlanScript).filter_by(backup_plan_id=plan.id).one()
    stored = json.loads(hook.parameter_values)["DB_PASSWORD"]
    assert decrypt_secret(stored) == "example-db-pw"


@pytest.mark.unit
def test_create_plan_partial_retention_zeroes_the_rest():
    result, api = run("create_backup_plan", _routes(), **FULL, retention={"daily": 14})
    body = api.posts[-1][1]
    assert body["prune_keep_daily"] == 14
    for unit in ("hourly", "weekly", "monthly", "quarterly", "yearly"):
        assert body[f"prune_keep_{unit}"] == 0, unit
    assert "Keeps: 14 daily" in result.text


@pytest.mark.unit
def test_create_schedule_partial_retention_zeroes_the_rest():
    routes = _routes(**{"POST /api/schedule/": {"job": {"id": 6, "name": "Hourly"}}})
    _, api = run(
        "create_schedule",
        routes,
        name="Hourly",
        repositories=["Photos"],
        schedule="0 2 * * *",
        retention={"daily": 14},
    )
    body = api.posts[-1][1]
    assert body["prune_keep_daily"] == 14
    assert body["prune_keep_weekly"] == 0 and body["prune_keep_yearly"] == 0


@pytest.mark.unit
def test_update_plan_timezone_only_revalidates_the_stored_cron():
    seen = []

    def validate(body):
        seen.append(body)
        return {
            "success": True,
            "cron_expression": "0 2 * * *",
            "timezone": "Europe/Berlin",
            "next_runs": [],
        }

    routes = {
        **PLANS,
        "/api/backup-plans/12": DETAIL,
        "POST /api/schedule/validate-cron": validate,
        "PUT /api/backup-plans/12": DETAIL,
    }
    result, api = run(
        "update_backup_plan", routes, backup_plan="Nightly", timezone="Europe/Berlin"
    )
    assert seen and seen[0]["hour"] == "2" and seen[0]["timezone"] == "Europe/Berlin"
    body = api.puts[0][1]
    assert body["timezone"] == "Europe/Berlin"
    assert body["cron_expression"] == "0 2 * * *"
    assert body["schedule_enabled"] is True
    assert "UTC → Europe/Berlin" in result.text


@pytest.mark.unit
def test_update_plan_sends_no_script_hooks():
    routes = {
        **PLANS,
        "/api/backup-plans/12": DETAIL,
        "PUT /api/backup-plans/12": DETAIL,
    }
    _, api = run("update_backup_plan", routes, backup_plan="Nightly", name="Renamed")
    assert "script_hooks" not in api.puts[0][1]


# PR #1585 review


AVAILABILITY = {
    "/api/schedule/": {
        "jobs": [
            {
                "id": 5,
                "name": "Nightly",
                "enabled": True,
                "cron_expression": None,
                "schedule_mode": "availability",
                "timezone": "UTC",
            }
        ]
    }
}


@pytest.mark.unit
def test_update_schedule_cron_switches_availability_to_cron_mode():
    routes = {**AVAILABILITY, **CRON_OK, "PUT /api/schedule/5": {"success": True}}
    _, api = run("update_schedule", routes, schedule="Nightly", cron="0 2 * * *")
    assert api.puts[0][1]["schedule_mode"] == "cron"


@pytest.mark.unit
def test_update_schedule_timezone_only_on_availability_needs_no_cron():
    routes = {**AVAILABILITY, "PUT /api/schedule/5": {"success": True}}
    result, api = run(
        "update_schedule", routes, schedule="Nightly", timezone="Europe/Berlin"
    )
    assert not result.is_error, result.text
    assert api.puts == [("/api/schedule/5", {"timezone": "Europe/Berlin"})]


@pytest.mark.unit
def test_update_plan_cron_switches_availability_to_cron_mode():
    detail = {**DETAIL, "schedule_mode": "availability", "cron_expression": None}
    routes = {
        "/api/backup-plans/": {"backup_plans": [detail]},
        "/api/backup-plans/12": detail,
        **CRON_OK,
        "PUT /api/backup-plans/12": detail,
    }
    _, api = run(
        "update_backup_plan", routes, backup_plan="Nightly", schedule="0 2 * * *"
    )
    assert api.puts[0][1]["schedule_mode"] == "cron"


@pytest.mark.unit
def test_update_plan_keeps_overrides_of_retained_repositories():
    link = {
        **DETAIL["repositories"][0],
        "enabled": False,
        "compression_source": "custom",
        "compression_override": "zstd,9",
        "upload_ratelimit_kib_override": 512,
    }
    detail = {**DETAIL, "repositories": [link]}
    routes = {
        "/api/backup-plans/": {"backup_plans": [detail]},
        "/api/backup-plans/12": detail,
        **REPOS,
        "PUT /api/backup-plans/12": detail,
    }
    _, api = run(
        "update_backup_plan",
        routes,
        backup_plan="Nightly",
        repositories=["Offsite", "Photos"],
    )
    sent = {r["repository_id"]: r for r in api.puts[0][1]["repositories"]}
    assert sent[2] == {"repository_id": 2, "execution_order": 1, "enabled": True}
    assert sent[1]["execution_order"] == 2
    assert sent[1]["enabled"] is False
    assert sent[1]["compression_override"] == "zstd,9"
    assert sent[1]["upload_ratelimit_kib_override"] == 512


@pytest.mark.unit
@pytest.mark.parametrize("field", ["sources", "repositories"])
def test_update_plan_rejects_empty_replacement_lists(field):
    routes = {
        **PLANS,
        "/api/backup-plans/12": DETAIL,
        "PUT /api/backup-plans/12": DETAIL,
    }
    result, api = run(
        "update_backup_plan",
        routes,
        backup_plan="Nightly",
        name="Renamed",
        **{field: []},
    )
    assert result.is_error
    assert api.puts == []


@pytest.mark.unit
def test_update_schedule_rejects_empty_repositories():
    routes = {**SCHEDULES, "PUT /api/schedule/5": {"success": True}}
    result, api = run("update_schedule", routes, schedule="Nightly", repositories=[])
    assert result.is_error
    assert api.puts == []


@pytest.mark.unit
def test_update_plan_manual_with_timezone_sets_both():
    routes = {
        **PLANS,
        "/api/backup-plans/12": DETAIL,
        "PUT /api/backup-plans/12": DETAIL,
    }
    _, api = run(
        "update_backup_plan",
        routes,
        backup_plan="Nightly",
        schedule="manual",
        timezone="Europe/Berlin",
    )
    body = api.puts[0][1]
    assert body["schedule_enabled"] is False
    assert body["timezone"] == "Europe/Berlin"


@pytest.mark.unit
def test_create_plan_reports_saved_next_run_and_template_default():
    created = {**CREATED, "next_run": "2026-11-22T01:00:00"}
    result, _ = run(
        "create_backup_plan", _routes(**{"POST /api/backup-plans/": created}), **FULL
    )
    assert "archive names `{plan_name}-{now}`" in result.text
    assert result.data["next_run"] == "2026-11-22T01:00:00"
    assert "2026-11-22" in result.text


@pytest.mark.unit
def test_create_plan_says_when_pruning_is_off():
    result, _ = run("create_backup_plan", _routes(), **FULL, retention={"daily": 14})
    assert "pruning after backups is off" in result.text
    result, _ = run(
        "create_backup_plan",
        _routes(),
        **FULL,
        retention={"daily": 14},
        after=["prune"],
    )
    assert "pruning after backups is off" not in result.text


@pytest.mark.unit
def test_create_plan_refuses_prune_with_an_empty_policy():
    result, api = run(
        "create_backup_plan",
        _routes(),
        **FULL,
        retention={"daily": 0},
        after=["prune"],
    )
    assert result.is_error
    assert [p for p, _ in api.posts if p == "/api/backup-plans/"] == []


@pytest.mark.unit
def test_create_schedule_refuses_an_empty_policy():
    routes = _routes(**{"POST /api/schedule/": {"job": {"id": 6, "name": "Hourly"}}})
    result, api = run(
        "create_schedule",
        routes,
        name="Hourly",
        repositories=["Photos"],
        schedule="0 2 * * *",
        retention={},
    )
    assert result.is_error
    assert [p for p, _ in api.posts if p == "/api/schedule/"] == []


@pytest.mark.unit
def test_create_schedule_reports_saved_next_run():
    routes = _routes(
        **{
            "POST /api/schedule/": {
                "job": {"id": 6, "name": "Hourly", "next_run": "2026-11-22T01:00:00"}
            }
        }
    )
    result, _ = run(
        "create_schedule",
        routes,
        name="Hourly",
        repositories=["Photos"],
        schedule="0 2 * * *",
    )
    assert result.data["next_run"] == "2026-11-22T01:00:00"
    assert "2026-11-22" in result.text


@pytest.mark.unit
def test_duplicate_schedule_warns_about_script_parameters():
    scheduled = {
        "/api/schedule/": {
            "jobs": [
                {**SCHEDULES["/api/schedule/"]["jobs"][0], "pre_backup_script_id": 3}
            ]
        },
        "POST /api/schedule/5/duplicate": {
            "job": {"id": 7, "name": "Nightly (copy)", "enabled": False}
        },
    }
    result, _ = run("duplicate_schedule", scheduled, schedule="Nightly")
    assert "script parameters" in result.text


@pytest.mark.unit
def test_duplicate_schedule_rename_failure_names_the_copy():
    from app.mcp.client import ApiError

    routes = {
        **SCHEDULES,
        "POST /api/schedule/5/duplicate": {"job": {"id": 7, "name": "Nightly (copy)"}},
        "PUT /api/schedule/7": ApiError(409, "backend.errors.schedule.nameExists"),
    }
    result, _ = run("duplicate_schedule", routes, schedule="Nightly", new_name="Weekly")
    assert result.is_error
    assert "*Nightly (copy)*" in result.text
    assert result.data["schedule_id"] == 7


@pytest.mark.unit
def test_update_schedule_name_only_validates_nothing():
    routes = {**SCHEDULES, "PUT /api/schedule/5": {"success": True}}
    _, api = run("update_schedule", routes, schedule="Nightly", name="Nightly two")
    assert api.posts == []  # no cron validation
    assert api.puts == [("/api/schedule/5", {"name": "Nightly two"})]
