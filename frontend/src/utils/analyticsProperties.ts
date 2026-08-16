export type JobStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'cancelled'
  | string

export const TERMINAL_JOB_STATUSES = new Set<JobStatus>([
  'completed',
  'completed_with_warnings',
  'failed',
  'cancelled',
])

export function isTerminalJobStatus(status: JobStatus | null | undefined): boolean {
  return !!status && TERMINAL_JOB_STATUSES.has(status)
}

export function getJobDurationSeconds(
  startedAt?: string | null,
  completedAt?: string | null
): number | undefined {
  if (!startedAt || !completedAt) return undefined

  const started = new Date(startedAt).getTime()
  const completed = new Date(completedAt).getTime()
  if (!Number.isFinite(started) || !Number.isFinite(completed) || completed < started) {
    return undefined
  }

  return Math.round((completed - started) / 1000)
}

export function getArchiveAgeBucket(
  archiveStart?: string | null,
  now: Date = new Date()
): string | undefined {
  if (!archiveStart) return undefined

  const started = new Date(archiveStart).getTime()
  const current = now.getTime()
  if (!Number.isFinite(started) || !Number.isFinite(current) || current < started) {
    return undefined
  }

  const ageDays = (current - started) / (1000 * 60 * 60 * 24)
  if (ageDays < 1) return 'lt_1d'
  if (ageDays < 7) return '1d_7d'
  if (ageDays < 30) return '7d_30d'
  if (ageDays < 90) return '30d_90d'
  return 'gte_90d'
}
