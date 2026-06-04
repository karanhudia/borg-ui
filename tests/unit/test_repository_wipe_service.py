from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.borg_router import BorgRouter
from app.database.models import Repository, RepositoryWipeJob, User
from app.services.repository_wipe_service import (
    RepositoryWipeService,
    WipeArchiveSetChanged,
    compute_archive_fingerprint,
    normalize_archive_manifest,
)


def test_wipe_delete_commands_are_version_aware_and_never_delete_repository():
    borg1_repo = SimpleNamespace(
        id=1,
        path="/repos/one",
        remote_path="/usr/local/bin/borg",
        borg_version=1,
    )
    borg2_repo = SimpleNamespace(
        id=2,
        path="/repos/two",
        remote_path="/usr/local/bin/borg2",
        borg_version=2,
    )

    borg1_preview = BorgRouter(borg1_repo).build_wipe_delete_command(dry_run=True)
    borg1_execute = BorgRouter(borg1_repo).build_wipe_delete_command(dry_run=False)
    borg2_preview = BorgRouter(borg2_repo).build_wipe_delete_command(dry_run=True)
    borg2_execute = BorgRouter(borg2_repo).build_wipe_delete_command(dry_run=False)

    assert borg1_preview == [
        "borg",
        "delete",
        "--list",
        "--dry-run",
        "--remote-path",
        "/usr/local/bin/borg",
        "--glob-archives",
        "*",
        "/repos/one",
    ]
    assert borg1_execute == [
        "borg",
        "delete",
        "--list",
        "--stats",
        "--remote-path",
        "/usr/local/bin/borg",
        "--glob-archives",
        "*",
        "/repos/one",
    ]
    assert borg2_preview == [
        "borg2",
        "-r",
        "/repos/two",
        "delete",
        "--list",
        "--dry-run",
        "-a",
        "sh:*",
        "--remote-path",
        "/usr/local/bin/borg2",
    ]
    assert borg2_execute == [
        "borg2",
        "-r",
        "/repos/two",
        "delete",
        "--list",
        "-a",
        "sh:*",
        "--remote-path",
        "/usr/local/bin/borg2",
    ]
    assert "repo-delete" not in borg2_execute
    assert "rdelete" not in borg2_execute


def test_archive_fingerprint_uses_borg2_ids_and_is_order_stable():
    borg1_manifest = normalize_archive_manifest(
        borg_version=1,
        archives=[
            {"name": "daily-2", "time": "2026-05-18T00:00:00"},
            {"name": "daily-1", "time": "2026-05-17T00:00:00"},
        ],
    )
    borg2_manifest = normalize_archive_manifest(
        borg_version=2,
        archives=[
            {"name": "daily", "id": "def456", "start": "2026-05-18T00:00:00"},
            {"name": "daily", "id": "abc123", "start": "2026-05-17T00:00:00"},
        ],
    )
    borg2_manifest_reordered = list(reversed(borg2_manifest))

    assert [item["identity"] for item in borg1_manifest] == ["daily-2", "daily-1"]
    assert [item["identity"] for item in borg2_manifest] == ["def456", "abc123"]
    assert compute_archive_fingerprint(borg2_manifest).startswith("sha256:")
    assert compute_archive_fingerprint(borg2_manifest) == compute_archive_fingerprint(
        borg2_manifest_reordered
    )
    assert compute_archive_fingerprint(borg1_manifest) != compute_archive_fingerprint(
        borg2_manifest
    )


@pytest.mark.asyncio
async def test_preview_blocks_borg2_protected_archives(db_session):
    user = User(username="admin", password_hash="hash", is_active=True, role="admin")
    repo = Repository(
        name="Protected Repo",
        path="/tmp/protected-repo",
        encryption="none",
        repository_type="local",
        borg_version=2,
    )
    db_session.add_all([user, repo])
    db_session.commit()
    db_session.refresh(repo)

    service = RepositoryWipeService()
    archives = [
        {
            "name": "protected-archive",
            "id": "abc123",
            "start": "2026-05-18T00:00:00",
            "tags": ["@PROT"],
        }
    ]

    with (
        patch.object(BorgRouter, "list_archives", new=AsyncMock(return_value=archives)),
        patch.object(
            BorgRouter,
            "run_wipe_delete",
            new=AsyncMock(return_value={"success": True, "stdout": "would delete"}),
        ) as run_wipe_delete,
    ):
        preview = await service.create_preview(db_session, repo, user)

    assert preview["blocked"] is True
    assert preview["blocking_reason"] == "protected_archives"
    assert preview["protected_archives"] == ["protected-archive"]
    assert preview["archive_count"] == 1
    run_wipe_delete.assert_not_awaited()

    job = db_session.query(RepositoryWipeJob).one()
    assert job.status == "previewed"
    assert job.phase == "preview"
    assert job.requested_by_user_id == user.id


