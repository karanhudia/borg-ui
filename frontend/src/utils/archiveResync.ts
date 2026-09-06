import type { QueryClient } from '@tanstack/react-query'
import { archivesAPI } from '../services/api'

/** Every query that reads the stored archive list for one repository. */
export function storedArchiveKeys(repositoryId: number) {
  return [
    ['repository-archives-stored', repositoryId],
    ['repository-archives-heatmap', repositoryId],
    ['repository-info', repositoryId],
  ]
}

export function invalidateStoredArchives(queryClient: QueryClient, repositoryId: number) {
  for (const queryKey of storedArchiveKeys(repositoryId)) {
    queryClient.invalidateQueries({ queryKey })
  }
}

/**
 * The Archives page reads the stored archive list, which only changes when
 * `archive_sync` runs, so work that removed archives (delete, prune, wipe)
 * has to ask for a reconcile run. Without it the removed archives stay
 * listed until the next reconcile tick, which can be an hour away.
 *
 * The list itself refreshes when the run finishes: the Archives page listens
 * for that on the operation event stream. A failure here is deliberately
 * quiet, since the destructive action already succeeded and the periodic
 * reconcile still catches up.
 */
export async function resyncStoredArchives(
  queryClient: QueryClient,
  repositoryId: number | null | undefined
) {
  if (repositoryId == null) return
  try {
    await archivesAPI.resync(repositoryId)
  } catch {
    // The reconcile interval is the fallback.
  }
  invalidateStoredArchives(queryClient, repositoryId)
  queryClient.invalidateQueries({ queryKey: ['operations-queue'] })
  queryClient.invalidateQueries({ queryKey: ['operations-repositories'] })
}
