"""Recovery contracts for errors observed in production; no repair side effects."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.parametrize(
    "result,status",
    [
        ({"return_code": 21}, 403),
        ({"error": "PermissionError: [Errno 13] Permission denied: '/repo'"}, 403),
        ({"return_code": 19}, 409),
        ({"return_code": 2, "stderr": "There is already something at /repo."}, 409),
        ({"stderr": "FileExistsError: [Errno 17] File exists: '/repo'"}, 409),
        ({"return_code": 2, "stderr": "unexplained failure"}, 500),
        ({"return_code": 73, "stderr": "Our lock was killed by another borg"}, 500),
    ],
)
def test_repository_refusal_status(result, status):
    from app.core.borg_errors import repository_failure_status

    assert repository_failure_status(result) == status


def test_repository_diagnostic_redacts_before_bounding():
    from app.api.repositories import _repository_init_failure_detail

    reason = 'password="' + "secret" * 1000 + '"\nPermission denied'
    detail = _repository_init_failure_detail({"stderr": reason})
    diagnostic = detail["params"]["error"]
    assert "secret" not in diagnostic
    assert "Permission denied" in diagnostic
    assert len(diagnostic) <= 2000


def test_prune_exception_preserves_bounded_redacted_reason():
    from app.services.prune_preview import DryRunFailed

    failure = DryRunFailed(
        'password="sensitive"\n' + "x" * 3000 + "\nPermission denied"
    )
    assert "Permission denied" in str(failure)
    assert "sensitive" not in str(failure)
    assert len(failure.log) <= 2000
    assert len(str(failure)) < 2100


@pytest.mark.parametrize(
    "reason,status", [("Permission denied", 403), ("unknown failure", 500)]
)
def test_import_failure_preserves_reason(
    test_client, test_db, admin_headers, tmp_path, reason, status
):
    from app.database.models import Repository

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "config").write_text("[repository]\n")
    with patch(
        "app.api.repositories.verify_existing_repository",
        new=AsyncMock(return_value={"success": False, "stderr": reason}),
    ):
        response = test_client.post(
            "/api/repositories/import",
            json={"name": "refused", "path": str(repo_path), "encryption": "none"},
            headers=admin_headers,
        )
    assert response.status_code == status
    assert reason in response.json()["detail"]["message"]
    assert test_db.query(Repository).filter_by(name="refused").first() is None


@pytest.mark.parametrize(
    "reason",
    [
        "fuse: device not found, try 'modprobe fuse' first",
        "fuse: failed to open /dev/fuse: No such file or directory",
    ],
)
def test_missing_fuse_device_is_unavailable(reason):
    from app.services.mount_service import MountService

    assert MountService()._is_fuse_unavailable_error(reason)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    [
        "subsystem request failed on channel 0",
        "sh: /usr/lib/openssh/sftp-server: not found",
    ],
)
async def test_sftp_unavailable_is_actionable_without_shell_fallback(test_db, reason):
    from app.api import filesystem
    from app.database.models import SSHKey

    key = SSHKey(name="unavailable", public_key="public", private_key="encrypted")
    test_db.add(key)
    test_db.commit()
    with (
        patch.object(filesystem, "decrypt_secret", return_value="PRIVATE KEY\n"),
        patch.object(
            filesystem,
            "_run_sftp_batch",
            return_value=SimpleNamespace(returncode=255, stdout="", stderr=reason),
        ) as run,
    ):
        with pytest.raises(HTTPException) as failure:
            await filesystem.browse_ssh_filesystem(
                "/", key.id, "host", "user", 22, test_db
            )
    assert failure.value.status_code == 422
    assert "SFTP" in failure.value.detail
    assert run.call_count == 1


@pytest.mark.parametrize(
    "reason,status",
    [("Permission denied", 403), ("FileExistsError: [Errno 17] File exists", 409)],
)
def test_create_refused_target_status(
    test_client, admin_headers, tmp_path, reason, status
):
    with patch(
        "app.api.repositories.initialize_borg_repository",
        new=AsyncMock(return_value={"success": False, "stderr": reason}),
    ):
        response = test_client.post(
            "/api/repositories/",
            json={
                "name": "refused-create",
                "path": str(tmp_path / "repo"),
                "encryption": "none",
            },
            headers=admin_headers,
        )
    assert response.status_code == status


@pytest.mark.parametrize(
    "reason,status", [("Permission denied", 403), ("unknown probe failure", 500)]
)
def test_update_unverified_path_preserves_reason_and_original_path(
    test_client, test_db, admin_headers, reason, status
):
    from app.database.models import Repository

    repo = Repository(
        name="update-refusal",
        path="/tmp/original-recovery",
        encryption="none",
        compression="lz4",
        repository_type="local",
    )
    test_db.add(repo)
    test_db.commit()
    with (
        patch(
            "app.api.repositories.BorgRouter.verify_repository",
            new=AsyncMock(return_value={"success": False, "stderr": reason}),
        ),
        patch(
            "app.api.repositories.BorgRouter.initialize_repository", new=AsyncMock()
        ) as initialize,
    ):
        response = test_client.put(
            f"/api/repositories/{repo.id}",
            json={"path": "/tmp/new-recovery"},
            headers=admin_headers,
        )
    assert response.status_code == status
    assert reason in response.json()["detail"]["message"]
    initialize.assert_not_awaited()
    test_db.refresh(repo)
    assert repo.path == "/tmp/original-recovery"
