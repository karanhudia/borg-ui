from pathlib import Path

import pytest
import re


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_shared_backend_boundaries_do_not_hardcode_borg_v1_commands():
    guarded_files = [
        REPO_ROOT / "app/services/backup_service.py",
        REPO_ROOT / "app/services/restore_service.py",
        REPO_ROOT / "app/services/mount_service.py",
        REPO_ROOT / "app/utils/process_utils.py",
        REPO_ROOT / "app/api/restore.py",
        REPO_ROOT / "app/api/browse.py",
    ]

    offenders = []
    for path in guarded_files:
        text = path.read_text()
        if '["borg"' in text or "['borg'" in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == [], f"shared version-aware files must route through BorgRouter: {offenders}"


@pytest.mark.unit
def test_frontend_versioned_archive_and_backup_routes_live_in_borg_api_client():
    borg_client = (REPO_ROOT / "frontend/src/services/borgApi/client.ts").read_text()
    assert "${this.v}/backup/run" in borg_client
    assert "${this.v}/archives/${archiveId}" in borg_client
    assert "/browse/" in borg_client

    forbidden_calls = {
        "frontend/src/pages/Archives.tsx": ["archivesAPI.deleteArchive", "repositoriesAPI.listRepositoryArchives"],
        "frontend/src/pages/Repositories.tsx": ["repositoriesAPI.listRepositoryArchives"],
    }

    offenders = []
    for relative_path, patterns in forbidden_calls.items():
        text = (REPO_ROOT / relative_path).read_text()
        for pattern in patterns:
            if pattern in text:
                offenders.append(f"{relative_path}:{pattern}")

    assert offenders == [], f"versioned archive routing must go through BorgApiClient: {offenders}"


@pytest.mark.unit
def test_direct_borg_v1_command_construction_is_confined_to_known_boundaries():
    allowed_files = {
        "app/api/repositories.py",
        "app/core/borg_router.py",
        "app/services/check_service.py",
        "app/services/compact_service.py",
        "app/services/delete_archive_service.py",
        "app/services/prune_service.py",
    }

    offenders = []
    pattern = re.compile(r"""\[\s*["']borg["']""")
    for path in (REPO_ROOT / "app").rglob("*.py"):
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        if relative_path in {"app/core/borg.py", "app/core/borg2.py"}:
            continue
        if pattern.search(path.read_text()) and relative_path not in allowed_files:
            offenders.append(relative_path)

    assert offenders == [], f"new direct borg command construction needs routing review: {offenders}"
