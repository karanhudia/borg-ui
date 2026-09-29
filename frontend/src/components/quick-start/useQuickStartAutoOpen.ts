import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'

import { backupPlansAPI, repositoriesAPI } from '../../services/api'

export const QUICK_START_DISMISSED_KEY = 'borg-ui.quickStart.autoOpenDismissed'

function isDismissed(): boolean {
  try {
    return localStorage.getItem(QUICK_START_DISMISSED_KEY) === '1'
  } catch {
    return true
  }
}

function markDismissed() {
  try {
    localStorage.setItem(QUICK_START_DISMISSED_KEY, '1')
  } catch {
    // Storage blocked: the sidebar button is still there.
  }
}

/**
 * Opens Quick Start once per browser on the dashboard of an empty install
 * (no repositories and no backup plans).
 */
export function useQuickStartAutoOpen({
  enabled,
  onOpen,
}: {
  enabled: boolean
  onOpen: () => void
}) {
  const { pathname } = useLocation()
  // Also kept in state: when storage writes fail, closing must still not reopen it.
  const [dismissed, setDismissed] = useState(isDismissed)
  const active = enabled && pathname === '/dashboard' && !dismissed

  // Same query keys as the Repositories page and the sidebar. A cached empty
  // list may be stale (default staleTime) or kept after a failed refetch, so the
  // decision needs a fetch that succeeded after this hook mounted.
  const freshOnly = { enabled: active, staleTime: 0, refetchOnMount: 'always' as const }
  const repositories = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
    ...freshOnly,
  })
  const plans = useQuery({
    queryKey: ['backup-plans'],
    queryFn: () => backupPlansAPI.list(),
    ...freshOnly,
  })

  const fresh = (query: typeof repositories | typeof plans) =>
    query.isFetchedAfterMount && !query.isFetching && query.isSuccess
  const settled = fresh(repositories) && fresh(plans)
  const repositoryCount = repositories.data?.data?.repositories?.length
  const planCount = plans.data?.data?.backup_plans?.length

  useEffect(() => {
    if (!active || !settled || repositoryCount !== 0 || planCount !== 0) return
    markDismissed()
    setDismissed(true)
    onOpen()
  }, [active, settled, repositoryCount, planCount, onOpen])
}
