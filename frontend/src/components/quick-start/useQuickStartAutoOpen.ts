import { useEffect } from 'react'
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
  const active = enabled && pathname === '/dashboard' && !isDismissed()

  // Same query keys as the Repositories page and the sidebar, so this reuses their cache.
  const { data: repositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
    enabled: active,
  })
  const { data: plans } = useQuery({
    queryKey: ['backup-plans'],
    queryFn: () => backupPlansAPI.list(),
    enabled: active,
  })

  const repositoryCount = repositories?.data?.repositories?.length
  const planCount = plans?.data?.backup_plans?.length

  useEffect(() => {
    if (!active || repositoryCount !== 0 || planCount !== 0) return
    markDismissed()
    onOpen()
  }, [active, repositoryCount, planCount, onOpen])
}
