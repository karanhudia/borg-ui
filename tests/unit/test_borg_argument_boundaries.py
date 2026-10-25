"""Every archive command closes options before its first operand."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.borg import BorgInterface
from app.core.borg2 import Borg2Interface
from app.core.borg_router import BorgRouter


CORE_BUILDERS = [
    ("info_archive", {"archive": "daily"}),
    ("list_archive_contents", {"archive": "daily", "path": "/folder with spaces/"}),
    ("diff_archives", {"archive_a": "daily", "archive_b": "previous"}),
    ("list_archive_lines", {"archive": "daily"}),
    (
        "export_archive_tar",
        {
            "archive": "daily",
            "directory_path": "/folder with spaces/",
            "strip_components": 1,
        },
    ),
    ("extract_archive", {"archive": "daily", "paths": [], "destination": "/restore"}),
    (
        "extract_archive",
        {
            "archive": "daily",
            "paths": ["folder with spaces/file"],
            "destination": "/restore",
        },
    ),
    ("delete_archive", {"archive": "daily"}),
    ("create", {"archive_name": "daily", "source_paths": ["/source with spaces"]}),
]


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
@pytest.mark.parametrize("method,kwargs", CORE_BUILDERS)
async def test_core_operand_boundary(monkeypatch, major, method, kwargs):
    interface = object.__new__(BorgInterface if major == 1 else Borg2Interface)
    interface.borg_cmd = "borg" if major == 1 else "borg2"
    process = MagicMock()
    process.returncode = 0
    process.communicate = AsyncMock(return_value=(b"", b""))
    process.wait = AsyncMock(return_value=0)
    process.stdout = AsyncMock()
    process.stdout.read = AsyncMock(return_value=b"")
    process.stdout.readline = AsyncMock(return_value=b"")
    process.stderr.read = AsyncMock(return_value=b"")
    execution = AsyncMock(return_value=process)
    monkeypatch.setattr("asyncio.create_subprocess_exec", execution)
    if method == "create" and major == 1:
        method = "run_backup"
    result = getattr(interface, method)(repository="/repo", **kwargs)
    if hasattr(result, "__await__"):
        completed = await result
        assert completed["success"]
    else:
        assert [item async for item in result] == []
    cmd = list(execution.await_args.args)
    operand = "daily" if major == 2 else "/repo::daily"
    assert cmd.count("--") == 1
    assert cmd[cmd.index("--") + 1] == operand
    if method == "export_archive_tar":
        assert cmd[cmd.index("--") + 1 :] == [operand, "-", "folder with spaces"]
        assert cmd.index("--strip-components") < cmd.index("--")


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
@pytest.mark.parametrize(
    "operation", ["backup", "info", "restore-empty", "restore-paths"]
)
def test_router_operand_boundary(major, operation):
    router = BorgRouter(SimpleNamespace(borg_version=major))
    if operation == "backup":
        cmd = router.build_backup_create_command(
            "/repo", "daily", "lz4", [], ["--one-file-system"]
        )
        # BackupService appends the resolved source operands later.
        cmd.extend(["source with spaces"])
        assert cmd.index("--one-file-system") < cmd.index("--")
    elif operation == "info":
        cmd = router.build_archive_info_command("/repo", "daily")
    else:
        paths = [] if operation == "restore-empty" else ["folder with spaces"]
        cmd = router.build_restore_extract_command(
            "/repo", "daily", paths=paths, strip_components=1
        )
    assert cmd.count("--") == 1
    assert cmd[cmd.index("--") + 1] == ("daily" if major == 2 else "/repo::daily")


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
@pytest.mark.parametrize(
    "field,value",
    [("archive", "--sentinel"), ("paths", ["--sentinel"]), ("paths", ["/-sentinel/"])],
)
async def test_stored_extract_values_are_validated(monkeypatch, major, field, value):
    interface = object.__new__(BorgInterface if major == 1 else Borg2Interface)
    interface.borg_cmd = "borg"
    execution = AsyncMock()
    monkeypatch.setattr(
        interface, "_execute_command" if major == 1 else "_run", execution
    )
    kwargs = dict(repository="/repo", archive="daily", paths=[], destination="/restore")
    kwargs[field] = value
    with pytest.raises(ValueError):
        await interface.extract_archive(**kwargs)
    execution.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize("template", ["--sentinel", "/sentinel", "{job_name}"])
def test_rendered_archive_name_is_validated(template):
    from app.utils.archive_names import build_archive_name

    with pytest.raises(ValueError):
        build_archive_name("--sentinel", None, template, "2026-10-09")


@pytest.mark.unit
@pytest.mark.parametrize(
    "source", ["--sentinel", " --sentinel", "ssh://host", "ssh://user@host:bad/path"]
)
def test_source_syntax_is_validated(source):
    from app.utils.source_locations import clean_source_paths

    with pytest.raises(ValueError):
        clean_source_paths([source])


@pytest.mark.unit
@pytest.mark.parametrize("module", ["app.api.archives", "app.api.v2.archives"])
@pytest.mark.parametrize(
    "kind,path",
    [("file", "--sentinel"), ("file", "/-sentinel/"), ("folder", "/-sentinel/")],
)
async def test_download_api_rejects_option_like_paths(module, kind, path):
    import importlib
    from fastapi import HTTPException

    api = importlib.import_module(module)
    kwargs = dict(
        repository="/repo", archive="daily", current_user=SimpleNamespace(), db=None
    )
    kwargs["file_path" if kind == "file" else "directory_path"] = path
    function = (
        api.download_file_from_archive
        if kind == "file"
        else api.download_folder_from_archive
    )
    with pytest.raises(HTTPException) as exc:
        await function(**kwargs)
    assert exc.value.status_code == 422


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value", [("archive", "--sentinel"), ("paths", ["/-sentinel/"])]
)
def test_restore_request_validates_operands(field, value):
    from app.api.restore import RestoreRequest

    with pytest.raises(ValueError):
        RestoreRequest(
            **{
                **dict(
                    repository="/repo",
                    archive="daily",
                    paths=[],
                    destination="/restore",
                    repository_id=1,
                ),
                field: value,
            }
        )


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
@pytest.mark.parametrize("method,kwargs", CORE_BUILDERS)
async def test_every_core_builder_rejects_option_like_operands(
    monkeypatch, major, method, kwargs
):
    interface = object.__new__(BorgInterface if major == 1 else Borg2Interface)
    interface.borg_cmd = "borg"
    execution = AsyncMock()
    for name in (
        "_execute_command",
        "_execute_command_streaming",
        "_run",
        "_run_streaming",
    ):
        monkeypatch.setattr(interface, name, execution, raising=False)
    kwargs = dict(kwargs)
    key = (
        "archive_name"
        if method == "create"
        else "archive_a"
        if method == "diff_archives"
        else "archive"
    )
    kwargs[key] = "--sentinel"
    if method == "create" and major == 1:
        method = "run_backup"
    with pytest.raises(ValueError):
        result = getattr(interface, method)(repository="/repo", **kwargs)
        if hasattr(result, "__await__"):
            await result
    execution.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize(
    "source",
    [
        "/source with spaces",
        "relative/path",
        "./-local",
        "/-local",
        "ssh://user@host:22/source with spaces",
        "ssh://host/./relative",
        "ssh://user@[::1]:22/source",
    ],
)
def test_supported_source_syntax_is_preserved(source):
    from app.utils.source_locations import clean_source_paths

    assert clean_source_paths([source]) == [source]


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
def test_router_rejects_disallowed_custom_flags(major):
    router = BorgRouter(SimpleNamespace(borg_version=major))
    with pytest.raises(ValueError):
        router.build_backup_create_command(
            "/repo", "daily", "lz4", [], ["--remote-path=sentinel"]
        )


@pytest.mark.unit
async def test_remote_backup_closes_options(monkeypatch):
    import shlex
    from app.database.models import Repository
    from app.services.remote_backup_service import RemoteBackupService

    service = RemoteBackupService()
    monkeypatch.setattr(service, "_get_repository_url", lambda *args, **kwargs: "/repo")
    command = await service._build_remote_command(
        Repository(path="/repo", repository_type="local", encryption="none"),
        "daily",
        ["source with spaces"],
        [],
        custom_flags="--one-file-system",
    )
    cmd = shlex.split(command)
    assert cmd.count("--") == 1
    assert cmd.index("--one-file-system") < cmd.index("--")
    assert cmd[cmd.index("--") + 1 :] == ["/repo::daily", "source with spaces"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "source", ["--sentinel", "ssh://host", "ssh://user@host:bad/path"]
)
def test_backup_plan_api_validates_sources_before_execution(source):
    from fastapi import HTTPException
    from app.api.backup_plans import BackupPlanPayload, _validate_payload

    payload = BackupPlanPayload(
        name="daily", source_directories=[source], repositories=[]
    )
    with pytest.raises(HTTPException) as exc:
        _validate_payload(None, SimpleNamespace(), payload)
    assert exc.value.status_code == 422


@pytest.mark.unit
@pytest.mark.parametrize("major", [1, 2])
@pytest.mark.parametrize("granted", [True, False])
def test_viewer_download_permissions_are_preserved(
    test_client, test_db, monkeypatch, major, granted
):
    import importlib
    from app.core.security import create_access_token
    from app.database.models import Repository, User, UserRepositoryPermission

    api = importlib.import_module(
        "app.api.archives" if major == 1 else "app.api.v2.archives"
    )
    user = User(
        username="boundary-viewer",
        password_hash="unused",
        is_active=True,
        role="viewer",
    )
    repo = Repository(
        name="boundary-repo", path="/repo", borg_version=major, encryption="none"
    )
    test_db.add_all([user, repo])
    test_db.flush()
    if granted:
        test_db.add(
            UserRepositoryPermission(
                user_id=user.id, repository_id=repo.id, role="viewer"
            )
        )
    test_db.commit()
    monkeypatch.setattr(
        api, "extract_file_download", AsyncMock(return_value={"download": True})
    )
    prefix = "/api/archives" if major == 1 else "/api/v2/archives"
    response = test_client.get(
        prefix + "/download",
        params={
            "repository": repo.path,
            "archive": "daily",
            "file_path": "folder with spaces/file",
        },
        headers={
            "Authorization": "Bearer "
            + create_access_token(data={"sub": user.username})
        },
    )
    assert response.status_code == (200 if granted else 403)
    if granted:
        assert response.json() == {"download": True}


@pytest.mark.unit
def test_router_borg1_archive_listing_closes_options():
    assert BorgRouter(SimpleNamespace(borg_version=1)).build_repo_list_command(
        "/repo"
    ) == ["borg", "list", "--json", "--", "/repo"]
