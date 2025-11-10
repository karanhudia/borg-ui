from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import structlog
import json
import os
import tempfile
from typing import List, Dict, Any

from app.database.database import get_db
from app.database.models import User, Repository
from app.core.security import get_current_user
from app.core.borg import borg
from app.api.repositories import update_repository_archive_count

logger = structlog.get_logger()
router = APIRouter()

@router.get("/list")
async def list_archives(
    repository: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List archives in a repository"""
    try:
        # Validate repository exists
        repo = db.query(Repository).filter(Repository.path == repository).first()
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )

        result = await borg.list_archives(repository)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to list archives: {result['stderr']}"
            )

        return {"archives": result["stdout"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to list archives", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list archives"
        )

@router.get("/{archive_id}/info")
async def get_archive_info(
    repository: str,
    archive_id: str,
    include_files: bool = False,
    file_limit: int = 1000,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific archive including command line, metadata, and optionally file listing"""
    try:
        # Validate repository exists
        repo = db.query(Repository).filter(Repository.path == repository).first()
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )

        result = await borg.info_archive(repository, archive_id)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive info: {result['stderr']}"
            )

        # Parse JSON output from Borg
        try:
            archive_data = json.loads(result["stdout"])

            # Extract archive information
            if "archives" in archive_data and len(archive_data["archives"]) > 0:
                archive_info = archive_data["archives"][0]
            else:
                archive_info = {}

            # Build enhanced response with all metadata
            enhanced_info = {
                "name": archive_info.get("name"),
                "id": archive_info.get("id"),
                "start": archive_info.get("start"),
                "end": archive_info.get("end"),
                "duration": archive_info.get("duration"),
                "stats": archive_info.get("stats", {}),

                # Creation metadata
                "command_line": archive_info.get("command_line", []),
                "hostname": archive_info.get("hostname"),
                "username": archive_info.get("username"),

                # Technical details
                "chunker_params": archive_info.get("chunker_params"),
                "limits": archive_info.get("limits", {}),
                "comment": archive_info.get("comment", ""),

                # Repository info
                "repository": archive_data.get("repository", {}),
                "encryption": archive_data.get("encryption", {}),
                "cache": archive_data.get("cache", {}),
            }

            # Optionally fetch file listing
            if include_files:
                list_result = await borg.list_archive_contents(repository, archive_id)
                if list_result["success"]:
                    try:
                        # Parse JSON-lines output
                        files = []
                        for line in list_result["stdout"].strip().split('\n'):
                            if line and len(files) < file_limit:
                                try:
                                    file_obj = json.loads(line)
                                    files.append({
                                        "path": file_obj.get("path"),
                                        "type": file_obj.get("type"),
                                        "mode": file_obj.get("mode"),
                                        "user": file_obj.get("user"),
                                        "group": file_obj.get("group"),
                                        "size": file_obj.get("size"),
                                        "mtime": file_obj.get("mtime"),
                                        "healthy": file_obj.get("healthy", True)
                                    })
                                except json.JSONDecodeError:
                                    continue
                        enhanced_info["files"] = files
                        enhanced_info["file_count"] = len(files)
                    except Exception as e:
                        logger.warning("Failed to parse file listing", error=str(e))
                        enhanced_info["files"] = []
                        enhanced_info["file_count"] = 0
                else:
                    enhanced_info["files"] = []
                    enhanced_info["file_count"] = 0

            return {"info": enhanced_info}

        except json.JSONDecodeError:
            # Fallback to raw output if not JSON
            logger.warning("Archive info is not JSON, returning raw output")
            return {"info": result["stdout"]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get archive info", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get archive info"
        )

@router.get("/{archive_id}/contents")
async def get_archive_contents(
    repository: str,
    archive_id: str,
    path: str = "",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get contents of an archive"""
    try:
        # Validate repository exists
        repo = db.query(Repository).filter(Repository.path == repository).first()
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )

        result = await borg.list_archive_contents(repository, archive_id, path)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to get archive contents: {result['stderr']}"
            )

        return {"contents": result["stdout"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get archive contents", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get archive contents"
        )

@router.delete("/{archive_id}")
async def delete_archive(
    repository: str,
    archive_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an archive"""
    try:
        # Validate repository exists first
        repo = db.query(Repository).filter(Repository.path == repository).first()
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )

        result = await borg.delete_archive(repository, archive_id)
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to delete archive: {result['stderr']}"
            )

        # Update archive count after successful deletion
        await update_repository_archive_count(repo, db)

        return {"message": "Archive deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete archive", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete archive"
        )

@router.get("/download")
async def download_file_from_archive(
    repository: str,
    archive: str,
    file_path: str,
    token: str,
    db: Session = Depends(get_db)
):
    """Extract and download a specific file from an archive"""
    # Authenticate using token from query parameter
    from app.core.security import verify_token
    username = verify_token(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Get user from database
    current_user = db.query(User).filter(User.username == username).first()
    if not current_user or not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )

    try:
        # Get repository details for passphrase and remote_path
        repo = db.query(Repository).filter(Repository.path == repository).first()
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found"
            )

        # Create a temporary directory for extraction
        temp_dir = tempfile.mkdtemp()

        try:
            # Extract the specific file using borg extract
            result = await borg.extract_archive(
                repository,
                archive,
                [file_path],
                temp_dir,
                dry_run=False,
                remote_path=repo.remote_path,
                passphrase=repo.passphrase
            )

            if not result.get("success"):
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to extract file: {result.get('stderr', 'Unknown error')}"
                )

            # Find the extracted file
            extracted_file_path = os.path.join(temp_dir, file_path.lstrip('/'))

            if not os.path.exists(extracted_file_path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="File not found after extraction"
                )

            # Get the filename for the download
            filename = os.path.basename(file_path)

            # Return the file as a download
            return FileResponse(
                path=extracted_file_path,
                filename=filename,
                media_type='application/octet-stream',
                background=None  # Don't delete temp file yet, will be handled by OS
            )

        except Exception as inner_e:
            # Clean up temp directory on error
            try:
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
            raise inner_e

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to download file from archive",
                    repository=repository,
                    archive=archive_id,
                    file_path=file_path,
                    error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download file: {str(e)}"
        ) 