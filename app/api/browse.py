from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
import structlog
import json

from app.database.models import User, Repository
from app.database.database import get_db
from app.api.auth import get_current_user
from app.core.borg import borg

logger = structlog.get_logger(__name__)

router = APIRouter()

@router.get("/{repository_id}/{archive_name}")
async def browse_archive_contents(
    repository_id: int,
    archive_name: str,
    path: str = Query("", description="Path within archive to browse"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Browse contents of an archive at a specific path (directory-by-directory)"""
    try:
        repository = db.query(Repository).filter(Repository.id == repository_id).first()
        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        result = await borg.list_archive_contents(
            repository.path,
            archive_name,
            path=path,
            remote_path=repository.remote_path,
            passphrase=repository.passphrase
        )

        # Parse borg list output
        items = []
        seen_paths = set()

        if result.get("stdout"):
            lines = result["stdout"].strip().split("\n")
            logger.info("Parsing archive contents for browsing",
                       archive=archive_name,
                       path=path,
                       total_lines=len(lines))

            for line in lines:
                if line:
                    try:
                        item_data = json.loads(line)
                        item_path = item_data.get("path", "")

                        # Skip empty paths
                        if not item_path:
                            continue

                        # Get relative path from current directory
                        if path and item_path.startswith(path + "/"):
                            relative_path = item_path[len(path) + 1:]
                        elif path and item_path == path:
                            continue
                        else:
                            relative_path = item_path

                        # Strip leading slash for proper path handling
                        relative_path = relative_path.lstrip("/")

                        # Skip if empty after stripping
                        if not relative_path:
                            continue

                        # Only show immediate children
                        if "/" in relative_path:
                            # This is a nested item, show only the directory
                            dir_name = relative_path.split("/")[0]
                            if dir_name not in seen_paths:
                                seen_paths.add(dir_name)
                                items.append({
                                    "name": dir_name,
                                    "type": "directory",
                                    "path": f"{path}/{dir_name}" if path else dir_name
                                })
                        else:
                            # This is an immediate child
                            if relative_path not in seen_paths:
                                seen_paths.add(relative_path)
                                item_type = item_data.get("type", "")
                                items.append({
                                    "name": relative_path,
                                    "type": "directory" if item_type == "d" else "file",
                                    "size": item_data.get("size"),
                                    "path": f"{path}/{relative_path}" if path else relative_path
                                })
                    except json.JSONDecodeError:
                        continue

        # Sort: directories first, then by name
        items.sort(key=lambda x: (x["type"] != "directory", x["name"].lower()))

        logger.info("Archive contents parsed for browsing",
                   archive=archive_name,
                   path=path,
                   items_count=len(items),
                   first_few_items=[item["name"] for item in items[:10]])

        return {"items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to browse archive contents", repository_id=repository_id,
                    archive_name=archive_name, path=path, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to browse archive: {str(e)}"
        )
