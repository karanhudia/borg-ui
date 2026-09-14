import type { QueryClient } from '@tanstack/react-query'
import { archivesAPI } from '../services/api'

/** Every query that reads the stored archive list for one repository.
 * The storage figures summed over its rows are not here: the Archives
 * page refetches those once per burst of index work, and a second,
 * immediate refetch from this list would double every one. */
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
  // the run just asked for is pending index work: the card and the header
  // say "indexing" for what it has not produced yet (#1063)
  queryClient.invalidateQueries({ queryKey: ['repository-storage', repositoryId] })
  queryClient.invalidateQueries({ queryKey: ['repositories'] })
  queryClient.invalidateQueries({ queryKey: ['operations-queue'] })
  queryClient.invalidateQueries({ queryKey: ['operations-repositories'] })
}
