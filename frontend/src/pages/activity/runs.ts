import type { TFunction } from 'i18next'
import { isToday, isYesterday } from 'date-fns'
import type { ActivityItem } from '../Activity'
import type { RunChainOperation } from '../../components/activity/RunChainRow'
import { getTypeLabel } from '../../components/jobs/jobLabels'
import { formatDurationSeconds, parseBackendDate } from '../../utils/dateUtils'

export const activityKey = (item: ActivityItem) => item.activity_key ?? `${item.type}-${item.id}`

export const ACTIVE_STATUSES = new Set(['running', 'pending', 'queued'])

export type UmbrellaKind =
  'plan' | 'schedule' | 'manual' | 'import' | 'followup' | 'reconcile' | 'retry' | 'other'

export interface Umbrella {
  kind: UmbrellaKind
  label: string
}

// What a run belongs to. A plan run names its plan and a scheduled run its
// schedule, so a row says "Plan · Nightly" rather than "plan trigger". Rows
// written before operations carried a trigger only have `triggered_by`.
export function umbrella(item: ActivityItem, t: TFunction): Umbrella {
  const trigger =
    item.trigger ??
    (item.triggered_by === 'backup_plan' || item.backup_plan_id
      ? 'plan'
      : item.triggered_by === 'schedule'
        ? 'schedule'
        : item.triggered_by === 'manual' || !item.triggered_by
          ? 'manual'
          : null)
  if (trigger === 'plan')
    return {
      kind: 'plan',
      label: item.backup_plan_name
        ? t('activity.umbrella.plan', { name: item.backup_plan_name })
        : t('activity.triggers.plan'),
    }
  if (trigger === 'schedule')
    return {
      kind: 'schedule',
      label: item.schedule_name
        ? t('activity.umbrella.schedule', { name: item.schedule_name })
        : t('activity.triggers.schedule'),
    }
  if (trigger === null) return { kind: 'other', label: capitalize(String(item.triggered_by)) }
  return { kind: trigger, label: t(`activity.triggers.${trigger}`) }
}

function capitalize(value: string): string {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : value
}

// A reconcile or rebuild is one row with its steps under it. Naming the
// row after its first step ("Sync archive list") undersold it, so index
// runs take their name from what started them (phase 9).
export function isIndexRun(item: ActivityItem): boolean {
  return item.category === 'index' && (item.followups?.length ?? 0) > 0
}

export function runTitle(item: ActivityItem, t: TFunction): string {
  const kind = item.kind ?? item.type
  if (isIndexRun(item)) {
    const trigger = item.trigger ?? (item.triggered_by === 'schedule' ? 'schedule' : 'manual')
    return t(`activity.runTitle.${trigger}`, {
      defaultValue: t(`operations.kind.${kind}`, { defaultValue: kind }),
    })
  }
  const legacy = getTypeLabel(item.type, t)
  if (legacy !== item.type) return legacy
  return capitalize(t(`operations.kind.${kind}`, { defaultValue: kind }))
}

// The chain a run draws beneath itself. An index run lists itself first
// so the row reads as "Reconcile run" over all its steps.
export function runChain(item: ActivityItem): RunChainOperation {
  const followups = item.followups ?? []
  const steps = isIndexRun(item) ? [item, ...followups] : followups
  return {
    id: item.id,
    kind: item.kind ?? item.type,
    type: item.type,
    status: item.status,
    started_at: item.started_at,
    completed_at: item.completed_at,
    followups: steps.map((step) => ({
      id: step.id,
      kind: step.kind ?? step.type,
      type: step.type,
      hook_type: step.hook_type,
      name: step.package_name,
      status: step.status,
      trigger: step.trigger,
      depends_on_id: step.depends_on_id,
      started_at: step.started_at,
      completed_at: step.completed_at,
      progress_current: step.progress_current,
      progress_total: step.progress_total,
    })),
  }
}

