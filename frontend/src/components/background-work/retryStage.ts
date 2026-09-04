import type { OperationItem, RebuildStage } from '../../types/operations'

// A retry re-runs the derivation from the stage that failed, which is what
// POST /repositories/{id}/rebuild does. `import_connect` has no rebuild stage
// (it is the synchronous import request, spec 10.1), so its cards get no
// retry control.
const RETRY_STAGE: Partial<Record<OperationItem['kind'], RebuildStage>> = {
  stats: 'stats',
  archive_sync: 'archives',
  history_index: 'history',
  history_merge: 'history',
}

export function retryStageFor(operation: OperationItem): RebuildStage | null {
  if (operation.repository_id == null) return null
  return RETRY_STAGE[operation.kind] ?? null
}
