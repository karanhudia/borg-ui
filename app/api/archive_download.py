import os
import shutil
import tempfile
from typing import Awaitable, Callable

from fastapi import HTTPException, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask


async def extract_file_download(
    file_path: str,
    extract: Callable[[str], Awaitable[dict]],
    temp_dir_factory: Callable[[], str] = tempfile.mkdtemp,
    path_exists: Callable[[str], bool] = os.path.exists,
    file_response_factory: Callable[..., FileResponse] = FileResponse,
) -> FileResponse:
    """Extract a file into a temp dir and return it as a download response."""
    temp_dir = temp_dir_factory()
    try:
        result = await extract(temp_dir)
        if not result.get("success"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "key": "backend.errors.archives.failedExtractFile",
                    "params": {"error": result.get("stderr", "Unknown error")},
                },
            )

        extracted_file_path = os.path.join(temp_dir, file_path.lstrip("/"))
        if not path_exists(extracted_file_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"key": "backend.errors.archives.fileNotFoundAfterExtraction"},
            )

        return file_response_factory(
            path=extracted_file_path,
            filename=os.path.basename(file_path),
            media_type="application/octet-stream",
            background=BackgroundTask(shutil.rmtree, temp_dir, ignore_errors=True),
        )
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
