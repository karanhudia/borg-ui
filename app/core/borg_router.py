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
