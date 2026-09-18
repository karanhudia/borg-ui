"""prune_compare executor (spec 4.5): the retention comparison, run as a
follow-up of a listing that changed the archive set."""

from app.database.models import Repository
from app.services.operations import executors
from app.services.operations.lanes import write_maintenance_running
from app.services.operations.runner import Outcome
from app.services.prune_compare import current_archive_count, run_comparison


async def run_prune_compare(ctx) -> Outcome:
    db = ctx.db
    repository = db.get(Repository, ctx.repository_id) if ctx.repository_id else None
    if repository is None:
        return Outcome(status="skipped", skip_reason="repository_missing")
    if repository.mode == "observe":
        return Outcome(status="skipped", skip_reason="observe_only")
    if current_archive_count(db, repository) < 2:
        return Outcome(status="skipped", skip_reason="too_few_archives")
    if write_maintenance_running(db, repository.id):
        # A real prune, compact, delete or wipe is about to change the
        # answer; the listing it triggers brings the comparison back.
        return Outcome(status="skipped", skip_reason="maintenance_pending")
    rows = await run_comparison(
        db, repository, run_id=ctx.operation.run_id, depends_on_id=ctx.operation.id
    )
    ctx.log(f"compared {len(rows)} policies")
    return Outcome(result={"candidates": len(rows)})


executors.register("prune_compare", run_prune_compare)
