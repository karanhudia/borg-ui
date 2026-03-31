"""BorgRouter — version-aware routing for repository operations.

This is the single place in the backend where borg_version is checked and
operations are dispatched to the correct implementation.

v1 repos  →  app/core/borg.py  + existing v1 services
v2 repos  →  app/core/borg2.py + app/services/v2/

Never add borg_version checks directly inside v1 service code.
Use BorgRouter instead so the routing stays in one place.
"""

import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()


class BorgRouter:
    def __init__(self, repo):
        self.repo = repo
        self.is_v2 = (repo.borg_version or 1) == 2

    async def update_stats(self, db: Session) -> bool:
        """Refresh archive count and size stats for this repository.

        v2: no-op — stats are fetched on-demand via /api/v2/repositories/{id}/stats.
        v1: delegates to the existing update_repository_stats helper.
        """
        if self.is_v2:
            return True
        from app.api.repositories import update_repository_stats
        return await update_repository_stats(self.repo, db)

    async def check(self, job_id: int) -> None:
        """Run a repository integrity check.

        v2: delegates to the Borg 2 check service.
        v1: delegates to the existing check service.
        """
        if self.is_v2:
            from app.services.v2.check_service import check_v2_service
            await check_v2_service.execute_check(job_id, self.repo.id)
        else:
            from app.services.check_service import check_service
            await check_service.execute_check(job_id, self.repo.id)

    async def list_archives(self) -> list:
        """Return the list of archives for this repository.

        Used as a version-aware guard before repository deletion.
        v2: calls borg2 list and parses the JSON archives array.
        v1: calls borg list and returns the archives list.
        """
        if self.is_v2:
            import json
            from app.core.borg2 import borg2
            result = await borg2.list_archives(
                self.repo.path,
                passphrase=self.repo.passphrase,
                remote_path=self.repo.remote_path,
                bypass_lock=self.repo.bypass_lock,
            )
            if not result["success"]:
                return []
            try:
                data = json.loads(result.get("stdout", "{}"))
                return data.get("archives", [])
            except Exception:
                return []
        else:
            from app.core.borg import borg
            result = await borg.list_archives(
                self.repo.path,
                remote_path=self.repo.remote_path,
                passphrase=self.repo.passphrase,
                bypass_lock=self.repo.bypass_lock,
            )
            if not result["success"]:
                return []
            return result.get("stdout") or []
