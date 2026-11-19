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
}
EM_DASH = "\u2014"
READ_POST_ALLOWLIST = {"POST /api/schedule/validate-cron"}


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
