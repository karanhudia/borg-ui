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

  // Same query keys as the Repositories page and the sidebar, so this reuses their cache.
  const { data: repositories, isFetching: fetchingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
    enabled: active,
  })
  const { data: plans, isFetching: fetchingPlans } = useQuery({
    queryKey: ['backup-plans'],
    queryFn: () => backupPlansAPI.list(),
    enabled: active,
  })

  const repositoryCount = repositories?.data?.repositories?.length
  const planCount = plans?.data?.backup_plans?.length
  // Cached empty lists can be stale while a refetch runs; decide on fresh answers only.
  const settled = !fetchingRepositories && !fetchingPlans

  useEffect(() => {
    if (!active || !settled || repositoryCount !== 0 || planCount !== 0) return
    markDismissed()
    setDismissed(true)
    onOpen()
  }, [active, settled, repositoryCount, planCount, onOpen])
}