export function runTime(item: ActivityItem): Date | null {
  const raw = item.started_at ?? item.completed_at
  return raw ? parseBackendDate(raw) : null
}

export function dayKey(date: Date | null): string {
  if (!date) return 'unknown'
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
}

export interface DayGroup {
  key: string
  date: Date | null
  items: ActivityItem[]
}

export function groupByDay(items: ActivityItem[]): DayGroup[] {
  const byDay = new Map<string, DayGroup>()
  for (const item of items) {
    const date = runTime(item)
    const key = dayKey(date)
    const group = byDay.get(key) ?? { key, date, items: [] }
    group.items.push(item)
    byDay.set(key, group)
  }
  return [...byDay.values()].sort((a, b) => (b.date?.getTime() ?? 0) - (a.date?.getTime() ?? 0))
}

export function dayLabel(date: Date | null, t: TFunction): string {
  if (!date) return t('activity.day.unknown')
  if (isToday(date)) return t('activity.day.today')
  if (isYesterday(date)) return t('activity.day.yesterday')
  return date.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })
}

export function runDuration(item: ActivityItem): string | null {
  if (!item.started_at || !item.completed_at) return null
  const seconds = Math.round(
    (parseBackendDate(item.completed_at).getTime() - parseBackendDate(item.started_at).getTime()) /
      1000
  )
  return formatDurationSeconds(Math.max(seconds, 0))
}

// Distinct repositories among the listed runs, for the summary line.
export function repositoryCount(items: ActivityItem[]): number {
  const keys = new Set<string>()
  for (const item of items) {
    const key = item.repository_id ?? item.repository_path ?? item.repository
    if (key != null) keys.add(String(key))
  }
  return keys.size
}

export interface Cluster {
  key: string
  umbrella: Umbrella
  items: ActivityItem[]
}

// Scheduled work fired together carries no shared run id, so runs of one
// schedule that start within this window of each other count as one firing.
const SCHEDULE_WINDOW_MS = 10 * 60 * 1000

// Every run sits under the umbrella that started it. A plan run groups by
// its run id; a schedule firing groups its runs by schedule and time; a
// manual click, an import, a reconcile stand alone. Members of a group
// read in the order they happened.
export function clusterRuns(items: ActivityItem[], t: TFunction): Cluster[] {
  const clusters: Cluster[] = []
  const byKey = new Map<string, Cluster>()
  for (const item of items) {
    const kind = umbrella(item, t)
    let key: string | null = null
    if (kind.kind === 'plan' && item.backup_plan_run_id != null) {
      key = `plan-run-${item.backup_plan_run_id}`
    } else if (kind.kind === 'schedule') {
      const scheduleKey = item.schedule_id ?? item.kind ?? item.type
      const time = runTime(item)?.getTime() ?? 0
      const open = [...byKey.values()].find(
        (cluster) =>
          cluster.key.startsWith(`schedule-${scheduleKey}-`) &&
          Math.abs((runTime(cluster.items[0])?.getTime() ?? 0) - time) <= SCHEDULE_WINDOW_MS
      )
      key = open?.key ?? `schedule-${scheduleKey}-${time}`
    }
    if (key === null) {
      clusters.push({ key: `run-${item.type}-${item.id}`, umbrella: kind, items: [item] })
      continue
    }
    let cluster = byKey.get(key)
    if (!cluster) {
      const label =
        kind.kind === 'schedule' && !item.schedule_name
          ? t('activity.umbrella.schedule', { name: runTitle(item, t) })
          : kind.label
      cluster = { key, umbrella: { ...kind, label }, items: [] }
      byKey.set(key, cluster)
      clusters.push(cluster)
    }
    cluster.items.push(item)
  }
  for (const cluster of clusters) {
    if (cluster.items.length > 1) {
      cluster.items.sort((a, b) => (runTime(a)?.getTime() ?? 0) - (runTime(b)?.getTime() ?? 0))
    }
  }
  return clusters
}