@pytest.mark.asyncio
async def test_execution_rejects_stale_preview_before_delete(db_session):
    user = User(username="admin", password_hash="hash", is_active=True, role="admin")
    repo = Repository(
        name="Primary",
        path="/tmp/repo",
        encryption="none",
        repository_type="local",
        borg_version=1,
    )
    db_session.add_all([user, repo])
    db_session.commit()
    db_session.refresh(repo)

    old_manifest = normalize_archive_manifest(
        borg_version=1,
        archives=[{"name": "archive-a", "time": "2026-05-17T00:00:00"}],
    )
    new_archives = [{"name": "archive-b", "time": "2026-05-18T00:00:00"}]
    preview = RepositoryWipeJob(
        repository_id=repo.id,
        repository_path=repo.path,
        repository_name=repo.name,
        borg_version=1,
        status="previewed",
        phase="preview",
        archive_count=1,
        archive_fingerprint=compute_archive_fingerprint(old_manifest),
        archive_manifest_json='[{"identity":"archive-a","name":"archive-a"}]',
        requested_by_user_id=user.id,
        created_at=datetime.utcnow(),
    )
    db_session.add(preview)
    db_session.commit()
    db_session.refresh(preview)

    service = RepositoryWipeService()

    with (
        patch.object(
            BorgRouter, "list_archives", new=AsyncMock(return_value=new_archives)
        ),
        patch.object(BorgRouter, "run_wipe_delete", new=AsyncMock()) as run_wipe_delete,
    ):
        with pytest.raises(WipeArchiveSetChanged):
            await service.start_execution(
                db_session,
                repo,
                user,
                preview_id=preview.id,
                preview_fingerprint=preview.archive_fingerprint,
                confirmation_phrase="WIPE Primary",
                understood=True,
                run_compact=True,
            )

    run_wipe_delete.assert_not_awaited()
    db_session.refresh(preview)
    assert preview.status == "previewed"
    assert preview.phase == "stale"


@pytest.mark.asyncio
async def test_execute_marks_compact_failure_after_successful_delete(db_session):
    user = User(username="admin", password_hash="hash", is_active=True, role="admin")
    repo = Repository(
        name="Primary",
        path="/tmp/repo",
        encryption="none",
        repository_type="local",
        borg_version=1,
    )
    manifest = normalize_archive_manifest(
        borg_version=1,
        archives=[{"name": "archive-a", "time": "2026-05-17T00:00:00"}],
    )
    db_session.add_all([user, repo])
    db_session.commit()
    db_session.refresh(repo)
    preview = RepositoryWipeJob(
        repository_id=repo.id,
        repository_path=repo.path,
        repository_name=repo.name,
        borg_version=1,
        status="pending",
        phase="queued",
        archive_count=1,
        archive_fingerprint=compute_archive_fingerprint(manifest),
        archive_manifest_json='[{"identity":"archive-a","name":"archive-a"}]',
        run_compact=True,
        requested_by_user_id=user.id,
        confirmed_by_user_id=user.id,
        created_at=datetime.utcnow(),
    )
    db_session.add(preview)
    db_session.commit()
    db_session.refresh(preview)

    service = RepositoryWipeService()

    with (
        patch(
            "app.services.repository_wipe_service.SessionLocal", return_value=db_session
        ),
        patch.object(
            BorgRouter,
            "run_wipe_delete",
            new=AsyncMock(return_value={"success": True, "stdout": "deleted"}),
        ),
        patch.object(
            BorgRouter,
            "run_wipe_compact",
            new=AsyncMock(return_value={"success": False, "stderr": "compact failed"}),
        ),
        patch.object(BorgRouter, "update_stats", new=AsyncMock(return_value=True)),
    ):
        await service.execute_wipe(preview.id, repo.id)

    db_session.refresh(preview)
    assert preview.status == "completed_compaction_failed"
    assert preview.phase == "compact_failed"
    assert "compact failed" in (preview.error_message or "")
