import type { TFunction } from 'i18next'
import type { ProcessedRepositories, Repository } from './types'

export function getCreatedRepositoryId(response: unknown): number | null {
  const data = (response as { data?: { id?: number; repository?: { id?: number } } })?.data
  return data?.repository?.id ?? data?.id ?? null
}

export function getCompressionLabel(compression: string) {
  return compression || 'lz4'
}

export function getRepositoryResultCount(processedRepositories: ProcessedRepositories) {
  return processedRepositories.groups.reduce((total, group) => total + group.repositories.length, 0)
}

export function processRepositories({
  repositories,
  searchQuery,
  sortBy,
  groupBy,
  backupPlanRepositoryIds,
  t,
}: {
  repositories: Repository[]
  searchQuery: string
  sortBy: string
  groupBy: string
  backupPlanRepositoryIds?: Set<number>
  t: TFunction
}): ProcessedRepositories {
  let filtered = repositories

  if (backupPlanRepositoryIds) {
    filtered = filtered.filter((repo) => backupPlanRepositoryIds.has(repo.id))
  }

  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase()
    filtered = filtered.filter((repo) => {
      return (
        repo.name?.toLowerCase().includes(query) ||
        repo.path?.toLowerCase().includes(query) ||
        repo.repository_type?.toLowerCase().includes(query)
      )
    })
  }

  const sorted = [...filtered].sort((a, b) => {
    switch (sortBy) {
      case 'name-asc':
        return (a.name || '').localeCompare(b.name || '')
      case 'name-desc':
        return (b.name || '').localeCompare(a.name || '')
      case 'last-backup-recent':
        if (!a.last_backup && !b.last_backup) return 0
        if (!a.last_backup) return 1
        if (!b.last_backup) return -1
        return new Date(b.last_backup).getTime() - new Date(a.last_backup).getTime()
      case 'last-backup-oldest':
        if (!a.last_backup && !b.last_backup) return 0
        if (!a.last_backup) return 1
        if (!b.last_backup) return -1
        return new Date(a.last_backup).getTime() - new Date(b.last_backup).getTime()
      case 'created-newest':
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      case 'created-oldest':
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      default:
        return 0
    }
  })

  if (groupBy === 'none') {
    return { groups: [{ name: null, repositories: sorted }] }
  }

  const groups: { name: string; repositories: Repository[] }[] = []

  if (groupBy === 'location') {
    const locationMap = new Map<string, Repository[]>()

    sorted.forEach((repo) => {
      let locationKey = t('repositories.groups.localMachine')

      if (repo.path?.startsWith('ssh://')) {
        const match = repo.path.match(/ssh:\/\/[^@]+@([^:/]+)/)
        locationKey = match ? match[1] : t('repositories.groups.remoteSsh')
      }

      if (!locationMap.has(locationKey)) {
        locationMap.set(locationKey, [])
      }
      locationMap.get(locationKey)!.push(repo)
    })

    const localMachineKey = t('repositories.groups.localMachine')
    const sortedKeys = Array.from(locationMap.keys()).sort((a, b) => {
      if (a === localMachineKey) return -1
      if (b === localMachineKey) return 1
      return a.localeCompare(b)
    })

    sortedKeys.forEach((key) => {
      groups.push({ name: key, repositories: locationMap.get(key)! })
    })
  } else if (groupBy === 'type') {
    const local = sorted.filter((repo) => !repo.path?.startsWith('ssh://'))
    const ssh = sorted.filter((repo) => repo.path?.startsWith('ssh://'))

    if (local.length > 0) groups.push({ name: t('repositories.groups.local'), repositories: local })
    if (ssh.length > 0) groups.push({ name: t('repositories.groups.remote'), repositories: ssh })
  } else if (groupBy === 'mode') {
    const full = sorted.filter((repo) => repo.mode === 'full' || !repo.mode)
    const observe = sorted.filter((repo) => repo.mode === 'observe')

    if (full.length > 0) groups.push({ name: t('repositories.groups.full'), repositories: full })
    if (observe.length > 0)
      groups.push({ name: t('repositories.groups.observeOnly'), repositories: observe })
  }

  return { groups: groups.length > 0 ? groups : [{ name: null, repositories: sorted }] }
}
