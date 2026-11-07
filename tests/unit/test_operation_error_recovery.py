"""Recovery contracts for errors observed in production; no repair side effects."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.parametrize(
    "result,status",
    [
        ({"return_code": 21}, 422),
        ({"error": "PermissionError: [Errno 13] Permission denied: '/repo'"}, 422),
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
    "reason,status", [("Permission denied", 422), ("unknown failure", 500)]
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
        "fusermount3: mount failed: Permission denied\nRuntime error: FUSE mount failed",
        "fusermount: mount failed: Operation not permitted",
        "fusermount3: mount failed: Operation not permitted",
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
    [("Permission denied", 422), ("FileExistsError: [Errno 17] File exists", 409)],
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
    "reason,status", [("Permission denied", 422), ("unknown probe failure", 500)]
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


@pytest.mark.parametrize("route", ["import", "update"])
@pytest.mark.parametrize("return_code,status", [(21, 422), (19, 409), (2, 500)])
def test_borg1_exit_code_reaches_real_verification_consumer(
    test_client, test_db, admin_headers, tmp_path, route, return_code, status
):
    from app.database.models import Repository

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "config").write_text("[repository]\n")
    repo = Repository(
        name="numeric-probe",
        path="/tmp/original-numeric",
        encryption="none",
        compression="lz4",
        repository_type="local",
    )
    if route == "update":
        test_db.add(repo)
        test_db.commit()
    with (
        patch(
            "app.services.repository_service.borg._execute_command",
            new=AsyncMock(
                return_value={
                    "success": False,
                    "return_code": return_code,
                    "stderr": "Fehler ohne englische Kennung",
                }
            ),
        ) as execute,
        patch(
            "app.api.repositories.BorgRouter.initialize_repository", new=AsyncMock()
        ) as initialize,
    ):
        if route == "import":
            response = test_client.post(
                "/api/repositories/import",
                json={
                    "name": "numeric-probe",
                    "path": str(repo_path),
                    "encryption": "none",
                },
                headers=admin_headers,
            )
        else:
            response = test_client.put(
                f"/api/repositories/{repo.id}",
                json={"path": str(repo_path)},
                headers=admin_headers,
            )
    assert response.status_code == status, response.text
    execute.assert_awaited_once()
    assert (
        response.json()["detail"]["params"]["error"] == "Fehler ohne englische Kennung"
    )
    initialize.assert_not_awaited()
    if route == "update":
        test_db.refresh(repo)
        assert repo.path == "/tmp/original-numeric"
    else:
        assert test_db.query(Repository).filter_by(name="numeric-probe").first() is None


@pytest.mark.parametrize("route", ["import", "cached", "direct", "update"])
@pytest.mark.parametrize(
    "marker",
    [
        "passphrase supplied in BORG_PASSPHRASE is incorrect.",
        "is not a valid repository",
    ],
)
def test_middle_of_long_failure_remains_available_for_classification(
    test_client, test_db, admin_headers, tmp_path, route, marker
):
    from app.database.models import Repository, RepositoryStorage, RcloneRemote
    from tests.unit.test_api_rclone import _enable_borg_v2

    reason = "prefix\n" * 600 + marker + "\npassword=private-value\n" + "suffix\n" * 600
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / "config").write_text("[repository]\n")
    payload = {"name": "long-probe", "path": str(repo_path), "encryption": "none"}
    if route == "direct":
        _enable_borg_v2(test_db)
        payload.update(
            path="rclone:remote:long-probe",
            borg_version=2,
            storage_backend="rclone_direct",
        )
    elif route == "cached":
        _enable_borg_v2(test_db)
        remote = RcloneRemote(
            name="long-remote", provider="s3", config_source="managed"
        )
        test_db.add(remote)
        test_db.commit()
        payload.update(
            storage_backend="rclone",
            rclone_remote_id=remote.id,
            rclone_remote_path="long-probe",
            rclone_sync_policy="manual",
        )
    elif route == "update":
        repo = Repository(
            name="long-probe",
            path="/tmp/original-long",
            encryption="none",
            compression="lz4",
            repository_type="local",
        )
        test_db.add(repo)
        test_db.commit()
    with (
        patch(
            "app.api.repositories.verify_existing_repository",
            new=AsyncMock(return_value={"success": False, "stderr": reason}),
        ),
        patch(
            "app.api.repositories.BorgRouter.verify_repository",
            new=AsyncMock(return_value={"success": False, "stderr": reason}),
        ),
        patch(
            "app.api.repositories.rclone_repository_service.cache_root",
            str(tmp_path / "cache"),
        ),
        patch(
            "app.api.repositories.rclone_repository_service.hydrate_repository",
            new=AsyncMock(return_value={"sync_status": "current"}),
        ),
        patch(
            "app.api.repositories.BorgRouter.initialize_repository",
            new=AsyncMock(
                return_value={"success": False, "stderr": "probe initialization denied"}
            ),
        ) as initialize,
    ):
        if route == "update":
            response = test_client.put(
                f"/api/repositories/{repo.id}",
                json={"path": str(repo_path)},
                headers=admin_headers,
            )
        else:
            response = test_client.post(
                "/api/repositories/import", json=payload, headers=admin_headers
            )
    if route == "update" and "valid repository" in marker:
        # Existing path-switch semantics initialize a confirmed empty/non-repository target.
        initialize.assert_awaited_once()
        assert response.status_code == 500
    else:
        assert response.status_code == 400, response.text
        initialize.assert_not_awaited()
        if route != "cached":
            expected = (
                "encryptedPassphraseIncorrect"
                if "passphrase" in marker
                else "borg2RepositoryNotReadable"
                if route == "direct"
                else "notValidBorgRepository"
            )
            assert response.json()["detail"]["key"] == f"backend.errors.repo.{expected}"
    assert "private-value" not in response.text
    if route == "cached":
        assert len(response.json()["detail"]["params"]["error"]) <= 2000
        assert test_db.query(RepositoryStorage).count() == 0
    if route == "update":
        test_db.refresh(repo)
        assert repo.path == "/tmp/original-long"
    else:
        assert test_db.query(Repository).filter_by(name="long-probe").first() is None
