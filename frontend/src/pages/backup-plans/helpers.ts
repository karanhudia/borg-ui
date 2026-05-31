import type { TFunction } from 'i18next'

import type { BackupPlan } from '../../types'

export interface ProcessedBackupPlans {
  groups: Array<{ name: string | null; plans: BackupPlan[] }>
}

export function parseRepositoryFilterId(value: string | null): number | null {
  if (!value) return null
  const id = Number(value)
  return Number.isInteger(id) && id > 0 ? id : null
}

export function backupPlanUsesRepository(plan: BackupPlan, repositoryId: number): boolean {
  return Boolean(
    plan.repositories?.some((link) => link.enabled && link.repository_id === repositoryId)
  )
}

export function processBackupPlans({
  backupPlans,
  repositoryFilterId,
  searchQuery,
  sortBy,
  groupBy,
  t,
}: {
  backupPlans: BackupPlan[]
  repositoryFilterId: number | null
  searchQuery: string
  sortBy: string
  groupBy: string
  t: TFunction
}): ProcessedBackupPlans {
  let filtered = backupPlans

  if (repositoryFilterId !== null) {
    filtered = filtered.filter((plan) => backupPlanUsesRepository(plan, repositoryFilterId))
  }

  if (searchQuery.trim()) {
    const query = searchQuery.toLowerCase()
    filtered = filtered.filter(
      (plan) =>
        plan.name.toLowerCase().includes(query) ||
        (plan.description?.toLowerCase().includes(query) ?? false)
    )
  }

  const compareDateDesc = (a?: string | null, b?: string | null) => {
    if (!a && !b) return 0
    if (!a) return 1
    if (!b) return -1
    return new Date(b).getTime() - new Date(a).getTime()
  }
  const compareDateAsc = (a?: string | null, b?: string | null) => -compareDateDesc(a, b)

  const sorted = [...filtered].sort((a, b) => {
    switch (sortBy) {
      case 'name-asc':
        return a.name.localeCompare(b.name)
      case 'name-desc':
        return b.name.localeCompare(a.name)
      case 'last-run-recent':
        return compareDateDesc(a.last_run, b.last_run)
      case 'last-run-oldest':
        return compareDateAsc(a.last_run, b.last_run)
      case 'next-run-soonest':
        return compareDateAsc(a.next_run, b.next_run)
      case 'created-newest':
        return compareDateDesc(a.created_at, b.created_at)
      case 'created-oldest':
        return compareDateAsc(a.created_at, b.created_at)
      default:
        return 0
    }
  })

  if (groupBy === 'none') {
    return { groups: [{ name: null, plans: sorted }] }
  }

  const groups: { name: string; plans: BackupPlan[] }[] = []

  if (groupBy === 'status') {
    const enabled = sorted.filter((p) => p.enabled)
    const disabled = sorted.filter((p) => !p.enabled)
    if (enabled.length > 0) groups.push({ name: t('backupPlans.groups.enabled'), plans: enabled })
    if (disabled.length > 0)
      groups.push({ name: t('backupPlans.groups.disabled'), plans: disabled })
  } else if (groupBy === 'schedule') {
    const scheduled = sorted.filter((p) => p.schedule_enabled)
    const manual = sorted.filter((p) => !p.schedule_enabled)
    if (scheduled.length > 0)
      groups.push({ name: t('backupPlans.groups.scheduled'), plans: scheduled })
    if (manual.length > 0) groups.push({ name: t('backupPlans.groups.manual'), plans: manual })
  } else if (groupBy === 'source') {
    const local = sorted.filter((p) => p.source_type === 'local')
    const remote = sorted.filter((p) => p.source_type === 'remote')
    const agent = sorted.filter((p) => p.source_type === 'agent')
    if (local.length > 0) groups.push({ name: t('backupPlans.groups.localSource'), plans: local })
    if (remote.length > 0)
      groups.push({ name: t('backupPlans.groups.remoteSource'), plans: remote })
    if (agent.length > 0)
      groups.push({ name: t('backupPlans.sourceChooser.managedAgent'), plans: agent })
  }

  return { groups: groups.length > 0 ? groups : [{ name: null, plans: sorted }] }
}
