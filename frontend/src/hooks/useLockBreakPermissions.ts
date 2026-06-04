import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { settingsAPI } from '../services/api'
import { usePermissions } from './usePermissions'
import type { Repository } from '../types'
import type { Job } from '../types/jobs'

type RepositoryReference = Pick<Repository, 'id' | 'path'>

export type LockBreakableJob = Pick<Job, 'repository_id' | 'repository' | 'repository_path'>

interface UseLockBreakPermissionsOptions {
  repositories?: RepositoryReference[]
  fallbackRepositoryId?: number | null
}

export function useLockBreakPermissions({
  repositories = [],
  fallbackRepositoryId = null,
}: UseLockBreakPermissionsOptions = {}) {
  const { canDo } = usePermissions()
  const { data: systemSettingsData } = useQuery({
    queryKey: ['systemSettings'],
    queryFn: async () => {
      const response = await settingsAPI.getSystemSettings()
      return response.data
    },
  })
  const lockBreakingEnabled = systemSettingsData?.settings?.lock_breaking_enabled ?? false
  const repositoryIdByPath = React.useMemo(
    () => new Map(repositories.map((repo) => [repo.path, repo.id])),
    [repositories]
  )

  const canBreakLock = React.useCallback(
    (job: LockBreakableJob) => {
      if (!lockBreakingEnabled) return false
      const repoId =
        job.repository_id ??
        fallbackRepositoryId ??
        (job.repository_path ? repositoryIdByPath.get(job.repository_path) : undefined) ??
        (job.repository ? repositoryIdByPath.get(job.repository) : undefined)

      return typeof repoId === 'number' ? canDo(repoId, 'maintenance') : false
    },
    [canDo, fallbackRepositoryId, lockBreakingEnabled, repositoryIdByPath]
  )

  return { canBreakLock, lockBreakingEnabled }
}
