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
