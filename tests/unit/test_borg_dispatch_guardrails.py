from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("relative_path", "forbidden_snippets"),
    [
        ("app/services/backup_service.py", ['["borg"', "'borg'"]),
        ("app/api/restore.py", ['["borg"', "'borg'"]),
        ("app/api/browse.py", ['["borg"', "'borg'"]),
        ("app/utils/process_utils.py", ['["borg", "break-lock"']),
        ("frontend/src/pages/Backup.tsx", ["backupAPI.startBackup("]),
    ],
)
def test_shared_paths_do_not_hardcode_version_sensitive_borg_dispatch(relative_path, forbidden_snippets):
    source = (REPO_ROOT / relative_path).read_text()

    for snippet in forbidden_snippets:
        assert snippet not in source, f"{relative_path} still contains forbidden snippet: {snippet}"
