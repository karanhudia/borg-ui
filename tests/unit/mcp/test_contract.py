"""Every tool follows the registry contract (plan Task 12)."""

import re

import pytest
from app.main import app
from app.mcp.levels import Level
from app.mcp.registry import REGISTRY, tools_for

EXPECTED_TOOLS = {
    # Task 8
    "get_overview",
    "list_problems",
    "get_upcoming_runs",
    "get_system_info",
    # Task 9
    "list_repositories",
    "get_repository",
    "get_repository_space",
    "compare_retention",
    "list_archives",
    "get_archive",
    "browse_archive",
    "search_files",
    "get_file_history",
    "compare_archives",
    # Task 10
    "list_activity",
    "list_running_jobs",
    "get_job",
    "get_job_log",
    "wait_for_job",
    "explain_failure",
    # Task 11
    "list_backup_plans",
    "get_backup_plan",
    "list_plan_runs",
    "list_schedules",
    "get_schedule",
    "check_cron",
    "browse_server_folders",
    "browse_agent_folders",
    "list_ssh_connections",
    "list_ssh_keys",
    "list_agents",
    "list_rclone_remotes",
    "list_scripts",
    "list_notification_channels",
    "get_settings",
    "list_users",
    # Phase 3, Task 3
    "start_backup",
    "run_backup_plan",
    "run_schedule_now",
    # Task 4
    "cancel_job",
    "retry_job",
    # Task 5
    "check_repository",
    "compact_repository",
    "run_restore_check",
    "refresh_repository",
    "preview_prune",
    # Task 6
    "preview_restore",
    "restore_files",
    # Task 7
    "mount_archive",
    "unmount_archive",
    # Task 8
    "test_ssh_connection",
    "test_notification",
    "test_script",
    "discover_sources",
    "pause_background_work",
    "resume_background_work",
}
EM_DASH = "\u2014"
READ_POST_ALLOWLIST = {"POST /api/schedule/validate-cron"}
# Spec 5.4 and 5.6: only full tools may declare these.
DESTRUCTIVE_EXACT = {
    "POST /api/repositories/{repo_id}/prune",
    "POST /api/v2/backup/prune",
}
DESTRUCTIVE_WORDS = ("wipe", "break-lock", "delete", "/rebuild")
# Only restore_files, behind its destination rule (spec 5.5), may start a restore.
RESTORE_START = "POST /api/restore/start"
# Spec 5.2 rule 5: no tool at any level.
FORBIDDEN_PREFIXES = (
    "/api/auth/tokens",
    "/api/settings/tokens",
    "/api/settings/mcp",
    "/api/system/licensing",
)


def _destructive(route: str) -> bool:
    method, path = route.split(" ", 1)
    if route in DESTRUCTIVE_EXACT or method == "DELETE":
        return True
    # cancelling a delete or wipe job stops it, which is not destructive
    return (
        method != "GET"
        and not path.endswith("/cancel")
        and any(word in path for word in DESTRUCTIVE_WORDS)
    )


def _forbidden(route: str) -> bool:
    path = route.split(" ", 1)[1]
    return path.startswith(FORBIDDEN_PREFIXES) or "password" in path


@pytest.mark.unit
def test_destructive_and_forbidden_checks_match():
    assert _destructive("POST /api/repositories/{repo_id}/prune")
    assert _destructive("POST /api/repositories/{repo_id}/wipe")
    assert _destructive("DELETE /api/scripts/{script_id}")
    assert not _destructive(
        "POST /api/repositories/{repo_id}/wipe-jobs/{job_id}/cancel"
    )
    assert not _destructive("POST /api/repositories/{repo_id}/prune/preview")
    assert _forbidden("POST /api/settings/mcp/connections")
    assert _forbidden("POST /api/auth/change-password")
    assert not _forbidden("GET /api/settings/system")


@pytest.mark.unit
def test_no_tool_below_full_declares_a_destructive_route():
    for spec in REGISTRY.values():
        if spec.level >= Level.FULL:
            continue
        for route in spec.routes:
            assert not _destructive(route), f"{spec.name} declares {route}"
            if route == RESTORE_START:
                assert spec.name == "restore_files", f"{spec.name} starts restores"


@pytest.mark.unit
def test_no_tool_declares_a_forbidden_route():
    for spec in REGISTRY.values():
        for route in spec.routes:
            assert not _forbidden(route), f"{spec.name} declares {route}"


def _app_routes() -> set[str]:
    """Every route as "METHOD /path", from the OpenAPI schema: FastAPI nests
    included routers, so app.routes is not flat."""
    return {
        f"{method.upper()} {path}"
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def _registered():
    return {name: spec for name, spec in REGISTRY.items() if not name.startswith("zz_")}


@pytest.mark.unit
def test_exactly_the_planned_tools_exist():
    assert set(_registered()) == EXPECTED_TOOLS


@pytest.mark.unit
@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_tool_contract(name):
    spec = REGISTRY[name]
    assert re.fullmatch(r"[a-z][a-z0-9_]{1,39}", spec.name)
    assert spec.title and not spec.title.endswith(".") and EM_DASH not in spec.title
    assert 40 <= len(spec.description) <= 600, len(spec.description)
    assert EM_DASH not in spec.description
    routes = _app_routes()
    for declared in spec.routes:
        assert declared in routes, (
            f"{name} declares {declared}, which the app does not have"
        )
        method = declared.split()[0]
        if spec.level == Level.READ and declared not in READ_POST_ALLOWLIST:
            assert method in ("GET", "HEAD"), f"read tool {name} declares {declared}"
        if spec.level < Level.FULL:
            assert method != "DELETE"
    schema = spec.input_model.model_json_schema()
    for field, details in (schema.get("properties") or {}).items():
        assert details.get("description"), f"{name}.{field} has no description"


@pytest.mark.unit
@pytest.mark.parametrize("level", list(Level))
@pytest.mark.parametrize("cap", list(Level))
def test_level_matrix_lists_exactly_the_allowed_tools(
    level, cap, mcp, create_connection, admin_headers, test_db
):
    from app.database.models import SystemSettings

    _, token = create_connection(admin_headers, level=level.label)
    settings = test_db.query(SystemSettings).first() or SystemSettings()
    settings.mcp_max_access_level = cap.label
    test_db.add(settings)
    test_db.commit()
    listed = {t["name"] for t in mcp(token).list_tools()}
    assert listed == {s.name for s in tools_for(min(level, cap))}
