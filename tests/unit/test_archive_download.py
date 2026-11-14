import os
from pathlib import Path

import pytest
from fastapi import HTTPException, status

from app.api.archive_download import extract_file_download


@pytest.mark.asyncio
async def test_extract_file_download_rejects_paths_outside_temp_dir(tmp_path):
    temp_dir = tmp_path / "extract"
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("do not download", encoding="utf-8")

    async def extract(target_dir: str) -> dict[str, object]:
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        return {"success": True, "stderr": ""}

    with pytest.raises(HTTPException) as exc_info:
        await extract_file_download(
            "../secret.txt",
            extract,
            temp_dir_factory=lambda: str(temp_dir),
            path_exists=os.path.exists,
            file_response_factory=lambda **kwargs: kwargs,
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == {
        "key": "backend.errors.archives.fileNotFoundAfterExtraction"
    }
    assert not temp_dir.exists()


@pytest.mark.asyncio
async def test_extract_file_download_of_a_missing_archive_is_not_found(tmp_path):
    # The archive was pruned while the page was open (dashboard 59a11c4953c3d968).
    async def extract(target_dir: str) -> dict[str, object]:
        return {
            "success": False,
            "return_code": 2,
            "stderr": "Archive manual-backup-2026-02-17T11:41:49 does not exist\n",
        }

    with pytest.raises(HTTPException) as exc_info:
        await extract_file_download(
            "etc/hosts",
            extract,
            temp_dir_factory=lambda: str(tmp_path / "extract"),
        )

    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
