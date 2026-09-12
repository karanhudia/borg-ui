import type { TFunction } from 'i18next'
import { isToday, isYesterday } from 'date-fns'
import type { ActivityItem } from '../Activity'
import type { RunChainOperation } from '../../components/activity/RunChainRow'
import { getTypeLabel, statusLabel } from '../../components/jobs/jobLabels'
import { formatDurationSeconds, parseBackendDate } from '../../utils/dateUtils'

export const activityKey = (item: ActivityItem) => item.activity_key ?? `${item.type}-${item.id}`

export const ACTIVE_STATUSES = new Set(['running', 'pending', 'queued'])

// A hook around one backup names that backup and rides under it. A hook
// around the whole plan names only the run, and hangs from its band.
export const isPlanHook = (item: ActivityItem): boolean =>
  item.type === 'script_execution' && item.operation_id == null && item.backup_plan_run_id != null

// The status dot already carries these: green and done, blue and moving,
// hollow and waiting. A run spells its status out only when the word says
// something the colour cannot, which is every way a run can end badly.
export const QUIET_STATUSES = new Set(['completed', 'running', 'pending', 'queued'])

// "Completed with Warnings" is a badge's worth of words; beside a duration it
// only needs to say which way the run went.
export function outcomeLabel(status: string, t: TFunction): string {
  return status === 'completed_with_warnings' ? t('status.warnings') : statusLabel(status, t)
}

// A collapsed run and every step under it, so a summary sees the follow-up
// chain and the hooks, not just the row that started them.
export const flattenRuns = (items: ActivityItem[]): ActivityItem[] =>
  items.flatMap((item) => [item, ...(item.followups ?? [])])

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
// One row of a chain as the chain widgets read it. A hook keeps the name of
// the script that ran, which is the only thing telling two hooks apart.
export function chainStep(step: ActivityItem): RunChainOperation {
  return {
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
    progress_message: step.progress_message,
  }
}

/** Convert an activity item and its follow-ups into the chain renderer shape. */
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
    followups: steps.map(chainStep),
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
// A script and a plan run carry a name in the repository slot (the script's
// own, the plan's) but ran against no repository of their own, so they must
// not be counted as one.
const NOT_A_REPOSITORY = new Set(['script_execution', 'backup_plan_run'])

/** Count distinct repositories while excluding plan and script summary rows. */
export function repositoryCount(items: ActivityItem[]): number {
  const keys = new Set<string>()
  for (const item of items) {
    if (NOT_A_REPOSITORY.has(item.type)) continue
    const key = item.repository_id ?? item.repository_path ?? item.repository
    if (key != null) keys.add(String(key))
  }
  return keys.size
}

export interface Cluster {
  key: string
  umbrella: Umbrella
  items: ActivityItem[]
  // The schedule a firing belongs to, compared whole: a prefix match would
  // fold "weekly" into "weekly-prod".
  schedule?: string
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
    let scheduleKey: string | null = null
    if (kind.kind === 'plan' && item.backup_plan_run_id != null) {
      key = `plan-run-${item.backup_plan_run_id}`
    } else if (kind.kind === 'schedule') {
      // Namespaced: a schedule id of 7 and a legacy schedule named "7" are
      // not the same firing.
      scheduleKey =
        item.schedule_id != null
          ? `id:${item.schedule_id}`
          : item.schedule_name != null
            ? `name:${item.schedule_name}`
            : // A repository's own check and restore-check schedules are
              // columns on the repository, not schedule rows, so they arrive
              // without an id. They are still one schedule each -- the
              // Schedule page lists them one card per repository, with their
              // own cron and timezone -- so they are keyed by the repository
              // they belong to. Keying them by operation alone merged two
              // repositories' schedules whenever they happened to fire
              // together, which reads as one schedule fanning out.
              `repository:${item.repository_id ?? item.repository ?? 'none'}:${item.kind ?? item.type}`
      const time = runTime(item)?.getTime() ?? 0
      const open = [...byKey.values()].find(
        (cluster) =>
          cluster.schedule === scheduleKey &&
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
      if (scheduleKey !== null) cluster.schedule = scheduleKey
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
